// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ManagedForm, Wizard } from '@amdenterpriseai/components';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'next-i18next';
import type { UseFormReturn } from 'react-hook-form';

import { useProject } from '@/contexts/ProjectContext';
import { listAllAdapterArtifacts } from '@/lib/app/artifacts';
import {
  createAimScalingPolicyConfig,
  getAimClusterProfiles,
} from '@/lib/app/aims';
import {
  canProfilesServeAdapter,
  isAdapterCapableProfileSpec,
} from '@/lib/app/aims/adapterCompatibility';
import {
  ADVANCED_PARAM_AUTOMATIC,
  filterProfilesByAdvancedParams,
} from '@/lib/app/aims/filterProfilesByAdvancedParams';
import { filterProfilesBySourceModel } from '@/lib/app/aims/filterProfilesBySourceModel';
import { deployInference } from '@/lib/app/inference';
import { fetchProjectSecrets } from '@/lib/app/secrets';
import {
  AIMClusterProfile,
  AIMDeployPayload,
  AggregatedAIM,
  ParsedAIM,
} from '@/types/aims';
import type { LoraAdapter } from '@/types/artifacts';
import { SecretResponseData } from '@/types/secrets';
import { toSecretNames } from '@/utils/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import {
  createModelStepDefaults,
  createModelStepSchema,
  ModelStepFields,
  ModelStepSummary,
} from './steps/ModelStep';
import {
  DEFAULT_MAX_LORA_RANK,
  MAX_LORA_RANK_OPTIONS,
  personalizationStepDefaults,
  personalizationStepSchema,
  PersonalizationStepFields,
  PersonalizationStepSummary,
} from './steps/PersonalizationStep';
import {
  performanceStepDefaults,
  performanceStepSchema,
  PerformanceStepFields,
  PerformanceStepSummary,
} from './steps/PerformanceStep';
import {
  scalingStepDefaults,
  scalingStepSchema,
  ScalingStepFields,
  ScalingStepSummary,
} from './steps/ScalingStep';
import {
  getMetricsStatusMap,
  PERFORMANCE_MODE_ADVANCED,
  type AdvancedProfileOptions,
  type DeployAIMFormValues,
} from './types';

type DeployAIMWizardProps = {
  onClose: () => void;
  onDeploying?: () => void;
  aggregatedAim: AggregatedAIM;
};

const unique = (values: Array<string | number | null | undefined>): string[] =>
  Array.from(
    new Set(values.flatMap((value) => (value == null ? [] : [String(value)]))),
  );

const PersonalizationStateReset = ({
  form,
  supportsAdapters,
}: {
  form: UseFormReturn<DeployAIMFormValues>;
  supportsAdapters: boolean;
}) => {
  useEffect(() => {
    if (supportsAdapters) return;
    form.setValue('personalizationEnabled', false);
    form.setValue('adapters', []);
    form.setValue(
      'maxLoraRank',
      personalizationStepDefaults.maxLoraRank ?? String(DEFAULT_MAX_LORA_RANK),
    );
  }, [form, supportsAdapters]);

  return null;
};

/**
 * Advanced parameter choices survive a version switch; the profiles backing
 * them do not.
 *
 * Every advanced control is offered from the selected version's own profiles,
 * so switching version can leave a pin behind that the new version does not
 * publish — and submit ships it verbatim, which is the exact failure the
 * per-version narrowing exists to prevent. Before the narrowing the retained
 * value still matched something in the pooled list, because both versions
 * share an aimId; now it does not.
 *
 * Each field is checked on its own and only dropped back to automatic when the
 * value is no longer among what the version offers, rather than clearing every
 * choice on any switch: two versions of one model usually publish the same
 * accelerator and precision, and a user who picked MI300X means it whichever
 * version is selected. Same shape as the Personalization step's adapter
 * re-validation, which filters the selection down to what is still offered
 * instead of emptying it.
 */
