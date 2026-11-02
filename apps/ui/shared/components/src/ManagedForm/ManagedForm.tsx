// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  DefaultValues,
  FieldErrors,
  FieldValues,
  Resolver,
  UseFormReturn,
  useForm,
} from 'react-hook-form';
import { ActionButton } from '../Buttons';
import { zodResolver } from '@hookform/resolvers/zod';
import { type ZodType, type ZodTypeDef } from 'zod';

/**
 * Shallow merge for submit/reset: parsed resolver output overwrites current values,
 * but keys missing from the patch or explicitly `undefined` in the patch keep the
 * current value. Zod (especially optional fields) can omit keys from `parse` output;
 * with `shouldUnregister` + `form.reset(parsed)` that would otherwise drop live fields
 * such as GPU preemption policy until the next full reload.
 */
function mergeParsedFormValues<T extends FieldValues>(
  base: T,
  patch: Record<string, unknown>,
): T {
  const out = { ...base };
  for (const key of Object.keys(patch)) {
    const v = patch[key];
    if (v !== undefined) {
      (out as Record<string, unknown>)[key] = v;
    }
  }
  return out as T;
}

/** Reset form state and re-broadcast values so controlled Form* fields stay in sync. */
export function resetFormValues<T extends FieldValues>(
  form: UseFormReturn<T>,
  values: DefaultValues<T> | T | undefined,
  options?: { shouldDirty?: boolean; shouldValidate?: boolean },
): void {
  form.reset(values);
  const patch = values as Record<string, unknown> | undefined;
  if (!patch) {
    return;
  }
  const shouldDirty = options?.shouldDirty ?? false;
  const shouldValidate = options?.shouldValidate ?? false;
  queueMicrotask(() => {
    for (const key of Object.keys(patch)) {
      const v = patch[key];
      if (v !== undefined) {
        form.setValue(key as never, v as never, {
          shouldDirty,
          shouldValidate,
        });
      }
    }
  });
}

interface Props<T extends FieldValues> {
  className?: string;
  defaultValues?: DefaultValues<T>;
  formRef?: React.RefObject<HTMLFormElement | null> | null;
  onFormFailure?: (errors: FieldErrors<T>, data: T) => void;
  onFormSuccess: (data: T) => void;
  validationSchema: ZodType<T, ZodTypeDef, unknown>;
  isActioning?: boolean;
  renderFields: (form: UseFormReturn<T>) => React.ReactNode;
  resolver?: (schema: ZodType<T, ZodTypeDef, unknown>) => Resolver<T>;
  showResetButton?: boolean;
  showSubmitButton?: boolean;
  submitButtonText?: string;
  resetButtonText?: string;
}

