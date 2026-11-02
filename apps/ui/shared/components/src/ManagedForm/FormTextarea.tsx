// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Textarea } from '@amdenterpriseai/components';
import { cn } from '@heroui/react';
import { FieldValues, Path, UseFormReturn } from 'react-hook-form';

type TextareaProps = React.ComponentProps<typeof Textarea>;

interface Props<T extends FieldValues>
  extends Omit<TextareaProps, 'form' | 'name'> {
  form: UseFormReturn<T>;
  name: Path<T>;
}

export const FormTextarea = <T extends FieldValues>({
  form,
  name,
  className,
  ...props
}: Props<T>): React.ReactElement => {
  const registration = form.register(name as Path<T>);
  const errorMessage = form.formState.errors[name as string]?.message as string;

  return (
    <Textarea
      {...props}
      {...registration}
      className={cn(className, {
        'text-opacity-disabled': props?.isReadOnly,
        'text-foreground': props?.isReadOnly,
      })}
      isInvalid={!!errorMessage}
      errorMessage={errorMessage}
    />
  );
};

FormTextarea.displayName = 'FormTextarea';

export default FormTextarea;
