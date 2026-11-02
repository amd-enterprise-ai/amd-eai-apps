// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Select,
  SelectProps,
  type Selection,
} from '@amdenterpriseai/components';

import { useEffect } from 'react';
import { FieldValues, Path, PathValue, UseFormReturn } from 'react-hook-form';

/** Resolves `name` on plain default-values objects (including dotted paths). */
function defaultValueAtPath<T extends FieldValues>(
  defaultValues: unknown,
  name: Path<T>,
): PathValue<T, Path<T>> | undefined {
  if (
    defaultValues == null ||
    typeof defaultValues !== 'object' ||
    Array.isArray(defaultValues)
  ) {
    return undefined;
  }
  const parts = String(name).split('.');
  let cur: unknown = defaultValues;
  for (const part of parts) {
    if (cur == null || typeof cur !== 'object') {
      return undefined;
    }
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur as PathValue<T, Path<T>> | undefined;
}

interface Props<T extends FieldValues>
  extends Omit<SelectProps, 'form' | 'name'> {
  form: UseFormReturn<T>;
  name: Path<T>;
}

export const FormSelect = <T extends FieldValues>({
  form,
  name,
  className,
  children,
  defaultSelectedKeys,
  startContent,
  ...selectRest
}: Props<T>): React.ReactElement => {
  const { disallowEmptySelection, ...rest } = selectRest;
  const errorMessage = form.formState.errors[name as string]?.message as string;
  const watchDefault = defaultValueAtPath<T>(
    form.formState.defaultValues,
    name,
  );
  // Avoid `watch(name, watchDefault)`: with `shouldUnregister`, `reset()` can make
  // RHF resolve the default from `{ [name]: default }` instead of full defaults.
  const watchedValue = form.watch(name);
  const isSingle = !rest.selectionMode || rest.selectionMode === 'single';
  // Fall back to watchDefault only when the field has no live value at all
  // (undefined) — e.g. before RHF has resolved it. Once the field holds any
  // live value, including `null` or an explicit '' from clearing every
  // selection, trust it: falling back on a blank-but-defined value would let
  // the UI render watchDefault while the form still submits the cleared
  // value. `??` would also fall back on `null`, which breaks intentionally
  // clearing a nullable field.
  const effectiveValue =
    watchedValue === undefined ? watchDefault : watchedValue;
  const selectedKeys =
    effectiveValue != null && effectiveValue !== ''
      ? isSingle
        ? [String(effectiveValue)]
        : String(effectiveValue).split(',').filter(Boolean)
      : [];

  // v3 Select drives form state through `onSelectionChange` rather than a hidden
  // native input, so register the field (for validation/schema awareness) but
  // sync its value manually.
  useEffect(() => {
    form.register(name);
  }, [form, name]);

  return (
    <Select
      {...rest}
      disallowEmptySelection={disallowEmptySelection}
      name={name}
      defaultSelectedKeys={defaultSelectedKeys}
      selectedKeys={selectedKeys}
      onSelectionChange={(keys: Selection) => {
        const selected =
          keys === 'all' ? [] : Array.from(keys).map((key) => String(key));
        const next = isSingle ? (selected[0] ?? '') : selected.join(',');
        if (disallowEmptySelection && next === '') {
          return;
        }
        form.setValue(name, next as PathValue<T, Path<T>>, {
          shouldValidate: true,
          shouldDirty: true,
        });
      }}
      className={className}
      isInvalid={!!errorMessage}
      errorMessage={errorMessage}
      startContent={startContent}
    >
      {children}
    </Select>
  );
};

FormSelect.displayName = 'FormSelect';

export default FormSelect;
