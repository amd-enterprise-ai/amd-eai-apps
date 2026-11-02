// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconCalculator } from '@tabler/icons-react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { FormNumberInput } from '@amdenterpriseai/components';
import {
  Accordion,
  AccordionItem,
  ManagedForm,
} from '@amdenterpriseai/components';

import userEvent from '@testing-library/user-event';
import { ZodType, z } from 'zod';

type SampleFormData = {
  count: number;
  price: number;
};

type OptionalNumberFormData = {
  count?: number;
};

const sampleFormSchema: ZodType<SampleFormData> = z.object({
  count: z.number().min(1, 'Count must be at least 1'),
  price: z.number().min(0, 'Price must be non-negative'),
});

// Helper function to render FormNumberInput with common props
const renderFormNumberInput = (
  formProps: Partial<
    React.ComponentProps<typeof ManagedForm<SampleFormData>>
  > = {},
  inputProps: Partial<{
    name: keyof SampleFormData;
    label: string;
    placeholder: string;
    icon: React.ComponentType<any>;
    isDisabled: boolean;
    isReadOnly: boolean;
    step: number;
    className: string;
  }> = {},
) => {
  const defaultFormProps = {
    onFormSuccess: vi.fn(),
    validationSchema: sampleFormSchema,
    defaultValues: { count: 0, price: 0 },
  };

  return render(
    <ManagedForm<SampleFormData>
      {...defaultFormProps}
      {...formProps}
      renderFields={(form) => (
        <FormNumberInput
          form={form as any}
          name="count"
          label="Count"
          placeholder="Enter count"
          {...inputProps}
        />
      )}
    />,
  );
};

