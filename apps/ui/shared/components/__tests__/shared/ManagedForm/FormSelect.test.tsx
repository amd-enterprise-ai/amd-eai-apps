// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  SelectItem,
  FormSelect,
  ManagedForm,
} from '@amdenterpriseai/components';
import { IconUser } from '@tabler/icons-react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { vi } from 'vitest';

import { UseFormReturn } from 'react-hook-form';
import { ZodType, z } from 'zod';

type SampleFormData = {
  category: string;
};

const sampleFormSchema: ZodType<SampleFormData> = z.object({
  category: z.string().nonempty('Category is required'),
});

const categoryOptions = [
  { key: 'development', label: 'Development' },
  { key: 'design', label: 'Design' },
  { key: 'testing', label: 'Testing' },
];

// Helper function to render FormSelect with common props
const renderFormSelect = (
  formProps: Partial<
    React.ComponentProps<typeof ManagedForm<SampleFormData>>
  > = {},
  selectProps: Partial<
    React.ComponentProps<typeof FormSelect<SampleFormData>>
  > = {},
) => {
  const defaultFormProps = {
    onFormSuccess: vi.fn(),
    validationSchema: sampleFormSchema,
    defaultValues: { category: '', priority: '' },
  };

  return render(
    <ManagedForm<SampleFormData>
      {...defaultFormProps}
      {...formProps}
      renderFields={(form) => (
        <FormSelect<SampleFormData>
          form={form}
          name="category"
          label="Category"
          placeholder="Select a category"
          {...selectProps}
        >
          {categoryOptions.map((option) => (
            <SelectItem key={option.key}>{option.label}</SelectItem>
          ))}
        </FormSelect>
      )}
    />,
  );
};

