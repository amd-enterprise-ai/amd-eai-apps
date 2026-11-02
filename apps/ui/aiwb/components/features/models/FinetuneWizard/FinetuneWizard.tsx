// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ManagedForm, Wizard } from '@amdenterpriseai/components';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { debounce } from 'lodash';
import { useTranslation } from 'next-i18next';
import { useCallback, useMemo, type ReactNode } from 'react';
import type { UseFormReturn } from 'react-hook-form';

import { SecretUseCase } from '@amdenterpriseai/types';

import { useProject } from '@/contexts/ProjectContext';
import { listAllAdapterArtifacts } from '@/lib/app/artifacts';
import { getAllDatasets } from '@/lib/app/datasets';
import { listProjectFineTunedModels } from '@/lib/app/models';
import { fetchAllPages } from '@/lib/app/pagination';
import { fetchProjectSecrets } from '@/lib/app/secrets';
import { listAllWorkloads } from '@/lib/app/workloads';
import { AIM_MODEL_NAME_LABEL } from '@/types/aims';
import type { components } from '@/types/api';
import type {
  FinetunableModel,
  Model,
  ModelFinetuneParams,
} from '@/types/models';
import type { SecretResponseData } from '@/types/secrets';

import {
  HyperparametersStepFields,
  hyperparametersStepSchema,
  HyperparametersStepSummary,
} from './steps/HyperparametersStep';
import {
  createModelStepSchema,
  ModelStepFields,
  ModelStepSummary,
} from './steps/ModelStep';
import {
  createTargetStepFieldsSchema,
  createTargetStepSchema,
  TargetStepFields,
  TargetStepSummary,
} from './steps/TargetStep';
import {
  createTrainingStepSchema,
  TrainingStepFields,
  TrainingStepSummary,
} from './steps/TrainingStep';
import {
  DEFAULT_FINETUNE_VALUES,
  finetuneBaseSchema,
  isBaseModelGated,
  MAX_FINETUNE_DATASETS,
  sanitizeModelNameLabel,
  type FineTuningType,
  type FinetuneFormValues,
} from './types';
import { useValidFineTuningType } from './useValidFineTuningType';

const roundToPrecision = (value: number | undefined, fractionDigits: number) =>
  value == null ? undefined : Number(value.toFixed(fractionDigits));

type FinetuneWizardProps = {
  model?: Model;
  finetunableModels: FinetunableModel[];
  onClose: () => void;
  onConfirmAction: (param: {
    id: string;
    params: ModelFinetuneParams;
  }) => Promise<void>;
};

const FineTuningTypeGuard = ({
  form,
  finetunableModels,
  model,
  children,
}: {
  form: UseFormReturn<FinetuneFormValues>;
  finetunableModels: FinetunableModel[];
  model?: Model;
  children: ReactNode;
}) => {
  useValidFineTuningType(form, finetunableModels, model);
  return children;
};

