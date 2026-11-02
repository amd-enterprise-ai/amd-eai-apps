// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  SelectItem,
  Alert,
  DrawerForm,
  FormInput,
  FormSelect,
  Spinner,
} from '@amdenterpriseai/components';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';

import {
  createApiKey,
  fetchApiKeyDetails,
  updateApiKeyBindings,
} from '@/lib/app/api-keys';

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { displayTimestamp } from '@amdenterpriseai/utils/app';

import type { components } from '@/types/api';

import { KeyCreatedDrawer } from './KeyCreatedDrawer';

import { z } from 'zod';
import { aimParser, resolveAIMServiceDisplay } from '@/lib/app/aims';
import { listAllProjectFineTunedModels } from '@/lib/app/models';
import { listAllInferenceDeployments } from '@/lib/app/inference';
import { useInferenceModelsByName } from '@/hooks/useInferenceModelsByName';
import { useCustomProfileDeployments } from '@/hooks/useCustomProfileDeployments';
import { useProfileSpecsForServices } from '@/hooks/useProfileSpecsForServices';
import { toProfileSummaryFields } from '@/components/shared/ModelProfileSummary';
import { formatModelDeploymentSubtitle } from '@/lib/app/modelDeploymentDisplay';
import {
  AIM_DISPLAY_NAME_ANNOTATION,
  AIMService,
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
} from '@/types/aims';

type ApiKey = components['schemas']['ApiKeyResponse'];
type ApiKeyDetails = components['schemas']['ApiKeyDetails'];
type ApiKeyWithFullKey = components['schemas']['ApiKeyWithFullKey'];

const apiKeyFormSchema = z.object({
  displayName: z.string().optional(),
  validityPeriod: z.string().optional(),
  modelDeployments: z.array(z.string()),
});
type CreateApiKeyFormData = z.infer<typeof apiKeyFormSchema>;

interface Props {
  isOpen: boolean;
  projectId: string;
  apiKey?: ApiKey;
  onClose: () => void;
}

