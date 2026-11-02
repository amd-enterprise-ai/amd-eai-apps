// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconAlertTriangle, IconRocket } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { z } from 'zod';

import { useTranslation } from 'next-i18next';

import {
  Alert,
  Divider,
  DrawerForm,
  FormInput,
  FormSelect,
  FormTextarea,
  resetFormValues,
  SelectItem,
} from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import {
  useRuntimeProfileCatalog,
  type RuntimeProfileCatalogState,
} from '@/hooks/useRuntimeProfileCatalog';
import { getMetricTranslationKey } from '@/lib/app/aims';
import type { BaseImageRuntimeProfileOptions } from '@/lib/app/custom-models';
import {
  createCustomProfile,
  CustomProfileConflictError,
  listCustomProfiles,
  updateCustomProfile,
  type CustomProfileResponse,
} from '@/lib/app/custom-profiles';
import {
  deviceIdToAcceleratorModel,
  intersectCombinations,
  reachableRuntimeAxes,
  RUNTIME_PROFILE_METRIC_KEYS,
  type RuntimeSelectionBlock,
} from '@/lib/app/runtimeProfileCatalog';
import {
  customProfileToFormValues,
  formValuesToCustomProfileCreate,
  formValuesToCustomProfilePatch,
  isRuntimeYamlMappingValid,
  type CustomProfileFormInput,
} from '@/lib/app/runtimeProfileMappers';

import {
  RuntimeProfileFields,
  type RuntimeProfileSelectionState,
} from '../runtime-profile';

/** The reserved display name of the model's synthetic onboarding profile. */
const RESERVED_PROFILE_NAME = 'default';

const DEFAULT_VALUES: CustomProfileFormInput = {
  displayName: '',
  containerImage: '',
  containerVersion: '',
  acceleratorType: 'gpu',
  accelerator: '',
  acceleratorCount: 1,
  modelPrecision: 'bf16',
  metric: RUNTIME_PROFILE_METRIC_KEYS[0],
  engineArgsYaml: '',
  envVarsYaml: '',
};

// `toLowerCase` rather than the locale-aware variant: this has to agree with the
// server's own case-insensitive comparison, and a locale where the mapping
// differs (Turkish dotted/dotless i) would otherwise accept a name the server
// then rejects as taken.
const normalizeName = (value: string): string => value.trim().toLowerCase();

/** A save, and whether the user asked to deploy the profile once it is saved. */
type SaveRequest = {
  values: CustomProfileFormInput;
  deploy: boolean;
};

/** A metric option, keyed by the value the form and the create body carry. */
type MetricOption = {
  key: CustomProfileFormInput['metric'];
  label: string;
};

interface FieldsProps {
  form: UseFormReturn<CustomProfileFormInput>;
  catalog: RuntimeProfileCatalogState;
  /** Absent when creating; drives the one-shot prefill when editing. */
  profile: CustomProfileResponse | undefined;
  /**
   * The model's Default profile, when creating: the narrowing axes start from its
   * tuple. Absent when editing, or until the profile list arrives.
   */
  axisSeed: CustomProfileResponse | undefined;
  /** The metrics this project's base template emits, in offer order. */
  metricOptions: MetricOption[];
  /** Labels a metric key for display; used to build the cascaded metric options. */
  metricLabelFor: (metric: string) => string;
  /** Lifts the runtime-selection block up so the drawer can gate the save. */
  onRuntimeBlockChange: (block: RuntimeSelectionBlock) => void;
  isDisabled: boolean;
}

/**
 * The drawer body. Split out as a component so the edit prefill can run as an
 * effect — `DrawerForm` hands the form instance to a render callback, which
 * cannot hold hooks of its own.
 */
