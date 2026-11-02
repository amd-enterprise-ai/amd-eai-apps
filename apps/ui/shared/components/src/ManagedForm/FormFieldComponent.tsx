// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import { Input } from '../Input/InputPrimitive';
import { ActionButton } from '../Buttons/ActionButton';
import { cn } from '@heroui/react';
import {
  FieldValues,
  Path,
  UseFormRegister,
  UseFormReturn,
} from 'react-hook-form';

import { FormField } from '@amdenterpriseai/types';

interface Props<T extends FieldValues> {
  formField: FormField<T>;
  isDisabled?: boolean;
  errorMessage?: string;
  register?: UseFormRegister<T> | null;
  form?: UseFormReturn<T>;
  defaultValue?: unknown;
  className?: string;
}

/**
 * Renders a single form field from a **FormField config** (name, label, component, etc.). Use it
 * inside ManagedForm's `renderFields` when the form is **config-driven**: you have an array of
 * `FormField<T>` and map over them instead of writing JSX per field.
 *
 * ## Relation to ManagedForm
 *
 * ManagedForm provides the form instance, validation, and submit/reset. FormFieldComponent consumes
 * that form in `renderFields`: pass `form` (and optionally `formField`); it derives `register` and
 * `errorMessage` from `form` when not provided. Prefer passing only `form` so the component stays
 * the single source for registration and error display. ManagedForm's `shouldUnregister: true`
 * handles cleanup when the field unmounts; FormFieldComponent does not need to call `unregister`.
 *
 * ## Element types
 *
 * - **Default (no `component`)**: Uses HeroUI `Input`. Good for text fields (name, email, etc.).
 * - **Custom component**: Set `formField.component` to any component that accepts `ref`, `onChange`,
 *   `label`, `errorMessage`, `variant`, and the other props FormFieldComponent passes through. Use
 *   for Select (with `defaultSelectedKeys` when not controlled), Textarea, or shared custom inputs.
 * - **Form* components**: You can pass a Form* (e.g. FormSelect) as `formField.component` when the
 *   field is part of a config-driven form and needs that control's API; FormFieldComponent forwards
 *   `form` and `name` to it.
 *
 * ## Examples
 *
 * **Text fields (default Input):**
 *
 * ```tsx
 * const fields: FormField<MyForm>[] = [
 *   { name: 'name', label: 'Name', isRequired: true },
 *   { name: 'email', label: 'Email', placeholder: 'you@example.com' },
 * ];
 * renderFields={(form) =>
 *   fields.map((f) => <FormFieldComponent key={f.name} formField={f} form={form} />)
 * }
 * ```
 *
 * **Select (custom component, stable default):**
 *
 * ```tsx
 * {
 *   name: 'scope',
 *   label: 'Scope',
 *   component: (props) => (
 *     <Select defaultSelectedKeys={[defaultScope]} {...props}>
 *       <SelectItem key="a">A</SelectItem>
 *       <SelectItem key="b">B</SelectItem>
 *     </Select>
 *   ),
 * }
 * ```
 *
 * **With icon and secondary action:**
 *
 * ```tsx
 * {
 *   name: 'query',
 *   label: 'Search',
 *   placeholder: 'Type to search',
 *   icon: MagnifyingGlassIcon,
 *   secondaryAction: { label: 'Clear', callback: () => resetSearch() },
 * }
 * ```
 */
export const FormFieldComponent = <T extends FieldValues>({
  defaultValue,
  formField,
  isDisabled,
  errorMessage: errorMessageProp,
  className,
  register: registerProp,
  form,
}: Props<T>) => {
  const register = registerProp ?? form?.register ?? null;
  const errorMessage =
    errorMessageProp ??
    (form?.formState.errors[formField.name as string]?.message as
      | string
      | undefined);

  const Component = (formField.component as React.ElementType) || Input;

  const FormField = (
    <Component
      {...formField?.props}
      {...(register ? register(formField.name as Path<T>) : {})}
      className={cn(className, {
        'text-opacity-disabled': formField.isReadOnly,
        'text-foreground': formField.isReadOnly,
      })}
      form={form}
      name={formField.name}
      isDisabled={isDisabled}
      isRequired={formField.isRequired}
      label={formField.label}
      isReadOnly={formField.isReadOnly}
      isInvalid={!!errorMessage}
      placeholder={formField.placeholder}
      errorMessage={errorMessage}
      description={formField.description}
      defaultValue={defaultValue}
      startContent={
        formField?.icon ? (
          <formField.icon
            className={cn({
              'stroke-danger': !!errorMessage,
              'stroke-neutral-500': !!errorMessage,
            })}
          />
        ) : null
      }
    />
  );
  return formField.secondaryAction ? (
    <div className="relative">
      {formField.secondaryAction ? (
        <div className="absolute top-[-0.6rem] right-2">
          <ActionButton
            tertiary
            size="sm"
            onPress={formField.secondaryAction.callback}
          >
            {formField.secondaryAction.label}
          </ActionButton>
        </div>
      ) : null}
      {FormField}
    </div>
  ) : (
    FormField
  );
};

export default FormFieldComponent;
