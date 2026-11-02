// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionButton,
  Alert,
  ListboxSection,
  Modal,
  Select,
  SelectItem,
} from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCpu,
  IconSquareRotatedAsterisk,
} from '@tabler/icons-react';
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { Trans, useTranslation } from 'next-i18next';
import { useMemo, useState } from 'react';

import {
  ModelProfileSummary,
  toProfileSummaryFields,
} from '@/components/shared/ModelProfileSummary';
import { useProject } from '@/contexts/ProjectContext';
import { useProfileSpecsForServices } from '@/hooks/useProfileSpecsForServices';
import { profileKey } from '@/lib/app/aims/profileKey';
import { getMaxSupportedLoraRank } from '@/lib/app/aims';
import { canProfilesServeAdapter } from '@/lib/app/aims/adapterCompatibility';
import {
  getDeploymentModelKind,
  resolveDeploymentAimId,
} from '@/lib/app/deployment-model';
import {
  attachAdapterToDeployment,
  invalidateAdapterQueries,
  listInferenceDeployments,
} from '@/lib/app/inference';
import { fetchAllPages } from '@/lib/app/pagination';
import { AIM_DISPLAY_NAME_ANNOTATION, type AIMService } from '@/types/aims';
import type { LoraAdapter } from '@/types/artifacts';

type Props = {
  adapter: LoraAdapter | undefined;
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
};

const getDeploymentName = (deployment: AIMService): string =>
  deployment.metadata.annotations?.[AIM_DISPLAY_NAME_ANNOTATION] ??
  deployment.metadata.name;

type DeploymentOption = {
  deployment: AIMService;
  incompatibilityReason?: IncompatibilityReason;
  isAttached: boolean;
};

type IncompatibilityReason = {
  translationKey:
    | 'attachLora.incompatibility.dynamicDisabled'
    | 'attachLora.incompatibility.maxRankUnavailable'
    | 'attachLora.incompatibility.adapterRankUnavailable'
    | 'attachLora.incompatibility.maxRank';
  rank?: number;
};

const getIncompatibilityReason = (
  deployment: AIMService,
  adapterRank: number | null | undefined,
): IncompatibilityReason | undefined => {
  if (deployment.spec?.adapterMode !== 'dynamic') {
    return {
      translationKey: 'attachLora.incompatibility.dynamicDisabled',
    };
  }
  const maxRank = getMaxSupportedLoraRank(deployment.spec);
  if (maxRank == null) {
    return {
      translationKey: 'attachLora.incompatibility.maxRankUnavailable',
    };
  }
  // Fail closed: an adapter with an unknown rank can't be proven compatible.
  if (adapterRank == null) {
    return {
      translationKey: 'attachLora.incompatibility.adapterRankUnavailable',
    };
  }
  return maxRank < adapterRank
    ? {
        translationKey: 'attachLora.incompatibility.maxRank',
        rank: maxRank,
      }
    : undefined;
};