const CustomProfileFormFields = ({
  form,
  catalog,
  profile,
  axisSeed,
  metricOptions,
  metricLabelFor,
  onRuntimeBlockChange,
  isDisabled,
}: FieldsProps) => {
  const { t } = useTranslation('models', {
    keyPrefix: 'customModels.profiles.drawer',
  });
  const [prefilled, setPrefilled] = useState(false);
  // Lifted from RuntimeProfileFields so the metric selector below narrows on the
  // same emitted combinations as the accelerator/count/precision selectors it owns,
  // and so the drawer can block the save when no valid combination is selectable.
  const [baseImageOptions, setBaseImageOptions] =
    useState<BaseImageRuntimeProfileOptions | null>(null);
  const [runtimeBlock, setRuntimeBlock] = useState<RuntimeSelectionBlock>(null);
  const handleSelectionState = useCallback(
    (state: RuntimeProfileSelectionState) => {
      setBaseImageOptions(state.baseImageOptions);
      setRuntimeBlock(state.block);
      onRuntimeBlockChange(state.block);
    },
    [onRuntimeBlockChange],
  );
  const catalogDisabled = isDisabled || catalog.isLoading || catalog.isError;

  // Prefill once the catalog has settled, so the reverse mapper can resolve the
  // saved image ref to a family/tag and the accelerator model to a device id.
  // Waiting also stops the catalog-seeded defaults in the child fields from
  // overwriting the saved selection. A failed catalog is not settled: mapping
  // against empty option lists would drop the saved selections, and because the
  // prefill runs once, a later retry could not put them back.
  useEffect(() => {
    if (!profile || prefilled || catalog.isLoading || catalog.isError) {
      return;
    }
    resetFormValues(
      form,
      customProfileToFormValues(
        profile,
        catalog.imageFamilies,
        catalog.accelerators,
      ),
    );
    setPrefilled(true);
  }, [
    profile,
    prefilled,
    catalog.isLoading,
    catalog.isError,
    catalog.imageFamilies,
    catalog.accelerators,
    form,
  ]);

  // Create takes its narrowing axes from the Default profile once the catalog has
  // settled, so the reverse mapper can resolve the accelerator model to a device
  // id. Only those axes are taken: the image keeps the catalog's own seeding, and
  // the engine arguments stay empty so a new profile does not silently inherit
  // overrides the user never asked for.
  const [seeded, setSeeded] = useState(false);
  useEffect(() => {
    if (
      profile ||
      seeded ||
      !axisSeed ||
      catalog.isLoading ||
      catalog.isError
    ) {
      return;
    }
    const seed = customProfileToFormValues(
      axisSeed,
      catalog.imageFamilies,
      catalog.accelerators,
    );
    // shouldDirty:false so the starting tuple does not read as a user edit.
    form.setValue('accelerator', seed.accelerator, { shouldDirty: false });
    form.setValue('acceleratorCount', seed.acceleratorCount, {
      shouldDirty: false,
    });
    form.setValue('modelPrecision', seed.modelPrecision, {
      shouldDirty: false,
    });
    form.setValue('metric', seed.metric, { shouldDirty: false });
    setSeeded(true);
  }, [
    profile,
    seeded,
    axisSeed,
    catalog.isLoading,
    catalog.isError,
    catalog.imageFamilies,
    catalog.accelerators,
    form,
  ]);

  // The metric selector cascades on the same emitted combinations as the
  // sibling axes: only metrics the base pairs with the current
  // accelerator/count/precision are offered, so a save cannot fail the API's
  // narrowing on a metric that combination never emits. Falls back to the full
  // labelled set when no combination matrix is loaded yet.
  const selectedDeviceId = form.watch('accelerator');
  const selectedCount = form.watch('acceleratorCount');
  const selectedPrecision = form.watch('modelPrecision');
  const narrowedMetricOptions = useMemo<MetricOption[]>(() => {
    // No valid combination is selectable (loading / failed / ambiguous-only):
    // offer no metric, matching the sibling selectors the drawer blocks the save.
    if (runtimeBlock !== null) {
      return [];
    }
    // Match the sibling selectors: the namespace matrix is authoritative and the
    // loaded image refines it, so a metric offered here is both resolvable and
    // image-discoverable.
    const namespaceCombinations = catalog.runtimeOptions?.combinations ?? [];
    const imageCombinations = baseImageOptions?.combinations;
    const combinations =
      imageCombinations !== undefined && namespaceCombinations.length > 0
        ? intersectCombinations(namespaceCombinations, imageCombinations)
        : namespaceCombinations.length > 0
          ? namespaceCombinations
          : (imageCombinations ?? []);
    // No matrix loaded yet: fall back to the static labelled superset.
    if (combinations.length === 0) {
      return metricOptions;
    }
    // Build straight from the reachable metrics rather than filtering the
    // labelled superset: a metric the base emits but this build does not yet
    // label must still be offered (labelled by its raw value), and — critically —
    // a metric absent from every reachable tuple must never be offered, or the
    // save would hit the same 400 this cascade exists to prevent.
    const reachableMetrics = reachableRuntimeAxes(combinations, {
      acceleratorModel:
        deviceIdToAcceleratorModel(
          String(selectedDeviceId ?? ''),
          catalog.accelerators,
        ) || undefined,
      acceleratorCount:
        selectedCount == null || String(selectedCount) === ''
          ? undefined
          : Number(selectedCount),
      precision: selectedPrecision ? String(selectedPrecision) : undefined,
    }).metrics;
    return reachableMetrics.map((metric) => ({
      key: metric as MetricOption['key'],
      label: metricLabelFor(metric),
    }));
  }, [
    runtimeBlock,
    baseImageOptions,
    catalog.runtimeOptions?.combinations,
    catalog.accelerators,
    metricOptions,
    metricLabelFor,
    selectedDeviceId,
    selectedCount,
    selectedPrecision,
  ]);

  // In edit mode the saved metric is preserved until the user changes an axis:
  // the base-image lookup can settle after the prefill, so snapping on the
  // interim (namespace/static) options would clobber a valid saved metric and a
  // name-only save would then send the changed value.
  const { dirtyFields } = form.formState;
  const axisEdited = Boolean(
    dirtyFields.accelerator ||
      dirtyFields.acceleratorCount ||
      dirtyFields.modelPrecision,
  );

  // Keep a reachable metric selected: the static/seeded metric has to give way
  // once the matrix narrows it out, or the first save fails the API's narrowing
  // on an axis the user never touched.
  const selectedMetric = form.watch('metric');
  useEffect(() => {
    if (profile && !axisEdited) {
      return;
    }
    if (narrowedMetricOptions.length === 0) {
      return;
    }
    if (narrowedMetricOptions.some((option) => option.key === selectedMetric)) {
      return;
    }
    form.setValue('metric', narrowedMetricOptions[0].key, {
      shouldDirty: false,
    });
  }, [profile, axisEdited, narrowedMetricOptions, selectedMetric, form]);

  const fieldLabels = useMemo(
    () => ({
      containerImage: {
        label: t('fields.containerImage.label'),
        placeholder: t('fields.containerImage.placeholder'),
      },
      containerVersion: {
        label: t('fields.containerVersion.label'),
        placeholder: t('fields.containerVersion.placeholder'),
      },
      acceleratorType: {
        label: t('fields.acceleratorType.label'),
        placeholder: t('fields.acceleratorType.placeholder'),
      },
      accelerator: {
        label: t('fields.accelerator.label'),
        placeholder: t('fields.accelerator.placeholder'),
      },
      acceleratorCount: { label: t('fields.acceleratorCount.label') },
      modelPrecision: {
        label: t('fields.modelPrecision.label'),
        placeholder: t('fields.modelPrecision.placeholder'),
      },
      catalogLoading: t('catalog.loading'),
      catalogError: t('catalog.error'),
      catalogRetry: t('catalog.retry'),
      baseImageOptionsWarning: t('catalog.baseImageOptionsWarning'),
      noValidCombinationsWarning: t('catalog.noValidCombinations'),
      emptyAccelerators: t('catalog.emptyAccelerators'),
    }),
    [t],
  );

  return (
    <div className="flex flex-col gap-4 mt-4">
      <FormInput<CustomProfileFormInput>
        form={form}
        name="displayName"
        label={t('fields.displayName.label')}
        placeholder={t('fields.displayName.placeholder')}
        isRequired
        isDisabled={isDisabled}
        data-testid="custom-profile-display-name"
      />

      <Divider />

      <RuntimeProfileFields<CustomProfileFormInput>
        form={form}
        catalog={catalog}
        labels={fieldLabels}
        isDisabled={isDisabled}
        onSelectionStateChange={handleSelectionState}
      />

      <FormSelect<CustomProfileFormInput>
        form={form}
        name="metric"
        label={t('fields.metric.label')}
        placeholder={t('fields.metric.placeholder')}
        isRequired
        isDisabled={catalogDisabled}
        data-testid="custom-profile-metric"
      >
        <>
          {narrowedMetricOptions.map((option) => (
            <SelectItem key={option.key}>{option.label}</SelectItem>
          ))}
        </>
      </FormSelect>

      <Divider />

      <FormTextarea<CustomProfileFormInput>
        form={form}
        name="engineArgsYaml"
        label={t('fields.engineArgs.label')}
        placeholder={t('fields.engineArgs.placeholder')}
        description={t('fields.engineArgs.description')}
        minRows={4}
        isDisabled={catalogDisabled}
        data-testid="custom-profile-engine-args-yaml"
      />

      <FormTextarea<CustomProfileFormInput>
        form={form}
        name="envVarsYaml"
        label={t('fields.envVars.label')}
        placeholder={t('fields.envVars.placeholder')}
        description={t('fields.envVars.description')}
        minRows={4}
        isDisabled={catalogDisabled}
        data-testid="custom-profile-env-vars-yaml"
      />
    </div>
  );
};

