// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Button, FormInput } from '@amdenterpriseai/components';
import {
  useFieldArray,
  type FieldValues,
  Path,
  UseFormReturn,
} from 'react-hook-form';

type Props<T extends FieldValues> = {
  form: UseFormReturn<T>;
  name: Path<T>;
  keyLabel: string;
  valueLabel: string;
  keyPlaceholder: string;
  valuePlaceholder: string;
  addEntryLabel: string;
  removeEntryLabel: string;
  isDisabled?: boolean;
  testIdPrefix: string;
};

export function RuntimeProfileKeyValueEditor<T extends FieldValues>({
  form,
  name,
  keyLabel,
  valueLabel,
  keyPlaceholder,
  valuePlaceholder,
  addEntryLabel,
  removeEntryLabel,
  isDisabled = false,
  testIdPrefix,
}: Props<T>) {
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: name as never,
  });
  return (
    <div
      className="flex flex-col gap-4"
      data-testid={`${testIdPrefix}-kv-editor`}
    >
      {fields.map((field, index) => (
        <div
          key={field.id}
          className="flex flex-col gap-2 rounded-lg border border-default p-3"
          data-testid={`${testIdPrefix}-kv-row-${index}`}
        >
          <div className="flex items-end gap-2">
            <FormInput<T>
              form={form}
              name={`${String(name)}.${index}.key` as Path<T>}
              label={keyLabel}
              placeholder={keyPlaceholder}
              className="flex-1"
              isDisabled={isDisabled}
              data-testid={`${testIdPrefix}-key-${index}`}
            />
            {fields.length > 1 && (
              <Button
                type="button"
                variant="light"
                color="danger"
                size="sm"
                onPress={() => remove(index)}
                isDisabled={isDisabled}
                aria-label={removeEntryLabel}
                data-testid={`${testIdPrefix}-remove-${index}`}
              >
                {removeEntryLabel}
              </Button>
            )}
          </div>
          <FormInput<T>
            form={form}
            name={`${String(name)}.${index}.value` as Path<T>}
            label={valueLabel}
            placeholder={valuePlaceholder}
            isDisabled={isDisabled}
            data-testid={`${testIdPrefix}-value-${index}`}
          />
        </div>
      ))}
      <Button
        type="button"
        variant="bordered"
        size="sm"
        onPress={() => append({ key: '', value: '' } as never)}
        isDisabled={isDisabled}
        data-testid={`${testIdPrefix}-add-row`}
      >
        {addEntryLabel}
      </Button>
    </div>
  );
}