describe('FormSelect', () => {
  it('renders select with label and placeholder', () => {
    renderFormSelect();

    expect(
      screen.getByRole('button', { name: /Category/ }),
    ).toBeInTheDocument();
  });

  it('renders select with icon', () => {
    renderFormSelect({}, { icon: IconUser });

    expect(
      screen.getByRole('button', { name: /Category/ }),
    ).toBeInTheDocument();
  });

  it('displays validation error when required field is empty', async () => {
    renderFormSelect({
      showSubmitButton: true,
      submitButtonText: 'Submit',
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    expect(screen.getByText('Category is required')).toBeInTheDocument();
  });

  it('handles selection and form submission', async () => {
    const mockOnFormSuccess = vi.fn();

    // Use a simple schema with just one required field for testing
    const simpleSchema = z.object({
      category: z.string().nonempty('Category is required'),
    });

    render(
      <ManagedForm<{ category: string }>
        defaultValues={{ category: '' }}
        showSubmitButton={true}
        submitButtonText="Submit"
        onFormSuccess={mockOnFormSuccess}
        validationSchema={simpleSchema}
        renderFields={(form) => (
          <FormSelect<{ category: string }>
            form={form}
            name="category"
            label="Category"
            placeholder="Select a category"
          >
            {categoryOptions.map((option) => (
              <SelectItem key={option.key}>{option.label}</SelectItem>
            ))}
          </FormSelect>
        )}
      />,
    );

    // Open select and choose option
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Category/ }));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: 'Development' }));
    });

    // Submit form
    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    // Wait for form processing
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200));
    });

    expect(mockOnFormSuccess).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'development' }),
    );
  });

  it('displays error styling when field is invalid', async () => {
    renderFormSelect(
      {
        showSubmitButton: true,
        submitButtonText: 'Submit',
      },
      {
        icon: IconUser,
      },
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    expect(screen.getByText('Category is required')).toBeInTheDocument();
    const categoryButton = screen.getByRole('button', { name: /Category/ });
    expect(categoryButton.closest('[data-invalid="true"]')).not.toBeNull();
  });

  it('handles disabled state', () => {
    renderFormSelect({}, { isDisabled: true });

    const categoryButton = screen.getByRole('button', { name: /Category/ });
    expect(categoryButton).toBeDisabled();
  });

  it('resets form values to initial state', async () => {
    const initialValues = { category: 'development', priority: 'low' };

    renderFormSelect({
      defaultValues: initialValues,
      showSubmitButton: true,
      submitButtonText: 'Submit',
      showResetButton: true,
      resetButtonText: 'Reset',
    });

    // Change selection
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Category/ }));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: 'Testing' }));
    });

    // Reset form using the button text
    await act(async () => {
      fireEvent.click(screen.getByText('Reset'));
    });

    // Verify reset to initial value
    const categoryButton = screen.getByRole('button', { name: /Category/ });
    expect(categoryButton).toHaveTextContent('Development');
  });

  it('keeps the second select option after submit when ManagedForm resets with shouldUnregister', async () => {
    enum Policy {
      OnPressure = 'OnPressure',
      Always = 'Always',
    }
    type PolicyForm = { policy: Policy };
    const policySchema: ZodType<PolicyForm> = z.object({
      policy: z.nativeEnum(Policy),
    });
    const mockOnFormSuccess = vi.fn();

    render(
      <ManagedForm<PolicyForm>
        defaultValues={{ policy: Policy.Always }}
        validationSchema={policySchema}
        showSubmitButton
        submitButtonText="Save"
        onFormSuccess={mockOnFormSuccess}
        renderFields={(form) => (
          <FormSelect<PolicyForm>
            form={form}
            name="policy"
            label="Policy"
            placeholder="Pick policy"
            disallowEmptySelection
          >
            <SelectItem key={Policy.OnPressure}>During GPU pressure</SelectItem>
            <SelectItem key={Policy.Always}>Always</SelectItem>
          </FormSelect>
        )}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    });

    await waitFor(() => {
      expect(mockOnFormSuccess).toHaveBeenCalledWith(
        expect.objectContaining({ policy: Policy.Always }),
      );
    });

    const policyTrigger = screen.getByRole('button', { name: /Policy/ });
    expect(policyTrigger).toHaveTextContent('Always');
  });

  it('discard resets to non-first default when disallowEmptySelection is set', async () => {
    enum Policy {
      OnPressure = 'OnPressure',
      Always = 'Always',
    }
    type PolicyForm = { policy: Policy };
    const policySchema: ZodType<PolicyForm> = z.object({
      policy: z.nativeEnum(Policy),
    });

    render(
      <ManagedForm<PolicyForm>
        defaultValues={{ policy: Policy.Always }}
        validationSchema={policySchema}
        showResetButton
        resetButtonText="Discard changes"
        onFormSuccess={vi.fn()}
        renderFields={(form) => (
          <FormSelect<PolicyForm>
            form={form}
            name="policy"
            label="Policy"
            placeholder="Pick policy"
            disallowEmptySelection
          >
            <SelectItem key={Policy.OnPressure}>During GPU pressure</SelectItem>
            <SelectItem key={Policy.Always}>Always active</SelectItem>
          </FormSelect>
        )}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Policy/ }));
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole('option', { name: 'During GPU pressure' }),
      );
    });

    const triggerBeforeDiscard = screen.getByRole('button', { name: /Policy/ });
    expect(triggerBeforeDiscard).toHaveTextContent('During GPU pressure');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    });

    expect(screen.getByRole('button', { name: /Policy/ })).toHaveTextContent(
      'Always active',
    );
  });

  it('shows no selected options after deselecting all options in a multi-select', async () => {
    renderFormSelect(
      { defaultValues: { category: 'development,design' } },
      { selectionMode: 'multiple' },
    );

    const categoryTrigger = screen.getByRole('button', { name: /Category/ });

    await act(async () => {
      fireEvent.click(categoryTrigger);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: 'Development' }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: 'Design' }));
    });

    expect(categoryTrigger).not.toHaveTextContent('Development');
    expect(categoryTrigger).not.toHaveTextContent('Design');
    expect(categoryTrigger).toHaveTextContent('Select a category');
  });

  it('shows no selected option after a single-select value is cleared to an empty string', async () => {
    let formRef: UseFormReturn<SampleFormData> | undefined;

    render(
      <ManagedForm<SampleFormData>
        defaultValues={{ category: 'development', priority: '' }}
        validationSchema={sampleFormSchema}
        onFormSuccess={vi.fn()}
        renderFields={(form) => {
          formRef = form;
          return (
            <FormSelect<SampleFormData>
              form={form}
              name="category"
              label="Category"
              placeholder="Select a category"
            >
              {categoryOptions.map((option) => (
                <SelectItem key={option.key}>{option.label}</SelectItem>
              ))}
            </FormSelect>
          );
        }}
      />,
    );

    const categoryTrigger = screen.getByRole('button', { name: /Category/ });
    expect(categoryTrigger).toHaveTextContent('Development');

    // Mirrors what FormSelect's own onSelectionChange does when the only
    // selection is cleared: setValue(name, '', { shouldDirty: true }).
    await act(async () => {
      formRef?.setValue('category', '', {
        shouldDirty: true,
        shouldValidate: true,
      });
    });

    expect(categoryTrigger).not.toHaveTextContent('Development');
    expect(categoryTrigger).toHaveTextContent('Select a category');
  });

  it('reflects a value cleared programmatically without dirtying the field', async () => {
    let formRef: UseFormReturn<SampleFormData> | undefined;

    render(
      <ManagedForm<SampleFormData>
        defaultValues={{ category: 'development', priority: '' }}
        validationSchema={sampleFormSchema}
        onFormSuccess={vi.fn()}
        renderFields={(form) => {
          formRef = form;
          return (
            <FormSelect<SampleFormData>
              form={form}
              name="category"
              label="Category"
              placeholder="Select a category"
            >
              {categoryOptions.map((option) => (
                <SelectItem key={option.key}>{option.label}</SelectItem>
              ))}
            </FormSelect>
          );
        }}
      />,
    );

    const categoryTrigger = screen.getByRole('button', { name: /Category/ });
    expect(categoryTrigger).toHaveTextContent('Development');

    await act(async () => {
      formRef?.setValue('category', '', { shouldDirty: false });
    });

    expect(categoryTrigger).toHaveTextContent('Select a category');
    expect(formRef?.getValues('category')).toBe('');
  });
});
