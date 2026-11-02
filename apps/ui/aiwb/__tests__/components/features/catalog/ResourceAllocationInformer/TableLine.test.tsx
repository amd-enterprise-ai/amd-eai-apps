// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import TableLine, {
  TableLineProps,
} from '@/components/features/catalog/ResourceAllocationInformer/TableLine';
import { ResourceType } from '@/components/features/catalog/ResourceAllocationInformer/constants';

// Mock next-i18next
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      const translations: Record<string, string> = {
        gpuLabel: 'GPU',
        cpuLabel: 'CPU',
        ramLabel: 'RAM',
        cpuFormattedValue: `${options?.count} vCPUs`,
        ramFormattedValue: `${options?.count} GB`,
        quotaFormatted: `Quota: ${options?.value}`,
        perGPU: `${options?.value} per GPU`,
        belowRequiredExceedsQuotaTooltip: 'Below required and exceeds quota',
        belowRequiredTooltip: 'Below required minimum',
        exceedsQuotaTooltip: 'Exceeds quota limit',
      };
      return translations[key] || key;
    },
  }),
}));

// Mock shared component adapters
vi.mock('@amdenterpriseai/components', () => ({
  cn: (...classes: string[]) => classes.filter(Boolean).join(' '),
  Chip: ({ children, size, variant }: any) => (
    <span data-testid="chip" data-size={size} data-variant={variant}>
      {children}
    </span>
  ),
  Skeleton: ({ className }: any) => (
    <div data-testid="skeleton" className={className}>
      Loading...
    </div>
  ),
  Tooltip: ({ children, content, size, className }: any) => (
    <div
      data-testid="tooltip"
      title={content}
      data-size={size}
      className={className}
    >
      {children}
    </div>
  ),
}));

// Mock HeroUI utilities
vi.mock('@heroui/react', () => ({
  cn: (...classes: string[]) => classes.filter(Boolean).join(' '),
}));

// Mock Tabler icons
vi.mock('@tabler/icons-react', () => ({
  IconAlertTriangle: ({ size, className }: any) => (
    <div data-testid="alert-triangle" data-size={size} className={className}>
      (!)
    </div>
  ),
}));