const AdvancedSelectionRevalidation = ({
  form,
  advancedProfileOptions,
  profilesLoading,
}: {
  form: UseFormReturn<DeployAIMFormValues>;
  advancedProfileOptions: AdvancedProfileOptions;
  profilesLoading: boolean;
}) => {
  useEffect(() => {
    // An in-flight fetch reports no profiles at all, which would read as every
    // choice having been withdrawn and clear the form on a refetch.
    if (profilesLoading) return;
    const offered: Array<[keyof DeployAIMFormValues, string[]]> = [
      [
        'profileName',
        advancedProfileOptions.profiles.map((profile) => profile.metadata.name),
      ],
      ['optimizationClass', advancedProfileOptions.optimizationClasses],
      ['gpuModel', advancedProfileOptions.gpuModels],
      ['precision', advancedProfileOptions.precisions],
      ['gpuCount', advancedProfileOptions.gpuCounts],
    ];
    for (const [field, options] of offered) {
      const value = form.getValues(field);
      // Automatic pins nothing, so there is nothing that can go stale.
      if (!value || value === ADVANCED_PARAM_AUTOMATIC) continue;
      if (!options.includes(String(value))) {
        form.setValue(field, ADVANCED_PARAM_AUTOMATIC, {
          shouldValidate: true,
        });
      }
    }
  }, [form, profilesLoading, advancedProfileOptions]);

  return null;
};

/**
 * The precision the submitted deployment will actually be pinned to.
 *
 * Leaving the control on automatic does not leave the choice open: the model's
 * preferred precision is substituted on submit whenever the cluster publishes
 * one, so anything derived from the raw form value believes every precision is
 * still in play while the payload already rules all but one of them out. The
 * offer and the payload both read this one resolution so they cannot disagree.
 *
 * Outside advanced mode the precision control is not in play, so a value left
 * behind on the form is not a choice the user made and only the preferred
 * substitution applies.
 *
 * Which precisions count as published depends on personalization: enabling it
 * restricts the Performance step to adapter-capable profiles, so substituting a
 * preferred precision only a non-adapter profile publishes would pin a choice
 * the step never offered — leaving no adapter-capable candidate and rejecting
 * the user's adapters for a precision they could not have picked or changed.
 */
export const resolveEffectivePrecision = (
  data: Pick<
    DeployAIMFormValues,
    'performanceMode' | 'precision' | 'personalizationEnabled'
  >,
  preferredPrecision: string | undefined,
  availablePrecisions: { all: string[]; adapterCapable: string[] },
): string | undefined => {
  const chosen =
    data.performanceMode === PERFORMANCE_MODE_ADVANCED
      ? data.precision
      : undefined;
  if (chosen && chosen !== ADVANCED_PARAM_AUTOMATIC) return chosen;
  const published = data.personalizationEnabled
    ? availablePrecisions.adapterCapable
    : availablePrecisions.all;
  return preferredPrecision && published.includes(preferredPrecision)
    ? preferredPrecision
    : undefined;
};

/**
 * The adapter-capable profiles still in the running for the user's current
 * performance choices.
 *
 * Performance narrows the candidate set after Personalization has offered its
 * adapters, so offering against every adapter-capable profile keeps an adapter
 * on the list that only a sibling variant can load — and submit then resolves
 * to the sibling the user ruled out. The narrowing itself is reused from the
 * Performance step's own helper so the two cannot drift apart.
 *
 * `effectivePrecision` is resolved by the caller rather than read off `data`,
 * because the precision the deploy is pinned to is not always the one on the
 * form — see `resolveEffectivePrecision`.
 */
export const selectCandidateAdapterProfiles = (
  adapterCapableProfiles: AIMClusterProfile[],
  data: Pick<
    DeployAIMFormValues,
    | 'performanceMode'
    | 'profileName'
    | 'optimizationClass'
    | 'gpuModel'
    | 'gpuCount'
  >,
  effectivePrecision?: string,
): AIMClusterProfile[] => {
  const isAdvancedMode = data.performanceMode === PERFORMANCE_MODE_ADVANCED;
  return filterProfilesByAdvancedParams(adapterCapableProfiles, {
    selectedMetric: isAdvancedMode ? undefined : data.performanceMode,
    profileName: isAdvancedMode ? data.profileName : undefined,
    optimizationClass: isAdvancedMode ? data.optimizationClass : undefined,
    gpuModel: isAdvancedMode ? data.gpuModel : undefined,
    precision: effectivePrecision,
    gpuCount: isAdvancedMode ? data.gpuCount : undefined,
  });
};

