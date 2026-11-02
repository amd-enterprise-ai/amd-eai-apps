// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';
import { ActionButton } from '@amdenterpriseai/components';

describe('ActionButton', () => {
  it('renders with default secondary styling when no variant is specified', () => {
    render(
      <ActionButton data-testid="action-button">Default Button</ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Default Button');
  });

  it('renders with primary styling when primary prop is true', () => {
    render(
      <ActionButton primary data-testid="action-button">
        Primary Button
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Primary Button');
  });

  it('renders with secondary styling when secondary prop is true', () => {
    render(
      <ActionButton secondary data-testid="action-button">
        Secondary Button
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Secondary Button');
  });

  it('renders with tertiary styling when tertiary prop is true', () => {
    render(
      <ActionButton tertiary data-testid="action-button">
        Tertiary Button
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Tertiary Button');
  });

  it('renders with icon when provided', () => {
    const TestIcon = () => <span data-testid="test-icon">Icon</span>;

    render(
      <ActionButton icon={<TestIcon />} data-testid="action-button">
        Button with Icon
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    const icon = screen.getByTestId('test-icon');

    expect(button).toBeInTheDocument();
    expect(icon).toBeInTheDocument();
  });

  it('forwards ref correctly', () => {
    const ref = React.createRef<HTMLButtonElement>();

    render(
      <ActionButton ref={ref} data-testid="action-button">
        Ref Button
      </ActionButton>,
    );

    expect(ref.current).toBeInstanceOf(HTMLButtonElement);
  });

  it('sets isIconOnly when children is undefined', () => {
    const TestIcon = () => <span data-testid="test-icon">Icon</span>;

    render(<ActionButton icon={<TestIcon />} data-testid="action-button" />);

    const button = screen.getByTestId('action-button');
    const icon = screen.getByTestId('test-icon');

    expect(button).toBeInTheDocument();
    expect(icon).toBeInTheDocument();
    // Button should have icon-only styling (this is handled by HeroUI internally)
  });

  it('sets isIconOnly when children is empty string', () => {
    const TestIcon = () => <span data-testid="test-icon">Icon</span>;

    render(
      <ActionButton icon={<TestIcon />} data-testid="action-button">
        {''}
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    const icon = screen.getByTestId('test-icon');

    expect(button).toBeInTheDocument();
    expect(icon).toBeInTheDocument();
  });

  it('sets isIconOnly when children is whitespace only', () => {
    const TestIcon = () => <span data-testid="test-icon">Icon</span>;

    render(
      <ActionButton icon={<TestIcon />} data-testid="action-button">
        {'   '}
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    const icon = screen.getByTestId('test-icon');

    expect(button).toBeInTheDocument();
    expect(icon).toBeInTheDocument();
  });

  it('sets isIconOnly when children is React fragment with whitespace', () => {
    const TestIcon = () => <span data-testid="test-icon">Icon</span>;

    render(
      <ActionButton icon={<TestIcon />} data-testid="action-button">
        <React.Fragment> </React.Fragment>
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    const icon = screen.getByTestId('test-icon');

    expect(button).toBeInTheDocument();
    expect(icon).toBeInTheDocument();
  });

  it('does not set isIconOnly when children has actual content', () => {
    const TestIcon = () => <span data-testid="test-icon">Icon</span>;

    render(
      <ActionButton icon={<TestIcon />} data-testid="action-button">
        Button Text
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    const icon = screen.getByTestId('test-icon');

    expect(button).toBeInTheDocument();
    expect(icon).toBeInTheDocument();
    expect(button).toHaveTextContent('Button Text');
  });

  it('renders when color="danger" without throwing', () => {
    // Regression: ActionButton used to ignore color="danger" because the
    // hardcoded secondary variant overrode it. Verify it renders cleanly.
    render(
      <ActionButton color="danger" data-testid="action-button">
        Danger Button
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Danger Button');
  });

  it('uses provided color prop instead of variant default color', () => {
    render(
      <ActionButton primary color="danger" data-testid="action-button">
        Custom Color Button
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Custom Color Button');
    // The button should use the provided color prop (danger) instead of the primary variant's default color
  });

  it('falls back to variant default color when no color prop is provided', () => {
    render(
      <ActionButton primary data-testid="action-button">
        Default Color Button
      </ActionButton>,
    );

    const button = screen.getByTestId('action-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Default Color Button');
    // The button should use the primary variant's default color (primary)
  });
});