describe('TableLine', () => {
  const defaultProps: TableLineProps = {
    value: 4,
    quota: 10,
    req: 2,
    type: ResourceType.GPU,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders GPU resource line correctly', () => {
      render(<TableLine {...defaultProps} type={ResourceType.GPU} />);

      expect(screen.getByText('GPU')).toBeInTheDocument();
      expect(screen.getByText('4')).toBeInTheDocument();
      expect(screen.getByText('Quota: 10')).toBeInTheDocument();
    });

    it('renders CPU resource line correctly', () => {
      render(<TableLine {...defaultProps} type={ResourceType.CPU} />);

      expect(screen.getByText('CPU')).toBeInTheDocument();
      expect(screen.getByText('4 vCPUs')).toBeInTheDocument();
    });

    it('renders RAM resource line correctly', () => {
      render(<TableLine {...defaultProps} type={ResourceType.RAM} />);

      expect(screen.getByText('RAM')).toBeInTheDocument();
      expect(screen.getByText('4 GB')).toBeInTheDocument();
    });

    it('renders without quota chip when quota is 0', () => {
      render(<TableLine {...defaultProps} quota={0} />);

      expect(screen.queryByTestId('chip')).not.toBeInTheDocument();
    });

    it('displays multiplier information when multiplier > 1', () => {
      render(<TableLine {...defaultProps} multiplier={2} />);

      expect(screen.getByText('4 per GPU')).toBeInTheDocument();
      expect(screen.getByText('8')).toBeInTheDocument(); // total value
    });

    it('does not display multiplier information when multiplier is 1', () => {
      render(<TableLine {...defaultProps} multiplier={1} />);

      expect(screen.queryByText('4 per GPU')).not.toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    it('renders skeleton components when loading', () => {
      render(<TableLine {...defaultProps} isLoading={true} />);

      const skeletons = screen.getAllByTestId('skeleton');
      expect(skeletons).toHaveLength(3);
      expect(skeletons[0]).toHaveClass('w-full h-6 rounded-lg');
      expect(skeletons[1]).toHaveClass('w-20 h-6 rounded-lg');
      expect(skeletons[2]).toHaveClass('w-20 h-6 rounded-lg');
    });

    it('does not render content when loading', () => {
      render(<TableLine {...defaultProps} isLoading={true} />);

      expect(screen.queryByText('GPU')).not.toBeInTheDocument();
      expect(screen.queryByTestId('alert-triangle')).not.toBeInTheDocument();
    });
  });

  describe('Warning States', () => {
    it('shows no warning when total is within limits', () => {
      render(<TableLine {...defaultProps} value={5} quota={10} req={2} />);

      expect(screen.queryByTestId('alert-triangle')).not.toBeInTheDocument();
      expect(screen.queryByTestId('tooltip')).not.toBeInTheDocument();
    });

    it('shows warning when total exceeds quota', () => {
      render(<TableLine {...defaultProps} value={12} quota={10} req={2} />);

      expect(screen.getByTestId('alert-triangle')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toHaveAttribute(
        'title',
        'Exceeds quota limit',
      );
      expect(screen.getByTestId('alert-triangle')).toHaveClass('text-warning');
      expect(screen.getByText('12')).toHaveClass('text-warning');
    });

    it('shows warning when total is below required', () => {
      render(<TableLine {...defaultProps} value={1} quota={10} req={2} />);

      expect(screen.getByTestId('alert-triangle')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toHaveAttribute(
        'title',
        'Below required minimum',
      );
      expect(screen.getByTestId('alert-triangle')).toHaveClass('text-danger');
      expect(screen.getByText('1')).toHaveClass('text-danger');
    });

    it('shows warning when total is below required without quota', () => {
      render(
        <TableLine {...defaultProps} value={1} quota={undefined} req={2} />,
      );

      expect(screen.getByTestId('alert-triangle')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toHaveAttribute(
        'title',
        'Below required minimum',
      );
      expect(screen.getByTestId('alert-triangle')).toHaveClass('text-danger');
      expect(screen.getByText('1')).toHaveClass('text-danger');
    });

    it('shows warning when total is below required and exceeds quota', () => {
      render(<TableLine {...defaultProps} value={3} quota={2} req={5} />);

      expect(screen.getByTestId('alert-triangle')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toHaveAttribute(
        'title',
        'Below required and exceeds quota',
      );
      expect(screen.getByTestId('alert-triangle')).toHaveClass('text-danger');
    });
  });

  describe('Multiplier Calculations', () => {
    it('calculates total correctly with multiplier', () => {
      render(
        <TableLine
          {...defaultProps}
          value={4}
          multiplier={3}
          type={ResourceType.CPU}
        />,
      );

      expect(screen.getByText('12 vCPUs')).toBeInTheDocument();
      expect(screen.getByText('4 per GPU')).toBeInTheDocument();
    });

    it('applies multiplier to warning calculations', () => {
      render(
        <TableLine
          {...defaultProps}
          value={4}
          multiplier={3}
          quota={10}
          req={5}
        />,
      );

      // total = 4 * 3 = 12, which is greater than quota (10)
      expect(screen.getByTestId('alert-triangle')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toHaveAttribute(
        'title',
        'Exceeds quota limit',
      );
    });

    it('applies multiplier to below required warning calculations', () => {
      render(
        <TableLine
          {...defaultProps}
          value={2}
          multiplier={3}
          quota={20}
          req={10}
        />,
      );

      // total = 2 * 3 = 6, which is less than req (10) but within quota (20)
      expect(screen.getByTestId('alert-triangle')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toHaveAttribute(
        'title',
        'Below required minimum',
      );
    });
  });

  describe('Resource Type Formatting', () => {
    it('formats GPU values as plain numbers', () => {
      render(<TableLine {...defaultProps} type={ResourceType.GPU} value={8} />);

      expect(screen.getByText('8')).toBeInTheDocument();
    });

    it('formats CPU values with vCPUs suffix', () => {
      render(<TableLine {...defaultProps} type={ResourceType.CPU} value={8} />);

      expect(screen.getByText('8 vCPUs')).toBeInTheDocument();
    });

    it('formats RAM values with GB suffix', () => {
      render(
        <TableLine {...defaultProps} type={ResourceType.RAM} value={16} />,
      );

      expect(screen.getByText('16 GB')).toBeInTheDocument();
    });
  });

  describe('Component Structure', () => {
    it('has correct CSS classes for layout', () => {
      const { container } = render(<TableLine {...defaultProps} />);

      const mainDiv = container.firstChild as HTMLElement;
      expect(mainDiv).toHaveClass('flex', 'gap-2', 'h-6', 'items-center');
    });

    it('renders chip with correct props', () => {
      render(<TableLine {...defaultProps} />);

      const chip = screen.getByTestId('chip');
      expect(chip).toHaveAttribute('data-size', 'sm');
      expect(chip).toHaveAttribute('data-variant', 'flat');
    });

    it('renders tooltip with correct props when warning is present', () => {
      render(<TableLine {...defaultProps} value={12} quota={10} />);

      const tooltip = screen.getByTestId('tooltip');
      expect(tooltip).toHaveAttribute('data-size', 'sm');
      expect(tooltip).toHaveClass('max-w-[300px]');
    });
  });

  describe('Edge Cases', () => {
    it('handles zero values correctly', () => {
      render(<TableLine {...defaultProps} value={0} quota={0} req={0} />);

      expect(screen.getByText('0')).toBeInTheDocument();
      expect(screen.queryByTestId('chip')).not.toBeInTheDocument();
      expect(screen.queryByTestId('alert-triangle')).not.toBeInTheDocument();
    });

    it('handles large numbers correctly', () => {
      render(
        <TableLine
          {...defaultProps}
          type={ResourceType.RAM}
          value={1024}
          multiplier={4}
        />,
      );

      expect(screen.getByText('4096 GB')).toBeInTheDocument();
      expect(screen.getByText('1024 per GPU')).toBeInTheDocument();
    });

    it('handles req parameter defaulting to 0', () => {
      const { value, quota, type, ...propsWithoutReq } = defaultProps;
      render(
        <TableLine
          value={value}
          quota={quota}
          type={type}
          {...propsWithoutReq}
        />,
      );

      // Should not show warning since req defaults to 0 and value > 0
      expect(screen.queryByTestId('alert-triangle')).not.toBeInTheDocument();
    });

    it('handles multiplier parameter defaulting to 1', () => {
      const { multiplier, ...propsWithoutMultiplier } = defaultProps;
      render(<TableLine {...propsWithoutMultiplier} />);

      expect(screen.getByText('4')).toBeInTheDocument();
      expect(screen.queryByText('per GPU')).not.toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('provides tooltip for warning icon', () => {
      render(<TableLine {...defaultProps} value={12} quota={10} />);

      const tooltip = screen.getByTestId('tooltip');
      expect(tooltip).toHaveAttribute('title', 'Exceeds quota limit');
    });

    it('uses semantic HTML structure', () => {
      render(<TableLine {...defaultProps} />);

      const spans = screen.getAllByText((content, element) => {
        return element?.tagName.toLowerCase() === 'span';
      });
      expect(spans.length).toBeGreaterThan(0);
    });
  });
});