/**
 * Servable adapters, plus any still-selected adapter those profiles can no
 * longer load. Dropping that selection here is how a deploy loses an adapter
 * nobody noticed going away; the row stays so it can be cleared.
 *
 * A selection is retained whether the lineage stopped matching or the weights
 * have not arrived, because both leave the adapter undeployable and the row is
 * the only place the user can act. The two are told apart at render time by
 * `readiness`, so each reads as the problem it actually is.
 */
const adaptersForPicker = (
  adapters: LoraAdapter[],
  candidateProfiles: AIMClusterProfile[],
  selectedNames: string[],
): LoraAdapter[] => {
  const profileSpecs = candidateProfiles.map((profile) => profile.spec);
  const selected = new Set(selectedNames);
  return adapters.flatMap((adapter) => {
    const servable = canProfilesServeAdapter({ adapter, profileSpecs });
    const ready = adapter.readiness === 'Ready';
    const offered = ready && servable;
    const retained = !offered && selected.has(adapter.name);
    return offered || retained ? [{ ...adapter, servable }] : [];
  });
};

export const hasIncompatiblePersonalizationProfile = (
  supportsAdapters: boolean,
  personalizationEnabled: boolean | undefined,
  profileName: string | undefined,
  profiles: AIMClusterProfile[],
) => {
  if (!supportsAdapters || !personalizationEnabled || !profileName) {
    return false;
  }
  return !isAdapterCapableProfileSpec(
    profiles.find((profile) => profile.metadata.name === profileName)?.spec,
  );
};

