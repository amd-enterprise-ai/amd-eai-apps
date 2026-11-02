// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Description,
  Label,
  NumberField as HeroUINumberField,
  cn,
} from '@heroui/react';
import { IconMinus, IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import React, { forwardRef, useCallback, useId } from 'react';

import {
  type FormFieldVariant,
  resolveFormFieldVariant,
} from '../internal/formFieldVariant';

export type { FormFieldVariant };

/**
 * v2→v3 NumberInput/NumberField compatibility wrapper.
 *
 * HeroUI v3 renamed `NumberInput`→`NumberField` and decomposed it into a
 * compound tree (`NumberField` > `NumberField.Group` >
 * `NumberField.Input`/`IncrementButton`/`DecrementButton`), reduced `variant`
 * to `primary`/`secondary`, and dropped `label`/`description`/`errorMessage`/
 * `startContent`/`onValueChange`/`classNames`. This wrapper recomposes the v2
 * surface so call sites (FormNumberInput, …) stay unchanged.
 */
type RootProps = React.ComponentProps<typeof HeroUINumberField>;

export interface NumberFieldProps
  extends Omit<RootProps, 'children' | 'onChange' | 'variant'> {
  label?: React.ReactNode;
  description?: React.ReactNode;
  errorMessage?: React.ReactNode;
  isInvalid?: boolean;
  startContent?: React.ReactNode;
  endContent?: React.ReactNode;
  /** Placeholder rendered in the input (v2 compat). */
  placeholder?: string;
  variant?: FormFieldVariant;
  onChange?: (value: number | undefined) => void;
  onValueChange?: (value: number) => void;
  onStep?: (direction: 'decrement' | 'increment') => void;
  className?: string;
}

export type NumberInputProps = NumberFieldProps;

export const NumberField = forwardRef<HTMLInputElement, NumberFieldProps>(
  (
    {
      label,
      description,
      errorMessage,
      isInvalid,
      isRequired,
      startContent,
      endContent,
      placeholder,
      variant,
      onChange,
      onValueChange,
      onStep,
      className,
      id: idProp,
      fullWidth = true,
      ...rest
    },
    forwardedRef,
  ) => {
    const { t } = useTranslation('sharedComponents');
    const generatedId = useId();
    const id = idProp ?? generatedId;
    const labelId = useId();
    const { ref: restRef, ...heroFieldProps } = rest as typeof rest & {
      ref?: React.Ref<HTMLInputElement | null>;
    };
    const setInputRef = useCallback(
      (node: HTMLInputElement | null) => {
        if (typeof forwardedRef === 'function') {
          forwardedRef(node);
        } else if (forwardedRef) {
          (
            forwardedRef as React.MutableRefObject<HTMLInputElement | null>
          ).current = node;
        }
        if (typeof restRef === 'function') {
          restRef(node);
        } else if (restRef) {
          (restRef as React.MutableRefObject<HTMLInputElement | null>).current =
            node;
        }
      },
      [forwardedRef, restRef],
    );

    const handleChange = (next: number | undefined) => {
      onChange?.(next);
      if (next === undefined) {
        onValueChange?.(NaN);
      } else {
        onValueChange?.(next);
      }
    };
    const value = heroFieldProps.value;
    const atMinimum =
      typeof value === 'number' &&
      typeof heroFieldProps.minValue === 'number' &&
      value <= heroFieldProps.minValue;
    const atMaximum =
      typeof value === 'number' &&
      typeof heroFieldProps.maxValue === 'number' &&
      value >= heroFieldProps.maxValue;
    const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (
        !onStep ||
        Number.isFinite(value) ||
        heroFieldProps.isDisabled ||
        heroFieldProps.isReadOnly
      ) {
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        onStep('decrement');
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        onStep('increment');
      }
    };

    return (
      <div className={cn('flex w-full min-w-0 flex-col gap-1.5', className)}>
        {label ? (
          <Label
            id={labelId}
            htmlFor={id}
            isRequired={isRequired}
            isInvalid={isInvalid}
          >
            {label}
          </Label>
        ) : null}
        <HeroUINumberField
          variant={resolveFormFieldVariant(variant)}
          isRequired={isRequired}
          isInvalid={isInvalid}
          fullWidth={fullWidth}
          className="min-w-0"
          onChange={handleChange}
          {...heroFieldProps}
          aria-labelledby={
            label
              ? [labelId, heroFieldProps['aria-labelledby']]
                  .filter(Boolean)
                  .join(' ')
              : heroFieldProps['aria-labelledby']
          }
        >
          <HeroUINumberField.Group className="min-w-0 max-w-full w-full overflow-visible!">
            {onStep ? (
              <button
                aria-label={t('numberField.decrease')}
                className="number-field__decrement-button shrink-0"
                data-slot="decrease-button"
                disabled={
                  heroFieldProps.isDisabled ||
                  heroFieldProps.isReadOnly ||
                  atMinimum
                }
                onClick={() => onStep('decrement')}
                type="button"
              >
                <IconMinus size={16} />
              </button>
            ) : (
              <HeroUINumberField.DecrementButton
                aria-label={t('numberField.decrease')}
                className="shrink-0"
              >
                <IconMinus size={16} />
              </HeroUINumberField.DecrementButton>
            )}
            <div className="flex min-w-0 items-center gap-1 overflow-hidden px-2">
              {startContent ? (
                <div className="shrink-0">{startContent}</div>
              ) : null}
              <HeroUINumberField.Input
                id={id}
                ref={setInputRef}
                placeholder={placeholder}
                className="min-w-0 flex-1 text-right"
                onKeyDown={handleKeyDown}
              />
              {endContent ? <div className="shrink-0">{endContent}</div> : null}
            </div>
            {onStep ? (
              <button
                aria-label={t('numberField.increase')}
                className="number-field__increment-button shrink-0"
                data-slot="increase-button"
                disabled={
                  heroFieldProps.isDisabled ||
                  heroFieldProps.isReadOnly ||
                  atMaximum
                }
                onClick={() => onStep('increment')}
                type="button"
              >
                <IconPlus size={16} />
              </button>
            ) : (
              <HeroUINumberField.IncrementButton
                aria-label={t('numberField.increase')}
                className="shrink-0"
              >
                <IconPlus size={16} />
              </HeroUINumberField.IncrementButton>
            )}
          </HeroUINumberField.Group>
        </HeroUINumberField>
        {description ? <Description>{description}</Description> : null}
        {isInvalid && errorMessage ? (
          <span className="text-danger text-xs">{errorMessage}</span>
        ) : null}
      </div>
    );
  },
);

NumberField.displayName = 'NumberField';

export const NumberInput = NumberField;

export default NumberField;