CustomProfileFormFields.displayName = 'CustomProfileFormFields';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  project: string;
  modelId: string;
  /** Resolved model display name, for the drawer heading. */
  modelName: string;
  /**
   * Resource name of the profile to edit. Absent creates a new one.
   *
   * Passed by name rather than by value so the drawer reads the profile from the
   * same cached list the screen renders, which keeps the two from disagreeing.
   */
  profileName?: string;
  /** Fires on create, not edit, for callers that adopt the new profile. */
  onCreated?: (profile: CustomProfileResponse) => void;
  /**
   * Offers "Save and deploy" on a new profile, handing the saved one to the
   * caller to deploy. Omitted by callers that are already deploying.
   */
  onSaveAndDeploy?: (profile: CustomProfileResponse) => void;
}

/** Creates or edits one named profile of a custom model. */
export const CustomProfileDrawer = ({
  isOpen,
  onClose,
  project,
  modelId,
  modelName,
  profileName,
  onCreated,
  onSaveAndDeploy,
}: Props) => {
  const { t } = useTranslation('models', {
    keyPrefix: 'customModels.profiles.drawer',
  });
  const { t: tModels } = useTranslation('models');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const catalog = useRuntimeProfileCatalog(project);
  const isEdit = Boolean(profileName);

  const profilesQueryKey = useMemo(
    () => ['project', project, 'custom-model', modelId, 'profiles'],
    [project, modelId],
  );

  // The drawer needs the sibling names for the inline duplicate check, and in
  // edit mode the profile being edited. Same key as the list screen, so opening
  // the drawer reads that cache rather than refetching it; the fetch only runs
  // when nothing is cached yet, such as a direct load of an edit URL.
  const { data: profiles } = useQuery<CustomProfileResponse[]>({
    queryKey: profilesQueryKey,
    queryFn: () => listCustomProfiles(project, modelId),
    enabled: isOpen && Boolean(project) && Boolean(modelId),
    refetchOnMount: false,
  });

  const profile = useMemo(
    () =>
      profileName
        ? profiles?.find((entry) => entry.name === profileName)
        : undefined,
    [profiles, profileName],
  );

  // The model's own Default profile, as the create form's starting tuple. The
  // per-axis option lists say which values exist but not which coexist, and the
  // API takes only a tuple that resolves to exactly one base profile; the Default
  // was derived from one, so it is the one combination known to resolve.
  //
  // Changing an axis can still assemble a tuple the base never emits, which only
  // the API can catch while the options carry values per axis and not the
  // combinations they came from.
  const axisSeed = useMemo(
    () =>
      profileName ? undefined : profiles?.find((entry) => entry.isDefault),
    [profiles, profileName],
  );

  const blockingDeployments = useMemo(
    () =>
      (profile?.inUseBy ?? [])
        .map((ref) => ref.displayName)
        .filter((name): name is string => Boolean(name)),
    [profile],
  );
  // A deployment referencing the profile blocks the update outright, so the
  // drawer says so up front instead of letting the user fill it in and fail.
  const isBlockedByDeployment = isEdit && blockingDeployments.length > 0;

  // Set by the runtime fields when no valid combination is selectable (options
  // loading/failed, or profiles that exist but none resolvable). The save is
  // blocked so the drawer cannot submit a tuple the API rejects with a 400.
  const [runtimeBlock, setRuntimeBlock] = useState<RuntimeSelectionBlock>(null);
  const isRuntimeBlocked = runtimeBlock !== null;

  const takenNames = useMemo(
    () =>
      new Set(
        (profiles ?? [])
          .filter((entry) => entry.name !== profileName)
          .map((entry) => normalizeName(entry.displayName)),
      ),
    [profiles, profileName],
  );

  // A create has to name four axes that resolve to exactly one base profile, so
  // offering a metric the base template never emits builds a request the API
  // rejects outright. The sibling axes are narrowed by the same matrix inside
  // `RuntimeProfileFields`; the metric is narrowed here because only this form
  // asks for it. An empty list means the base has emitted no profiles yet, where
  // the endpoint's contract is to fall back to the static superset.
  const availableMetrics = useMemo<string[]>(() => {
    // Narrowed to the metrics this build can label, because the label map lives
    // beside that union: a metric added upstream would otherwise be offered
    // under the fallback label until the pair is updated together.
    const labelled = new Set<string>(RUNTIME_PROFILE_METRIC_KEYS);
    const emitted = (catalog.runtimeOptions?.metrics ?? []).filter((metric) =>
      labelled.has(metric),
    );
    return emitted.length > 0 ? emitted : RUNTIME_PROFILE_METRIC_KEYS;
  }, [catalog.runtimeOptions?.metrics]);

  const metricLabelFor = useCallback(
    (metric: string) =>
      String(
        tModels(getMetricTranslationKey(metric), { defaultValue: metric }),
      ),
    [tModels],
  );

  const metricOptions = useMemo<MetricOption[]>(
    () =>
      availableMetrics.map((metric) => ({
        key: metric,
        label: metricLabelFor(metric),
      })),
    [availableMetrics, metricLabelFor],
  );

  const schema = useMemo(
    () =>
      z
        .object({
          displayName: z
            .string()
            .trim()
            .min(1, { message: t('errors.nameRequired') })
            .refine((name) => normalizeName(name) !== RESERVED_PROFILE_NAME, {
              message: t('errors.nameReserved'),
            })
            .refine((name) => !takenNames.has(normalizeName(name)), {
              message: t('errors.nameTaken'),
            }),
          containerImage: z
            .string()
            .trim()
            .min(1, { message: t('errors.containerImageRequired') }),
          containerVersion: z.string(),
          acceleratorType: z
            .string()
            .trim()
            .min(1, { message: t('errors.acceleratorTypeRequired') }),
          accelerator: z
            .string()
            .trim()
            .min(1, { message: t('errors.acceleratorRequired') }),
          acceleratorCount: z.coerce
            .number()
            .int()
            .min(1, { message: t('errors.acceleratorCountRequired') }),
          modelPrecision: z
            .string()
            .trim()
            .min(1, { message: t('errors.modelPrecisionRequired') }),
          metric: z
            .string()
            .trim()
            .min(1, { message: t('errors.metricRequired') }),
          engineArgsYaml: z.string(),
          envVarsYaml: z.string(),
        })
        .superRefine((data, ctx) => {
          const family = catalog.imageFamilies.find(
            (entry) => entry.familyId === data.containerImage,
          );
          if (
            (family?.tags?.length ?? 0) > 0 &&
            !data.containerVersion.trim()
          ) {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              message: t('errors.containerVersionRequired'),
              path: ['containerVersion'],
            });
          }
          if (!isRuntimeYamlMappingValid(data.engineArgsYaml)) {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              message: t('errors.invalidEngineArgsYaml'),
              path: ['engineArgsYaml'],
            });
          }
          if (!isRuntimeYamlMappingValid(data.envVarsYaml)) {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              message: t('errors.invalidEnvVarsYaml'),
              path: ['envVarsYaml'],
            });
          }
        }),
    [t, takenNames, catalog.imageFamilies],
  );

  const saveMutation = useMutation({
    mutationFn: ({ values }: SaveRequest) =>
      profileName
        ? updateCustomProfile(
            project,
            modelId,
            profileName,
            formValuesToCustomProfilePatch(
              values,
              catalog.imageFamilies,
              catalog.accelerators,
            ),
          )
        : createCustomProfile(
            project,
            modelId,
            formValuesToCustomProfileCreate(
              values,
              catalog.imageFamilies,
              catalog.accelerators,
            ),
          ),
    onSuccess: (saved, { deploy }) => {
      queryClient.invalidateQueries({ queryKey: profilesQueryKey });
      // The card's profile count comes from the custom models list, so it has
      // to be refreshed too.
      queryClient.invalidateQueries({
        queryKey: ['project', project, 'custom-models'],
      });
      toast.success(
        isEdit ? t('notifications.updated') : t('notifications.created'),
      );
      if (!isEdit) {
        onCreated?.(saved);
        if (deploy) {
          onSaveAndDeploy?.(saved);
        }
      }
      onClose();
    },
    onError: (error: unknown) => {
      // Kept open with the user's values intact so they can correct and retry.
      if (error instanceof CustomProfileConflictError) {
        toast.error(
          error.blockingServices.length > 0
            ? t('notifications.conflictInUse', {
                services: error.blockingServices.join(', '),
              })
            : t('notifications.conflictName'),
        );
        return;
      }
      toast.error(
        error instanceof APIRequestError
          ? error.message
          : t('notifications.error'),
      );
    },
  });

  // Guards the save itself, not just the disabled button: the form can still be
  // submitted by keyboard, and the update would only fail at the API anyway.
  const handleSave = useCallback(
    (
      values: CustomProfileFormInput,
      { viaSecondaryConfirm }: { viaSecondaryConfirm: boolean },
    ) => {
      if (isBlockedByDeployment || isRuntimeBlocked) {
        return;
      }
      saveMutation.mutate({ values, deploy: viaSecondaryConfirm });
    },
    [isBlockedByDeployment, isRuntimeBlocked, saveMutation],
  );

  // The name is the one saved field that needs no catalog to resolve, so it is
  // seeded here rather than waiting for the prefill effect; everything else
  // renders behind the catalog's own loading state until that effect runs.
  const defaultValues = useMemo<CustomProfileFormInput>(
    () => ({
      ...DEFAULT_VALUES,
      ...(profile ? { displayName: profile.displayName } : {}),
    }),
    [profile],
  );

  return (
    <DrawerForm<CustomProfileFormInput>
      isOpen={isOpen}
      onCancel={onClose}
      onOpenChange={onClose}
      onFormSuccess={handleSave}
      onFormFailure={() => {}}
      title={isEdit ? t('title.edit') : t('title.create')}
      confirmText={t('actions.save')}
      cancelText={t('actions.cancel')}
      secondaryConfirm={
        onSaveAndDeploy && !isEdit
          ? {
              label: t('actions.saveAndDeploy'),
              icon: <IconRocket size={16} />,
            }
          : undefined
      }
      validationSchema={schema}
      isActioning={saveMutation.isPending}
      // The runtime controls are unmounted while the catalog is loading or
      // failed, so a save then fails validation on required fields whose error
      // UI is unmounted too — the button would look inert. The catalog's own
      // status banner explains the wait and offers the retry.
      isDisabled={
        saveMutation.isPending ||
        isBlockedByDeployment ||
        isRuntimeBlocked ||
        catalog.isLoading ||
        catalog.isError
      }
      hideCloseButton={false}
      defaultValues={defaultValues}
      renderFields={(form) => (
        <div className="flex flex-col gap-4">
          <p
            className="text-2xl font-bold"
            data-testid="custom-profile-heading"
          >
            {isEdit
              ? t('heading.edit', { modelName })
              : t('heading.create', { modelName })}
          </p>

          {isBlockedByDeployment && (
            <Alert
              status="warning"
              icon={<IconAlertTriangle />}
              title={t('inUse.title')}
              description={t('inUse.description', {
                services: blockingDeployments.join(', '),
              })}
              data-testid="custom-profile-in-use-notice"
            />
          )}

          <CustomProfileFormFields
            form={form}
            catalog={catalog}
            profile={profile}
            axisSeed={axisSeed}
            metricOptions={metricOptions}
            metricLabelFor={metricLabelFor}
            onRuntimeBlockChange={setRuntimeBlock}
            isDisabled={isBlockedByDeployment}
          />
        </div>
      )}
    />
  );
};

CustomProfileDrawer.displayName = 'CustomProfileDrawer';
