// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import React, { useState } from 'react';

import { ManagedForm } from '../../../src/ManagedForm/ManagedForm';
import { FormFieldComponent } from '../../../src/ManagedForm/FormFieldComponent';
import { FormInput } from '../../../src/ManagedForm/FormInput';
import { FormNumberInput } from '../../../src/ManagedForm/FormNumberInput';
import { FormPasswordInput } from '../../../src/ManagedForm/FormPasswordInput';
import { FormSelect } from '../../../src/ManagedForm/FormSelect';
import { FormSlider } from '../../../src/ManagedForm/FormSlider';
import { FormSliderNumberInput } from '../../../src/ManagedForm/FormSliderNumberInput';
import { FormFileUpload } from '../../../src/ManagedForm/FormFileUpload/FormFileUpload';
import type { FormField } from '@amdenterpriseai/types';
import { SelectItem } from '@amdenterpriseai/components';

import { ZodType, z } from 'zod';

type SampleFormData = { name: string; email: string };

const sampleFormSchema: ZodType<SampleFormData> = z.object({
  name: z.string().trim().nonempty('Name is required'),
  email: z
    .string()
    .trim()
    .nonempty('Email is required')
    .email('Valid email is required'),
});

const formElements: FormField<SampleFormData>[] = [
  { name: 'name', label: 'Name', isRequired: true },
  { name: 'email', label: 'Email', isRequired: true },
];

export default {
  title: 'Components/ManagedForm/Dynamic patterns',
} satisfies StoryDefault;

// ============================================================================
// FormFieldComponent with only form prop (recommended pattern)
// ============================================================================

export const FormFieldComponentWithFormOnly: Story = () => {
  const [lastSubmit, setLastSubmit] = useState<SampleFormData | null>(null);

  return (
    <div className="flex flex-col gap-4 max-w-md">
      <p className="text-sm text-muted">
        Pass only <code>form</code> to FormFieldComponent; register and
        errorMessage are derived. Fill the fields and submit to see the payload
        below.
      </p>
      <ManagedForm<SampleFormData>
        showSubmitButton
        submitButtonText="Submit"
        onFormSuccess={(data) => setLastSubmit(data)}
        validationSchema={sampleFormSchema}
        defaultValues={{ name: '', email: '' }}
        renderFields={(form) => (
          <>
            {formElements.map((field) => (
              <FormFieldComponent<SampleFormData>
                key={field.name}
                formField={field}
                form={form}
              />
            ))}
          </>
        )}
      />
      {lastSubmit && (
        <pre className="text-xs p-3 bg-default rounded-lg overflow-auto">
          {JSON.stringify(lastSubmit, null, 2)}
        </pre>
      )}
    </div>
  );
};

// ============================================================================
// Conditional field (shouldUnregister) — unmounted FormSelect excluded from submit
// ============================================================================

type ConditionalFormData = { name: string; category?: string };

const conditionalSchema = z.object({
  name: z.string().nonempty('Name required'),
  // When the category FormSelect is hidden (unmounted) it may still appear as "" from defaultValues;
  // treat empty string as undefined so validation passes.
  category: z.preprocess(
    (v) => (v === '' || v === undefined ? undefined : v),
    z.string().min(1, 'Category required').optional(),
  ),
}) as ZodType<ConditionalFormData>;

export const ConditionalFieldExcludedFromSubmit: Story = () => {
  const [showCategory, setShowCategory] = useState(true);
  const [lastSubmit, setLastSubmit] = useState<ConditionalFormData | null>(
    null,
  );

  return (
    <div className="flex flex-col gap-4 max-w-md">
      <p className="text-sm text-muted">
        With <code>shouldUnregister: true</code>, only mounted fields are in the
        submit payload. Toggle the category FormSelect off, then submit — the
        payload below will not include <code>category</code>.
      </p>
      <ManagedForm<ConditionalFormData>
        showSubmitButton
        submitButtonText="Submit"
        onFormSuccess={(data) => setLastSubmit(data)}
        validationSchema={conditionalSchema}
        defaultValues={{ name: '', category: '' }}
        renderFields={(form) => (
          <>
            <FormFieldComponent<ConditionalFormData>
              formField={{ name: 'name', label: 'Name' }}
              form={form}
            />
            {showCategory && (
              <FormSelect<ConditionalFormData>
                form={form}
                name="category"
                label="Category"
                placeholder="Pick a category"
              >
                <SelectItem key="hardware">Hardware</SelectItem>
                <SelectItem key="software">Software</SelectItem>
                <SelectItem key="other">Other</SelectItem>
              </FormSelect>
            )}
          </>
        )}
      />
      <button
        type="button"
        className="px-3 py-1.5 text-sm rounded-md bg-default-hover hover:bg-default-hover"
        onClick={() => setShowCategory((prev) => !prev)}
      >
        {showCategory
          ? 'Hide category (FormSelect)'
          : 'Show category (FormSelect)'}
      </button>
      {lastSubmit && (
        <pre className="text-xs p-3 bg-default rounded-lg overflow-auto">
          {JSON.stringify(lastSubmit, null, 2)}
        </pre>
      )}
    </div>
  );
};

