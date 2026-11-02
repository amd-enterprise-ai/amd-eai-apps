// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useEffect, useMemo, useState } from 'react';
import type { FieldValues, UseFormReturn } from 'react-hook-form';

import type { RuntimeProfileCatalogState } from '@/hooks/useRuntimeProfileCatalog';
import {
  getBaseImageRuntimeProfileOptions,
  type BaseImageRuntimeProfileOptions,
} from '@/lib/app/custom-models';
import {
  deviceIdToAcceleratorModel,
  getLatestImageTag,
  intersectCombinations,
  reachableRuntimeAxes,
  runtimeSelectionBlock,
  type RuntimeSelectionBlock,
} from '@/lib/app/runtimeProfileCatalog';

import { RuntimeProfileAcceleratorFields } from './RuntimeProfileAcceleratorFields';
import { RuntimeProfileCatalogStatus } from './RuntimeProfileCatalogStatus';
import { RuntimeProfileImageFields } from './RuntimeProfileImageFields';
import { RuntimeProfilePrecisionField } from './RuntimeProfilePrecisionField';

type FieldLabels = {
  containerImage: { label: string; placeholder: string };
  containerVersion: { label: string; placeholder: string };
  acceleratorType: { label: string; placeholder: string };
  accelerator: { label: string; placeholder: string };
  acceleratorCount: { label: string };
  modelPrecision: { label: string; placeholder: string };
  catalogLoading: string;
  catalogError: string;
  catalogRetry: string;
  baseImageOptionsWarning: string;
  noValidCombinationsWarning: string;
  emptyAccelerators: string;
};

/** Lifted to a parent that owns a sibling selector (the drawer's metric) and the save action. */
export type RuntimeProfileSelectionState = {
  baseImageOptions: BaseImageRuntimeProfileOptions | null;
  /** Non-null when the selectors offer no valid choice and the save must be blocked. */
  block: RuntimeSelectionBlock;
};

type Props<T extends FieldValues> = {
  form: UseFormReturn<T>;
  catalog: RuntimeProfileCatalogState;
  labels: FieldLabels;
  isDisabled?: boolean;
  /**
   * Lifts the resolved base-image options and the block state to a parent that
   * owns the drawer's metric field and the save action. Onboard passes it too so
   * it can block Next while no valid runtime combination is selectable.
   */
  onSelectionStateChange?: (state: RuntimeProfileSelectionState) => void;
};