export const FinetuneWizard = ({
  model,
  finetunableModels,
  onClose,
  onConfirmAction,
}: FinetuneWizardProps) => {
  const { t } = useTranslation('models');
  const { activeProject } = useProject();
  const queryClient = useQueryClient();

  const { data: datasets = [] } = useQuery({
    queryKey: ['project', activeProject, 'datasets'],
    queryFn: () => getAllDatasets(activeProject!, { type: 'Fine-tuning' }),
    enabled: Boolean(activeProject),
  });
  const { data: projectSecrets } = useQuery<SecretResponseData[]>({
    queryKey: ['project', activeProject, 'secrets'],
    queryFn: async () => {
      const response = await fetchProjectSecrets(activeProject ?? '');
      return response.data;
    },
    enabled: Boolean(activeProject),
  });
  const hfTokens =
    projectSecrets?.filter(
      (secret) => secret.useCase === SecretUseCase.HUGGING_FACE,
    ) ?? [];

  const checkModelName = useCallback(
    async (name: string, fineTuningType: FineTuningType): Promise<boolean> => {
      try {
        const [isOutputNameAvailable, workloads] = await Promise.all([
          fineTuningType === 'lora'
            ? queryClient
                .fetchQuery({
                  queryKey: [
                    'project',
                    activeProject,
                    'artifacts',
                    'name-check',
                  ],
                  queryFn: () => listAllAdapterArtifacts(activeProject!),
                  staleTime: 0,
                })
                .then(
                  (adapters) =>
                    !adapters.some((adapter) => adapter.displayName === name),
                )
            : queryClient
                .fetchQuery({
                  queryKey: ['project', activeProject, 'models', 'name-check'],
                  queryFn: () =>
                    fetchAllPages<components['schemas']['AIMModelResource']>(
                      (page, pageSize) =>
                        listProjectFineTunedModels(activeProject!, {
                          page,
                          pageSize,
                        }),
                    ),
                  staleTime: 0,
                })
                .then((models) => {
                  const sanitizedName = sanitizeModelNameLabel(name);
                  return !models.some(
                    (candidate) =>
                      candidate.metadata?.labels?.[AIM_MODEL_NAME_LABEL] ===
                      sanitizedName,
                  );
                }),
          queryClient.fetchQuery({
            queryKey: ['project', activeProject, 'workloads', 'name-check'],
            queryFn: () =>
              listAllWorkloads(activeProject!, {
                workloadType: ['FINE_TUNING'],
                statusFilter: ['Pending', 'Starting', 'Running'],
              }),
            staleTime: 0,
          }),
        ]);
        return (
          isOutputNameAvailable &&
          !workloads.some((workload) => workload.displayName === name)
        );
      } catch (error) {
        // Fail open: a transient name-check outage should not hard-block the
        // wizard when the async resolver re-checks again at submit time.
        console.error('Error checking model name availability:', error);
        return true;
      }
    },
    [activeProject, queryClient],
  );
  const validateModelName = useMemo(() => {
    let resolvePrevious: ((isAvailable: boolean) => void) | undefined;
    const debouncedCheck = debounce(
      async (name: string, fineTuningType: FineTuningType) => {
        const resolve = resolvePrevious;
        resolvePrevious = undefined;
        resolve?.(await checkModelName(name, fineTuningType));
      },
      700,
    );
    return (name: string, fineTuningType: FineTuningType): Promise<boolean> =>
      new Promise((resolve) => {
        resolvePrevious?.(true);
        resolvePrevious = resolve;
        debouncedCheck(name, fineTuningType);
      });
  }, [checkModelName]);

  const modelStepSchema = useMemo(
    () =>
      createModelStepSchema({
        finetunableModels,
        model,
        requiredModelMessage: t('finetuneWizard.validation.baseModelRequired'),
        requiredTokenMessage: t(
          'huggingFaceTokenDrawer.notifications.noTokenSelected',
        ),
      }),
    [finetunableModels, model, t],
  );
  const trainingStepSchema = useMemo(
    () =>
      createTrainingStepSchema(
        t('finetuneWizard.validation.datasetRequired'),
        t('finetuneWizard.validation.datasetsMaxReached', {
          max: MAX_FINETUNE_DATASETS,
        }),
      ),
    [t],
  );
  const targetStepFieldsSchema = useMemo(
    () =>
      createTargetStepFieldsSchema({
        requiredMessage: t('finetuneWizard.validation.modelNameRequired'),
        tooLongMessage: t('finetuneWizard.validation.modelNameTooLong'),
        descriptionTooLongMessage: t(
          'finetuneWizard.validation.descriptionTooLong',
        ),
      }),
    [t],
  );
  const targetStepSchema = useMemo(
    () =>
      createTargetStepSchema({
        requiredMessage: t('finetuneWizard.validation.modelNameRequired'),
        tooLongMessage: t('finetuneWizard.validation.modelNameTooLong'),
        descriptionTooLongMessage: t(
          'finetuneWizard.validation.descriptionTooLong',
        ),
        duplicateModelMessage: t('finetuneWizard.validation.modelNameUnique'),
        duplicateLoraMessage: t('finetuneWizard.validation.loraNameUnique'),
        checkNameAvailable: validateModelName,
      }),
    [t, validateModelName],
  );
  const formSchema = useMemo(
    () =>
      finetuneBaseSchema
        .and(modelStepSchema)
        .and(trainingStepSchema)
        .and(targetStepSchema)
        .and(hyperparametersStepSchema),
    [modelStepSchema, targetStepSchema, trainingStepSchema],
  );

  const handleComplete = async (data: FinetuneFormValues) => {
    const params: ModelFinetuneParams = {
      displayName: data.displayName,
      datasetIds: data.datasetIds,
      ...(data.description ? { description: data.description } : {}),
      ...(data.customizeHyperparameters
        ? {
            batchSize: data.batchSize,
            epochs: data.epochs,
            learningRate: roundToPrecision(data.learningRate, 1),
          }
        : {}),
    };
    if (data.fineTuningType === 'lora') {
      params.output = 'adapter';
      if (
        [data.loraRank, data.loraAlpha, data.loraDropout].some(
          (value) => value != null,
        )
      ) {
        params.lora = {
          rank: data.loraRank,
          alpha: data.loraAlpha,
          dropout: roundToPrecision(data.loraDropout, 3),
        };
      }
    }
    if (
      !model?.sourceUri &&
      isBaseModelGated(finetunableModels, data.canonicalName, model)
    ) {
      params.hfTokenSecretName = data.hfTokenSecretName;
    }
    await onConfirmAction({
      id: model?.id ?? model?.resourceName ?? data.canonicalName,
      params,
    });
  };

  if (!activeProject) return null;

  return (
    <ManagedForm<FinetuneFormValues>
      validationSchema={formSchema}
      defaultValues={DEFAULT_FINETUNE_VALUES}
      onFormSuccess={handleComplete}
      renderFields={(form) => {
        const values = { ...DEFAULT_FINETUNE_VALUES, ...form.watch() };
        return (
          <FineTuningTypeGuard
            form={form}
            finetunableModels={finetunableModels}
            model={model}
          >
            <Wizard
              title={t('finetuneWizard.title')}
              description={t('finetuneWizard.subtitle')}
              completeLabel={t('finetuneWizard.actions.submit')}
              onClose={onClose}
              onComplete={async () => {
                let isValid = true;
                await form.handleSubmit(handleComplete, () => {
                  isValid = false;
                })();
                return isValid;
              }}
            >
              <Wizard.Step
                id="model"
                title={t('finetuneWizard.steps.model.label')}
                description={t('finetuneWizard.steps.model.subtitle')}
                canProceed={modelStepSchema.safeParse(values).success}
                renderSummary={() => (
                  <ModelStepSummary
                    data={values}
                    model={model}
                    finetunableModels={finetunableModels}
                    hfTokens={hfTokens}
                  />
                )}
              >
                <ModelStepFields
                  form={form}
                  model={model}
                  finetunableModels={finetunableModels}
                  namespace={activeProject}
                />
              </Wizard.Step>
              <Wizard.Step
                id="training"
                title={t('finetuneWizard.steps.training.label')}
                description={t('finetuneWizard.steps.training.subtitle')}
                canProceed={trainingStepSchema.safeParse(values).success}
                renderSummary={() => (
                  <TrainingStepSummary data={values} datasets={datasets} />
                )}
              >
                <TrainingStepFields
                  form={form}
                  datasets={datasets}
                  model={model}
                  finetunableModels={finetunableModels}
                />
              </Wizard.Step>
              <Wizard.Step
                id="target"
                title={t('finetuneWizard.steps.target.label')}
                description={t(
                  values.fineTuningType === 'lora'
                    ? 'finetuneWizard.steps.target.loraSubtitle'
                    : 'finetuneWizard.steps.target.subtitle',
                )}
                canProceed={
                  targetStepFieldsSchema.safeParse(values).success &&
                  !form.formState.errors.displayName &&
                  !form.formState.isValidating
                }
                renderSummary={() => <TargetStepSummary data={values} />}
              >
                <TargetStepFields
                  form={form}
                  uniqueCheckInProgress={form.formState.isValidating}
                />
              </Wizard.Step>
              <Wizard.Step
                id="hyperparameters"
                title={t('finetuneWizard.steps.hyperparameters.label')}
                description={t('finetuneWizard.steps.hyperparameters.subtitle')}
                isOptional
                canProceed={hyperparametersStepSchema.safeParse(values).success}
                renderSummary={() => (
                  <HyperparametersStepSummary
                    data={values}
                    model={model}
                    finetunableModels={finetunableModels}
                  />
                )}
              >
                <HyperparametersStepFields
                  form={form}
                  model={model}
                  finetunableModels={finetunableModels}
                />
              </Wizard.Step>
            </Wizard>
          </FineTuningTypeGuard>
        );
      }}
    />
  );
};

FinetuneWizard.displayName = 'FinetuneWizard';