// ============================================================================
// Basic form with submit payload display (classic: register + defaultValue)
// ============================================================================

export const BasicWithSubmitPayload: Story = () => {
  const [lastSubmit, setLastSubmit] = useState<SampleFormData | null>(null);

  return (
    <div className="flex flex-col gap-4 max-w-md">
      <ManagedForm<SampleFormData>
        showSubmitButton
        submitButtonText="Submit"
        showResetButton
        resetButtonText="Reset"
        onFormSuccess={(data) => {
          setLastSubmit(data);
          alert(JSON.stringify(data, null, 2));
        }}
        validationSchema={sampleFormSchema}
        defaultValues={{ name: '', email: '' }}
        renderFields={(form) => (
          <>
            {formElements.map((field) => (
              <FormFieldComponent<SampleFormData>
                key={field.name}
                formField={field}
                defaultValue={form.formState.defaultValues?.[field.name] ?? ''}
                register={form.register}
                form={form}
              />
            ))}
          </>
        )}
      />
      {lastSubmit && (
        <pre className="text-xs p-3 bg-default rounded-lg overflow-auto">
          {JSON.stringify(lastSubmit, null, 2)}
        </pre>
      )}
    </div>
  );
};

// ============================================================================
// Form* components — example usage of each input type
// ============================================================================

type AllInputsFormData = {
  text: string;
  number?: number;
  password: string;
  choice: string;
  volume: number;
  cpuCores: number;
  attachment?: File | FileList | null;
};

const allInputsSchema: ZodType<AllInputsFormData> = z.object({
  text: z.string().min(1, 'Text is required'),
  number: z.number().min(0).max(100).optional(),
  password: z.string().min(6, 'Min 6 characters'),
  choice: z.string().min(1, 'Pick one'),
  volume: z.number().min(0).max(100),
  cpuCores: z.number().min(0).max(85),
  attachment: z.any().optional(),
});

export const FormInputComponentsShowcase: Story = () => {
  const [lastSubmit, setLastSubmit] = useState<AllInputsFormData | null>(null);

  return (
    <div className="flex flex-col gap-4 max-w-md">
      <p className="text-sm text-muted">
        Example usage of each Form* component: FormInput, FormNumberInput,
        FormPasswordInput, FormSelect, FormSlider, FormSliderNumberInput,
        FormFileUpload.
      </p>
      <ManagedForm<AllInputsFormData>
        showSubmitButton
        submitButtonText="Submit"
        onFormSuccess={(data) => setLastSubmit(data)}
        validationSchema={allInputsSchema}
        defaultValues={{
          text: '',
          number: undefined,
          password: '',
          choice: '',
          volume: 50,
          cpuCores: 14,
          attachment: null,
        }}
        renderFields={(form) => (
          <div className="flex flex-col gap-4">
            {/* FormInput — text */}
            <FormInput<AllInputsFormData>
              form={form}
              name="text"
              label="Text (FormInput)"
              placeholder="Enter text"
            />

            {/* FormNumberInput — numeric with min/max */}
            <FormNumberInput<AllInputsFormData>
              form={form}
              name="number"
              label="Number (FormNumberInput)"
              placeholder="0–100"
              minValue={0}
              maxValue={100}
            />

            {/* FormPasswordInput — password with show/hide */}
            <FormPasswordInput<AllInputsFormData>
              form={form}
              name="password"
              label="Password (FormPasswordInput)"
              placeholder="Min 6 characters"
            />

            {/* FormSelect — single choice, selectedKeys from form.watch(name) */}
            <FormSelect<AllInputsFormData>
              form={form}
              name="choice"
              label="Choice (FormSelect)"
              placeholder="Pick one"
            >
              <SelectItem key="a">Option A</SelectItem>
              <SelectItem key="b">Option B</SelectItem>
              <SelectItem key="c">Option C</SelectItem>
            </FormSelect>

            {/* FormSlider — numeric range */}
            <FormSlider<AllInputsFormData>
              form={form}
              name="volume"
              label="Volume (FormSlider)"
              minValue={0}
              maxValue={100}
              step={5}
              description="0–100"
            />

            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">
                CPU cores (FormSliderNumberInput)
              </span>
              <FormSliderNumberInput<AllInputsFormData>
                form={form}
                name="cpuCores"
                aria-label="CPU cores"
                minValue={0}
                maxValue={85}
                step={1}
              />
            </div>

            {/* FormFileUpload — single or multiple files */}
            <FormFileUpload<AllInputsFormData>
              form={form}
              name="attachment"
              label="Attachment (FormFileUpload)"
              placeholder="Drop file or click to browse"
              multiple={false}
            />
          </div>
        )}
      />
      {lastSubmit && (
        <pre className="text-xs p-3 bg-default rounded-lg overflow-auto max-h-48">
          {JSON.stringify(
            {
              ...lastSubmit,
              attachment: lastSubmit.attachment
                ? lastSubmit.attachment instanceof File
                  ? lastSubmit.attachment.name
                  : Array.from(lastSubmit.attachment as FileList).map(
                      (f) => f.name,
                    )
                : null,
            },
            null,
            2,
          )}
        </pre>
      )}
    </div>
  );
};
