// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, within } from '@testing-library/react';

import {
  BadgeStackDisplay,
  ChipDisplay,
  DateDisplay,
  NoDataDisplay,
  StatusDisplay,
  TranslationDisplay,
} from '@amdenterpriseai/components';

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/src/DateSince', () => ({
  DateSince: ({ date }: { date: string }) => (
    <span data-testid="mock-datesince" data-date={date} />
  ),
}));

vi.mock('@/src/InlineBadge', () => ({
  InlineBadge: ({
    children,
    color = 'default',
    size,
    isOneChar,
    className,
    ...rest
  }: any) => (
    <div
      data-testid="mock-inline-badge"
      data-color={color}
      data-size={size}
      data-isonechar={isOneChar}
      className={className}
      {...rest}
    >
      {children}
    </div>
  ),
}));

vi.mock('@/src/Status/Status', () => ({
  default: ({ label, color, icon: IconComponent, isPending }: any) => (
    <div
      data-testid="mock-status-display"
      data-color={color}
      data-pending={isPending}
    >
      {isPending ? (
        <div data-testid="mock-spinner" data-color={color}>
          Spinner
        </div>
      ) : (
        IconComponent && <IconComponent size="20" role="img" />
      )}
      {label}
    </div>
  ),
}));

// Mock next-i18next
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, any>) => {
      if (key === 'test.key' && !options) {
        return 'Translated';
      } else if (key === 'test.key') {
        return `Translated with ${Object.entries(options!)
          .map(([k, v]) => `${k}:${v}`)
          .join(' ')}`;
      }
      return key;
    },
  }),
}));

// Mock HeroUI components
vi.mock('@heroui/react', async () => {
  const original = await vi.importActual<any>('@heroui/react');
  return {
    ...original,
    cn: (...args: any[]) => {
      return original.cn(...args);
    },
    Chip: Object.assign(
      ({ children, size, color, variant, className }: any) => (
        <div
          data-testid="mock-chip"
          data-size={size}
          data-color={color}
          data-variant={variant}
          className={className}
        >
          {children}
        </div>
      ),
      {
        Label: ({ children, className }: any) => (
          <span className={className}>{children}</span>
        ),
      },
    ),

    Popover: Object.assign(
      ({ children }: any) => <div data-testid="mock-popover">{children}</div>,
      {
        Trigger: ({ children }: any) => (
          <div data-testid="mock-popover-trigger">{children}</div>
        ),
        Content: ({ children }: any) => (
          <div data-testid="mock-popover-content">{children}</div>
        ),
        Dialog: ({ children }: any) => (
          <div data-testid="mock-popover-dialog">{children}</div>
        ),
      },
    ),
    Spinner: ({ size, color, className }: any) => (
      <div
        data-testid="mock-spinner"
        data-size={size}
        data-color={color}
        className={className}
      >
        Spinner
      </div>
    ),
  };
});
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    Tooltip: ({ children, content }: any) => (
      <div data-testid="mock-tooltip">
        <div data-testid="tooltip-trigger">{children}</div>
        <div data-testid="tooltip-content">{content}</div>
      </div>
    ),
  };
});

vi.mock('../../../src/Tooltip', () => ({
  Tooltip: ({ children, content }: any) => (
    <div data-testid="mock-tooltip">
      <div data-testid="tooltip-trigger">{children}</div>
      <div data-testid="tooltip-content">{content}</div>
    </div>
  ),
}));

describe('DateDisplay', () => {
  it('passes date to DateSince', () => {
    const date = '2023-01-01T12:00:00Z';
    render(<DateDisplay date={date} />);
    const el = screen.getByTestId('mock-datesince');
    expect(el).toHaveAttribute('data-date', date);
  });
});

describe('ChipDisplay', () => {
  const MockIcon = ({
    size,
    className,
  }: {
    size?: string;
    className?: string;
  }) => (
    <span data-testid="mock-icon" data-size={size} className={className}>
      Icon
    </span>
  );

  const variants = {
    success: {
      label: 'Success',
      color: 'success' as const,
      icon: MockIcon,
    },
    error: {
      label: 'Error',
      color: 'danger' as const,
    },
    default: {
      label: 'Default',
    },
  };

  it('renders chip with correct label and color when variant exists', () => {
    render(<ChipDisplay variants={variants} type="success" />);

    const chip = screen.getByTestId('mock-chip');
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveAttribute('data-color', 'success');
    // v3 Chip renames the v2 `flat` variant to `soft`; the adapter maps it.
    expect(chip).toHaveAttribute('data-variant', 'soft');
    expect(chip).toHaveTextContent('Success');
    // The variant's icon is passed through as the chip's start content.
    expect(screen.getByTestId('mock-icon')).toBeInTheDocument();
  });

  it('renders chip without icon when not provided', () => {
    render(<ChipDisplay variants={variants} type="error" />);

    const chip = screen.getByTestId('mock-chip');
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveAttribute('data-color', 'danger');
    expect(chip).toHaveTextContent('Error');
    expect(screen.queryByTestId('chip-start-content')).not.toBeInTheDocument();
  });

  it('renders chip with default color when not specified', () => {
    render(<ChipDisplay variants={variants} type="default" />);

    const chip = screen.getByTestId('mock-chip');
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveAttribute('data-color', 'default');
    expect(chip).toHaveTextContent('Default');
  });

  it('renders fallback chip when variant does not exist', () => {
    render(<ChipDisplay variants={variants} type="nonexistent" />);

    const chip = screen.getByTestId('mock-chip');
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveAttribute('data-color', 'danger');
    expect(chip).toHaveTextContent('nonexistent!');
  });
});

