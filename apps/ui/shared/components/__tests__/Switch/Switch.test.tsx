// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { Switch } from '@amdenterpriseai/components';

describe('Switch adapter', () => {
  it('renders unselected by default', () => {
    render(<Switch data-testid="switch">Label</Switch>);
    expect(screen.getByTestId('switch')).toBeInTheDocument();
    expect(screen.getByRole('switch')).not.toBeChecked();
  });
  it('renders selected when isSelected is true', () => {
    render(
      <Switch isSelected data-testid="switch">
        On
      </Switch>,
    );
    expect(screen.getByRole('switch')).toBeChecked();
  });
  it('calls onValueChange when toggled', () => {
    const onValueChange = vi.fn();
    render(
      <Switch isSelected={false} onValueChange={onValueChange}>
        Toggle
      </Switch>,
    );
    fireEvent.click(screen.getByRole('switch'));
    expect(onValueChange).toHaveBeenCalledWith(true);
  });
  it('respects isDisabled', () => {
    render(
      <Switch isDisabled data-testid="switch">
        Disabled
      </Switch>,
    );
    expect(screen.getByRole('switch')).toBeDisabled();
  });
  it('renders description below the label', () => {
    render(
      <Switch data-testid="switch" description="Help text">
        Label
      </Switch>,
    );
    expect(screen.getByText('Help text')).toBeInTheDocument();
    expect(screen.getByTestId('switch')).toHaveClass('grid');
  });
  it('applies text-muted to description via HeroUI default styles', () => {
    render(<Switch description="Help text">Label</Switch>);
    const description = screen.getByText('Help text');
    expect(description).toHaveClass('text-muted');
    expect(description).toHaveClass('col-start-2');
  });
  it('does not apply grid layout when description is absent', () => {
    render(<Switch data-testid="switch">Label</Switch>);
    expect(screen.getByTestId('switch')).not.toHaveClass('grid');
  });
  it('keeps label inside clickable switch content when description is set', () => {
    render(<Switch description="Help text">Label</Switch>);
    const labelText = screen.getByText('Label');
    expect(
      labelText.closest('[data-slot="switch-content"]'),
    ).toBeInTheDocument();
  });
  it('does not toggle when the description is clicked', () => {
    const onValueChange = vi.fn();
    render(
      <Switch
        isSelected={false}
        onValueChange={onValueChange}
        description="Help text"
      >
        Label
      </Switch>,
    );
    fireEvent.click(screen.getByText('Help text'));
    expect(onValueChange).not.toHaveBeenCalled();
  });
});
