// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Input, type InputProps } from '../Input/InputPrimitive';
import { cn } from '@heroui/react';
import { ComponentType } from 'react';
import { FieldValues, Path, UseFormReturn } from 'react-hook-form';

interface Props<T extends FieldValues>
  extends Omit<InputProps, 'form' | 'name'> {
  icon?: ComponentType<any>;
  form: UseFormReturn<T>;
  name: Path<T>;
}

export const FormInput = <T extends FieldValues>({
  form,
  icon: Icon,
  name,
  className,
  ...props
}: Props<T>): React.ReactElement => {
  const registration = form.register(name as Path<T>);
  const errorMessage = form.formState.errors[name as string]?.message as string;

  return (
    <Input
      {...props}
      {...registration}
      className={cn(className, {
        'text-opacity-disabled': props?.isReadOnly,
        'text-foreground': props?.isReadOnly,
      })}
      isInvalid={!!errorMessage}
      errorMessage={errorMessage}
      startContent={
        Icon ? (
          <Icon
            className={cn({
              'stroke-danger': !!errorMessage,
              'stroke-neutral-500': !errorMessage,
            })}
          />
        ) : null
      }
    />
  );
};

FormInput.displayName = 'FormInput';

export default FormInput;