describe('StatusDisplay', () => {
  const MockIcon = ({
    size,
    role,
  }: {
    size?: string | number;
    role?: string;
  }) => (
    <span data-testid="mock-status-icon" data-size={size} role={role}>
      Icon
    </span>
  );

  const variants = {
    active: {
      label: 'Active',
      color: 'success' as const,
      icon: MockIcon,
      isPending: false as const,
    },
    processing: {
      label: 'Processing',
      color: 'primary' as const,
      isPending: true as const,
    },
    default: {
      label: 'Default',
      icon: MockIcon,
      isPending: false as const,
    },
  };

  it('renders status badge with icon component', () => {
    render(<StatusDisplay variants={variants} type="active" />);

    const statusDisplay = screen.getByTestId('mock-status-display');
    expect(statusDisplay).toBeInTheDocument();
    expect(statusDisplay).toHaveAttribute('data-color', 'success');
    expect(screen.getByText('Active')).toBeInTheDocument();
    // Icon is rendered directly by Status mock, so check it exists within status
    const icon = within(statusDisplay).getByTestId('mock-status-icon');
    expect(icon).toBeInTheDocument();
  });

  it('renders status badge with spinner', () => {
    render(<StatusDisplay variants={variants} type="processing" />);

    const statusDisplay = screen.getByTestId('mock-status-display');
    expect(statusDisplay).toBeInTheDocument();
    expect(statusDisplay).toHaveAttribute('data-color', 'primary');
    expect(statusDisplay).toHaveAttribute('data-pending', 'true');
    expect(screen.getByText('Processing')).toBeInTheDocument();
    expect(screen.getByTestId('mock-spinner')).toBeInTheDocument();
    expect(screen.getByTestId('mock-spinner')).toHaveAttribute(
      'data-color',
      'primary',
    );
  });

  it('renders status badge with default styling', () => {
    render(<StatusDisplay variants={variants} type="default" />);

    const statusDisplay = screen.getByTestId('mock-status-display');
    expect(statusDisplay).toBeInTheDocument();
    expect(screen.getByText('Default')).toBeInTheDocument();
    // Icon is rendered directly by Status mock, so check it exists within status
    const icon = within(statusDisplay).getByTestId('mock-status-icon');
    expect(icon).toBeInTheDocument();
  });

  it('renders fallback chip when variant does not exist', () => {
    render(<StatusDisplay variants={variants} type="nonexistent" />);

    const chip = screen.getByTestId('mock-chip');
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveAttribute('data-color', 'danger');
    expect(chip).toHaveTextContent('nonexistent!');
  });
});

describe('TranslationDisplay', () => {
  it('renders translated string with translation key', () => {
    const { container } = render(
      <TranslationDisplay tKey="test.key" ns="common" />,
    );
    // Since we're mocking useTranslation, we check that something is rendered
    expect(container).not.toBeEmptyDOMElement();
  });

  it('renders translated string with interpolation options', () => {
    render(
      <TranslationDisplay tKey="test.key" ns="common" count={5} name="User" />,
    );
    expect(
      screen.getByText('Translated with count:5 name:User'),
    ).toBeInTheDocument();
  });
});

describe('NoDataDisplay', () => {
  it('renders mdash with correct styling', () => {
    render(<NoDataDisplay />);

    const mdash = screen.getByText('—');
    expect(mdash).toBeInTheDocument();
    expect(mdash).toHaveClass('text-muted');
  });
});