/**
 * Form container that wires react-hook-form with Zod validation, submit/reset handling,
 * and optional buttons. Use `renderFields(form)` to render fields; submit payload
 * includes only currently mounted fields (`shouldUnregister: true`).
 *
 * Why use ManagedForm:
 *
 * Compared to a vanilla React form (useState per field, manual validation, hand-rolled
 * submit handler): ManagedForm gives you react-hook-form under the hood, so you get
 * fewer re-renders (subscription per field), built-in touched/dirty/errors, and Zod
 * for declarative validation in one schema instead of scattered checks. You avoid
 * per-field state and custom validation logic.
 *
 * Compared to using react-hook-form and Zod directly (useForm, zodResolver, handleSubmit
 * in every form): ManagedForm is a single place for that setup. You pass validationSchema,
 * defaultValues, and renderFields; ManagedForm configures mode, reValidateMode,
 * shouldUnregister, and submit/reset handling. Optional submit and reset buttons are
 * built in. The Form* components (FormSelect, FormInput, etc.) then work the same way
 * in every form without repeating registration and error wiring.
 *
 * ## Examples
 *
 * ### Pass form to FormFieldComponent
 * Pass only `form`; `register` and `errorMessage` are derived.
 *
 * ```tsx
 * <ManagedForm
 *   validationSchema={schema}
 *   defaultValues={{ name: '', email: '' }}
 *   onFormSuccess={(data) => {}}
 *   renderFields={(form) =>
 *     formContent.map((field) => (
 *       <FormFieldComponent key={field.name} formField={field} form={form} />
 *     ))
 *   }
 * />
 * ```
 *
 * ### Dynamic fields by watched value
 * Memoize configs by dependency, then pick by `form.watch()`.
 *
 * ```tsx
 * const formTypeByScope = useMemo(
 *   () => ({ [Scope.A]: getTypeField(Scope.A), [Scope.B]: getTypeField(Scope.B) }),
 *   [getTypeField]
 * );
 * renderFields={(form) => {
 *   const scope = form.watch('scope') ?? defaultScope;
 *   return <FormFieldComponent formField={formTypeByScope[scope]} form={form} />;
 * }}
 * ```
 *
 * ### Controlled Select (FormSelect)
 * Use `FormSelect` when the field must stay controlled; `selectedKeys` comes from the form.
 *
 * ```tsx
 * <FormSelect form={form} name="type" label="Type" placeholder="Pick type">
 *   <SelectItem key="a">Option A</SelectItem>
 *   <SelectItem key="b">Option B</SelectItem>
 * </FormSelect>
 * ```
 *
 * ### Stable Select with default only
 * Plain HeroUI `Select` inside FormFieldComponent when config is stable and `defaultSelectedKeys` is enough.
 *
 * ```tsx
 * component: (props) => <Select defaultSelectedKeys={[defaultScope]} {...props} />
 * ```
 *
 * ## FormFieldComponent vs Form* components
 *
 * **FormFieldComponent** is a generic renderer: it takes a single `FormField<T>` config (name, label,
 * placeholder, optional `component`, icon, etc.) and renders one field. It passes `register(name)`,
 * `errorMessage`, and common props (label, variant) to the underlying component;
 * if no `component` is provided, it uses HeroUI `Input`. Use it when your form is **config-driven** —
 * you have an array of FormField configs and map over them instead of writing JSX per field.
 *
 * **When to use FormFieldComponent**
 *
 * - The form is defined by **data** (e.g. an array of FormField configs from a constant or computed
 *   list). Add, remove, or reorder fields by editing the config, not JSX.
 * - The field type is a simple text input (default) or a component that accepts the same prop shape
 *   (label, errorMessage, ref, onChange). For Selects that don't need to be controlled by form state,
 *   you can pass a Select as `formField.component` with `defaultSelectedKeys`.
 * - You want one loop in `renderFields`: `formContent.map(field => <FormFieldComponent key={field.name}
 *   formField={field} form={form} />)`. Prefer passing only `form`; the component derives `register`
 *   and `errorMessage`.
 *
 * **When to use a Form* component directly**
 *
 * - You're writing explicit JSX and the control needs **special wiring**: `FormSelect`
 *   (selectedKeys/onSelectionChange), `FormNumberInput` (number, onValueChange), `FormSlider`,
 *   `FormFileUpload`. Use the Form* component so registration and value sync are handled.
 * - The field must be **controlled** by form state (e.g. a Select whose value affects other fields).
 *   Use `FormSelect` (or the appropriate Form*) directly, or pass it as `formField.component`
 *   when using FormFieldComponent.
 *
 * **Example: FormFieldComponent (config-driven)**
 *
 * ```tsx
 * const fields: FormField<MyForm>[] = [
 *   { name: 'name', label: 'Name', isRequired: true },
 *   { name: 'email', label: 'Email', placeholder: 'you@example.com' },
 * ];
 * renderFields={(form) =>
 *   fields.map((field) => (
 *     <FormFieldComponent key={field.name} formField={field} form={form} />
 *   ))
 * }
 * ```
 *
 * **Example: Form* components (explicit JSX)**
 *
 * ```tsx
 * renderFields={(form) => (
 *   <>
 *     <FormInput form={form} name="name" label="Name" />
 *     <FormSelect form={form} name="type" label="Type" placeholder="Pick one">
 *       <SelectItem key="a">A</SelectItem>
 *       <SelectItem key="b">B</SelectItem>
 *     </FormSelect>
 *     <FormNumberInput form={form} name="count" label="Count" minValue={0} />
 *   </>
 * )}
 * ```
 *
 * **When to create a new Form* component** (e.g. FormSelect, FormInput, FormSlider):
 *
 * - The underlying UI component uses a different value/change API than ref + onChange
 *   (e.g. selectedKeys/onSelectionChange for Select, onValueChange for Slider/NumberInput).
 *   A Form* wrapper can bridge that API to react-hook-form in one place so every form
 *   doesn't repeat the wiring.
 *
 * - You want consistent styling and default props (variant, error
 *   display, startContent for icons) for that control across all forms. The Form*
 *   component is the single place to set those defaults and keep styling uniform.
 *
 * - You need form-specific behavior centralized: registration, reading errors from
 *   formState, and optional cleanup. Putting that in a Form* component avoids
 *   duplicating it in every renderFields.
 *
 * - You want to reuse the same control in both ManagedForm (via renderFields) and
 *   standalone (e.g. in a drawer or modal that has its own form). A Form* component
 *   that accepts form + name works in both cases.
 *
 * ---
 * Anti-patterns to avoid:
 *
 * - Creating new FormField config objects inside renderFields on every render (e.g. calling
 *   getFormTypeContent(scope) each time). That creates new component refs and can reset
 *   dropdowns. Memoize configs by scope/dependency and pick from a map (e.g. formTypeByScope[scope]).
 *
 * - Passing both form and register/errorMessage to FormFieldComponent when form is enough;
 *   prefer passing only form so the component derives the rest.
 *
 * - Using raw HeroUI Select with only defaultSelectedKeys for fields that depend on form
 *   state (e.g. type or useCase). Use FormSelect so selectedKeys stays in sync with form.
 *
 * - Assuming unmounted (conditional) fields appear in the submit payload. With
 *   shouldUnregister: true, only currently mounted fields are included.
 *
 * - **Using Controller with Form* components.** Form* inputs already register the field,
 *   sync value, and show errors. Wrapping them in Controller duplicates that and adds
 *   boilerplate (control, render prop, value/onChange wiring) with no benefit. Use
 *   Controller only when you need custom control (e.g. value transform, or a component
 *   without standard ref/onChange).
 */