describe('FormNumberInput', () => {
  it('renders number input with label and placeholder', () => {
    renderFormNumberInput();

    expect(screen.getByLabelText('Count')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter count')).toBeInTheDocument();
  });

  it('displays defaultValues on mount', () => {
    renderFormNumberInput(
      {
        defaultValues: { count: 42, price: 0 },
      },
      { name: 'count' },
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    expect(input.value).toBe('42');
  });

  it('renders decrement and increment stepper controls', () => {
    renderFormNumberInput();

    expect(
      screen.getByRole('button', { name: 'Decrease' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Increase' }),
    ).toBeInTheDocument();
  });

  it('renders number input with icon', () => {
    renderFormNumberInput({}, { icon: IconCalculator });

    expect(screen.getByLabelText('Count')).toBeInTheDocument();
    // Icon should be present in the DOM
    const iconElement = document.querySelector('svg');
    expect(iconElement).toBeInTheDocument();
  });

  it('handles number input and updates form value', async () => {
    const user = userEvent.setup();
    renderFormNumberInput();

    const input = screen.getByLabelText('Count') as HTMLInputElement;

    await user.clear(input);
    await user.type(input, '42');

    expect(input.value).toBe('42');
  });

  it('handles formatted numbers with commas', async () => {
    const user = userEvent.setup();
    renderFormNumberInput();

    const input = screen.getByLabelText('Count') as HTMLInputElement;

    await user.clear(input);
    await user.type(input, '1,234');

    // Blur to trigger parseFormattedNumber
    await user.tab();

    await waitFor(() => {
      expect(input.value).toBe('1,234');
    });
  });

  it('displays validation error when field is invalid', async () => {
    renderFormNumberInput(
      {
        showSubmitButton: true,
        submitButtonText: 'Submit',
        defaultValues: { count: -1, price: 0 },
      },
      { name: 'count' },
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    expect(screen.getByText('Count must be at least 1')).toBeInTheDocument();
  });

  it('handles form submission with valid number', async () => {
    const mockOnFormSuccess = vi.fn();
    const user = userEvent.setup();

    // Use a simple schema with just one required field for testing
    const simpleSchema = z.object({
      count: z.number().min(1, 'Count must be at least 1'),
    });

    render(
      <ManagedForm<{ count: number }>
        defaultValues={{ count: 0 }}
        showSubmitButton={true}
        submitButtonText="Submit"
        onFormSuccess={mockOnFormSuccess}
        validationSchema={simpleSchema}
        renderFields={(form) => (
          <FormNumberInput
            form={form as any}
            name="count"
            label="Count"
            placeholder="Enter count"
          />
        )}
      />,
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;

    // Enter a valid number
    await user.clear(input);
    await user.type(input, '10');
    await user.tab(); // Trigger blur

    // Submit form
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    // Wait for form processing
    await waitFor(() => {
      expect(mockOnFormSuccess).toHaveBeenCalledWith(
        expect.objectContaining({ count: 10 }),
      );
    });
  });

  it('displays error styling when field is invalid', async () => {
    renderFormNumberInput(
      {
        showSubmitButton: true,
        submitButtonText: 'Submit',
        defaultValues: { count: -1, price: 0 },
      },
      {
        icon: IconCalculator,
        name: 'count',
      },
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    const input = screen.getByLabelText('Count');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Count must be at least 1')).toBeInTheDocument();
  });

  it('handles disabled state', () => {
    renderFormNumberInput({}, { isDisabled: true });

    const input = screen.getByLabelText('Count');
    expect(input).toBeDisabled();
  });

  it('handles readonly state with proper styling', () => {
    renderFormNumberInput({}, { isReadOnly: true });

    const input = screen.getByLabelText('Count');
    expect(input).toHaveAttribute('readonly');
  });

  it('handles empty input value correctly', async () => {
    const user = userEvent.setup();
    renderFormNumberInput();

    const input = screen.getByLabelText('Count') as HTMLInputElement;

    // Clear the input
    await user.clear(input);
    await user.tab(); // Trigger blur

    expect(input.value).toBe('');
  });

  it('handles invalid number input', async () => {
    const user = userEvent.setup();
    renderFormNumberInput();

    const input = screen.getByLabelText('Count') as HTMLInputElement;

    // Try to enter invalid characters (should be filtered by NumberInput)
    await user.clear(input);
    await user.type(input, 'abc');

    // NumberInput should prevent non-numeric input
    expect(input.value).toBe('');
  });

  it('handles decimal numbers', async () => {
    const user = userEvent.setup();

    // Create schema that allows decimals
    const decimalSchema = z.object({
      price: z.number().min(0, 'Price must be non-negative'),
    });

    render(
      <ManagedForm<{ price: number }>
        defaultValues={{ price: 0 }}
        validationSchema={decimalSchema}
        onFormSuccess={vi.fn()}
        renderFields={(form) => (
          <FormNumberInput
            form={form as any}
            name="price"
            label="Price"
            placeholder="Enter price"
          />
        )}
      />,
    );

    const input = screen.getByLabelText('Price') as HTMLInputElement;

    await user.clear(input);
    await user.type(input, '19.99');

    expect(input.value).toBe('19.99');
  });

  it('triggers onBlur correctly with setTimeout', async () => {
    const user = userEvent.setup();
    renderFormNumberInput();

    const input = screen.getByLabelText('Count') as HTMLInputElement;

    await user.clear(input);
    await user.type(input, '123');

    // Focus and then blur to trigger the handleBlur function
    await user.tab();

    // The component uses setTimeout in handleBlur, so we need to wait
    await waitFor(() => {
      expect(input.value).toBe('123');
    });
  });

  it('handles large numbers with comma formatting', async () => {
    const user = userEvent.setup();
    renderFormNumberInput();

    const input = screen.getByLabelText('Count') as HTMLInputElement;

    await user.clear(input);
    await user.type(input, '1,000,000');
    await user.tab(); // Trigger blur

    await waitFor(() => {
      expect(input.value).toBe('1,000,000');
    });
  });

  it('handles step increments when step prop is provided', async () => {
    const user = userEvent.setup();
    renderFormNumberInput({}, { step: 10 });

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    expect(input.value).toBe('0');

    await user.click(screen.getByRole('button', { name: 'Increase' }));

    await waitFor(() => {
      expect(input.value).toBe('10');
    });
  });

  it('steps from emptyValue when an untouched input is increased', async () => {
    const user = userEvent.setup();
    render(
      <ManagedForm<OptionalNumberFormData>
        defaultValues={{}}
        onFormSuccess={vi.fn()}
        validationSchema={z.object({ count: z.number().optional() })}
        renderFields={(form) => (
          <FormNumberInput
            emptyValue={3}
            form={form}
            label="Count"
            maxValue={10}
            minValue={1}
            name="count"
            step={1}
          />
        )}
      />,
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    await user.click(screen.getByRole('button', { name: 'Increase' }));

    await waitFor(() => {
      expect(input.value).toBe('4');
    });
  });

  it('clamps an emptyValue step to the minimum', async () => {
    const user = userEvent.setup();
    render(
      <ManagedForm<OptionalNumberFormData>
        defaultValues={{}}
        onFormSuccess={vi.fn()}
        validationSchema={z.object({ count: z.number().optional() })}
        renderFields={(form) => (
          <FormNumberInput
            emptyValue={1}
            form={form}
            label="Count"
            minValue={1}
            name="count"
            step={5}
          />
        )}
      />,
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    await user.click(screen.getByRole('button', { name: 'Decrease' }));

    await waitFor(() => {
      expect(input.value).toBe('1');
    });
  });

  it('clamps an emptyValue step to the maximum', async () => {
    const user = userEvent.setup();
    render(
      <ManagedForm<OptionalNumberFormData>
        defaultValues={{}}
        onFormSuccess={vi.fn()}
        validationSchema={z.object({ count: z.number().optional() })}
        renderFields={(form) => (
          <FormNumberInput
            emptyValue={10}
            form={form}
            label="Count"
            maxValue={10}
            name="count"
            step={1}
          />
        )}
      />,
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    await user.click(screen.getByRole('button', { name: 'Increase' }));

    await waitFor(() => {
      expect(input.value).toBe('10');
    });
  });

  it('uses the default stepper behavior without emptyValue', async () => {
    const user = userEvent.setup();
    render(
      <ManagedForm<OptionalNumberFormData>
        defaultValues={{}}
        onFormSuccess={vi.fn()}
        validationSchema={z.object({ count: z.number().optional() })}
        renderFields={(form) => (
          <FormNumberInput
            form={form}
            label="Count"
            minValue={2}
            name="count"
            step={1}
          />
        )}
      />,
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    await user.click(screen.getByRole('button', { name: 'Increase' }));

    await waitFor(() => {
      expect(input.value).toBe('2');
    });
  });

  it('steps from emptyValue when ArrowUp is pressed', async () => {
    render(
      <ManagedForm<OptionalNumberFormData>
        defaultValues={{}}
        onFormSuccess={vi.fn()}
        validationSchema={z.object({ count: z.number().optional() })}
        renderFields={(form) => (
          <FormNumberInput
            emptyValue={3}
            form={form}
            label="Count"
            minValue={1}
            name="count"
            step={1}
          />
        )}
      />,
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    fireEvent.keyDown(input, { key: 'ArrowUp' });

    await waitFor(() => {
      expect(input.value).toBe('4');
    });
  });

  it('applies custom className correctly', () => {
    const customClass = 'custom-test-class';
    renderFormNumberInput({}, { className: customClass });

    // Check that the component renders with the custom class somewhere in its tree
    const componentContainer = document.querySelector(`.${customClass}`);
    expect(componentContainer).toBeInTheDocument();
  });

  it('renders inside expanded accordion without clipping focus ring wrapper', async () => {
    const user = userEvent.setup();
    render(
      <ManagedForm<SampleFormData>
        onFormSuccess={vi.fn()}
        validationSchema={sampleFormSchema}
        defaultValues={{ count: 0, price: 0 }}
        renderFields={(form) => (
          <Accordion defaultSelectedKeys={['advanced']}>
            <AccordionItem id="advanced" title="Advanced settings">
              <FormNumberInput
                form={form as any}
                name="count"
                label="Count"
                placeholder="Enter count"
              />
            </AccordionItem>
          </Accordion>
        )}
      />,
    );

    await user.tab();
    await user.tab();

    expect(document.querySelector('.accordion__panel')).toHaveClass(
      'data-[expanded=true]:!overflow-visible',
    );
    expect(document.querySelector('.number-field__group')).toHaveClass(
      'overflow-visible!',
    );
  });

  it('submits an optional field left at its undefined default without a validation error', async () => {
    // Regression test: an optional numeric field whose default is `undefined`
    // (e.g. an "Auto" hyperparameter left unset) must submit successfully even
    // after being focused and blurred without typing — it should never resolve
    // to a stray empty-string/NaN sentinel that a `.optional()` schema rejects.
    const mockOnFormSuccess = vi.fn();
    type OptionalFormData = { count?: number };
    const optionalSchema: ZodType<OptionalFormData> = z.object({
      count: z.number().min(1, 'Count must be at least 1').optional(),
    });

    render(
      <ManagedForm<OptionalFormData>
        defaultValues={{ count: undefined }}
        showSubmitButton
        submitButtonText="Submit"
        onFormSuccess={mockOnFormSuccess}
        validationSchema={optionalSchema}
        renderFields={(form) => (
          <Accordion defaultSelectedKeys={['advanced']}>
            <AccordionItem id="advanced" title="Advanced settings">
              <FormNumberInput
                form={form as any}
                name="count"
                label="Count"
                placeholder="Auto"
              />
            </AccordionItem>
          </Accordion>
        )}
      />,
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    expect(input.value).toBe('');

    // Focus and blur without typing anything.
    fireEvent.focus(input);
    fireEvent.blur(input);

    expect(input.value).toBe('');
    expect(input).not.toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByText('Count must be at least 1')).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    await waitFor(() => {
      expect(mockOnFormSuccess).toHaveBeenCalledWith(
        expect.objectContaining({ count: undefined }),
      );
    });
    expect(screen.queryByText('Count must be at least 1')).toBeNull();
  });

  it('submits an optional numeric field as undefined, not NaN, after it is cleared', async () => {
    // Regression: FormNumberInput must map an empty NumberField commit to `undefined`,
    // never a NaN sentinel, so an optional field the user clears submits cleanly instead
    // of failing `z.number().optional()` or reaching the backend as NaN. react-stately
    // itself reports an empty commit as `NaN` (not `undefined`), so NumberField's `else`
    // branch forwards that NaN straight through to onValueChange — committing a real
    // value and then clearing it drives updateFormValue with that non-finite value, the
    // exact input its `Number.isFinite(next) ? next : undefined` guard exists to map.
    const mockOnFormSuccess = vi.fn();
    type OptionalFormData = { count?: number };
    const optionalSchema: ZodType<OptionalFormData> = z.object({
      count: z.number().min(1, 'Count must be at least 1').optional(),
    });

    render(
      <ManagedForm<OptionalFormData>
        defaultValues={{ count: undefined }}
        showSubmitButton
        submitButtonText="Submit"
        onFormSuccess={mockOnFormSuccess}
        validationSchema={optionalSchema}
        renderFields={(form) => (
          <Accordion defaultSelectedKeys={['advanced']}>
            <AccordionItem id="advanced" title="Advanced settings">
              <FormNumberInput
                form={form as any}
                name="count"
                label="Count"
                placeholder="Auto"
              />
            </AccordionItem>
          </Accordion>
        )}
      />,
    );

    const input = screen.getByLabelText('Count') as HTMLInputElement;
    expect(input.value).toBe('');

    // Commit a real value, then clear it: the second blur commits an empty
    // NumberField, firing onValueChange(NaN) through the guard.
    fireEvent.change(input, { target: { value: '4' } });
    fireEvent.blur(input);
    await waitFor(() => expect(input.value).toBe('4'));

    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);
    await waitFor(() => expect(input.value).toBe(''));

    // With the guard intact the cleared value is `undefined`, so the optional
    // schema stays valid; a NaN would surface an invalid_type error here.
    expect(input).not.toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByText('Count must be at least 1')).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    await waitFor(() => expect(mockOnFormSuccess).toHaveBeenCalledTimes(1));
    const submitted = mockOnFormSuccess.mock.calls[0][0];
    expect(submitted.count).toBeUndefined();
  });
});
