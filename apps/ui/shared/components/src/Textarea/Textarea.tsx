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
 * v2→v3 Textarea compatibility wrapper.
 *
 * HeroUI v3 reduced `Textarea` to a bare styled `TextArea` (RAC TextArea +
 * `primary`/`secondary` variant) and dropped `label`/`description`/
 * `errorMessage`/`minRows`/`classNames`. This wrapper recomposes the
 * v2 surface so call sites (TextAreaWrapper, FormTextarea, AddSecret) stay
 * unchanged. `minRows` maps to a fixed `rows` when `rows` is not set.
 * Prefix/suffix slots use `InputGroup.TextArea` (suffix aligns to top).
 */
export interface TextareaProps
  extends Omit<
    React.TextareaHTMLAttributes<HTMLTextAreaElement>,
    'size' | 'color'
  > {
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
  /** v3 has no auto-resize; mapped to `rows` when `rows` is not set. */
  minRows?: number;
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

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
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
      minRows,
      rows,
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

    const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
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
          data-invalid={isInvalid || undefined}
        >
          {startContent ? (
            <InputGroup.Prefix>{startContent}</InputGroup.Prefix>
          ) : null}
          <InputGroup.TextArea
            id={id}
            ref={ref}
            disabled={isDisabled}
            readOnly={isReadOnly}
            aria-required={isRequired || undefined}
            aria-invalid={isInvalid || undefined}
            rows={rows ?? minRows}
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

Textarea.displayName = 'Textarea';

export default Textarea;
