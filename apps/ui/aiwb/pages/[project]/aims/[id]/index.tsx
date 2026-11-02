// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Select,
  SelectItem,
  ActionButton,
  DateSince,
  HeroMessage,
  Status,
  StatusDisplay,
  CopySnippet,
  Accordion,
  AccordionItem,
  Tooltip,
  Skeleton,
} from '@amdenterpriseai/components';
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconCpu,
  IconDashboard,
  IconDatabase,
  IconFileText,
  IconLink,
  IconMessage,
  IconRefresh,
  IconTrash,
  IconWorld,
} from '@tabler/icons-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/router';

import { useTranslation } from 'next-i18next';

import {
  DOCS_WORKBENCH_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';

import { useSystemToast } from '@amdenterpriseai/hooks';
import { getPageTranslations } from '@/lib/server/i18n';

import {
  aiWorkbenchMenuItems,
  APIRequestError,
} from '@amdenterpriseai/utils/app';
import { get } from 'lodash';
import {
  getProjectFineTunedModel,
  aimParser,
  getAIMServiceStatusVariants,
  getMaxSupportedLoraRank,
  getMetricTranslationKey,
  getModelCapability,
  getInferenceApiPath,
} from '@/lib/app/aims';
import {
  deleteInferenceDeployment,
  getInferenceDeployment,
  getInferenceModel,
  getInferenceReplicas,
  listAllInferenceDeployments,
} from '@/lib/app/inference';
import { getCustomModel } from '@/lib/app/custom-models';
import type { AutoscalingFieldValues } from '@/lib/app/aims';
import type { AIMService, AIMServiceCondition } from '@/types/aims';
import {
  AIM_DISPLAY_NAME_ANNOTATION,
  AIM_PROFILE_TYPE_OPTIMIZED,
  AIMClusterModel,
  AIMModel,
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
} from '@/types/aims';
import type { components } from '@/types/api';
import { useState, useCallback } from 'react';
import AIMConnectModal from '@/components/features/models/AIMConnectModal';
import DeleteWorkloadModal from '@/components/features/workloads/DeleteWorkloadModal';
import WorkloadLogsModal from '@/components/features/workloads/WorkloadLogsModal';
import InferenceMetrics from '@/components/features/workloads/InferenceMetrics';
import { Intent } from '@amdenterpriseai/types';
import type { EnrichedWorkloadMetrics } from '@/types/projects';
import { useProject } from '@/contexts/ProjectContext';
import { ScalingStatusCard } from '@/components/features/workloads/ScalingStatusCard';
import { LoraAdaptersCard } from '@/components/features/workloads/LoraAdaptersCard';
import { resolvedProfileQuery } from '@/hooks/useProfileSpecsForServices';
import { SUBMITTER_ANNOTATION_KEY } from '@/components/features/secrets/constants';
import {
  useScalingConvergence,
  CONVERGENCE_POLL_INTERVAL_MS,
} from '@/hooks/useScalingConvergence';
import AIMConditionsList from '@/components/shared/AIMConditionsList';
import { resolveModelDeploymentName } from '@/lib/app/modelDeploymentDisplay';

type CustomModelResponse = components['schemas']['CustomModelResponse'];

interface AimDetailsPageProps {
  /** Optional breadcrumb navigation items */
  pageBreadcrumb?: { title: string; href?: string }[];
  /** Unique identifier of the deployed AIM service (workload ID) */
  id: string;
}

type ProfileOverrides = {
  precision?: string;
  metricRaw?: string;
  gpuModel?: string;
  gpuRequestsNum?: number;
};

const extractProfileOverrides = (
  overrides: Record<string, unknown> | undefined,
): ProfileOverrides => {
  const precision =
    typeof overrides?.precision === 'string' ? overrides.precision : undefined;
  const metricRaw =
    typeof overrides?.metric === 'string' ? overrides.metric : undefined;
  const gpuModel =
    typeof overrides?.acceleratorModel === 'string'
      ? overrides.acceleratorModel
      : undefined;
  const rawGpuRequests = overrides?.acceleratorCount;
  const gpuRequestsNum =
    typeof rawGpuRequests === 'number'
      ? rawGpuRequests
      : typeof rawGpuRequests === 'string' &&
          rawGpuRequests !== '' &&
          !Number.isNaN(Number(rawGpuRequests))
        ? Number(rawGpuRequests)
        : undefined;

  return { precision, metricRaw, gpuModel, gpuRequestsNum };
};

/** True when deploy `spec.profileOverrides` carries any profile-related field (used to skip template skeleton). */
const hasDeployProfileOverrides = (o: ProfileOverrides): boolean =>
  Boolean(o.gpuModel) ||
  o.gpuRequestsNum != null ||
  Boolean(o.metricRaw) ||
  Boolean(o.precision);

const toGpuCountLabel = (count: number | undefined): string | undefined =>
  count != null
    ? `${count} ${count === 1 ? 'Accelerator' : 'Accelerators'}`
    : undefined;

/** Appends translated "(automatic)" when the value comes from resolved template metadata, not deploy overrides. */
const formatProfileDetailValue = (
  display: string | undefined,
  isOverride: boolean,
  automaticLabel: string,
): string => {
  if (display == null || display === '') return '—';
  if (isOverride) return display;
  return `${display} ${automaticLabel}`;
};

const AimDetailsPage: React.FC<AimDetailsPageProps> & WithDocumentationLink = ({
  id,
}) => {
  const { t } = useTranslation([
    'workloads',
    'common',
    'autoscaling',
    'models',
  ]);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useSystemToast();
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isPollingForConvergence, setIsPollingForConvergence] = useState(false);
  const [selectedReplica, setSelectedReplica] = useState<string>('all');
  const {
    activeProject: namespace,
    projectPath,
    projectUrl,
    aiGatewayEnabled,
    aiGatewayUrl,
  } = useProject();

  const {
    data: aimService,
    isLoading: isLoadingAimService,
    isError: isAimServiceError,
    error: aimServiceError,
    refetch: refetchAimService,
  } = useQuery({
    queryKey: ['aimService', namespace, id],
    queryFn: () => getInferenceDeployment(namespace as string, id as string),
    enabled: !!namespace && !!id && !isDeleting,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchInterval: isPollingForConvergence
      ? CONVERGENCE_POLL_INTERVAL_MS
      : false,
    // Skip retries on 404 so the deleted-history fallback below runs immediately.
    retry: (failureCount, error) =>
      !(error instanceof APIRequestError && error.statusCode === 404) &&
      failureCount < 3,
  });

  const stopConvergencePolling = useCallback(
    () => setIsPollingForConvergence(false),
    [],
  );
  const handleConvergenceTimeout = useCallback(() => {
    setIsPollingForConvergence(false);
    toast.warning(t('autoscaling:notifications.convergenceTimeout'));
  }, [toast, t]);

  const { startPolling } = useScalingConvergence({
    aimService,
    isAimServiceError,
    isPolling: isPollingForConvergence,
    onConverged: stopConvergencePolling,
    onTimeout: handleConvergenceTimeout,
  });

  const liveQuery404 =
    aimServiceError instanceof APIRequestError &&
    aimServiceError.statusCode === 404;

  // The history query walks the entire Deleted list via fetchAllPages — gate it
  // on liveQuery404 so live-AIM visits don't pay that cost.
  const { data: aimServiceHistory, isLoading: isLoadingAimServiceHistory } =
    useQuery({
      queryKey: ['aimServiceHistory', namespace, id],
      queryFn: () =>
        listAllInferenceDeployments(namespace as string, {
          statusFilter: ['Deleted'],
        }),
      enabled: !!namespace && !!id && !isDeleting && liveQuery404,
      refetchOnWindowFocus: false,
      refetchOnMount: false,
    });

  const historicalService: AIMService | undefined = aimServiceHistory?.find(
    (h) => h.id === id,
  );

  // The AIMClusterModel/AIMModel resource name. AIWB always sets
  // `spec.model.name` at create time; the backend (`AIMServiceResource`)
  // backfills it from `status.resolvedModel.name` for legacy v1alpha1
  // deploy-by-image services where the user only set `spec.model.image`.
  const resourceName =
    aimService?.spec?.model?.name || historicalService?.spec?.model?.name;

  const _isHistorical = !aimService && !!historicalService;

  const isFinetunedModel =
    aimService?.metadata?.labels?.[FINE_TUNED_LABEL] === 'true';

  const isCustomModel =
    aimService?.metadata?.labels?.[NAMESPACE_AIM_MODEL_LABEL] === 'true';

  // The cluster-model branch shares its cache with useInferenceModelsByName via
  // ['inferenceModel', resourceName] so list pages and this details page resolve to a
  // single fetch per name. The fine-tuned, custom-model, and historical-fallback branches
  // keep their namespace-scoped key because they hit different endpoints.
  const clusterModelQueryKey = ['inferenceModel', resourceName] as const;
  const finetunedQueryKey = [
    'aim',
    namespace,
    id,
    resourceName,
    isFinetunedModel,
  ] as const;
  const customModelQueryKey = ['customModel', namespace, resourceName] as const;
  const {
    data: aimClusterModel,
    isLoading: isLoadingAim,
    isError: isAimError,
  } = useQuery<AIMClusterModel | AIMModel | CustomModelResponse>({
    queryKey:
      isFinetunedModel || _isHistorical
        ? finetunedQueryKey
        : isCustomModel
          ? customModelQueryKey
          : clusterModelQueryKey,
    queryFn: async () => {
      if (isFinetunedModel) {
        return getProjectFineTunedModel(
          resourceName as string,
          namespace as string,
        );
      }
      if (isCustomModel) {
        // Custom (BYOM) models are namespace-scoped AIMModels; their detail
        // data lives on the custom-models endpoint, not the cluster catalog.
        return getCustomModel(namespace as string, resourceName as string);
      }
      // For historical services isFinetunedModel is always false (aimService is gone).
      // Try cluster-scoped first; if it 404s, the model was namespace-scoped (finetuned or custom).
      if (_isHistorical) {
        try {
          return await getInferenceModel(resourceName as string);
        } catch {
          return getProjectFineTunedModel(
            resourceName as string,
            namespace as string,
          );
        }
      }
      return getInferenceModel(resourceName as string);
    },
    enabled:
      !!resourceName && (!isFinetunedModel || !!namespace) && !isDeleting,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });

  const { data: replicas } = useQuery({
    queryKey: ['inferenceReplicas', namespace, id],
    queryFn: () => getInferenceReplicas(namespace as string, id as string),
    enabled:
      !!namespace &&
      !!id &&
      !isDeleting &&
      (aimService?.status?.status === 'Running' ||
        aimService?.status?.status === 'Degraded'),
    refetchOnWindowFocus: false,
  });

  const resolvedProfile = aimService?.status?.resolvedProfile;
  const resolvedProfileName = resolvedProfile?.name ?? null;
  // Resolved through the same rule the adapter picker's own lookup uses, rather
  // than a second copy of it: treating everything that is not exactly
  // `Namespace` as cluster-wide sent `Merged`, `Unknown` and absent-scope
  // references past every namespace-only overlay, and reached LoraAdaptersCard
  // with the wrong modelId and capabilities.
  const {
    data: resolvedProfileResource,
    isLoading: isResolvedProfileLoading,
    isError: isResolvedProfileError,
  } = useQuery(
    resolvedProfileQuery({
      project: typeof namespace === 'string' ? namespace : null,
      name: resolvedProfileName,
      scope: resolvedProfile?.scope,
    }),
  );
  const resolvedProfileSpec = resolvedProfileResource?.spec;

  const isMetricUnoptimized =
    !!resolvedProfileSpec &&
    resolvedProfileSpec.type !== AIM_PROFILE_TYPE_OPTIMIZED;

  const { mutate: deleteWorkloadMutation } = useMutation({
    mutationFn: (serviceId: string) => {
      setIsDeleting(true);
      return deleteInferenceDeployment(namespace!, serviceId);
    },
    onSuccess: () => {
      queryClient.removeQueries({
        queryKey: ['aimService', namespace, id],
      });
      toast.success(t('list.actions.delete.notification.success'));
      router.push(projectPath('/models'));
    },
    onError: () => {
      setIsDeleting(false);
      toast.error(t('list.actions.delete.notification.error'));
    },
  });

  const handleSettingsSaved = useCallback(
    (savedValues: AutoscalingFieldValues) => {
      setIsPollingForConvergence(true);
      startPolling(savedValues);
      refetchAimService();
    },
    [startPolling, refetchAimService],
  );

  const handleBack = () => {
    router.back();
  };

  // History only starts loading after the live query 404s, so the two loading
  // flags must be ORed (not ANDed) — sequenced via liveQuery404.
  const isLoadingFirstQuery =
    isLoadingAimService || (liveQuery404 && isLoadingAimServiceHistory);
  const isLoadingSecondQuery =
    !!resourceName && !aimClusterModel && !isAimError;
  const isLoading = isLoadingFirstQuery || isLoadingSecondQuery;

  if (isLoading) {
    return (
      <div className="flex flex-col space-y-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Skeleton className="h-8 w-8 rounded-lg" />
            <div className="flex items-center space-x-3 pr-2">
              <Skeleton className="h-7 w-64 rounded-lg" />
              <Skeleton className="h-6 w-24 rounded-full" />
            </div>
          </div>
        </div>
        <Skeleton className="h-6 w-64 rounded-lg" />
        <div className="columns-1 md:columns-2 xl:columns-3 gap-6 space-y-6">
          <Skeleton className="h-64 w-full rounded-lg" />
          <Skeleton className="h-64 w-full rounded-lg" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      </div>
    );
  }

  // A live error that isn't recovered by a historical lookup is the error path.
  const hasServiceError = isAimServiceError && !_isHistorical;
  const hasAimError = isAimError || !aimClusterModel;

  if ((hasServiceError && !isLoading) || hasAimError) {
    return (
      <HeroMessage
        intent={Intent.DANGER}
        title={t('errors.workloadNotFound.title')}
        description={t('errors.workloadNotFound.description', {
          project: namespace,
        })}
        endContent={
          <ActionButton
            className="mt-4"
            onPress={() => router.reload()}
            icon={<IconRefresh size={18} />}
          >
            {t('common:error.refreshActionLabel')}
          </ActionButton>
        }
      />
    );
  }

  // Deleted/historical entries arrive as standard AIMServiceResponse shapes
  // (synthesized from the DB row), so the regular aimParser handles both live
  // and historical services uniformly.
  const parsedAim = aimParser(
    aimClusterModel,
    aimService
      ? [aimService]
      : historicalService
        ? [historicalService]
        : undefined,
  );
  const deployedService = parsedAim.deployedService;
  const detailsTitle = resolveModelDeploymentName({
    displayName:
      deployedService?.metadata?.annotations?.[AIM_DISPLAY_NAME_ANNOTATION],
    resourceName: deployedService?.metadata?.name,
    canonicalName: isFinetunedModel ? parsedAim.title : parsedAim.canonicalName,
  });

  // Speech-to-text deployments advertise transcription tags; the Connect snippet
  // and chat-playground affordances key off this so STT users get the audio
  // endpoint instead of chat completions.
  const capability = getModelCapability(parsedAim.tags);
  const isTranscription = capability === 'transcription';

  const specOverrides = deployedService?.spec?.profileOverrides as
    | Record<string, unknown>
    | undefined;
  const profileOverrides = extractProfileOverrides(specOverrides);

  const hasProfileDataFromSpec = hasDeployProfileOverrides(profileOverrides);
  const {
    precision: overridePrecision,
    metricRaw: overrideMetricRaw,
    gpuModel: overrideGpuModel,
    gpuRequestsNum: overrideGpuRequestsNum,
  } = profileOverrides;

  const profileSpec = resolvedProfileSpec;
  const profileGpuDisplay =
    overrideGpuModel ?? profileSpec?.acceleratorModel ?? undefined;
  const profileGpuCountDisplay =
    toGpuCountLabel(overrideGpuRequestsNum) ??
    toGpuCountLabel(profileSpec?.acceleratorCount ?? undefined);
  const profileMetricKey = overrideMetricRaw ?? profileSpec?.metric;
  const profileMetricDisplay = profileMetricKey
    ? t(getMetricTranslationKey(String(profileMetricKey)), { ns: 'models' })
    : undefined;
  const profilePrecisionDisplay =
    overridePrecision ?? profileSpec?.precision ?? undefined;

  const isMetricOverride = Boolean(overrideMetricRaw);
  const isGpuOverride = Boolean(overrideGpuModel);
  const isGpuCountOverride = overrideGpuRequestsNum != null;
  const isPrecisionOverride = Boolean(overridePrecision);

  const profileAutomaticLabel = t('details.profile.automatic');

  // Backend types conditions as a loose map; read them via the FE-known shape.
  const aimConditions = deployedService?.status?.conditions as
    | AIMServiceCondition[]
    | undefined;
  const { external, internal } = deployedService?.endpoints || {};
  // Share the path selection with the Connect modal so the copyable host URLs in
  // the Output card never contradict the snippet the modal generates.
  const inferencePath = getInferenceApiPath(capability);
  const externalHost = external ? `${external}${inferencePath}` : '';
  const internalHost = internal ? `${internal}${inferencePath}` : '';

  // The unified Envoy AI Gateway serves JSON chat completions; speech-to-text is
  // a multipart upload, so transcription deployments use the per-service host
  // instead of the gateway (matching the Connect modal).
  const gatewayHost =
    !isTranscription && aiGatewayEnabled && aiGatewayUrl
      ? `${aiGatewayUrl.replace(/\/$/, '')}${inferencePath}`
      : '';
  const useGateway = !!gatewayHost;

  const workloadCreatedBy =
    deployedService?.metadata?.annotations?.[SUBMITTER_ANNOTATION_KEY] || null;

  // Construct workload object for WorkloadLogsModal
  const aimWorkload: EnrichedWorkloadMetrics = {
    id,
    name: parsedAim.model,
    displayName: detailsTitle,
    type: 'INFERENCE',
    status: deployedService?.status?.status ?? 'Unknown',
    gpuCount: null,
    templateGpuCount: null,
    gpu: null,
    acceleratorType: null,
    metric: null,
    precision: null,
    vram: null,
    createdAt: deployedService?.metadata?.creationTimestamp ?? null,
    createdBy: workloadCreatedBy,
    resourceType: 'AIMService',
  };

  // Show only "{*}Ready" conditions, filter out anything else.
  const hasConditions = (aimConditions ?? []).some(
    (c) => c.type !== 'Ready' && c.type?.endsWith('Ready'),
  );

  return (
    <div className="flex flex-col space-y-6 py-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <ActionButton
            secondary
            onPress={handleBack}
            size="sm"
            icon={<IconArrowLeft size={16} />}
          />
          <div className="flex items-center space-x-3 pr-2">
            <h2>{detailsTitle}</h2>
            <StatusDisplay
              type={deployedService?.status?.status as string}
              variants={getAIMServiceStatusVariants(t)}
              additionalProps={{ isShowBackground: true, isTextColored: true }}
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center space-x-2">
          {replicas && replicas.length > 1 && (
            <Select
              className="w-48"
              selectedKeys={[selectedReplica]}
              onSelectionChange={(keys) => {
                const selectedKey = Array.from(keys)[0] as string;
                if (selectedKey !== undefined) setSelectedReplica(selectedKey);
              }}
              aria-label={t('details.metrics.replicaSelector.label')}
            >
              {[
                {
                  key: 'all',
                  label: t('details.metrics.replicaSelector.allReplicas'),
                },
                ...replicas.map((r) => ({
                  key: r.metadata.name,
                  label: r.metadata.name.split('-').at(-1) ?? r.metadata.name,
                  fullName: r.metadata.name,
                })),
              ].map((opt) => (
                <SelectItem key={opt.key} textValue={opt.label}>
                  {'fullName' in opt ? (
                    <Tooltip content={opt.fullName} placement="right">
                      {/* biome-ignore lint/a11y/useSemanticElements: the element reveals the full label rather than performing an action. */}
                      <span role="button" tabIndex={0}>
                        {opt.label}
                      </span>
                    </Tooltip>
                  ) : (
                    opt.label
                  )}
                </SelectItem>
              ))}
            </Select>
          )}
          {!isTranscription && (
            <ActionButton
              secondary
              onPress={() =>
                router.push({
                  pathname: projectPath('/chat'),
                  query: { workload: id },
                })
              }
              icon={<IconMessage size={16} />}
              isDisabled={deployedService?.status?.status !== 'Running'}
            >
              {t('list.actions.chat.label')}
            </ActionButton>
          )}

          <ActionButton
            secondary
            onPress={() => setIsLogsModalOpen(true)}
            icon={<IconFileText size={16} />}
          >
            {t('list.actions.logs.label')}
          </ActionButton>

          <ActionButton
            secondary
            color="danger"
            onPress={() => setIsDeleteModalOpen(true)}
            icon={<IconTrash size={16} />}
            isDisabled={deployedService?.status?.status === 'Deleted'}
          >
            {t('list.actions.delete.label')}
          </ActionButton>
        </div>
      </div>

      {/* Inference metrics */}
      {!_isHistorical &&
        (deployedService?.status?.status === 'Starting' ||
          deployedService?.status?.status === 'Running' ||
          deployedService?.status?.status === 'Degraded') && (
          <InferenceMetrics
            workloadId={id}
            podName={selectedReplica === 'all' ? undefined : selectedReplica}
          />
        )}

      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">{t('list.headers.aim.title')}</h3>
      </div>

      {/* Autoscaling Status Card - own row, spans 2 of 3 columns at xl */}
      {aimService?.spec?.autoScaling && (
        <div className="w-full xl:w-[calc((200%_-_1.5rem)_/_3)]">
          <ScalingStatusCard
            spec={aimService.spec}
            runtime={aimService.status?.runtime}
            namespace={namespace ?? undefined}
            id={id}
            onSettingsSaved={handleSettingsSaved}
            replicas={replicas}
          />
        </div>
      )}

      <div className="columns-1 md:columns-2 xl:columns-3 gap-6 space-y-6">
        {/* AIM Information + Profile (stacked under basic information) */}
        {(aimClusterModel || isLoadingAim) && (
          <div className="break-inside-avoid mb-6 flex flex-col gap-6">
            <Card>
              <CardHeader>
                <h4 className="flex items-center gap-2 font-semibold">
                  <IconDatabase size={16} className="text-muted" />
                  {t('details.sections.basicInformation')}
                </h4>
              </CardHeader>
              <CardBody>
                {isLoadingAim ? (
                  <div className="flex flex-col space-y-3">
                    <Skeleton className="w-full h-6 rounded-lg" />
                    <Skeleton className="w-3/4 h-6 rounded-lg" />
                    <Skeleton className="w-2/3 h-6 rounded-lg" />
                    <Skeleton className="w-1/2 h-6 rounded-lg" />
                  </div>
                ) : (
                  <div className="flex flex-col space-y-3">
                    {aimClusterModel!.spec?.image && (
                      <div className="flex items-center space-x-3">
                        <div>
                          <h5 className="text-sm text-foreground">
                            {t('list.headers.aim.image')}
                          </h5>
                          <p className="font-mono text-sm">
                            {aimClusterModel!.spec?.image}
                          </p>
                        </div>
                      </div>
                    )}

                    {parsedAim.imageVersion && (
                      <div className="flex items-center space-x-3">
                        <div>
                          <h5 className="text-sm text-foreground">
                            {t('list.headers.aim.containerVersion')}
                          </h5>
                          <p className="font-mono text-sm">
                            {parsedAim.imageVersion}
                          </p>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center space-x-3">
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('list.headers.aim.resourceName')}
                        </h5>
                        <p className="font-mono text-sm">
                          {parsedAim.model || '—'}
                        </p>
                      </div>
                    </div>

                    {parsedAim.canonicalName && (
                      <div className="flex items-center space-x-3">
                        <div>
                          <h5 className="text-sm text-foreground">
                            {t(
                              isFinetunedModel
                                ? 'list.headers.aim.baseModel'
                                : 'list.headers.aim.canonicalName',
                            )}
                          </h5>
                          <p className="font-mono text-sm">
                            {parsedAim.canonicalName}
                          </p>
                        </div>
                      </div>
                    )}

                    {aimClusterModel!.status?.imageMetadata?.oci
                      ?.description && (
                      <div className="flex items-center space-x-3">
                        <div>
                          <h5 className="text-sm text-foreground">
                            {t('list.headers.aim.description')}
                          </h5>
                          <p className="text-sm">
                            {
                              aimClusterModel!.status.imageMetadata.oci
                                .description
                            }
                          </p>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center space-x-3">
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('list.headers.aim.id')}
                        </h5>
                        <p className="font-mono text-sm">{id}</p>
                      </div>
                    </div>
                  </div>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <h4 className="flex items-center gap-2 font-semibold">
                  <IconCpu size={16} className="text-muted" />
                  {t('details.profile.title')}
                </h4>
              </CardHeader>
              <CardBody className="space-y-4">
                {isLoadingAim ? (
                  <div className="flex flex-col space-y-3">
                    <Skeleton className="h-4 w-full rounded-lg" />
                    <Skeleton className="h-4 w-full rounded-lg" />
                    <Skeleton className="h-4 w-full rounded-lg" />
                    <Skeleton className="h-4 w-full rounded-lg" />
                  </div>
                ) : (
                  <>
                    <div className="space-y-3">
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('details.profile.performanceMetric')}
                        </h5>
                        <p className="font-mono text-sm">
                          {formatProfileDetailValue(
                            profileMetricDisplay,
                            isMetricOverride,
                            profileAutomaticLabel,
                          )}
                        </p>
                      </div>
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('details.profile.accelerator')}
                        </h5>
                        <p className="font-mono text-sm">
                          {formatProfileDetailValue(
                            profileGpuDisplay,
                            isGpuOverride,
                            profileAutomaticLabel,
                          )}
                        </p>
                      </div>
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('details.profile.acceleratorCount')}
                        </h5>
                        <p className="font-mono text-sm">
                          {formatProfileDetailValue(
                            profileGpuCountDisplay,
                            isGpuCountOverride,
                            profileAutomaticLabel,
                          )}
                        </p>
                      </div>
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('details.profile.precision')}
                        </h5>
                        <p className="font-mono text-sm">
                          {formatProfileDetailValue(
                            profilePrecisionDisplay,
                            isPrecisionOverride,
                            profileAutomaticLabel,
                          )}
                        </p>
                      </div>
                    </div>
                    {isMetricUnoptimized && (
                      <div className="border-t border-default pt-4">
                        <div className="flex items-start gap-1.5">
                          <IconAlertTriangle
                            size={14}
                            className="mt-0.5 shrink-0 text-warning"
                            aria-hidden
                          />
                          <p className="text-xs text-muted">
                            {t('details.profile.unoptimizedNotice')}
                          </p>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </CardBody>
            </Card>
          </div>
        )}
        {deployedService &&
          ((deployedService.spec?.adapters?.length ?? 0) > 0 ||
            getMaxSupportedLoraRank(deployedService.spec) != null) && (
            <LoraAdaptersCard
              namespace={namespace!}
              deployment={deployedService}
              resolvedProfileSpec={resolvedProfileSpec}
              isResolvedProfileLoading={isResolvedProfileLoading}
              isResolvedProfileError={isResolvedProfileError}
              onAdaptersUpdated={refetchAimService}
            />
          )}
        {/* Status */}
        <Card className="break-inside-avoid mb-6">
          <CardHeader>
            <h4 className="flex items-center gap-2 font-semibold">
              <IconDashboard size={16} className="text-muted" />
              {t('details.sections.status')}
            </h4>
          </CardHeader>
          <CardBody>
            <div className="mb-4 space-y-3 border-b border-default pb-4">
              <div className="flex items-center space-x-3">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.createdBy.title')}
                  </h5>
                  <p className="text-sm">{workloadCreatedBy ?? '—'}</p>
                </div>
              </div>
              <div className="flex items-center space-x-3">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.createdAt.title')}
                  </h5>
                  {deployedService?.metadata?.creationTimestamp ? (
                    <DateSince
                      date={deployedService.metadata.creationTimestamp}
                      className="text-sm text-foreground"
                    />
                  ) : (
                    <p className="text-sm">—</p>
                  )}
                </div>
              </div>
            </div>
            {hasConditions ? (
              <Accordion className="px-0">
                <AccordionItem
                  title={
                    <StatusDisplay
                      type={deployedService?.status?.status as string}
                      variants={getAIMServiceStatusVariants(t)}
                    />
                  }
                  classNames={{
                    trigger: 'py-2',
                    content: 'pt-2',
                  }}
                >
                  <AIMConditionsList conditions={aimConditions ?? []} />
                </AccordionItem>
              </Accordion>
            ) : (
              <StatusDisplay
                type={deployedService?.status?.status as string}
                variants={getAIMServiceStatusVariants(t)}
              />
            )}
          </CardBody>
        </Card>
        {/* Output Information */}
        {(useGateway || externalHost || internalHost) && (
          <Card className="break-inside-avoid mb-6">
            <CardHeader>
              <div className="flex w-full items-center justify-between gap-2">
                <h4 className="flex items-center gap-2 font-semibold">
                  <IconWorld size={16} className="text-muted" />
                  {t('details.sections.output')}
                </h4>
                <Button
                  data-testid="connect-to-model-button"
                  size="sm"
                  variant="light"
                  startContent={<IconLink size={14} />}
                  onPress={() => setIsConnectModalOpen(true)}
                >
                  {t('models:aimCatalog.actions.connect.label')}
                </Button>
              </div>
            </CardHeader>
            <CardBody className="space-y-2">
              {useGateway ? (
                <CopySnippet
                  label={t(
                    'models:aimCatalog.actions.connect.modal.inferenceUrl',
                  )}
                  value={gatewayHost}
                  className="w-full"
                />
              ) : (
                externalHost && (
                  <CopySnippet
                    label={t('details.fields.externalHost')}
                    value={externalHost}
                    className="w-full"
                  />
                )
              )}

              {internalHost && (
                <CopySnippet
                  label={t('details.fields.internalHost')}
                  value={internalHost}
                  className="w-full"
                />
              )}
            </CardBody>
          </Card>
        )}
      </div>

      {/* Modals */}
      <DeleteWorkloadModal
        isOpen={isDeleteModalOpen}
        onOpenChange={setIsDeleteModalOpen}
        workload={aimWorkload}
        onConfirmAction={deleteWorkloadMutation}
      />

      {isLogsModalOpen && (
        <WorkloadLogsModal
          isOpen={isLogsModalOpen}
          onOpenChange={setIsLogsModalOpen}
          workload={aimWorkload}
          namespace={namespace as string}
        />
      )}

      {isConnectModalOpen && (
        <AIMConnectModal
          isOpen={isConnectModalOpen}
          onOpenChange={setIsConnectModalOpen}
          endpoints={deployedService?.endpoints}
          modelName={deployedService?.status?.resolvedModel?.name ?? undefined}
          serviceId={deployedService?.id ?? undefined}
          capability={capability}
          onChatRequested={(serviceId) => {
            router.push({
              pathname: projectPath('/chat'),
              query: { workload: serviceId },
            });
          }}
        />
      )}
    </div>
  );
};

export async function getServerSideProps(context: {
  locale: any;
  params: any;
  query: any;
}) {
  const { locale, params, query } = context;

  const id = params?.id;
  const project = params?.project as string;

  if (!id) {
    return {
      redirect: {
        destination: `/${project}/models`,
        permanent: false,
      },
    };
  }

  const translations = await getPageTranslations(locale, [
    'workloads',
    'loras',
    'models',
    'autoscaling',
    'projects',
  ]);

  let breadcrumb: { title: string; href?: string }[] = [
    {
      title:
        translations._nextI18Next?.initialI18nStore[locale]?.workloads?.details
          ?.breadcrumb || 'Workload details',
    },
  ];

  // Determine previous route from referer query param for correct parent breadcrumb
  const refererRoutePath = query?.ref || '/';
  const prevNavItem = aiWorkbenchMenuItems.find(
    (item) => item.href === refererRoutePath,
  );

  if (prevNavItem) {
    const title = get(
      translations._nextI18Next?.initialI18nStore[locale]?.common,
      prevNavItem.stringKey,
      prevNavItem.stringKey,
    );

    breadcrumb = [
      {
        title,
        href: `/${project}${prevNavItem.href}`,
      },
      ...breadcrumb,
    ];
  }

  return {
    props: {
      ...translations,
      pageBreadcrumb: breadcrumb,
      id,
    },
  };
}

export default AimDetailsPage;

AimDetailsPage.documentationLink = `${DOCS_WORKBENCH_BASE}/models.html`;
