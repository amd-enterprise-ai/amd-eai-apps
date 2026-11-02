// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { NumberField, NumberInput } from '@amdenterpriseai/components';
import { vi } from 'vitest';

describe('NumberField adapter', () => {
  it('exposes NumberField and NumberInput as the same component', () => {
    expect(NumberField).toBe(NumberInput);
  });
  it('renders NumberField', () => {
    render(
      <NumberField
        aria-label="Replicas"
        data-testid="number-field"
        defaultValue={2}
        step={1}
      />,
    );
    expect(screen.getByTestId('number-field')).toBeInTheDocument();
  });

  it('uses the visible label as its accessible name', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(<NumberField label="Replicas" defaultValue={2} step={1} />);
    const warnedAboutMissingLabel = warn.mock.calls.some(([message]) =>
      String(message).includes('must specify an aria-label'),
    );
    warn.mockRestore();

    expect(warnedAboutMissingLabel).toBe(false);
    expect(
      screen.getByRole('textbox', { name: 'Replicas' }),
    ).toBeInTheDocument();
  });

  it('renders NumberInput alias', () => {
    render(
      <NumberInput
        aria-label="Replicas"
        data-testid="number-input"
        defaultValue={1}
        step={1}
      />,
    );
    expect(screen.getByTestId('number-input')).toBeInTheDocument();
  });
  it('defaults to secondary variant', () => {
    const { container } = render(
      <NumberField
        aria-label="Replicas"
        data-testid="number-field"
        defaultValue={2}
        step={1}
      />,
    );
    expect(
      container.querySelector('.number-field--secondary'),
    ).toBeInTheDocument();
  });
  it('applies primary variant when requested', () => {
    const { container } = render(
      <NumberField
        aria-label="Replicas"
        variant="primary"
        defaultValue={2}
        step={1}
      />,
    );
    expect(
      container.querySelector('.number-field--primary'),
    ).toBeInTheDocument();
  });

  it('allows focus ring to paint outside the group', () => {
    const { container } = render(
      <NumberField aria-label="Replicas" defaultValue={2} step={1} />,
    );
    expect(container.querySelector('.number-field__group')).toHaveClass(
      'overflow-visible!',
    );
  });

  it('defaults to full width for narrow-container shrinking', () => {
    const { container } = render(
      <NumberField aria-label="Replicas" defaultValue={2} step={1} />,
    );
    expect(
      container.querySelector('.number-field--full-width'),
    ).toBeInTheDocument();
  });

  it('applies min-w-0 through the shrink chain', () => {
    const { container } = render(
      <NumberField aria-label="Replicas" defaultValue={2} step={1} />,
    );
    const outerBase = container.firstElementChild;
    expect(outerBase).toHaveClass('min-w-0');
    expect(container.querySelector('.number-field')).toHaveClass('min-w-0');
    const middleWrapper = container.querySelector('.number-field__group > div');
    expect(middleWrapper).toHaveClass('min-w-0');
  });

  it('right-aligns numeric input values', () => {
    render(<NumberField aria-label="Replicas" defaultValue={2} step={1} />);

    expect(screen.getByRole('textbox', { name: 'Replicas' })).toHaveClass(
      'text-right',
    );
  });

  it('keeps recipe-backed steppers in HeroUI slots and disables at bounds', () => {
    render(
      <NumberField
        aria-label="Replicas"
        maxValue={4}
        minValue={1}
        onStep={vi.fn()}
        value={1}
      />,
    );

    expect(screen.getByRole('button', { name: 'Decrease' })).toHaveAttribute(
      'data-slot',
      'decrease-button',
    );
    expect(screen.getByRole('button', { name: 'Decrease' })).toHaveClass(
      'number-field__decrement-button',
    );
    expect(screen.getByRole('button', { name: 'Decrease' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Increase' })).toHaveAttribute(
      'data-slot',
      'increase-button',
    );
    expect(screen.getByRole('button', { name: 'Increase' })).toHaveClass(
      'number-field__increment-button',
    );
  });

  it.each([{ isDisabled: true }, { isReadOnly: true }])(
    'does not step with arrow keys when unavailable',
    (props) => {
      const onStep = vi.fn();
      render(
        <NumberField
          aria-label="Replicas"
          onStep={onStep}
          value={NaN}
          {...props}
        />,
      );

      const input = screen.getByRole('textbox', { name: 'Replicas' });
      fireEvent.keyDown(input, { key: 'ArrowDown' });
      fireEvent.keyDown(input, { key: 'ArrowUp' });

      expect(onStep).not.toHaveBeenCalled();
    },
  );
});
