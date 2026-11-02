// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { cn } from '@heroui/react';
import { useCallback, useEffect, useMemo } from 'react';
import { FieldValues, Path, UseFormReturn } from 'react-hook-form';

import { useBoundaryValidation } from '@amdenterpriseai/hooks';

import { NumberInput } from '../NumberField/NumberField';
import { Slider, SliderProps } from '../Slider/Slider';

interface Props<T extends FieldValues>
  extends Omit<SliderProps, 'form' | 'name' | 'onChange' | 'value'> {
  form: UseFormReturn<T>;
  name: Path<T>;
  className?: string;
  /** Fixed-width wrapper for the number stepper so values are not clipped in tight layouts. */
  numberInputClassName?: string;
}

/** Slider and number stepper bound to a single form field via one update path. */
export const FormSliderNumberInput = <T extends FieldValues>({
  form,
  name,
  className,
  numberInputClassName = 'w-40 shrink-0',
  minValue = 0,
  maxValue,
  step = 1,
  isDisabled,
  'aria-label': ariaLabel,
  ...sliderProps
}: Props<T>) => {
  const { currentValue, updateFormValue } = useBoundaryValidation(
    form,
    name,
    minValue,
    maxValue,
  );

  useEffect(() => {
    form.register(name, {
      setValueAs: (value) =>
        value === '' || value === null || value === undefined
          ? undefined
          : Number(value),
    });
  }, [form, name]);

  const errorMessage =
    typeof form.formState.errors[name]?.message === 'string'
      ? form.formState.errors[name]?.message
      : undefined;

  const safeValue = useMemo(() => {
    if (
      currentValue !== undefined &&
      currentValue !== null &&
      typeof currentValue === 'number' &&
      Number.isFinite(currentValue)
    ) {
      return currentValue;
    }
    const defaults = form.formState.defaultValues as
      | Record<string, unknown>
      | undefined;
    const defaultFieldValue = defaults?.[name as string];
    if (
      typeof defaultFieldValue === 'number' &&
      Number.isFinite(defaultFieldValue)
    ) {
      return defaultFieldValue;
    }
    if (sliderProps.defaultValue !== undefined) {
      return sliderProps.defaultValue as number;
    }
    return minValue ?? 0;
  }, [
    currentValue,
    form.formState.defaultValues,
    minValue,
    name,
    sliderProps.defaultValue,
  ]);

  const handleNumberChange = useCallback(
    (next: number | undefined) => {
      if (next === undefined || Number.isNaN(next)) {
        updateFormValue(minValue ?? 0);
        return;
      }
      updateFormValue(next);
    },
    [minValue, updateFormValue],
  );

  return (
    <div className={cn('flex min-w-0 w-full items-center gap-2', className)}>
      <div className="min-w-0 flex-1">
        <Slider
          {...sliderProps}
          minValue={minValue}
          maxValue={maxValue}
          step={step}
          isDisabled={isDisabled}
          value={safeValue}
          onChange={updateFormValue}
          isInvalid={!!errorMessage}
          errorMessage={errorMessage}
        />
      </div>
      <div className={cn(numberInputClassName)}>
        <NumberInput
          aria-label={ariaLabel}
          minValue={minValue}
          maxValue={maxValue}
          step={step}
          isDisabled={isDisabled}
          value={safeValue}
          onChange={handleNumberChange}
          isInvalid={!!errorMessage}
          className="w-full"
        />
      </div>
    </div>
  );
};

FormSliderNumberInput.displayName = 'FormSliderNumberInput';

export default FormSliderNumberInput;
