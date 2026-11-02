// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  NumberInput,
  type NumberInputProps,
} from '@amdenterpriseai/components';
import { cn } from '@heroui/react';
import { ComponentType, useCallback } from 'react';
import {
  FieldValues,
  Path,
  PathValue,
  UseFormReturn,
  useController,
} from 'react-hook-form';

interface Props<T extends FieldValues>
  extends Omit<NumberInputProps, 'form' | 'name' | 'value'> {
  emptyValue?: number;
  icon?: ComponentType<any>;
  form: UseFormReturn<T>;
  name: Path<T>;
}

export const FormNumberInput = <T extends FieldValues>({
  form,
  emptyValue,
  icon: Icon,
  name,
  className,
  ...props
}: Props<T>) => {
  // Only `field.ref` is used from useController, to get react-hook-form's
  // Controller-style stub ref (focus/select/reportValidity, no DOM `.value`)
  // instead of register()'s real DOM ref. Schema validation reads a field's
  // current value via its ref as a fallback whenever the tracked value is
  // `undefined` (exactly the state of an untouched optional field); with a
  // real DOM ref that reads the raw input string (e.g. `""`), which fails a
  // `z.number().optional()` schema with "Expected number, received string"
  // even though nothing was entered. The stub ref has no `.value`, so that
  // fallback correctly resolves to `undefined` instead.
  const { field } = useController({ control: form.control, name });
  const errorMessage = form.formState.errors[name]?.message as string;
  const watched = form.watch(name);
  const defaults = form.formState.defaultValues as
    | Record<string, unknown>
    | undefined;
  const dirtyFields = form.formState.dirtyFields as
    | Record<string, boolean | unknown>
    | undefined;
  const isDirty = Boolean(dirtyFields?.[name as string]);
  // `field.value` (react-hook-form's Controller/useWatch) can't be used
  // directly for the displayed value: it falls back to the field's
  // mount-time default whenever the live value is `undefined`, which would
  // incorrectly resurrect a cleared value on a required field with a real
  // default (e.g. `AutoscalingFormFields`'s `targetValue`). Deriving from
  // `watch()` instead, with the mount-time default only as a pre-touch
  // fallback, keeps that behavior while still allowing an optional field to
  // settle on — and stay at — `undefined`.
  const raw = isDirty ? watched : (watched ?? defaults?.[name as string]);
  // `value` is always a defined number (real or `NaN`), never `undefined`:
  // react-stately's NumberField only stays reactive to prop changes while
  // continuously "controlled". Passing `undefined` flips it to
  // "uncontrolled", and its internal value then stops following the `value`
  // prop entirely (it's only resynced from within the field's own commit) —
  // so an external reset (e.g. clearing batchSize when the base model
  // changes) would display the stale number forever instead of clearing.
  const value = typeof raw === 'number' && Number.isFinite(raw) ? raw : NaN;

  // custom update handler to work with number instead of formatted string
  const updateFormValue = useCallback(
    (next: number): void => {
      form.setValue(
        name,
        (Number.isFinite(next) ? next : undefined) as PathValue<T, Path<T>>,
        { shouldValidate: true, shouldDirty: true },
      );
    },
    [form, name],
  );
  const stepFromValue = useCallback(
    (direction: 'decrement' | 'increment'): void => {
      const baseline = Number.isFinite(value) ? value : (emptyValue ?? NaN);
      const delta = props.step ?? 1;
      const next = baseline + (direction === 'increment' ? delta : -delta);
      const minValue = props.minValue ?? -Infinity;
      const maxValue = props.maxValue ?? Infinity;
      updateFormValue(Math.min(Math.max(next, minValue), maxValue));
    },
    [
      emptyValue,
      props.maxValue,
      props.minValue,
      props.step,
      updateFormValue,
      value,
    ],
  );

  return (
    <NumberInput
      {...props}
      name={field.name}
      ref={field.ref}
      value={value}
      onValueChange={updateFormValue}
      onStep={Number.isFinite(emptyValue) ? stepFromValue : undefined}
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

FormNumberInput.displayName = 'FormNumberInput';

export default FormNumberInput;