export const ManagedForm = <T extends Record<string, any>>({
  validationSchema,
  className,
  defaultValues,
  onFormFailure,
  onFormSuccess,
  resolver = zodResolver,
  isActioning,
  renderFields,
  showSubmitButton,
  showResetButton,
  resetButtonText,
  submitButtonText,
  formRef,
}: Props<T>) => {
  const form = useForm<T>({
    mode: 'onChange',
    reValidateMode: 'onChange',
    resolver: resolver(validationSchema),
    defaultValues: defaultValues,
    // Only currently mounted (registered) fields are included in getValues() and submit.
    // When a field unmounts, it is unregistered and its value is removed from form state.
    // Form* components do not need to call unregister manually; this handles cleanup.
    shouldUnregister: true,
  });

  const onSubmit = (data: Record<string, unknown>) => {
    if (!isActioning && onFormSuccess) {
      const merged = mergeParsedFormValues(form.getValues() as T, data);
      onFormSuccess(merged);
      // Reset to merged submit snapshot so optional keys omitted by Zod do not clear
      // fields that were present in form state (see mergeParsedFormValues).
      resetFormValues(form, merged);
    }
  };

  const onError = (errors: Record<string, unknown>) => {
    // Handle form errors
    if (!isActioning && onFormFailure) {
      onFormFailure(errors as FieldErrors<T>, form.getValues() as T);
    }
  };

  return (
    <form
      ref={formRef}
      onSubmit={(event) => {
        // Portalled forms stay in their parent's React tree, so their submit
        // events must not trigger validation on an ancestor form.
        event.stopPropagation();
        void form.handleSubmit(onSubmit, onError)(event);
      }}
      className={className}
    >
      {renderFields(form)}
      {showResetButton || showSubmitButton ? (
        <div className="flex items-center gap-3 py-4">
          {showResetButton ? (
            <ActionButton
              secondary
              aria-label={resetButtonText}
              isDisabled={isActioning}
              type="button"
              onPress={() => resetFormValues(form, defaultValues)}
            >
              {resetButtonText}
            </ActionButton>
          ) : null}
          {showSubmitButton ? (
            <ActionButton
              primary
              aria-label={submitButtonText}
              isLoading={isActioning}
              type="submit"
            >
              {submitButtonText}
            </ActionButton>
          ) : null}
        </div>
      ) : null}
    </form>
  );
};

export default ManagedForm;