export const DeployAIMWizard = ({
  onClose,
  onDeploying,
  aggregatedAim,
}: DeployAIMWizardProps) => {
  const { t } = useTranslation('models');
  const { toast } = useSystemToast();
  const { activeProject: namespace } = useProject();
  const queryClient = useQueryClient();

  const defaultAim =
    aggregatedAim.latestAim ??
    aggregatedAim.parsedAIMs.find((a) => a.status === 'Ready') ??
    aggregatedAim.parsedAIMs[0]!;
  const [selectedAim, setSelectedAim] = useState<ParsedAIM>(defaultAim);

  const { data: projectSecrets } = useQuery<SecretResponseData[]>({
    queryKey: ['project', namespace, 'secrets'],
    queryFn: async () => {
      const response = await fetchProjectSecrets(namespace ?? '');
      return response.data;
    },
    enabled: !!namespace,
  });

  const {
    data: serviceProfiles,
    isLoading: profilesLoading,
    isError: profilesError,
    error: profilesErrorObj,
  } = useQuery<AIMClusterProfile[]>({
    // The listing endpoint filters by aimId only, so one fetch covers every
    // version of the model; the per-version narrowing below is a pure
    // derivation of that response and needs no cache entry of its own.
    queryKey: ['aim-profiles', selectedAim.aimId],
    queryFn: () => getAimClusterProfiles(selectedAim.aimId ?? ''),
    enabled: !!namespace && !!selectedAim.aimId,
    retry: (failureCount, error) => {
      if (error instanceof APIRequestError && error.statusCode === 404) {
        return false;
      }
      return failureCount < 3;
    },
  });

  // Every serving decision in this wizard — whether Personalization is
  // offered, which profiles the advanced parameters expose, which profile the
  // engine may resolve — has to be judged against the version the user picked,
  // not against the pooled profiles of every version sharing the architecture.
  const readyProfiles = useMemo(
    () =>
      filterProfilesBySourceModel(
        serviceProfiles ?? [],
        selectedAim.model,
      ).filter((profile) => profile.status?.status === 'Ready'),
    [serviceProfiles, selectedAim.model],
  );
  const adapterCapableProfiles = readyProfiles.filter((profile) =>
    isAdapterCapableProfileSpec(profile.spec),
  );
  const supportsAdapters = adapterCapableProfiles.length > 0;
  const { data: adapters = [], isLoading: adaptersLoading } = useQuery<
    LoraAdapter[]
  >({
    queryKey: ['project', namespace, 'artifacts'],
    queryFn: () => listAllAdapterArtifacts(namespace ?? ''),
    enabled: supportsAdapters && !!namespace,
  });
  const is404 =
    profilesErrorObj instanceof APIRequestError &&
    profilesErrorObj.statusCode === 404;
  const metricsStatusMap = getMetricsStatusMap(readyProfiles);
  const isAtleastOneOptimized =
    Object.keys(metricsStatusMap).length === 0 ||
    Object.values(metricsStatusMap).some((v) => v);

  const advancedProfileOptions = useMemo(() => {
    return {
      optimizationClasses: unique(
        readyProfiles.map((p) => p.spec?.type),
      ).sort(),
      gpuModels: unique(
        readyProfiles.map((p) => p.spec?.acceleratorModel),
      ).sort(),
      precisions: unique(readyProfiles.map((p) => p.spec?.precision)).sort(),
      gpuCounts: unique(
        readyProfiles.map((p) => p.spec?.acceleratorCount),
      ).sort((a, b) => Number(a) - Number(b)),
      profiles: readyProfiles,
    };
  }, [readyProfiles]);
  const adapterAdvancedProfileOptions = useMemo(() => {
    return {
      optimizationClasses: unique(
        adapterCapableProfiles.map((p) => p.spec?.type),
      ).sort(),
      gpuModels: unique(
        adapterCapableProfiles.map((p) => p.spec?.acceleratorModel),
      ).sort(),
      precisions: unique(
        adapterCapableProfiles.map((p) => p.spec?.precision),
      ).sort(),
      gpuCounts: unique(
        adapterCapableProfiles.map((p) => p.spec?.acceleratorCount),
      ).sort((a, b) => Number(a) - Number(b)),
      profiles: adapterCapableProfiles,
    };
  }, [adapterCapableProfiles]);

  // Keyed by version rather than by architecture: two versions of one model
  // share an aimId, and one of them having profiles says nothing about the
  // other, so suppressing the warning across a version switch would hide it.
  const toastedVersion = useRef<string | null>(null);

  useEffect(() => {
    if (
      !selectedAim.aimId ||
      profilesLoading ||
      toastedVersion.current === selectedAim.model
    ) {
      return;
    }

    const isSuccessWithNoProfiles =
      !profilesError && readyProfiles.length === 0;

    if (is404 || isSuccessWithNoProfiles) {
      toast.error(t('deployAIM.notifications.noProfilesDescription'));
      toastedVersion.current = selectedAim.model;
    }
  }, [
    selectedAim.aimId,
    selectedAim.model,
    profilesLoading,
    profilesError,
    is404,
    readyProfiles.length,
    toast,
    t,
  ]);

  const imagePullSecrets =
    projectSecrets?.filter(
      (ps) => ps.useCase === SecretUseCase.IMAGE_PULL_SECRET,
    ) ?? [];
  const hfTokens =
    projectSecrets?.filter((ps) => ps.useCase === SecretUseCase.HUGGING_FACE) ??
    [];

  const hasNoReadyProfiles =
    !!selectedAim.aimId &&
    !profilesLoading &&
    !profilesError &&
    readyProfiles.length === 0;
  const profilesReady =
    !profilesLoading && !is404 && (!selectedAim.aimId || !hasNoReadyProfiles);

  const modelStepSchema = useMemo(
    () => createModelStepSchema(selectedAim.isHfTokenRequired, t),
    [selectedAim.isHfTokenRequired, t],
  );

  const handleComplete = useCallback(
    async (data: DeployAIMFormValues) => {
      try {
        // Every enabled personalization request sends adapterMode: 'dynamic'
        // below, regardless of whether any adapter is selected yet, so the
        // profile must support adapters whenever personalization is enabled
        // — not only once an adapter has been picked. Only an explicitly
        // pinned profile is validated here; leaving profile selection on
        // "Automatic" defers the choice to the engine, and the advanced-profile
        // options are already restricted to adapter-capable profiles whenever
        // personalization is enabled, so automatic resolution is safe.
        const explicitProfileName =
          data.profileName && data.profileName !== ADVANCED_PARAM_AUTOMATIC
            ? data.profileName
            : undefined;
        if (
          hasIncompatiblePersonalizationProfile(
            supportsAdapters,
            data.personalizationEnabled,
            explicitProfileName,
            readyProfiles,
          )
        ) {
          toast.error(t('deployAIM.personalization.validation.profile'));
          return;
        }
        // The Performance step can narrow the candidates after the adapters
        // were picked, and the profile the deploy resolves to comes from the
        // narrowed set — so the selection is checked against that set here
        // rather than against every adapter-capable profile. Without this the
        // service is accepted and only fails once it tries to load the weights.
        const effectivePrecision = resolveEffectivePrecision(
          data,
          aggregatedAim.aggregated.preferredPrecision,
          {
            all: advancedProfileOptions.precisions,
            adapterCapable: adapterAdvancedProfileOptions.precisions,
          },
        );
        if (supportsAdapters && data.personalizationEnabled) {
          const profileSpecs = selectCandidateAdapterProfiles(
            adapterCapableProfiles,
            data,
            effectivePrecision,
          ).map((profile) => profile.spec);
          const byName = new Map(
            adapters.map((adapter) => [adapter.name, adapter]),
          );
          const unservable: string[] = [];
          const notReady: string[] = [];
          for (const name of data.adapters ?? []) {
            const adapter = byName.get(name);
            if (!adapter) continue;
            if (!canProfilesServeAdapter({ adapter, profileSpecs })) {
              unservable.push(name);
            } else if (adapter.readiness !== 'Ready') {
              notReady.push(name);
            }
          }
          if (unservable.length > 0) {
            toast.error(
              t('deployAIM.personalization.validation.adapters', {
                names: unservable.join(', '),
              }),
            );
            return;
          }
          if (notReady.length > 0) {
            toast.error(
              t('deployAIM.personalization.validation.notReadyAdapters', {
                names: notReady.join(', '),
              }),
            );
            return;
          }
        }
        const payload: AIMDeployPayload = {
          model: data.model,
          displayName: data.displayName || undefined,
          replicas: 1,
        };
        if (data.hfTokenSecretName) payload.hfToken = data.hfTokenSecretName;
        const imagePullSecretNames = toSecretNames(data.imagePullSecrets);
        if (imagePullSecretNames.length) {
          payload.imagePullSecrets = imagePullSecretNames;
        }
        if (data.performanceMode !== PERFORMANCE_MODE_ADVANCED) {
          payload.metric = data.performanceMode;
        }
        const isExplicit = (value: string | undefined) =>
          !!value && value !== ADVANCED_PARAM_AUTOMATIC;
        if (effectivePrecision) payload.precision = effectivePrecision;
        if (isExplicit(data.gpuModel)) payload.gpuModel = data.gpuModel;
        if (isExplicit(data.gpuCount)) {
          const count = Number(data.gpuCount);
          if (!Number.isNaN(count) && count >= 1) payload.gpuCount = count;
        }
        if (isExplicit(data.profileName))
          payload.profileName = data.profileName;
        if (data.autoscalingEnabled) {
          payload.minReplicas = data.minReplicas;
          payload.maxReplicas = data.maxReplicas;
          payload.autoScaling = createAimScalingPolicyConfig(data);
        }
        if (supportsAdapters && data.personalizationEnabled) {
          payload.adapterMode = 'dynamic';
          if (data.adapters?.length) payload.adapters = data.adapters;
          if (data.maxLoraRank) {
            const maxLoraRank = MAX_LORA_RANK_OPTIONS.find(
              (rank) => rank === Number(data.maxLoraRank),
            );
            if (maxLoraRank) payload.maxLoraRank = maxLoraRank;
          }
        }
        await deployInference(namespace ?? '', payload);
        queryClient.invalidateQueries({ queryKey: ['inferenceModel'] });
        onClose();
        toast.success(t('deployAIM.notifications.success'));
        onDeploying?.();
      } catch (error) {
        toast.error(
          t('deployAIM.notifications.error', {
            message: (error as APIRequestError).message || 'Unknown error',
          }),
          error as APIRequestError,
        );
      }
    },
    [
      namespace,
      adapters,
      adapterCapableProfiles,
      adapterAdvancedProfileOptions.precisions,
      advancedProfileOptions.precisions,
      aggregatedAim.aggregated.preferredPrecision,
      readyProfiles,
      supportsAdapters,
      onClose,
      onDeploying,
      queryClient,
      t,
      toast,
    ],
  );

  const formSchema = useMemo(
    () =>
      modelStepSchema
        .and(personalizationStepSchema)
        .and(performanceStepSchema)
        .and(scalingStepSchema),
    [modelStepSchema],
  );
  const defaultValues = {
    ...createModelStepDefaults(defaultAim.model),
    ...personalizationStepDefaults,
    ...performanceStepDefaults,
    ...scalingStepDefaults,
  } as DeployAIMFormValues;

  if (!namespace) {
    return null;
  }

  return (
    <ManagedForm<DeployAIMFormValues>
      validationSchema={formSchema}
      defaultValues={defaultValues}
      onFormSuccess={handleComplete}
      renderFields={(form) => {
        const values = { ...defaultValues, ...form.watch() };
        // Enabling personalization always sends adapterMode: 'dynamic' on
        // submit (see handleComplete), regardless of whether an adapter has
        // been selected yet, so the Performance step must restrict profile
        // choices to adapter-capable ones as soon as the toggle is on —
        // otherwise a user can pin a non-adapter profile before picking an
        // adapter and only discover the conflict from a rejected deploy.
        const restrictProfilesToAdapterCapable = values.personalizationEnabled;
        // Recomputed from the live form rather than once per profile fetch, so
        // narrowing the performance choices takes the adapters only a ruled-out
        // sibling profile can load back off the list.
        const pickerAdapters = adaptersForPicker(
          adapters,
          selectCandidateAdapterProfiles(
            adapterCapableProfiles,
            values,
            resolveEffectivePrecision(
              values,
              aggregatedAim.aggregated.preferredPrecision,
              {
                all: advancedProfileOptions.precisions,
                adapterCapable: adapterAdvancedProfileOptions.precisions,
              },
            ),
          ),
          values.adapters ?? [],
        );
        return (
          <>
            <PersonalizationStateReset
              form={form}
              supportsAdapters={supportsAdapters}
            />
            <AdvancedSelectionRevalidation
              form={form}
              advancedProfileOptions={advancedProfileOptions}
              profilesLoading={profilesLoading}
            />
            <Wizard
              title={t('deployAIM.title')}
              description={t('deployAIM.subtitle')}
              onClose={onClose}
              onComplete={() => form.handleSubmit(handleComplete)()}
            >
              <Wizard.Step
                id="model"
                title={t('deployAIM.steps.model.label')}
                description={t('deployAIM.steps.model.subtitle')}
                canProceed={
                  profilesReady && modelStepSchema.safeParse(values).success
                }
                renderSummary={() => (
                  <ModelStepSummary
                    data={values}
                    selectedAim={selectedAim}
                    hfTokens={hfTokens}
                    imagePullSecrets={imagePullSecrets}
                  />
                )}
              >
                <ModelStepFields
                  form={form}
                  aggregatedAim={aggregatedAim}
                  selectedAim={selectedAim}
                  namespace={namespace}
                  imagePullSecrets={imagePullSecrets}
                  onAimChange={setSelectedAim}
                />
              </Wizard.Step>
              {supportsAdapters ? (
                <Wizard.Step
                  id="personalization"
                  title={t('deployAIM.steps.personalization.label')}
                  description={t('deployAIM.steps.personalization.subtitle')}
                  isOptional
                  canProceed={
                    personalizationStepSchema.safeParse(values).success
                  }
                  renderSummary={() => (
                    <PersonalizationStepSummary
                      data={values}
                      adapters={pickerAdapters}
                    />
                  )}
                >
                  <PersonalizationStepFields
                    form={form}
                    adapters={pickerAdapters}
                    isLoading={adaptersLoading}
                  />
                </Wizard.Step>
              ) : null}
              <Wizard.Step
                id="performance"
                title={t('deployAIM.steps.performance.label')}
                description={t('deployAIM.steps.performance.subtitle')}
                canProceed={performanceStepSchema.safeParse(values).success}
                renderSummary={() => (
                  <PerformanceStepSummary
                    data={values}
                    readyProfiles={readyProfiles}
                  />
                )}
              >
                <PerformanceStepFields
                  form={form}
                  metricsStatusMap={metricsStatusMap}
                  isAtleastOneOptimized={isAtleastOneOptimized}
                  profilesLoading={profilesLoading}
                  advancedProfileOptions={
                    restrictProfilesToAdapterCapable
                      ? adapterAdvancedProfileOptions
                      : advancedProfileOptions
                  }
                />
              </Wizard.Step>
              <Wizard.Step
                id="scaling"
                title={t('deployAIM.steps.scaling.label')}
                description={t('deployAIM.steps.scaling.subtitle')}
                isOptional
                canProceed={scalingStepSchema.safeParse(values).success}
                renderSummary={() => <ScalingStepSummary data={values} />}
              >
                <ScalingStepFields form={form} />
              </Wizard.Step>
            </Wizard>
          </>
        );
      }}
    />
  );
};
