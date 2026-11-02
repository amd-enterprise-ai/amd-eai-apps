// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Slider, SliderProps } from '@amdenterpriseai/components';
import { useMemo } from 'react';
import { FieldValues, Path, UseFormReturn } from 'react-hook-form';

import { useBoundaryValidation } from '@amdenterpriseai/hooks';

interface Props<T extends FieldValues>
  extends Omit<SliderProps, 'form' | 'name' | 'onChange' | 'value'> {
  form: UseFormReturn<T>;
  name: Path<T>;
  description?: string;
}

export const FormSlider = <T extends FieldValues>({
  form,
  name,
  ...props
}: Props<T>) => {
  const { currentValue, updateFormValue } = useBoundaryValidation(
    form,
    name,
    props.minValue,
    props.maxValue,
  );

  const { onChange: _, ...registration } = form.register(name, {
    setValueAs: (value) =>
      value === '' || value === null || value === undefined
        ? undefined
        : Number(value),
  });
  const errorMessage =
    typeof form.formState.errors[name]?.message === 'string'
      ? form.formState.errors[name]?.message
      : undefined;

  const safeCurrentValue = useMemo((): number => {
    if (
      currentValue !== undefined &&
      currentValue !== null &&
      typeof currentValue === 'number' &&
      Number.isFinite(currentValue)
    ) {
      return currentValue;
    }
    if (
      typeof props.defaultValue === 'number' &&
      Number.isFinite(props.defaultValue)
    ) {
      return props.defaultValue;
    }
    return props.minValue ?? 0;
  }, [currentValue, props.defaultValue, props.minValue]);

  return (
    <Slider
      {...props}
      {...registration}
      value={safeCurrentValue}
      onChange={updateFormValue}
      isInvalid={!!errorMessage}
      errorMessage={errorMessage}
    />
  );
};

FormSlider.displayName = 'FormSlider';

export default FormSlider;
