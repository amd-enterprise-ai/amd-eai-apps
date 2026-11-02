// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React, { ComponentType } from 'react';

import type { InputProps } from '../Input/InputPrimitive';
import { cn } from '@heroui/react';
import type { FieldValues, Path, UseFormReturn } from 'react-hook-form';

import { PasswordInput } from '../Input/PasswordInput';

interface Props<T extends FieldValues>
  extends Omit<InputProps, 'form' | 'name' | 'type'> {
  icon?: ComponentType<any>;
  form: UseFormReturn<T>;
  name: Path<T>;
  /** See `PasswordInput`'s prop of the same name. */
  preventPasswordManagerPrompt?: boolean;
}

export const FormPasswordInput = <T extends FieldValues>({
  form,
  icon,
  name,
  className,
  ...props
}: Props<T>): React.ReactElement => {
  const registration = form.register(name as Path<T>);
  const errorMessage = form.formState.errors[name as string]?.message as string;

  return (
    <PasswordInput
      {...props}
      {...registration}
      icon={icon}
      className={cn(className, {
        'text-opacity-disabled': props?.isReadOnly,
        'text-foreground': props?.isReadOnly,
      })}
      isInvalid={!!errorMessage}
      errorMessage={errorMessage}
    />
  );
};

FormPasswordInput.displayName = 'FormPasswordInput';

export default FormPasswordInput;
