// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';
import { Spinner } from '@amdenterpriseai/components';

describe('Spinner adapter', () => {
  it('renders with default props', () => {
    render(<Spinner data-testid="spinner" />);
    expect(screen.getByTestId('spinner')).toBeInTheDocument();
  });

  it('renders with size and color', () => {
    render(<Spinner size="sm" color="primary" data-testid="spinner" />);
    expect(screen.getByTestId('spinner')).toBeInTheDocument();
  });

  it('keeps HeroUI spinner root sizing contract for standalone layout', () => {
    render(<Spinner size="sm" data-testid="spinner" />);
    const root = screen.getByTestId('spinner');
    expect(root).toHaveAttribute('data-slot', 'spinner');
    expect(root).toHaveClass('spinner', 'spinner--sm');
  });

  it('renders with label', () => {
    render(<Spinner label="Loading" data-testid="spinner" />);
    expect(screen.getByText('Loading')).toBeInTheDocument();
  });
});