export function RuntimeProfileFields<T extends FieldValues>({
  form,
  catalog,
  labels,
  isDisabled = false,
  onSelectionStateChange,
}: Props<T>) {
  const catalogDisabled = isDisabled || catalog.isLoading || catalog.isError;
  const selectedFamilyId = form.watch('containerImage' as never) as unknown;
  const selectedImageTag = form.watch('containerVersion' as never) as unknown;
  const selectedDeviceId = form.watch('accelerator' as never) as unknown;
  const selectedCount = form.watch('acceleratorCount' as never) as unknown;
  const selectedPrecision = form.watch('modelPrecision' as never) as unknown;
  const [baseImageOptions, setBaseImageOptions] =
    useState<BaseImageRuntimeProfileOptions | null>(null);
  const [baseImageOptionsError, setBaseImageOptionsError] = useState(false);
  const [baseImageOptionsLoading, setBaseImageOptionsLoading] = useState(false);

  const selectedFamily = useMemo(() => {
    const familyId = String(selectedFamilyId ?? '');
    if (!familyId) {
      return undefined;
    }
    return catalog.imageFamilies.find((family) => family.familyId === familyId);
  }, [catalog.imageFamilies, selectedFamilyId]);

  const selectedRepository = useMemo(() => {
    return selectedFamily?.repository ?? '';
  }, [selectedFamily]);

  const selectedTagForLookup = useMemo(() => {
    const explicit = String(selectedImageTag ?? '').trim();
    if (explicit) {
      return explicit;
    }
    return getLatestImageTag(selectedFamily?.tags);
  }, [selectedFamily, selectedImageTag]);
  const hasBaseImageSelection = useMemo(
    () =>
      selectedRepository.trim().length > 0 &&
      selectedTagForLookup.trim().length > 0,
    [selectedRepository, selectedTagForLookup],
  );

  useEffect(() => {
    let cancelled = false;
    const project = catalog.project?.trim() ?? '';
    const repository = selectedRepository.trim();
    const tag = selectedTagForLookup.trim();
    if (!project || !repository || !tag) {
      setBaseImageOptions(null);
      setBaseImageOptionsError(false);
      setBaseImageOptionsLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setBaseImageOptions(null);
    setBaseImageOptionsError(false);
    setBaseImageOptionsLoading(true);
    void getBaseImageRuntimeProfileOptions(project, repository, tag)
      .then((options) => {
        if (!cancelled) {
          setBaseImageOptions(options);
          setBaseImageOptionsError(false);
          setBaseImageOptionsLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBaseImageOptions(null);
          setBaseImageOptionsError(true);
          setBaseImageOptionsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [catalog.project, selectedRepository, selectedTagForLookup]);

  const acceleratorsForImage = useMemo(() => {
    if (!baseImageOptions) {
      return catalog.accelerators;
    }
    const allowedModels = new Set(baseImageOptions.acceleratorModels);
    const allowedTypes = new Set(
      baseImageOptions.acceleratorTypes.map((value) => value.toLowerCase()),
    );
    const filtered = catalog.accelerators.filter((entry) => {
      const model = entry.acceleratorModel ?? '';
      const type = (entry.acceleratorType ?? '').toLowerCase();
      const typeAllowed = allowedTypes.size === 0 || allowedTypes.has(type);
      const modelAllowed = allowedModels.size === 0 || allowedModels.has(model);
      return typeAllowed && modelAllowed;
    });
    return filtered.length > 0 ? filtered : catalog.accelerators;
  }, [baseImageOptions, catalog.accelerators]);

  // Why (if at all) there is no valid runtime combination to select right now.
  // When an image is selected its matrix governs; otherwise the namespace matrix
  // does. A non-null block means the save must be prevented (loading/failed image
  // options, or profiles that exist but none resolvable) rather than falling back
  // to the broad per-axis lists.
  const block = useMemo(
    () =>
      runtimeSelectionBlock({
        imageSelected: hasBaseImageSelection,
        baseImageLoading: baseImageOptionsLoading,
        baseImageError: baseImageOptionsError,
        baseImageMatrix: baseImageOptions
          ? {
              combinations: baseImageOptions.combinations,
              profilesAvailable: baseImageOptions.profilesAvailable,
            }
          : null,
        namespaceMatrix: catalog.runtimeOptions
          ? {
              combinations: catalog.runtimeOptions.combinations ?? [],
              profilesAvailable:
                catalog.runtimeOptions.profilesAvailable ?? false,
            }
          : null,
      }),
    [
      hasBaseImageSelection,
      baseImageOptionsLoading,
      baseImageOptionsError,
      baseImageOptions,
      catalog.runtimeOptions,
    ],
  );
  const blocked = block !== null;

  // Hand the resolved base-image matrix and the block state to the parent (the
  // drawer's metric selector narrows on the same combinations, and the parent
  // gates the save on the block).
  useEffect(() => {
    onSelectionStateChange?.({ baseImageOptions, block });
  }, [baseImageOptions, block, onSelectionStateChange]);

  // The combinations the cascade offers. The namespace matrix is authoritative
  // (the create/update resolver validates against it); once the selected image's
  // matrix loads it refines that set to the tuples the image also emits, so a
  // shown tuple is both resolvable and image-discoverable. While the image lookup
  // is still pending, the namespace matrix is used rather than the flat per-axis
  // lists (which would recreate the invalid cartesian product).
  const combinations = useMemo(() => {
    const namespaceCombinations = catalog.runtimeOptions?.combinations ?? [];
    const imageCombinations = baseImageOptions?.combinations;
    if (imageCombinations !== undefined && namespaceCombinations.length > 0) {
      return intersectCombinations(namespaceCombinations, imageCombinations);
    }
    return namespaceCombinations.length > 0
      ? namespaceCombinations
      : (imageCombinations ?? []);
  }, [catalog.runtimeOptions?.combinations, baseImageOptions]);

  // A matrix governs the selectors when either side has emitted profiles. Under a
  // governing matrix with no offered combination there is nothing valid to pick,
  // so the selectors show nothing rather than falling back to the broad per-axis
  // lists (which the warning tells the user are not valid).
  const matrixGoverns = Boolean(
    catalog.runtimeOptions?.profilesAvailable ||
      baseImageOptions?.profilesAvailable,
  );
  const constrained = blocked || (matrixGoverns && combinations.length === 0);

  // Restrict the accelerator selector to models the matrix actually emits. When
  // blocked there is no valid choice, so offer none. When combinations exist,
  // intersect with the cluster devices and offer nothing if none match, rather
  // than restoring the unfiltered list (which would let an unrelated model be
  // picked and reachableRuntimeAxes then expose other models' counts/precisions).
  const acceleratorsForWizard = useMemo(() => {
    if (constrained) {
      return [];
    }
    if (combinations.length === 0) {
      return acceleratorsForImage;
    }
    const allowedModels = new Set(
      combinations.map((combination) => combination.acceleratorModel),
    );
    return acceleratorsForImage.filter((entry) =>
      allowedModels.has(entry.acceleratorModel ?? ''),
    );
  }, [constrained, combinations, acceleratorsForImage]);
  const showNoValidCombinationsWarning = block === 'noValidCombinations';
  const showBaseImageOptionsWarning =
    hasBaseImageSelection &&
    baseImageOptionsError &&
    acceleratorsForWizard.length > 0;

  const selectedAcceleratorModel = useMemo(() => {
    if (!selectedDeviceId) {
      return '';
    }
    return deviceIdToAcceleratorModel(
      String(selectedDeviceId),
      acceleratorsForWizard,
    );
  }, [acceleratorsForWizard, selectedDeviceId]);

  // Cascade the count and precision selectors: each narrows to values still
  // reachable given the higher-priority selections, so the form cannot assemble
  // a tuple the base never emits (which a create/update rejects). Falls back to
  // the flat per-model / namespace lists only when no matrix governs (nothing
  // emitted yet); when blocked it offers nothing.
  const reachable = useMemo(
    () =>
      reachableRuntimeAxes(combinations, {
        acceleratorModel: selectedAcceleratorModel || undefined,
        acceleratorCount:
          selectedCount == null || selectedCount === ''
            ? undefined
            : Number(selectedCount),
        precision: selectedPrecision ? String(selectedPrecision) : undefined,
      }),
    [combinations, selectedAcceleratorModel, selectedCount, selectedPrecision],
  );

  const acceleratorCounts = useMemo(() => {
    if (constrained) {
      return [];
    }
    if (combinations.length > 0) {
      return reachable.acceleratorCounts;
    }
    if (!baseImageOptions || !selectedAcceleratorModel) {
      return catalog.runtimeOptions?.acceleratorCounts ?? [];
    }
    return (
      baseImageOptions.acceleratorCountsByModel[selectedAcceleratorModel] ??
      catalog.runtimeOptions?.acceleratorCounts ??
      []
    );
  }, [
    constrained,
    combinations.length,
    reachable.acceleratorCounts,
    baseImageOptions,
    catalog.runtimeOptions?.acceleratorCounts,
    selectedAcceleratorModel,
  ]);

  const precisionOptions = useMemo(() => {
    let precisions: string[];
    if (constrained) {
      precisions = [];
    } else if (combinations.length > 0) {
      precisions = reachable.precisions;
    } else {
      const fromImage =
        baseImageOptions && selectedAcceleratorModel
          ? baseImageOptions.precisionsByModel[selectedAcceleratorModel]
          : undefined;
      precisions = fromImage ?? catalog.runtimeOptions?.precisions ?? [];
    }
    return precisions.map((precision: string) => ({
      key: precision,
      label: precision,
    }));
  }, [
    constrained,
    combinations.length,
    reachable.precisions,
    baseImageOptions,
    catalog.runtimeOptions?.precisions,
    selectedAcceleratorModel,
  ]);

  return (
    <div className="flex flex-col gap-4">
      <RuntimeProfileCatalogStatus
        isLoading={catalog.isLoading}
        isError={catalog.isError}
        errorMessage={catalog.error?.message}
        showNoValidCombinationsWarning={showNoValidCombinationsWarning}
        noValidCombinationsMessage={labels.noValidCombinationsWarning}
        showBaseImageOptionsWarning={showBaseImageOptionsWarning}
        baseImageOptionsWarningMessage={labels.baseImageOptionsWarning}
        showEmptyAcceleratorsWarning={
          !catalog.isLoading &&
          !catalog.isError &&
          !blocked &&
          acceleratorsForWizard.length === 0
        }
        emptyAcceleratorsMessage={labels.emptyAccelerators}
        loadingMessage={labels.catalogLoading}
        loadErrorMessage={labels.catalogError}
        retryLabel={labels.catalogRetry}
        onRetry={catalog.invalidateCatalog}
      />
      {!catalog.isLoading && !catalog.isError && (
        <>
          <RuntimeProfileImageFields<T>
            form={form}
            imageFamilies={catalog.imageFamilies}
            containerImageField={'containerImage' as never}
            containerVersionField={'containerVersion' as never}
            containerImageLabel={labels.containerImage.label}
            containerImagePlaceholder={labels.containerImage.placeholder}
            containerVersionLabel={labels.containerVersion.label}
            containerVersionPlaceholder={labels.containerVersion.placeholder}
            isDisabled={catalogDisabled}
          />
          <RuntimeProfileAcceleratorFields<T>
            form={form}
            accelerators={acceleratorsForWizard}
            acceleratorCounts={acceleratorCounts}
            acceleratorTypeField={'acceleratorType' as never}
            acceleratorField={'accelerator' as never}
            acceleratorCountField={'acceleratorCount' as never}
            acceleratorTypeLabel={labels.acceleratorType.label}
            acceleratorTypePlaceholder={labels.acceleratorType.placeholder}
            acceleratorLabel={labels.accelerator.label}
            acceleratorPlaceholder={labels.accelerator.placeholder}
            acceleratorCountLabel={labels.acceleratorCount.label}
            isDisabled={catalogDisabled}
            isConstrained={constrained}
          />
          <RuntimeProfilePrecisionField<T>
            form={form}
            precisionField={'modelPrecision' as never}
            precisionLabel={labels.modelPrecision.label}
            precisionPlaceholder={labels.modelPrecision.placeholder}
            isDisabled={catalogDisabled}
            options={precisionOptions}
            isConstrained={constrained}
          />
        </>
      )}
    </div>
  );
}