describe('BadgeStackDisplay', () => {
  const MockIcon = ({ size }: { size?: string }) => (
    <span data-testid="mock-badge-icon" data-size={size}>
      Icon
    </span>
  );

  const variants = {
    gpu: { label: 'GPU', color: 'primary' as const, icon: MockIcon },
    cpu: { label: 'CPU', color: 'secondary' as const },
    memory: { label: 'Memory', color: 'warning' as const, icon: MockIcon },
    storage: { label: 'Storage', color: 'success' as const },
    singleChar: { label: 'S', color: 'default' as const }, // Added for testing isOneChar
  };

  beforeEach(() => {
    vi.clearAllMocks(); // Clear mocks before each test
  });

  it('renders badges correctly when types are within limit', () => {
    render(
      <BadgeStackDisplay
        variants={variants}
        types={['gpu', 'cpu']}
        limit={3}
      />,
    );
    const tooltipTrigger = screen.getByTestId('tooltip-trigger');
    const badges = within(tooltipTrigger).getAllByTestId('mock-inline-badge');
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveTextContent('Icon'); // GPU with MockIcon
    expect(badges[0]).toHaveAttribute('data-color', 'primary');
    expect(badges[1]).toHaveTextContent('CPU'); // CPU with label
    expect(badges[1]).toHaveAttribute('data-color', 'secondary');
    expect(screen.queryByText(/\\+\\d+/)).not.toBeInTheDocument(); // No +N indicator
  });

  it('renders badges and +N indicator when types exceed limit', () => {
    render(
      <BadgeStackDisplay
        variants={variants}
        types={['gpu', 'cpu', 'memory', 'storage']}
        limit={2}
      />,
    );
    const tooltipTrigger = screen.getByTestId('tooltip-trigger');
    const badges = within(tooltipTrigger).getAllByTestId('mock-inline-badge');
    expect(badges).toHaveLength(2);
    expect(screen.getByText('+2')).toBeInTheDocument();
  });

  it('displays tooltip with all items and title when provided', () => {
    render(
      <BadgeStackDisplay
        variants={variants}
        types={['gpu', 'cpu', 'memory']}
        title="Resources"
      />,
    );
    const tooltip = screen.getByTestId('mock-tooltip');
    expect(tooltip).toBeInTheDocument();

    const tooltipContent = screen.getByTestId('tooltip-content');
    expect(tooltipContent).toHaveTextContent('Resources:');
    expect(tooltipContent).toHaveTextContent('GPU');
    expect(tooltipContent).toHaveTextContent('CPU');
    expect(tooltipContent).toHaveTextContent('Memory');
  });

  it('renders nothing when types array is empty', () => {
    const { container } = render(
      <BadgeStackDisplay variants={variants} types={[]} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders badges with icons when provided in variants', () => {
    render(<BadgeStackDisplay variants={variants} types={['gpu']} />);
    const tooltipTrigger = screen.getByTestId('tooltip-trigger');
    const badge = within(tooltipTrigger).getByTestId('mock-inline-badge');
    expect(badge).toBeInTheDocument();
    const iconInBadge = within(badge).getByTestId('mock-badge-icon');
    expect(iconInBadge).toBeInTheDocument();
    expect(iconInBadge).toHaveAttribute('data-size', '12');
    expect(badge).toHaveAttribute('data-isonechar', 'true');
  });

  it('renders badges with labels when icons are not provided in variants', () => {
    render(<BadgeStackDisplay variants={variants} types={['cpu']} />);
    const tooltipTrigger = screen.getByTestId('tooltip-trigger');
    const badge = within(tooltipTrigger).getByTestId('mock-inline-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('CPU');
    expect(
      within(badge).queryByTestId('mock-badge-icon'),
    ).not.toBeInTheDocument();
  });

  it('applies -ml-2 class to subsequent badges', () => {
    render(<BadgeStackDisplay variants={variants} types={['gpu', 'cpu']} />);
    const tooltipTrigger = screen.getByTestId('tooltip-trigger');
    const badges = within(tooltipTrigger).getAllByTestId('mock-inline-badge');
    expect(badges[0]).not.toHaveClass('-ml-2');
    expect(badges[1]).toHaveClass('-ml-2');
  });

  it('renders default label if variant type is not found in variants object', () => {
    render(
      <BadgeStackDisplay
        variants={variants}
        types={['nonexistent']}
        title="Test"
      />,
    );
    const tooltipTrigger = screen.getByTestId('tooltip-trigger');
    const badge = within(tooltipTrigger).getByTestId('mock-inline-badge');
    expect(badge).toBeInTheDocument();
    // The badge itself will render the type as label if icon is missing
    expect(badge).toHaveTextContent('nonexistent');
    expect(badge).toHaveAttribute('data-color', 'default'); // Added assertion

    // Check tooltip content for the default label
    const tooltipContent = screen.getByTestId('tooltip-content');
    expect(tooltipContent).toHaveTextContent('Test:');
    // The InlineBadge in the tooltip will also render the type as label
    const tooltipBadge =
      within(tooltipContent).getByTestId('mock-inline-badge');
    expect(tooltipBadge).toBeInTheDocument();
    expect(tooltipBadge).toHaveTextContent('nonexistent');
    expect(tooltipBadge).toHaveAttribute('data-color', 'default'); // Added assertion
    expect(tooltipContent).toHaveTextContent('nonexistent'); // The span with the label
  });

  it('passes isOneChar={true} to InlineBadge for multi-character labels without icon', () => {
    render(<BadgeStackDisplay variants={variants} types={['cpu']} />); // 'cpu' label "CPU"
    const tooltipTrigger = screen.getByTestId('tooltip-trigger');
    const badge = within(tooltipTrigger).getByTestId('mock-inline-badge');
    // Implementation always passes isOneChar={true} regardless of label length
    expect(badge).toHaveAttribute('data-isonechar', 'true');
  });

  it('passes isOneChar={true} to InlineBadge for single-character labels without icon', () => {
    render(<BadgeStackDisplay variants={variants} types={['singleChar']} />); // 'singleChar' label "S"
    const tooltipTrigger = screen.getByTestId('tooltip-trigger');
    const badge = within(tooltipTrigger).getByTestId('mock-inline-badge');
    expect(badge).toHaveAttribute('data-isonechar', 'true');
  });
});
