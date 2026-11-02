// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';

import {
  FormSliderNumberInput,
  ManagedForm,
} from '@amdenterpriseai/components';
import { z } from 'zod';

type SampleFormData = {
  value: number;
};

const sampleFormSchema = z.object({
  value: z.number().min(0).max(100),
});

const renderValueField = (
  form: Parameters<
    React.ComponentProps<typeof ManagedForm<SampleFormData>>['renderFields']
  >[0],
) => (
  <FormSliderNumberInput
    form={form}
    name="value"
    aria-label="Value"
    minValue={0}
    maxValue={100}
  />
);

describe('FormSliderNumberInput', () => {
  it('keeps slider and number input in sync when slider changes', async () => {
    render(
      <ManagedForm<SampleFormData>
        defaultValues={{ value: 20 }}
        validationSchema={sampleFormSchema}
        onFormSuccess={vi.fn()}
        renderFields={(form) => (
          <FormSliderNumberInput
            form={form}
            name="value"
            aria-label="Value"
            minValue={0}
            maxValue={100}
          />
        )}
      />,
    );

    const slider = screen.getByRole('slider');
    const input = screen.getByRole('textbox', { name: 'Value' });

    expect(slider).toHaveValue('20');
    expect(input).toHaveValue('20');

    await act(async () => {
      fireEvent.change(slider, { target: { value: '45' } });
    });

    expect(slider).toHaveValue('45');
    expect(input).toHaveValue('45');
  });

  it('forwards step to the slider for single-unit increments', () => {
    render(
      <ManagedForm<SampleFormData>
        defaultValues={{ value: 14 }}
        validationSchema={sampleFormSchema}
        onFormSuccess={vi.fn()}
        renderFields={(form) => (
          <FormSliderNumberInput
            form={form}
            name="value"
            aria-label="CPU cores"
            minValue={0}
            maxValue={85}
            step={1}
          />
        )}
      />,
    );

    expect(screen.getByRole('slider')).toHaveAttribute('step', '1');
  });

  it('keeps slider and number input in sync when increment is pressed', async () => {
    render(
      <ManagedForm<SampleFormData>
        defaultValues={{ value: 20 }}
        validationSchema={sampleFormSchema}
        onFormSuccess={vi.fn()}
        renderFields={(form) => (
          <FormSliderNumberInput
            form={form}
            name="value"
            aria-label="Value"
            minValue={0}
            maxValue={100}
          />
        )}
      />,
    );

    const slider = screen.getByRole('slider');
    const input = screen.getByRole('textbox', { name: 'Value' });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Increase' }));
    });

    expect(input).toHaveValue('21');
    expect(slider).toHaveValue('21');
  });

  it('keeps slider value after form submit resets state', async () => {
    const onFormSuccess = vi.fn();

    render(
      <ManagedForm<SampleFormData>
        defaultValues={{ value: 20 }}
        validationSchema={sampleFormSchema}
        showSubmitButton
        submitButtonText="Save"
        onFormSuccess={onFormSuccess}
        renderFields={(form) => (
          <FormSliderNumberInput
            form={form}
            name="value"
            aria-label="Value"
            minValue={0}
            maxValue={100}
          />
        )}
      />,
    );

    const slider = screen.getByRole('slider');
    const input = screen.getByRole('textbox', { name: 'Value' });

    await act(async () => {
      fireEvent.change(slider, { target: { value: '45' } });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save' }));
      await Promise.resolve();
    });

    expect(onFormSuccess).toHaveBeenCalledWith({ value: 45 });
    expect(slider).toHaveValue('45');
    expect(input).toHaveValue('45');
  });

  it('shows defaultValues after ManagedForm remounts with a new key', () => {
    const { rerender } = render(
      <ManagedForm<SampleFormData>
        key="initial"
        defaultValues={{ value: 33 }}
        validationSchema={sampleFormSchema}
        onFormSuccess={vi.fn()}
        renderFields={renderValueField}
      />,
    );

    expect(screen.getByRole('slider')).toHaveValue('33');
    expect(screen.getByRole('textbox', { name: 'Value' })).toHaveValue('33');

    rerender(
      <ManagedForm<SampleFormData>
        key="remounted"
        defaultValues={{ value: 33 }}
        validationSchema={sampleFormSchema}
        onFormSuccess={vi.fn()}
        renderFields={renderValueField}
      />,
    );

    expect(screen.getByRole('slider')).toHaveValue('33');
    expect(screen.getByRole('textbox', { name: 'Value' })).toHaveValue('33');
  });
});
