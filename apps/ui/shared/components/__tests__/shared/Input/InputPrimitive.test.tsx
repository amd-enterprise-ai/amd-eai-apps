// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { Input } from '@amdenterpriseai/components';

describe('Input adapter', () => {
  it('renders with placeholder', () => {
    render(<Input placeholder="Search…" data-testid="input" />);
    expect(screen.getByPlaceholderText('Search…')).toBeInTheDocument();
  });
  it('renders with value', () => {
    render(<Input value="hello" data-testid="input" onChange={() => {}} />);
    expect(screen.getByTestId('input')).toHaveValue('hello');
  });
  it('calls onChange when typing', async () => {
    const user = userEvent.setup();
    const handleChange = vi.fn();
    render(<Input data-testid="input" onChange={handleChange} />);
    await user.type(screen.getByTestId('input'), 'a');
    expect(handleChange).toHaveBeenCalled();
  });
  it('renders isInvalid with errorMessage', () => {
    const { container } = render(
      <Input
        isInvalid
        errorMessage="Required field"
        label="Name"
        data-testid="input"
      />,
    );
    expect(screen.getByText('Required field')).toBeInTheDocument();
    expect(container.querySelector('.input-group--secondary')).toHaveAttribute(
      'data-invalid',
      'true',
    );
  });
  it('passes isDisabled', () => {
    render(<Input isDisabled data-testid="input" />);
    expect(screen.getByTestId('input')).toBeDisabled();
  });
  it('defaults to secondary variant on InputGroup', () => {
    const { container } = render(<Input data-testid="input" />);
    expect(
      container.querySelector('.input-group--secondary'),
    ).toBeInTheDocument();
  });
  it('applies primary variant when requested', () => {
    const { container } = render(
      <Input data-testid="input" variant="primary" />,
    );
    expect(
      container.querySelector('.input-group--primary'),
    ).toBeInTheDocument();
  });
});
