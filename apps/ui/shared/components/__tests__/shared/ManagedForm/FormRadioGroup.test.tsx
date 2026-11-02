// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormRadioGroup,
  ManagedForm,
  Radio,
} from '@amdenterpriseai/components';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { z } from 'zod';

const formSchema = z.object({
  mode: z.string().min(1, 'Mode is required'),
});

type FormValues = z.infer<typeof formSchema>;

const renderForm = ({
  defaultValue = '',
  onFormSuccess = vi.fn(),
}: {
  defaultValue?: string;
  onFormSuccess?: (values: FormValues) => void;
} = {}) => {
  render(
    <ManagedForm<FormValues>
      defaultValues={{ mode: defaultValue }}
      validationSchema={formSchema}
      onFormSuccess={onFormSuccess}
      showSubmitButton
      submitButtonText="Submit"
      renderFields={(form) => (
        <FormRadioGroup form={form} name="mode" label="Mode">
          <Radio value="a">Option A</Radio>
          <Radio value="b">Option B</Radio>
        </FormRadioGroup>
      )}
    />,
  );
};

describe('FormRadioGroup', () => {
  it('selects the configured default value', () => {
    renderForm({ defaultValue: 'b' });

    expect(screen.getByRole('radio', { name: 'Option B' })).toBeChecked();
  });

  it('updates form state when an option is selected', async () => {
    const onFormSuccess = vi.fn();
    renderForm({ onFormSuccess });

    fireEvent.click(screen.getByRole('radio', { name: 'Option A' }));
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    await waitFor(() =>
      expect(onFormSuccess).toHaveBeenCalledWith({ mode: 'a' }),
    );
  });

  it('renders the validation error and invalid state', async () => {
    renderForm();

    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    expect(await screen.findByText('Mode is required')).toBeInTheDocument();
    expect(screen.getByRole('radiogroup')).toHaveAttribute(
      'data-invalid',
      'true',
    );
  });
});
