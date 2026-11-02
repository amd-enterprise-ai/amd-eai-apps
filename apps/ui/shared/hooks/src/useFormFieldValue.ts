// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useCallback, useRef } from 'react';
import {
  FieldValues,
  Path,
  PathValue,
  UseFormReturn,
  useWatch,
} from 'react-hook-form';

// Hook for watching form field values
export const useFormFieldValue = <T extends FieldValues>(
  form: UseFormReturn<T>,
  name: Path<T>,
) => {
  // react-hook-form owns the subscription deliberately: do not mirror the value into local
  // state from a `form.watch(callback)` and read it back with `form.getValues(name)`. Under
  // ManagedForm's `shouldUnregister`, the field is briefly unregistered while reset() is
  // published, so that read yields undefined and leaves the mirror stranded there.
  const currentValue = useWatch({ control: form.control, name });
  const isUpdatingRef = useRef(false);

  const updateFormValue = useCallback(
    (value: number | number[]): void => {
      const numericValue = typeof value === 'number' ? value : value[0];

      isUpdatingRef.current = true;
      form.setValue(name, numericValue as PathValue<T, Path<T>>, {
        shouldValidate: true,
      });

      // Reset flag after update
      queueMicrotask(() => {
        isUpdatingRef.current = false;
      });
    },
    [form, name],
  );

  return { currentValue, updateFormValue, isUpdatingRef };
};
