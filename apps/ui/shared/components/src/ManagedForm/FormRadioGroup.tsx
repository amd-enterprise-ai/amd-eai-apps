// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useController } from 'react-hook-form';
import type { FieldValues, Path, UseFormReturn } from 'react-hook-form';

import { RadioGroup } from '../Radio';
import type { RadioGroupProps } from '../Radio';

interface Props<T extends FieldValues>
  extends Omit<RadioGroupProps, 'form' | 'name' | 'value' | 'onChange'> {
  form: UseFormReturn<T>;
  name: Path<T>;
}

export const FormRadioGroup = <T extends FieldValues>({
  form,
  name,
  children,
  ...props
}: Props<T>): React.ReactElement => {
  const { field, fieldState } = useController({
    control: form.control,
    name,
  });
  const errorMessage =
    typeof fieldState.error?.message === 'string'
      ? fieldState.error.message
      : undefined;

  return (
    <RadioGroup
      {...props}
      name={field.name}
      value={field.value ?? null}
      onBlur={field.onBlur}
      onChange={field.onChange}
      isInvalid={!!errorMessage}
      errorMessage={errorMessage}
    >
      {children}
    </RadioGroup>
  );
};

FormRadioGroup.displayName = 'FormRadioGroup';

export default FormRadioGroup;
