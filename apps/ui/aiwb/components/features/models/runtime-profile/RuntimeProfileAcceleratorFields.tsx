// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { FormInput, FormSelect, SelectItem } from '@amdenterpriseai/components';
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'next-i18next';
import type { FieldValues, Path, UseFormReturn } from 'react-hook-form';

import {
  acceleratorTypeKey,
  getDefaultAcceleratorDeviceId,
  supportedAcceleratorCounts,
  toAcceleratorSelectOptions,
  toAcceleratorTypeSelectOptions,
} from '@/lib/app/runtimeProfileCatalog';
import type { ClusterAccelerator } from '@/types/cluster';

const MODEL_ACCELERATOR_TRANSLATION_PREFIXES = [
  'customModels.import.steps.runtime.catalog',
  'customModels.profiles.drawer.catalog',
] as const;

type Props<T extends FieldValues> = {
  form: UseFormReturn<T>;
  accelerators: ClusterAccelerator[];
  /**
   * Accelerator counts the base template supports (e.g. `[1,2,4,8]`). When
   * present the count becomes a select limited to these (further capped by the
   * selected device's allocatable count), since aim-engine only emits profiles
   * for these sizes — an in-between value leaves the profile `NotAvailable`.
   * Empty falls back to a free numeric input (base profiles not loaded yet).
   */
  acceleratorCounts?: number[];
  acceleratorTypeField: Path<T>;
  acceleratorField: Path<T>;
  acceleratorCountField: Path<T>;
  acceleratorTypeLabel: string;
  acceleratorTypePlaceholder: string;
  acceleratorLabel: string;
  acceleratorPlaceholder: string;
  acceleratorCountLabel: string;
  isDisabled?: boolean;
  /**
   * True when a runtime matrix governs but offers no valid combination. An empty
   * count list then means "no valid choice", not "not loaded yet", so the count
   * renders as an empty disabled select rather than a free numeric input.
   */
  isConstrained?: boolean;
};

