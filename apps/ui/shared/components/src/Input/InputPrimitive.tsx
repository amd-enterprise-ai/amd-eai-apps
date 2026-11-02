// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Description, InputGroup, Label, cn } from '@heroui/react';
import React, { forwardRef, useId } from 'react';

import {
  type FormFieldVariant,
  resolveFormFieldVariant,
} from '../internal/formFieldVariant';

export type { FormFieldVariant };

/**
 * v2→v3 Input compatibility wrapper.
 *
 * HeroUI v3 decomposed the v2 monolithic `Input` (which bundled label,
 * description, error, start/end content, and variants) into separate `Label`,
 * `InputGroup` (`Prefix`/`Input`/`Suffix`), and `Description` primitives, and
 * reduced `variant` to `primary`/`secondary`. This wrapper recomposes them
 * behind the v2 prop surface so the many Input call sites (FormInput,
 * PasswordInput, …) stay unchanged. `SearchInput` uses `SearchField` directly.
 * Native `value`/`onChange`
 * (event) semantics are preserved by keeping them on the inner input.
 */
export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size' | 'color'> {
  label?: React.ReactNode;
  description?: React.ReactNode;
  errorMessage?: React.ReactNode;
  isInvalid?: boolean;
  isRequired?: boolean;
  isDisabled?: boolean;
  isReadOnly?: boolean;
  startContent?: React.ReactNode;
  endContent?: React.ReactNode;
  variant?: FormFieldVariant;
  onValueChange?: (value: string) => void;
  className?: string;
  classNames?: {
    base?: string;
    label?: string;
    input?: string;
    inputWrapper?: string;
    description?: string;
    errorMessage?: string;
  };
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      description,
      errorMessage,
      isInvalid,
      isRequired,
      isDisabled,
      isReadOnly,
      startContent,
      endContent,
      variant,
      onChange,
      onValueChange,
      className,
      classNames,
      id: idProp,
      ...rest
    },
    ref,
  ) => {
    const generatedId = useId();
    const id = idProp ?? generatedId;

    const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
      onChange?.(event);
      onValueChange?.(event.target.value);
    };

    return (
      <div
        className={cn(
          'flex w-full flex-col gap-1.5',
          classNames?.base,
          className,
        )}
      >
        {label ? (
          <Label
            htmlFor={id}
            isRequired={isRequired}
            isInvalid={isInvalid}
            className={classNames?.label}
          >
            {label}
          </Label>
        ) : null}
        <InputGroup
          variant={resolveFormFieldVariant(variant)}
          className={classNames?.inputWrapper}
          isInvalid={isInvalid}
        >
          {startContent ? (
            <InputGroup.Prefix>{startContent}</InputGroup.Prefix>
          ) : null}
          <InputGroup.Input
            id={id}
            ref={ref}
            disabled={isDisabled}
            readOnly={isReadOnly}
            // Use `aria-required` (matching v2/react-aria) rather than the native
            // `required` attribute: native HTML constraint validation would abort
            // `form.requestSubmit()` before react-hook-form's JS validation runs,
            // breaking submit-time validation and focus-on-error.
            aria-required={isRequired || undefined}
            aria-invalid={isInvalid || undefined}
            className={classNames?.input}
            onChange={handleChange}
            {...rest}
          />
          {endContent ? (
            <InputGroup.Suffix>{endContent}</InputGroup.Suffix>
          ) : null}
        </InputGroup>
        {description ? (
          <Description className={classNames?.description}>
            {description}
          </Description>
        ) : null}
        {isInvalid && errorMessage ? (
          <span className={cn('text-danger text-xs', classNames?.errorMessage)}>
            {errorMessage}
          </span>
        ) : null}
      </div>
    );
  },
);

Input.displayName = 'Input';

export default Input;