export function AttachLoraModal({ adapter, isOpen, onOpenChange }: Props) {
  const { activeProject } = useProject();
  const { toast } = useSystemToast();
  const { t: tModels } = useTranslation('models');
  const { t: tLoras } = useTranslation('loras');
  const { t: tCommon } = useTranslation('common');
  const queryClient = useQueryClient();
  const [selectedDeploymentId, setSelectedDeploymentId] = useState('');
  // Fetch every Running deployment in the project rather than joining through
  // the cluster-scoped model catalog: a fine-tuned/custom AIMModel deployment
  // otherwise never appears unless its name happens to collide with a cluster
  // model name.
  const {
    data: runningDeployments = [],
    isLoading: isDeploymentsLoading,
    isError: isDeploymentsError,
    refetch: refetchDeployments,
  } = useQuery({
    queryKey: ['project', activeProject, 'inference', 'running'],
    queryFn: () =>
      fetchAllPages<AIMService>((page, pageSize) =>
        listInferenceDeployments(activeProject!, {
          page,
          pageSize,
          statusFilter: ['Running'],
        }),
      ),
    enabled: isOpen && !!activeProject,
    retry: false,
  });
  const deploymentsWithId = useMemo(
    () =>
      Array.from(
        new Map(
          runningDeployments
            .filter((deployment) => deployment.id)
            .map((deployment) => [deployment.id, deployment]),
        ).values(),
      ),
    [runningDeployments],
  );
  const aimIdQueries = useQueries({
    queries: deploymentsWithId.map((deployment) => ({
      queryKey: [
        'lora-attach-model',
        activeProject,
        deployment.spec?.model?.name,
        getDeploymentModelKind(deployment.metadata.labels ?? {}),
      ],
      queryFn: () => resolveDeploymentAimId(activeProject ?? '', deployment),
      enabled: isOpen && !!activeProject && !!deployment.spec?.model?.name,
      retry: false,
    })),
  });
  const isResolvingAimIds = aimIdQueries.some((query) => query.isLoading);
  const hasAimIdResolutionError = aimIdQueries.some((query) => query.isError);
  // Whether the adapter can be served is decided by each deployment's resolved
  // profile, so profiles are fetched for every Running deployment and the
  // filtering happens afterwards — narrowing first would starve this fetch of
  // its own inputs. The aimId resolved here only scopes which profile catalogs
  // to pull; compatibility is read off the profile spec itself. Both inputs wait
  // for every aimId to settle, because the hook refetches once per arrival on a
  // growing set.
  const aimIds = useMemo<string[]>(
    () =>
      isResolvingAimIds
        ? []
        : Array.from(
            new Set(
              aimIdQueries.flatMap((query) => (query.data ? [query.data] : [])),
            ),
          ),
    [aimIdQueries, isResolvingAimIds],
  );
  const resolvedProfiles = useMemo(
    () =>
      isResolvingAimIds
        ? []
        : deploymentsWithId.map(({ status }) => status?.resolvedProfile),
    [deploymentsWithId, isResolvingAimIds],
  );
  const {
    specByName: profileSpecByName,
    isLoading: isLoadingProfiles,
    isError: isProfilesError,
    refetch: refetchProfiles,
  } = useProfileSpecsForServices({
    aimIds,
    project: activeProject,
    resolvedProfiles,
  });
  // A profile lookup that failed yields an empty spec map, and the filter below
  // then drops every deployment — which would render as the settled "nothing
  // here can serve this adapter" answer for a question that was never answered.
  // An unreadable eligibility lookup belongs with the other load failures.
  const hasDeploymentLoadError =
    isDeploymentsError || hasAimIdResolutionError || isProfilesError;
  const adapterCompatibleDeployments = useMemo(() => {
    if (!adapter) return [];
    return deploymentsWithId.filter((deployment) => {
      const resolvedProfile = deployment.status?.resolvedProfile;
      const profileName = resolvedProfile?.name;
      if (!profileName) return false;
      return canProfilesServeAdapter({
        adapter,
        profileSpecs: [
          profileSpecByName.get(
            profileKey(resolvedProfile?.scope, profileName),
          ),
        ],
      });
    });
  }, [adapter, deploymentsWithId, profileSpecByName]);
  const deploymentOptions = useMemo<DeploymentOption[]>(
    () =>
      adapterCompatibleDeployments.map((deployment) => ({
        deployment,
        incompatibilityReason: getIncompatibilityReason(
          deployment,
          adapter?.rank,
        ),
        isAttached:
          deployment.spec?.adapters?.some(
            (attachedAdapter) => attachedAdapter.name === adapter?.name,
          ) ?? false,
      })),
    [adapter?.name, adapter?.rank, adapterCompatibleDeployments],
  );
  const compatibleDeployments = deploymentOptions.filter(
    ({ incompatibilityReason }) => !incompatibilityReason,
  );
  const incompatibleDeployments = deploymentOptions.filter(
    ({ incompatibilityReason }) => !!incompatibilityReason,
  );
  const selectedDeployment = compatibleDeployments.find(
    ({ deployment, isAttached }) =>
      !isAttached && deployment.id === selectedDeploymentId,
  )?.deployment;

  const renderDeployment = ({
    deployment,
    incompatibilityReason,
    isAttached,
  }: DeploymentOption) => {
    const maxRank = getMaxSupportedLoraRank(deployment.spec);
    const baseProfile = toProfileSummaryFields(deployment, profileSpecByName);
    // toProfileSummaryFields only returns null when maxRank is also null, so
    // there's no case here where baseProfile is falsy but maxRank is set.
    const profile = baseProfile
      ? {
          ...baseProfile,
          maxLoraRank: incompatibilityReason ? null : maxRank,
        }
      : null;
    const hasProfileSummary =
      !!profile &&
      !!(
        profile.profileDisplayName ||
        profile.metric ||
        profile.gpu ||
        profile.templateGpuCount != null ||
        profile.precision
      );
    return (
      <SelectItem
        key={deployment.id}
        isDisabled={isAttached || !!incompatibilityReason}
        startContent={
          isAttached ? (
            <span aria-label={tLoras('attachLora.status.attached')} role="img">
              <IconCircleCheck aria-hidden className="text-success" size={20} />
            </span>
          ) : incompatibilityReason ? (
            <IconAlertTriangle className="text-danger" size={20} />
          ) : (
            <IconCpu className="text-muted" size={20} />
          )
        }
        description={
          <span className="flex flex-wrap items-center gap-1">
            <ModelProfileSummary profile={profile} t={tModels} />
            {incompatibilityReason ? (
              <>
                {hasProfileSummary ? <span aria-hidden>•</span> : null}
                <span className="inline-flex items-center gap-1 text-danger">
                  {incompatibilityReason.translationKey ===
                  'attachLora.incompatibility.maxRank' ? (
                    <IconSquareRotatedAsterisk aria-hidden size={14} />
                  ) : null}
                  {tLoras(incompatibilityReason.translationKey, {
                    rank: incompatibilityReason.rank,
                  })}
                </span>
              </>
            ) : null}
          </span>
        }
      >
        {getDeploymentName(deployment)}
      </SelectItem>
    );
  };

  const attachMutation = useMutation({
    mutationFn: (deployment: AIMService) =>
      attachAdapterToDeployment(activeProject!, deployment, adapter!.name),
    onSuccess: (_, deployment) => {
      toast.success(
        tLoras('attachLora.notifications.attaching', {
          adapter: adapter?.displayName,
          deployment: getDeploymentName(deployment),
        }),
      );
      invalidateAdapterQueries(queryClient, activeProject!);
      setSelectedDeploymentId('');
      onOpenChange(false);
    },
    onError: (error: unknown) => {
      toast.error(
        error instanceof APIRequestError
          ? error.message
          : tLoras('attachLora.notifications.error'),
      );
    },
  });
  if (!isOpen || !adapter) return null;
  const compatibleModels =
    adapter.compatibleWith.join(', ') ||
    tLoras('attachLora.fallbacks.compatibleModel');
  const requiredRank =
    adapter.rank ?? tLoras('attachLora.fallbacks.adapterRank');
  const handleClose = () => {
    if (attachMutation.isPending) return;
    setSelectedDeploymentId('');
    onOpenChange(false);
  };
  const retryDeploymentLoad = () => {
    void Promise.all([
      refetchDeployments(),
      ...aimIdQueries.map((query) => query.refetch()),
      refetchProfiles(),
    ]);
  };

  return (
    <Modal
      title={tLoras('attachLora.title')}
      onClose={handleClose}
      footer={
        <>
          <ActionButton
            secondary
            isDisabled={attachMutation.isPending}
            onPress={handleClose}
          >
            {tCommon('actions.cancel.title')}
          </ActionButton>
          <ActionButton
            primary
            isLoading={attachMutation.isPending}
            isDisabled={!selectedDeployment}
            onPress={() =>
              selectedDeployment && attachMutation.mutate(selectedDeployment)
            }
          >
            {tLoras('attachLora.actions.attach')}
          </ActionButton>
        </>
      }
    >
      <div className="space-y-6">
        <p>
          <Trans
            i18nKey="attachLora.description"
            ns="loras"
            values={{
              name: adapter.displayName,
              models: compatibleModels,
              rank: requiredRank,
            }}
            components={{ strong: <strong /> }}
          />
        </p>
        {hasDeploymentLoadError ? (
          <Alert
            data-testid="attach-lora-error-state"
            status="danger"
            title={tLoras('attachLora.error.title')}
            description={tLoras('attachLora.error.description')}
          >
            <ActionButton secondary onPress={retryDeploymentLoad}>
              {tLoras('attachLora.actions.retry')}
            </ActionButton>
          </Alert>
        ) : !isDeploymentsLoading &&
          !isResolvingAimIds &&
          !isLoadingProfiles &&
          deploymentOptions.length === 0 ? (
          <Alert
            data-testid="attach-lora-empty-state"
            status="warning"
            title={tLoras('attachLora.empty.title')}
            description={tLoras('attachLora.empty.description', {
              models: compatibleModels,
              rank: requiredRank,
            })}
          />
        ) : (
          <>
            <p>{tLoras('attachLora.durationNotice')}</p>
            <Select
              label={tLoras('attachLora.deployment.label')}
              placeholder={tLoras('attachLora.deployment.placeholder')}
              selectedKeys={selectedDeploymentId ? [selectedDeploymentId] : []}
              onChange={(event) => setSelectedDeploymentId(event.target.value)}
              showDescriptionInTrigger
            >
              {compatibleDeployments.length > 0 ? (
                <ListboxSection
                  title={tLoras('attachLora.sections.compatible')}
                >
                  {compatibleDeployments.map(renderDeployment)}
                </ListboxSection>
              ) : null}
              {incompatibleDeployments.length > 0 ? (
                <ListboxSection
                  title={tLoras('attachLora.sections.incompatible')}
                >
                  {incompatibleDeployments.map(renderDeployment)}
                </ListboxSection>
              ) : null}
            </Select>
          </>
        )}
      </div>
    </Modal>
  );
}