export function RuntimeProfileAcceleratorFields<T extends FieldValues>({
  form,
  accelerators,
  acceleratorCounts = [],
  acceleratorTypeField,
  acceleratorField,
  acceleratorCountField,
  acceleratorTypeLabel,
  acceleratorTypePlaceholder,
  acceleratorLabel,
  acceleratorPlaceholder,
  acceleratorCountLabel,
  isDisabled = false,
  isConstrained = false,
}: Props<T>) {
  const { t } = useTranslation('models');
  const acceleratorTypeOptions = useMemo(
    () => toAcceleratorTypeSelectOptions(accelerators),
    [accelerators],
  );
  const selectedAcceleratorType = form.watch(acceleratorTypeField) as
    | string
    | undefined;
  const acceleratorsForType = useMemo(() => {
    if (!selectedAcceleratorType) {
      return accelerators;
    }
    return accelerators.filter(
      (entry) =>
        acceleratorTypeKey(entry.acceleratorType) ===
        acceleratorTypeKey(selectedAcceleratorType),
    );
  }, [accelerators, selectedAcceleratorType]);
  const acceleratorModelLabel = useMemo(
    () =>
      (model: string): string => {
        for (const prefix of MODEL_ACCELERATOR_TRANSLATION_PREFIXES) {
          const key = `${prefix}.modelAccelerators.${model}`;
          const translated = String(t(key as never));
          if (translated !== key) {
            return translated;
          }
        }
        for (const prefix of MODEL_ACCELERATOR_TRANSLATION_PREFIXES) {
          const key = `${prefix}.modelAccelerator`;
          const fallback = String(t(key as never, { model } as never));
          if (fallback !== key) {
            return fallback;
          }
        }
        return model;
      },
    [t],
  );

  const acceleratorOptions = useMemo(
    () =>
      toAcceleratorSelectOptions(acceleratorsForType, acceleratorModelLabel),
    [acceleratorsForType, acceleratorModelLabel],
  );

  useEffect(() => {
    if (acceleratorTypeOptions.length === 0) {
      return;
    }
    const currentType = acceleratorTypeKey(
      form.getValues(acceleratorTypeField) as string,
    );
    const isCurrentTypeValid = acceleratorTypeOptions.some(
      (option) => option.key === currentType,
    );
    if (!isCurrentTypeValid) {
      form.setValue(
        acceleratorTypeField,
        acceleratorTypeOptions[0].key as never,
        {
          shouldValidate: true,
        },
      );
    }
  }, [acceleratorTypeField, acceleratorTypeOptions, form]);

  useEffect(() => {
    const defaultDeviceId = getDefaultAcceleratorDeviceId(acceleratorsForType);
    const current = form.getValues(acceleratorField) as string;
    const isCurrentStillValid = acceleratorsForType.some(
      (entry) => entry.deviceId === current,
    );
    if ((!current || !isCurrentStillValid) && defaultDeviceId) {
      form.setValue(acceleratorField, defaultDeviceId as never, {
        shouldValidate: true,
      });
    }
  }, [acceleratorField, acceleratorsForType, form]);

  // Cap the supported counts by how many of the selected device the cluster can
  // actually allocate; if that filter empties the list (incomplete capacity
  // data), keep the full supported set rather than blocking onboarding.
  const selectedDeviceId = form.watch(acceleratorField) as string | undefined;
  const allocatableCount = useMemo(() => {
    const match = accelerators.find(
      (entry) => entry.deviceId === selectedDeviceId,
    );
    return match?.allocatableCount ?? 0;
  }, [accelerators, selectedDeviceId]);
  const countOptions = useMemo(
    () => supportedAcceleratorCounts(acceleratorCounts, allocatableCount),
    [acceleratorCounts, allocatableCount],
  );

  // Always keep a valid count selected, defaulting to the first option. Covers
  // the initial default and the case where switching devices narrows the
  // options below the current value. shouldDirty:false so it never fabricates
  // an edit (e.g. on edit-mode prefill of a now-unsupported count). The
  // membership guard makes re-running on each render harmless.
  const rawCount = form.watch(acceleratorCountField);
  useEffect(() => {
    if (countOptions.length === 0) {
      return;
    }
    if (countOptions.includes(Number(rawCount))) {
      return;
    }
    form.setValue(acceleratorCountField, countOptions[0] as never, {
      shouldDirty: false,
    });
  }, [countOptions, rawCount, acceleratorCountField, form]);

  return (
    <>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <FormSelect<T>
          form={form}
          name={acceleratorTypeField}
          label={acceleratorTypeLabel}
          placeholder={acceleratorTypePlaceholder}
          isRequired
          isDisabled={isDisabled}
          data-testid="custom-model-import-accelerator-type"
        >
          {acceleratorTypeOptions.map((option) => (
            <SelectItem key={option.key}>{option.label}</SelectItem>
          ))}
        </FormSelect>
        <FormSelect<T>
          form={form}
          name={acceleratorField}
          label={acceleratorLabel}
          placeholder={acceleratorPlaceholder}
          isRequired
          isDisabled={
            isDisabled || isConstrained || acceleratorOptions.length === 0
          }
          data-testid="custom-model-import-accelerator"
        >
          {acceleratorOptions.map((option) => (
            <SelectItem key={option.key}>{option.label}</SelectItem>
          ))}
        </FormSelect>
      </div>
      {countOptions.length > 0 || isConstrained ? (
        <FormSelect<T>
          form={form}
          name={acceleratorCountField}
          label={acceleratorCountLabel}
          isRequired
          isDisabled={isDisabled || isConstrained}
          data-testid="custom-model-import-accelerator-count"
        >
          {countOptions.map((count) => (
            <SelectItem key={String(count)}>{String(count)}</SelectItem>
          ))}
        </FormSelect>
      ) : (
        <FormInput<T>
          form={form}
          name={acceleratorCountField}
          label={acceleratorCountLabel}
          type="number"
          min={1}
          isRequired
          isDisabled={isDisabled}
          data-testid="custom-model-import-accelerator-count"
        />
      )}
    </>
  );
}
