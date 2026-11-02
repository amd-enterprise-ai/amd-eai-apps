// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { FormSelect, SelectItem } from '@amdenterpriseai/components';
import { useEffect } from 'react';
import type { FieldValues, Path, UseFormReturn } from 'react-hook-form';

import { RUNTIME_PROFILE_PRECISION_OPTIONS } from '@/lib/app/runtimeProfileCatalog';
import type { RuntimeProfileSelectOption } from '@/types/runtime-profile';

type Props<T extends FieldValues> = {
  form: UseFormReturn<T>;
  precisionField: Path<T>;
  precisionLabel: string;
  precisionPlaceholder: string;
  isDisabled?: boolean;
  /**
   * Precisions the project's base template actually emits. Precision is
   * base-determined (the AIMModel CRD prunes a freely chosen value), so when
   * present these constrain the selector to what the model will really run at.
   * Falls back to the static superset when omitted/empty (base profiles not
   * loaded yet).
   */
  options?: RuntimeProfileSelectOption[];
  /**
   * True when a runtime matrix governs but offers no valid combination. The
   * empty `options` then means "no valid choice", not "not loaded yet", so the
   * field must render nothing rather than the static superset.
   */
  isConstrained?: boolean;
};

export function RuntimeProfilePrecisionField<T extends FieldValues>({
  form,
  precisionField,
  precisionLabel,
  precisionPlaceholder,
  isDisabled = false,
  options,
  isConstrained = false,
}: Props<T>) {
  const precisionOptions = isConstrained
    ? []
    : options && options.length > 0
      ? options
      : RUNTIME_PROFILE_PRECISION_OPTIONS;

  // Always keep a valid precision selected, defaulting to the first option.
  // Precision is base-determined, so the static default can be absent from the
  // real option set (e.g. base emits only fp16); snap to a valid value without
  // marking the field dirty so it never fabricates an edit. The membership
  // guard makes re-running on each render harmless.
  const selectedPrecision = form.watch(precisionField);
  useEffect(() => {
    if (precisionOptions.length === 0) {
      return;
    }
    const current = selectedPrecision == null ? '' : String(selectedPrecision);
    if (precisionOptions.some((option) => option.key === current)) {
      return;
    }
    form.setValue(precisionField, precisionOptions[0].key as never, {
      shouldDirty: false,
    });
  }, [precisionOptions, selectedPrecision, precisionField, form]);

  return (
    <FormSelect<T>
      form={form}
      name={precisionField}
      label={precisionLabel}
      placeholder={precisionPlaceholder}
      isRequired
      isDisabled={isDisabled || isConstrained}
      data-testid="custom-model-import-model-precision"
    >
      <>
        {precisionOptions.map((option) => (
          <SelectItem key={option.key}>{option.label}</SelectItem>
        ))}
      </>
    </FormSelect>
  );
}
