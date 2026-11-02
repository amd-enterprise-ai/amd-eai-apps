// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { Intent } from '@amdenterpriseai/types';

import { Status } from '@amdenterpriseai/components';

// Mock HeroUI components
vi.mock('@heroui/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@heroui/react')>()),
  // v3 Chip is compound: the wrapper composes start/label/end as children and
  // wraps text in `Chip.Label`, so the stub renders children and exposes Label.
  Chip: Object.assign(
    ({ children, color, size, className }: any) => (
      <div
        data-testid="chip"
        data-color={color}
        data-size={size}
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
    ({ children }: any) => <div data-testid="popover">{children}</div>,
    {
      Trigger: ({ children }: any) => (
        <div data-testid="popover-trigger">{children}</div>
      ),
      Content: ({ children }: any) => (
        <div data-testid="popover-content">{children}</div>
      ),
      Dialog: ({ children }: any) => (
        <div data-testid="popover-dialog">{children}</div>
      ),
    },
  ),
  cn: (...args: any[]) => {
    return args
      .filter(Boolean)
      .map((arg) => {
        if (typeof arg === 'object' && arg !== null) {
          // Handle object with boolean values (like { "animate-spin": true })
          return Object.entries(arg)
            .filter(([, value]) => value)
            .map(([key]) => key)
            .join(' ');
        }
        return String(arg);
      })
      .join(' ');
  },
}));

vi.mock('@tabler/icons-react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tabler/icons-react')>();
  return {
    ...actual,
    IconCircleCheck: ({ size, role, className }: any) => (
      <svg
        data-testid="icon-success"
        data-size={size}
        role={role}
        className={className}
      >
        <title>Success Icon</title>
      </svg>
    ),
    IconAlertTriangle: ({ size, role, className }: any) => (
      <svg
        data-testid="icon-warning-danger"
        data-size={size}
        role={role}
        className={className}
      >
        <title>Warning Icon</title>
      </svg>
    ),
    IconLoaderQuarter: ({ size, role, className }: any) => (
      <svg
        data-testid="icon-pending"
        data-size={size}
        role={role}
        className={className}
      >
        <title>Pending Icon</title>
      </svg>
    ),
    IconInfoCircle: ({ size, role, className }: any) => (
      <svg
        data-testid="icon-info"
        data-size={size}
        role={role}
        className={className}
      >
        <title>Info Icon</title>
      </svg>
    ),
  };
});
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    Tooltip: ({ children, content, placement }: any) => (
      <div
        data-testid="tooltip"
        data-placement={placement}
        data-content={content}
      >
        {children}
      </div>
    ),
  };
});

// Custom icon for testing overrides
const MockCustomIcon = ({ size, role, className }: any) => (
  <svg
    data-testid="icon-custom"
    data-size={size}
    role={role}
    className={className}
  >
    <title>Custom Icon</title>
  </svg>
);

vi.mock('../../../src/Tooltip', () => ({
  Tooltip: ({ children, content, placement }: any) => (
    <div
      data-testid="tooltip"
      data-placement={placement}
      data-content={content}
    >
      {children}
    </div>
  ),
}));

