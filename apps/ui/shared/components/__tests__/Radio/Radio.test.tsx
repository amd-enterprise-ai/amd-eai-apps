// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { Radio, RadioGroup } from '@amdenterpriseai/components';

describe('Radio adapter', () => {
  it('renders unselected by default', () => {
    render(
      <RadioGroup value="">
        <Radio value="a" data-testid="radio">
          Option A
        </Radio>
      </RadioGroup>,
    );
    expect(screen.getByTestId('radio')).toBeInTheDocument();
    expect(screen.getByRole('radio')).not.toBeChecked();
  });

  it('renders selected when value matches', () => {
    render(
      <RadioGroup value="a">
        <Radio value="a" data-testid="radio">
          Option A
        </Radio>
      </RadioGroup>,
    );
    expect(screen.getByRole('radio')).toBeChecked();
  });

  it('respects isDisabled', () => {
    render(
      <RadioGroup value="">
        <Radio value="a" isDisabled data-testid="radio">
          Disabled
        </Radio>
      </RadioGroup>,
    );
    expect(screen.getByRole('radio')).toBeDisabled();
  });

  it('shows the label tooltip on focus', async () => {
    const user = userEvent.setup();
    render(
      <RadioGroup label="Fruit" tooltipContent="Choose your favorite fruit">
        <Radio value="apple">Apple</Radio>
      </RadioGroup>,
    );
    const trigger = screen.getByRole('button', {
      name: 'Choose your favorite fruit',
    });
    await user.tab();
    expect(trigger).toHaveFocus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Choose your favorite fruit',
    );
  });

  it('renders description after the clickable radio content', () => {
    render(
      <RadioGroup value="">
        <Radio value="a" description="Help text">
          Label
        </Radio>
      </RadioGroup>,
    );
    const description = screen.getByText('Help text');
    const content = screen
      .getByText('Label')
      .closest('[data-slot="radio-content"]');

    expect(description).toHaveAttribute('data-slot', 'description');
    expect(content).toBeInTheDocument();
    expect(content?.nextElementSibling).toBe(description);
    expect(description.closest('[data-slot="radio-content"]')).toBeNull();
  });

  it('does not select when the description is clicked', () => {
    const onChange = vi.fn();
    render(
      <RadioGroup value="" onChange={onChange}>
        <Radio value="a" description="Help text">
          Label
        </Radio>
      </RadioGroup>,
    );
    fireEvent.click(screen.getByText('Help text'));
    expect(onChange).not.toHaveBeenCalled();
  });
});