export const CreateApiKey: React.FC<Props> = ({
  isOpen,
  projectId,
  apiKey,
  onClose,
}) => {
  const { t } = useTranslation('api-keys');
  const { t: tModels } = useTranslation('models');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const isEditMode = !!apiKey;

  const [createdApiKey, setCreatedApiKey] = useState<ApiKeyWithFullKey | null>(
    null,
  );
  const [isKeyCreatedDrawerOpen, setIsKeyCreatedDrawerOpen] = useState(false);

  // Fetch API key details in edit mode to get current group bindings
  const { data: apiKeyDetails, isLoading: isLoadingDetails } =
    useQuery<ApiKeyDetails>({
      queryKey: ['api-key-details', projectId, apiKey?.id],
      queryFn: () => fetchApiKeyDetails(projectId, apiKey!.id),
      enabled: isEditMode && isOpen && !!apiKey?.id,
      refetchOnMount: 'always',
      staleTime: 0,
    });

  const { mutate: createKey, isPending: isCreating } = useMutation({
    mutationFn: async (data: {
      displayName: string;
      ttl?: string;
      aimIds?: string[];
    }) => {
      return createApiKey(projectId, data);
    },
    onSuccess: (data: ApiKeyWithFullKey) => {
      queryClient.invalidateQueries({
        queryKey: ['project-api-keys', projectId],
      });
      toast.success(t('form.create.notification.success'));
      setCreatedApiKey(data);
      setIsKeyCreatedDrawerOpen(true);
    },
    onError: (error) => {
      toast.error(
        t('form.create.notification.error'),
        error as APIRequestError,
      );
    },
  });

  // Validity period options for API keys (ordered from shortest to longest)
  const validityPeriodOptions = useMemo(
    () => [
      {
        value: '24h',
        label: t('form.create.field.validityPeriod.options.1day'),
      },
      {
        value: '7d',
        label: t('form.create.field.validityPeriod.options.1week'),
      },
      {
        value: '14d',
        label: t('form.create.field.validityPeriod.options.2weeks'),
      },
      {
        value: '30d',
        label: t('form.create.field.validityPeriod.options.30days'),
      },
      {
        value: '60d',
        label: t('form.create.field.validityPeriod.options.60days'),
      },
      {
        value: '90d',
        label: t('form.create.field.validityPeriod.options.90days'),
      },
      {
        value: '0',
        label: t('form.create.field.validityPeriod.options.never'),
      },
    ],
    [t],
  );

  // Mutation for updating API key bindings in edit mode
  const { mutateAsync: updateBindings, isPending: isUpdating } = useMutation({
    mutationFn: async ({ aimIds }: { aimIds: string[] }) => {
      return updateApiKeyBindings(projectId, apiKey!.id, aimIds);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['project-api-keys', projectId],
      });
      queryClient.invalidateQueries({
        queryKey: ['api-key-details', projectId, apiKey?.id],
      });
      toast.success(t('form.edit.notification.success'));
      onClose();
    },
    onError: (error) => {
      toast.error(t('form.edit.notification.error'), error as APIRequestError);
    },
  });

  const isPending = isCreating || isUpdating;

  const handleCreateSubmit = useCallback(
    async (data: CreateApiKeyFormData): Promise<void> => {
      if (isEditMode) {
        // Edit mode: only send modelDeployments (aim_ids) to backend
        try {
          await updateBindings({
            aimIds: data.modelDeployments,
          });
        } catch {
          // Error is already handled by mutation's onError callback
          // This catch prevents unhandled promise rejection
        }
      } else {
        // Create mode: create new key with aim_ids
        const payload: {
          displayName: string;
          ttl?: string;
          aimIds?: string[];
        } = {
          displayName: data.displayName!,
          aimIds: data.modelDeployments,
        };

        if (data.validityPeriod) {
          payload.ttl = data.validityPeriod;
        }

        createKey(payload);
      }
    },
    [createKey, updateBindings, isEditMode],
  );

  const handleKeyCreatedDrawerClose = useCallback(() => {
    setIsKeyCreatedDrawerOpen(false);
    setCreatedApiKey(null);
    onClose();
  }, [onClose]);

  const formSchema = useMemo(() => {
    const modelDeploymentsField = z.preprocess((val: unknown) => {
      if (Array.isArray(val)) return val.filter(Boolean);
      if (typeof val === 'string' && val !== '')
        return val.split(',').filter(Boolean);
      return [];
    }, z.array(z.string()));
    if (isEditMode) {
      // In edit mode, only modelDeployments is submitted; the name and validity
      // are shown read-only and never registered as inputs, so they stay optional.
      return z.object({
        displayName: z.string().optional(),
        validityPeriod: z.string().optional(),
        modelDeployments: modelDeploymentsField.default([]),
      });
    }
    // In create mode, name is required.
    return z.object({
      displayName: z
        .string()
        .trim()
        .min(1, t('form.create.field.name.error.required'))
        .min(3, t('form.create.field.name.error.minLength'))
        .max(64, t('form.create.field.name.error.maxLength')),
      validityPeriod: z.string().default('0'),
      modelDeployments: modelDeploymentsField.default([]),
    });
  }, [t, isEditMode]);

  const { data: aimServices = [], isLoading: isLoadingAimServices } = useQuery({
    queryKey: ['aim-services', projectId],
    queryFn: () => listAllInferenceDeployments(projectId),
    enabled: isOpen && !!projectId,
  });

  // Cluster-catalog models are only needed to enrich the display of cluster-scoped AIM
  // services. Namespace-scoped AIMModel services (fine-tuned and custom-imported) aren't
  // in that catalog — resolveAIMServiceDisplay already falls back to their annotations,
  // so we skip those names. Profile metric/gpu/precision come from
  // `useProfileSpecsForServices` (separate fetch joined by `status.resolvedProfile.name`),
  // so this fan-out only covers display-name enrichment.
  const clusterAimNames = useMemo(
    () =>
      aimServices
        .filter(
          (s: AIMService) =>
            s.metadata.labels?.[FINE_TUNED_LABEL] !== 'true' &&
            s.metadata.labels?.[NAMESPACE_AIM_MODEL_LABEL] !== 'true',
        )
        .map((s: AIMService) => s.spec?.model?.name)
        .filter((name): name is string => !!name),
    [aimServices],
  );
  const { byName: clusterAimsByName, isLoading: isClusterAimsLoading } =
    useInferenceModelsByName(isOpen ? clusterAimNames : []);
  const parsedAIMs = useMemo(
    () => Array.from(clusterAimsByName.values()).map((m) => aimParser(m)),
    [clusterAimsByName],
  );

  // Project AIMModel CRs — used here only so namespace-scoped (fine-tuned)
  // deployments contribute their `status.aimId` to the namespace AIMProfile
  // fetch below. Cluster-scoped deployments contribute via clusterAimsByName.
  const { data: fineTunedModels = [], isLoading: isFineTunedLoading } =
    useQuery({
      queryKey: ['project', projectId, 'fine-tuned-models'],
      queryFn: () => listAllProjectFineTunedModels(projectId),
      enabled: isOpen && !!projectId,
      staleTime: 5 * 60_000,
    });

  // Profile lookup map for the metric / gpu / precision subtitle. Wait for
  // both upstream model fetches to settle before deriving aimIds — otherwise
  // each per-name model landing would trigger a superseding profile fetch.
  const isUpstreamLoading = isClusterAimsLoading || isFineTunedLoading;
  const aimIds = isUpstreamLoading
    ? []
    : [
        ...Array.from(clusterAimsByName.values()).map((m) => m.status?.aimId),
        ...fineTunedModels.map((m) => m.status?.aimId),
      ].filter((id): id is string => !!id);
  // The picker only lists Running deployments with an external endpoint, so scope
  // profile resolution to those too — otherwise a slow profile lookup for a
  // Pending/Failed custom model the user can never pick would keep the whole
  // selector disabled.
  const pickerEligibleServices = useMemo(
    () =>
      aimServices.filter(
        (service: AIMService) =>
          service.id != null &&
          service.status?.status === 'Running' &&
          service.endpoints?.external != null,
      ),
    [aimServices],
  );
  const resolvedProfiles = useMemo(
    () => pickerEligibleServices.map(({ status }) => status?.resolvedProfile),
    [pickerEligibleServices],
  );
  const { specByName: profileSpecByName, isLoading: isLoadingProfiles } =
    useProfileSpecsForServices({
      aimIds,
      project: projectId,
      resolvedProfiles,
    });

  const {
    profileByServiceId: customProfileByServiceId,
    isLoading: isCustomProfilesLoading,
  } = useCustomProfileDeployments({
    services: isOpen ? pickerEligibleServices : [],
    project: projectId,
  });

  const modelDeployments = useMemo(() => {
    return pickerEligibleServices.map((service: AIMService) => {
      const displayInfo = resolveAIMServiceDisplay(service, parsedAIMs);
      const profile = toProfileSummaryFields(service, profileSpecByName);
      const canonicalName =
        `${displayInfo.canonicalName} ${displayInfo.imageVersion ? `(${displayInfo.imageVersion})` : ''}`.trim();
      // Prefer the user-entered deploy name; fall back to canonical + version
      // when the API only echoes the K8s resource name.
      const deployDisplayName =
        service.metadata.annotations?.[AIM_DISPLAY_NAME_ANNOTATION];
      const title =
        deployDisplayName && deployDisplayName !== service.metadata.name
          ? deployDisplayName
          : canonicalName;
      const subtitle = formatModelDeploymentSubtitle(tModels, {
        metric: profile?.metric ?? String(displayInfo.metric),
        gpu: profile?.gpu,
        templateGpuCount: profile?.templateGpuCount,
        acceleratorType: profile?.acceleratorType,
        precision: profile?.precision,
        profileDisplayName: customProfileByServiceId.get(service.id!)
          ?.displayName,
      });
      return {
        id: service.id!,
        title,
        subtitle,
      };
    });
  }, [
    pickerEligibleServices,
    parsedAIMs,
    profileSpecByName,
    customProfileByServiceId,
    tModels,
  ]);

  const defaultValues = useMemo((): CreateApiKeyFormData => {
    if (!isEditMode) {
      return { displayName: '', validityPeriod: '0', modelDeployments: [] };
    }
    if (!apiKeyDetails || modelDeployments.length === 0) {
      return {
        displayName: apiKeyDetails?.displayName ?? apiKey?.displayName ?? '',
        validityPeriod: '0',
        modelDeployments: [],
      };
    }
    const selectedAimIds = modelDeployments
      .filter((d) => apiKeyDetails.groups?.includes(d.id))
      .map((d) => d.id);
    return {
      displayName: apiKeyDetails.displayName ?? apiKey?.displayName ?? '',
      validityPeriod: '0',
      modelDeployments: selectedAimIds,
    };
  }, [isEditMode, apiKeyDetails, modelDeployments, apiKey?.displayName]);

  // Capture form.reset so we can call it imperatively once both data sources
  // are ready, instead of remounting the form via a key change (which flashes).
  const resetFormRef = useRef<((values: CreateApiKeyFormData) => void) | null>(
    null,
  );
  // All five fetches must settle before modelDeployments has stable titles,
  // subtitles, and workload-ids. Gate the field on all of them so the select goes
  // directly from spinner to correct values with no intermediary states.
  // isLoadingDetails (not !!apiKeyDetails) is used so an error response still
  // unblocks the field rather than leaving it stuck in a permanent loading state.
  const isDeploymentsLoading =
    isLoadingDetails ||
    isLoadingAimServices ||
    isClusterAimsLoading ||
    isFineTunedLoading ||
    isLoadingProfiles ||
    isCustomProfilesLoading;
  const dataReady = isEditMode && !isDeploymentsLoading;
  const isSelectLoading = isEditMode ? !dataReady : isDeploymentsLoading;
  useEffect(() => {
    if (dataReady) {
      resetFormRef.current?.(defaultValues);
    }
    // `defaultValues` is intentionally omitted from deps. This effect is a
    // one-shot trigger: we want to reset the form exactly once, when `dataReady`
    // first flips to true. Re-firing on every `defaultValues` recomputation
    // (e.g. profile subtitle changes) would wipe user edits mid-session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataReady]);

  const editModeFields = isEditMode
    ? [
        {
          label: t('form.create.field.name.label'),
          value: apiKeyDetails?.displayName || apiKey?.displayName,
        },
        {
          label: t('form.create.field.expiresAt.label'),
          value:
            apiKeyDetails?.expiresAt === null
              ? t('form.create.field.validityPeriod.options.never')
              : apiKeyDetails?.expiresAt
                ? displayTimestamp(new Date(apiKeyDetails.expiresAt))
                : '-',
        },
      ]
    : [];

  const renderLinkedDeployments = (
    selectedAimIdsRaw: string[] | string | undefined,
  ): React.ReactNode => {
    const selectedAimIds = Array.isArray(selectedAimIdsRaw)
      ? selectedAimIdsRaw
      : typeof selectedAimIdsRaw === 'string'
        ? selectedAimIdsRaw.split(',').filter(Boolean)
        : [];

    if (isSelectLoading) {
      return (
        <div className="pl-2">
          <Spinner size="sm" color="primary" />
        </div>
      );
    }

    if (!selectedAimIds.length) {
      return (
        <div className="text-sm text-muted pl-2">
          {t('form.edit.section.noLinkedDeployments')}
        </div>
      );
    }

    const selectedDeploymentsList = selectedAimIds
      .map((aimId) => modelDeployments?.find((d) => d.id === aimId))
      .filter(
        (deployment): deployment is NonNullable<typeof deployment> =>
          deployment != null,
      );

    return (
      <div className="flex flex-col gap-1 pl-2">
        {selectedDeploymentsList.map((deployment) => (
          <div key={deployment.id} className="text-sm text-foreground">
            <div>• {deployment.title}</div>
            {deployment.subtitle !== '' && (
              <div className="text-xs text-muted pl-3">
                {deployment.subtitle}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <>
      <DrawerForm<CreateApiKeyFormData>
        key={`create-api-key-${projectId}-${isEditMode ? apiKey?.id : 'new'}`}
        isOpen={isOpen && !isKeyCreatedDrawerOpen}
        isActioning={isPending}
        onFormSuccess={(values) => {
          handleCreateSubmit(values);
        }}
        onCancel={onClose}
        title={isEditMode ? t('form.edit.title') : t('form.create.title')}
        confirmText={
          isEditMode
            ? t('form.edit.action.save')
            : t('form.create.action.create')
        }
        cancelText={
          isEditMode
            ? t('form.edit.action.cancel')
            : t('form.create.action.cancel')
        }
        defaultValues={defaultValues}
        validationSchema={formSchema}
        renderFields={(form) => {
          resetFormRef.current = form.reset;
          return (
            <div className="flex flex-col gap-4">
              {isEditMode &&
                editModeFields.map((field, index) => (
                  <div key={index} className="flex flex-col gap-1">
                    <label className="text-sm text-muted">{field.label}</label>
                    <p className="text-foreground">{field.value}</p>
                  </div>
                ))}
              {!isEditMode && (
                <>
                  <FormInput<CreateApiKeyFormData>
                    form={form}
                    name="displayName"
                    label={t('form.create.field.name.label')}
                    placeholder={t('form.create.field.name.placeholder')}
                    isRequired
                  />
                  <FormSelect<CreateApiKeyFormData>
                    form={form}
                    name="validityPeriod"
                    label={t('form.create.field.validityPeriod.label')}
                    placeholder={t(
                      'form.create.field.validityPeriod.placeholder',
                    )}
                    description={t(
                      'form.create.field.validityPeriod.description',
                    )}
                  >
                    {validityPeriodOptions.map((option) => (
                      <SelectItem key={option.value}>{option.label}</SelectItem>
                    ))}
                  </FormSelect>
                </>
              )}
              <div className="text-sm font-semibold text-foreground mt-2">
                {t('form.create.section.endpointAccess')}
              </div>
              <FormSelect<CreateApiKeyFormData>
                form={form}
                name="modelDeployments"
                label={t('form.create.field.modelDeployment.label')}
                placeholder={t('form.create.field.modelDeployment.placeholder')}
                description={t('form.create.field.modelDeployment.description')}
                selectionMode="multiple"
                isDisabled={isSelectLoading}
              >
                {modelDeployments.map((d) => (
                  <SelectItem
                    key={d.id}
                    textValue={`${d.title} ${d.subtitle}`}
                    description={d.subtitle || undefined}
                  >
                    {d.title}
                  </SelectItem>
                ))}
              </FormSelect>
              {isEditMode && (
                <>
                  <div className="flex flex-col gap-1.5">
                    <label className="block text-sm subpixel-antialiased text-muted">
                      {t('form.edit.section.linkedDeployments')}
                    </label>
                    {renderLinkedDeployments(
                      form.watch('modelDeployments') ?? [],
                    )}
                  </div>
                  <Alert
                    status="warning"
                    description={t(
                      'form.edit.warning.linkedDeploymentsWarning',
                    )}
                  />
                </>
              )}
            </div>
          );
        }}
      />

      <KeyCreatedDrawer
        isOpen={isKeyCreatedDrawerOpen}
        apiKey={createdApiKey}
        onClose={handleKeyCreatedDrawerClose}
      />
    </>
  );
};

export default CreateApiKey;
