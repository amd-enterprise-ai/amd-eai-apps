// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconFilter } from '@tabler/icons-react';
import React from 'react';
import { render, screen } from '@testing-library/react';

import { FilterButtonTrigger } from '@amdenterpriseai/components';

// Mock HeroUI components
vi.mock('@heroui/react', async () => {
  const original = await vi.importActual<any>('@heroui/react');
  return {
    ...original,
    cn: (...args: any[]) => {
      return original.cn(...args);
    },
    Chip: ({ children, color, variant, startContent, className }: any) => (
      <div
        data-testid="chip"
        data-color={color}
        data-variant={variant}
        className={className}
      >
        {startContent && (
          <div data-testid="chip-start-content">{startContent}</div>
        )}
        {children}
      </div>
    ),
    Button: ({
      children,
      color,
      startContent,
      endContent,
      variant,
      isIconOnly,
      onPress,
      'aria-label': ariaLabel,
      className,
    }: any) => (
      <button
        data-testid={isIconOnly ? 'icon-button' : 'button'}
        data-color={color}
        data-variant={variant}
        data-icon-only={isIconOnly}
        aria-label={ariaLabel}
        className={className}
        onClick={onPress}
      >
        {startContent && <div data-testid="start-content">{startContent}</div>}
        {children}
        {endContent && <div data-testid="end-content">{endContent}</div>}
      </button>
    ),
    DropdownTrigger: ({ children }: any) => (
      <div data-testid="dropdown-trigger">{children}</div>
    ),
  };
});
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    Tooltip: ({ children, content, delay, size, className }: any) => (
      <div
        data-testid="tooltip"
        data-content={content}
        data-delay={delay}
        data-size={size}
        className={className}
      >
        {children}
      </div>
    ),
  };
});

vi.mock('../../../src/Tooltip', () => ({
  Tooltip: ({ children, content, delay, size, className }: any) => (
    <div
      data-testid="tooltip"
      data-content={content}
      data-delay={delay}
      data-size={size}
      className={className}
    >
      {children}
    </div>
  ),
}));

describe('FilterButtonTrigger Component', () => {
  const defaultProps = {
    label: 'Status',
    numberOfSelectedKeys: 1,
  };

  it('renders correctly with default props (inactive state)', () => {
    render(<FilterButtonTrigger {...defaultProps} />);

    const input = screen.getByDisplayValue('Status');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('readonly');
    expect(input).toHaveAttribute('aria-hidden', 'true');

    const badgeElement = screen.queryByTestId('chip');
    expect(badgeElement).not.toBeInTheDocument();
  });

  it('renders badge when active with selected keys', () => {
    render(
      <FilterButtonTrigger
        {...defaultProps}
        isActive={true}
        numberOfSelectedKeys={2}
      />,
    );

    const badgeElement = screen.getByTestId('chip');
    expect(badgeElement).toBeInTheDocument();
    expect(badgeElement).toHaveAttribute('data-color', 'accent');
    expect(badgeElement).toHaveTextContent('2');
  });

  it('displays badge with tooltip when active', () => {
    const tooltipText = 'Selected: Option A, Option B';

    render(
      <FilterButtonTrigger
        {...defaultProps}
        isActive={true}
        numberOfSelectedKeys={2}
        tooltipText={tooltipText}
      />,
    );

    const tooltipElement = screen.getByTestId('tooltip');
    expect(tooltipElement).toBeInTheDocument();
    expect(tooltipElement).toHaveAttribute('data-content', tooltipText);
    expect(tooltipElement).toHaveAttribute('data-delay', '500');
    expect(tooltipElement).toHaveAttribute('data-size', 'sm');

    expect(
      screen.getByTestId('tooltip').querySelector('[data-testid="chip"]'),
    ).toBeInTheDocument();
  });

  it('displays icon when inactive', () => {
    const startContent = <IconFilter data-testid="filter-icon" />;

    render(
      <FilterButtonTrigger {...defaultProps} startContent={startContent} />,
    );

    expect(screen.getByTestId('filter-icon')).toBeInTheDocument();
    expect(screen.queryByTestId('chip')).not.toBeInTheDocument();
    expect(screen.getByDisplayValue('Status')).toBeInTheDocument();
  });

  it('shows badge instead of icon when active', () => {
    const startContent = <IconFilter data-testid="filter-icon" />;

    render(
      <FilterButtonTrigger
        {...defaultProps}
        isActive={true}
        numberOfSelectedKeys={2}
        startContent={startContent}
      />,
    );

    expect(screen.getByTestId('chip')).toBeInTheDocument();
    expect(screen.queryByTestId('filter-icon')).not.toBeInTheDocument();
  });

  it('hides chevron when clear button is shown', () => {
    const { container } = render(
      <FilterButtonTrigger
        {...defaultProps}
        isActive={true}
        showClearButton={true}
      />,
    );

    expect(container.querySelector('svg')).not.toBeInTheDocument();
  });

  it('shows chevron when clear button is not shown', () => {
    const { container } = render(
      <FilterButtonTrigger
        {...defaultProps}
        isActive={true}
        showClearButton={false}
      />,
    );

    expect(container.querySelector('svg')).toBeInTheDocument();
  });
});