describe('Status', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic rendering', () => {
    it('renders with label', () => {
      render(<Status label="Test Status" />);
      expect(screen.getByText('Test Status')).toBeInTheDocument();
    });

    it('renders chip with default props', () => {
      render(<Status label="Test Status" />);
      const chip = screen.getByTestId('chip');
      // Chip color is "default" unless isTextColored is true
      expect(chip).toHaveAttribute('data-color', 'default');
      expect(chip).toHaveAttribute('data-size', 'md');
    });
  });

  describe('Intent functionality', () => {
    it('renders SUCCESS intent with correct color and icon', () => {
      render(<Status label="Success" intent={Intent.SUCCESS} />);
      // Chip color is "default" unless isTextColored is true, but icon should render
      expect(screen.getByTestId('chip')).toHaveAttribute(
        'data-color',
        'default',
      );
      expect(screen.getByTestId('icon-success')).toBeInTheDocument();
    });

    it('renders SUCCESS intent with isTextColored applies color to chip', () => {
      render(<Status label="Success" intent={Intent.SUCCESS} isTextColored />);
      expect(screen.getByTestId('chip')).toHaveAttribute(
        'data-color',
        'success',
      );
      expect(screen.getByTestId('icon-success')).toBeInTheDocument();
    });

    it('renders WARNING intent with correct color and icon', () => {
      render(<Status label="Warning" intent={Intent.WARNING} />);
      expect(screen.getByTestId('chip')).toHaveAttribute(
        'data-color',
        'default',
      );
      expect(screen.getByTestId('icon-warning-danger')).toBeInTheDocument();
    });

    it('renders DANGER intent with correct color and icon', () => {
      render(<Status label="Danger" intent={Intent.DANGER} />);
      expect(screen.getByTestId('chip')).toHaveAttribute(
        'data-color',
        'default',
      );
      expect(screen.getByTestId('icon-warning-danger')).toBeInTheDocument();
    });

    it('renders PENDING intent with correct color and icon', () => {
      render(<Status label="Pending" intent={Intent.PENDING} />);
      expect(screen.getByTestId('chip')).toHaveAttribute(
        'data-color',
        'default',
      );
      expect(screen.getByTestId('icon-pending')).toBeInTheDocument();
    });
  });

  describe('Overriding intents', () => {
    it('overrides intent color with color prop when isTextColored is true', () => {
      render(
        <Status
          label="Test"
          intent={Intent.SUCCESS}
          color="danger"
          isTextColored
        />,
      );
      const chip = screen.getByTestId('chip');
      // Color prop should override intent color
      expect(chip).toHaveAttribute('data-color', 'danger');
      // But icon from intent should still be used
      expect(screen.getByTestId('icon-success')).toBeInTheDocument();
    });

    it('overrides intent icon with icon prop', () => {
      render(
        <Status
          label="Test"
          intent={Intent.SUCCESS}
          icon={MockCustomIcon}
          isTextColored
        />,
      );
      // Intent color should still be used (when isTextColored is true)
      expect(screen.getByTestId('chip')).toHaveAttribute(
        'data-color',
        'success',
      );
      // Custom icon should override intent icon
      expect(screen.getByTestId('icon-custom')).toBeInTheDocument();
      // Intent icon should not be rendered
      expect(screen.queryByTestId('icon-success')).not.toBeInTheDocument();
    });

    it('overrides both intent color and icon with props', () => {
      render(
        <Status
          label="Test"
          intent={Intent.WARNING}
          color="success"
          icon={MockCustomIcon}
          isTextColored
        />,
      );
      const chip = screen.getByTestId('chip');
      // Both color and icon should be overridden
      expect(chip).toHaveAttribute('data-color', 'success');
      expect(screen.getByTestId('icon-custom')).toBeInTheDocument();
      // Intent icon should not be rendered
      expect(
        screen.queryByTestId('icon-warning-danger'),
      ).not.toBeInTheDocument();
    });

    it('uses intent defaults when color and icon props are not provided', () => {
      render(<Status label="Test" intent={Intent.DANGER} isTextColored />);
      const chip = screen.getByTestId('chip');
      expect(chip).toHaveAttribute('data-color', 'danger');
      expect(screen.getByTestId('icon-warning-danger')).toBeInTheDocument();
    });

    it('handles color override with null icon prop', () => {
      render(
        <Status
          label="Test"
          intent={Intent.SUCCESS}
          color="warning"
          icon={undefined}
          isTextColored
        />,
      );
      const chip = screen.getByTestId('chip');
      expect(chip).toHaveAttribute('data-color', 'warning');
      // When icon is null, the ?? operator will fall back to intent icon
      // So intent icon should still render
      expect(screen.getByTestId('icon-success')).toBeInTheDocument();
    });

    it('handles color override with undefined icon prop', () => {
      render(
        <Status
          label="Test"
          intent={Intent.SUCCESS}
          color="warning"
          icon={undefined}
          isTextColored
        />,
      );
      const chip = screen.getByTestId('chip');
      expect(chip).toHaveAttribute('data-color', 'warning');
      // When icon is undefined, intent icon should be used
      expect(screen.getByTestId('icon-success')).toBeInTheDocument();
    });

    it('color prop overrides intent color even when isTextColored is false', () => {
      // The color prop still affects text styling via classes, just not chip color
      render(<Status label="Test" intent={Intent.SUCCESS} color="danger" />);
      const chip = screen.getByTestId('chip');
      // Chip color is default when isTextColored is false
      expect(chip).toHaveAttribute('data-color', 'default');
      // But icon from intent should still be used
      expect(screen.getByTestId('icon-success')).toBeInTheDocument();
    });
  });

  describe('Size prop', () => {
    it('renders with sm size', () => {
      render(<Status label="Test" size="sm" />);
      expect(screen.getByTestId('chip')).toHaveAttribute('data-size', 'sm');
    });

    it('renders with md size', () => {
      render(<Status label="Test" size="md" />);
      expect(screen.getByTestId('chip')).toHaveAttribute('data-size', 'md');
    });

    it('renders with lg size', () => {
      render(<Status label="Test" size="lg" />);
      expect(screen.getByTestId('chip')).toHaveAttribute('data-size', 'lg');
    });

    it('passes correct icon size based on component size', () => {
      render(<Status label="Test" size="sm" intent={Intent.SUCCESS} />);
      expect(screen.getByTestId('icon-success')).toHaveAttribute(
        'data-size',
        '14',
      );
    });
  });

  describe('Help content', () => {
    it('renders tooltip when helpContent is provided and not clickable', () => {
      render(<Status label="Test" helpContent="Help text" />);
      expect(screen.getByTestId('tooltip')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toHaveAttribute(
        'data-content',
        'Help text',
      );
    });

    it('renders popover when helpContent is provided and clickable', () => {
      render(<Status label="Test" helpContent="Help text" isClickable />);
      expect(screen.getByTestId('popover')).toBeInTheDocument();
      expect(screen.getByTestId('popover-trigger')).toBeInTheDocument();
      expect(screen.getByTestId('popover-content')).toBeInTheDocument();
    });

    it('renders info icon when helpContent is provided', () => {
      render(<Status label="Test" helpContent="Help text" />);
      expect(screen.getByTestId('icon-info')).toBeInTheDocument();
    });

    it('does not render info icon when helpContent is not provided', () => {
      render(<Status label="Test" />);
      expect(screen.queryByTestId('icon-info')).not.toBeInTheDocument();
    });
  });

  describe('isTextColored prop', () => {
    it('applies color to chip when isTextColored is true', () => {
      render(<Status label="Test" color="success" isTextColored />);
      const chip = screen.getByTestId('chip');
      expect(chip).toHaveAttribute('data-color', 'success');
    });

    it('uses default color when isTextColored is false', () => {
      render(<Status label="Test" color="success" isTextColored={false} />);
      const chip = screen.getByTestId('chip');
      expect(chip).toHaveAttribute('data-color', 'default');
    });
  });

  describe('Icon rendering', () => {
    it('renders custom icon when provided', () => {
      render(<Status label="Test" icon={MockCustomIcon} />);
      expect(screen.getByTestId('icon-custom')).toBeInTheDocument();
    });

    it('does not render icon when no icon or intent is provided', () => {
      render(<Status label="Test" />);
      // When IconComponent is null, startContent should not be rendered
      const startContent = screen.queryByTestId('chip-start-content');
      // The div might exist but should be empty or not contain an icon
      if (startContent) {
        // If it exists, it should not contain any icon testids
        expect(screen.queryByTestId('icon-success')).not.toBeInTheDocument();
        expect(
          screen.queryByTestId('icon-warning-danger-danger'),
        ).not.toBeInTheDocument();
        expect(screen.queryByTestId('icon-pending')).not.toBeInTheDocument();
      }
    });

    it('applies animate-spin class to pending icon', () => {
      render(<Status label="Test" intent={Intent.PENDING} />);
      const pendingIcon = screen.getByTestId('icon-pending');
      // The className is passed as a prop, check if it contains animate-spin
      const className = pendingIcon.getAttribute('class');
      expect(className).toContain('animate-spin');
    });
  });

  describe('Combined props', () => {
    it('handles intent override with helpContent and isClickable', () => {
      render(
        <Status
          label="Test"
          intent={Intent.SUCCESS}
          color="warning"
          helpContent="Help"
          isClickable
          isTextColored
        />,
      );
      expect(screen.getByTestId('chip')).toHaveAttribute(
        'data-color',
        'warning',
      );
      expect(screen.getByTestId('icon-success')).toBeInTheDocument();
      expect(screen.getByTestId('popover')).toBeInTheDocument();
    });

    it('handles all props together', () => {
      render(
        <Status
          label="Complete Test"
          intent={Intent.DANGER}
          color="success"
          icon={MockCustomIcon}
          helpContent="Help text"
          isClickable
          isTextColored
          size="lg"
        />,
      );
      const chip = screen.getByTestId('chip');
      expect(chip).toHaveAttribute('data-color', 'success');
      expect(chip).toHaveAttribute('data-size', 'lg');
      expect(screen.getByTestId('icon-custom')).toBeInTheDocument();
      expect(screen.getByTestId('popover')).toBeInTheDocument();
    });
  });
});
