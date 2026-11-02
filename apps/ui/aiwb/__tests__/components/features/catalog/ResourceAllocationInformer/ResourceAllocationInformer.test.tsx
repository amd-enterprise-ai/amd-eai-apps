// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import ResourceAllocationInformer, {
  ResourceAllocationInformerProps,
} from '@/components/features/catalog/ResourceAllocationInformer/ResourceAllocationInformer';

/**
 * Note: The component has a quirk in its comparison logic for memory and CPU requirements.
 * It compares:
 * - totalMemory (gpus * memoryPerGpu) with requiredResources.memoryPerGpu (not the total required)
 * - totalCpu (gpus * cpuPerGpu) with requiredResources.cpuPerGpu (not the total required)
 *
 * This means the component may show incorrect warnings when the per-GPU requirements
 * are higher than the total allocated resources.
 */

// Mock next-i18next
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      const translations: Record<string, string> = {
        totalResourceAllocation: 'Total Resource Allocation',
        belowRequiredExceedsQuotaWarning:
          'Resources are below required and exceed quota',
        belowRequiredWarning: 'Resources are below required minimum',
        exceedsQuotaWarning: 'Resources exceed quota limits',
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
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    Alert: ({
      status,
      description,
    }: {
      status?: string;
      description?: string;
    }) => (
      <div role="alert" data-status={status}>
        {description}
      </div>
    ),
  };
});

// Mock TableLine component
vi.mock(
  '@/components/features/catalog/ResourceAllocationInformer/TableLine',
  () => ({
    default: ({ type, value, req, quota, multiplier, isLoading }: any) => (
      <div data-testid={`table-line-${type}`}>
        {isLoading ? (
          <div data-testid="skeleton">Loading...</div>
        ) : (
          <div>
            <span data-testid="value">{value}</span>
            <span data-testid="req">{req}</span>
            <span data-testid="quota">{quota}</span>
            {multiplier && <span data-testid="multiplier">{multiplier}</span>}
          </div>
        )}
      </div>
    ),
  }),
);

describe('ResourceAllocationInformer', () => {
  const defaultProps: ResourceAllocationInformerProps = {
    isLoading: false,
    currentResources: {
      gpus: 2,
      memoryPerGpu: 8,
      cpuPerGpu: 4,
    },
    quota: {
      gpus: 4,
      memory: 32,
      cpu: 16,
    },
    requiredResources: {
      gpus: 1,
      memoryPerGpu: 4,
      cpuPerGpu: 2,
    },
  };

  const renderComponent = (
    props: Partial<ResourceAllocationInformerProps> = {},
  ) => {
    return render(<ResourceAllocationInformer {...defaultProps} {...props} />);
  };

  describe('Basic Rendering', () => {
    it('should render the component with title', () => {
      renderComponent();
      expect(screen.getByText('Total Resource Allocation')).toBeInTheDocument();
    });

    it('should render all three resource lines (GPU, RAM, CPU)', () => {
      renderComponent();
      expect(screen.getByTestId('table-line-gpu')).toBeInTheDocument();
      expect(screen.getByTestId('table-line-ram')).toBeInTheDocument();
      expect(screen.getByTestId('table-line-cpu')).toBeInTheDocument();
    });

    it('should pass correct props to TableLine components', () => {
      renderComponent();

      const gpuLine = screen.getByTestId('table-line-gpu');
      expect(gpuLine).toHaveTextContent('2'); // value
      expect(gpuLine).toHaveTextContent('1'); // req
      expect(gpuLine).toHaveTextContent('4'); // quota

      const ramLine = screen.getByTestId('table-line-ram');
      expect(ramLine).toHaveTextContent('8'); // value
      expect(ramLine).toHaveTextContent('4'); // req
      expect(ramLine).toHaveTextContent('32'); // quota
      expect(ramLine).toHaveTextContent('2'); // multiplier (gpus)

      const cpuLine = screen.getByTestId('table-line-cpu');
      expect(cpuLine).toHaveTextContent('4'); // value
      expect(cpuLine).toHaveTextContent('2'); // req
      expect(cpuLine).toHaveTextContent('16'); // quota
      expect(cpuLine).toHaveTextContent('2'); // multiplier (gpus)
    });
  });

  describe('Loading State', () => {
    it('should pass isLoading prop to all TableLine components', () => {
      renderComponent({ isLoading: true });

      const skeletons = screen.getAllByTestId('skeleton');
      expect(skeletons).toHaveLength(3); // GPU, RAM, CPU
    });

    it('should not show alert when loading', () => {
      renderComponent({
        isLoading: true,
        currentResources: {
          gpus: 10, // Exceeds quota
          memoryPerGpu: 8,
          cpuPerGpu: 4,
        },
      });

      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  describe('Alert States', () => {
    it('should not show alert when resources are within limits', () => {
      renderComponent({
        currentResources: {
          gpus: 2,
          memoryPerGpu: 8,
          cpuPerGpu: 4,
        },
        quota: {
          gpus: 4,
          memory: 32,
          cpu: 16,
        },
        requiredResources: {
          gpus: 1,
          memoryPerGpu: 4,
          cpuPerGpu: 2,
        },
      });

      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('should show warning alert when resources exceed quota', () => {
      renderComponent({
        currentResources: {
          gpus: 5, // Exceeds GPU quota of 4
          memoryPerGpu: 8,
          cpuPerGpu: 4,
        },
      });

      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveAttribute('data-status', 'warning');
      expect(
        screen.getByText('Resources exceed quota limits'),
      ).toBeInTheDocument();
    });

    it('should show danger alert when resources are below required', () => {
      renderComponent({
        currentResources: {
          gpus: 0, // Below required GPU of 1
          memoryPerGpu: 8,
          cpuPerGpu: 4,
        },
      });

      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveAttribute('data-status', 'danger');
      expect(
        screen.getByText('Resources are below required minimum'),
      ).toBeInTheDocument();
    });

    it('should show danger alert when resources are below required AND exceed quota', () => {
      renderComponent({
        currentResources: {
          gpus: 0, // Below required
          memoryPerGpu: 40, // Total memory (0 * 40 = 0) is below required, but memoryPerGpu exceeds quota
          cpuPerGpu: 4,
        },
        quota: {
          gpus: 4,
          memory: 32,
          cpu: 16,
        },
        requiredResources: {
          gpus: 1,
          memoryPerGpu: 4,
          cpuPerGpu: 2,
        },
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      // The component shows "below required and exceed quota" when gpus=0 < requiredGpus=1,
      // and calculated totals exceed quota due to Math.max(gpus, 1) multiplier
      expect(
        screen.getByText('Resources are below required and exceed quota'),
      ).toBeInTheDocument();
    });

    it('should show danger alert with both conditions when resources truly exceed quota and are below required', () => {
      renderComponent({
        currentResources: {
          gpus: 6, // Exceeds GPU quota of 4
          memoryPerGpu: 2, // Total: 6 * 2 = 12 GB, below required 4 per GPU
          cpuPerGpu: 4,
        },
        quota: {
          gpus: 4,
          memory: 32,
          cpu: 16,
        },
        requiredResources: {
          gpus: 1,
          memoryPerGpu: 15, // Component compares totalMemory (12) < requiredMemoryPerGpu (15)
          cpuPerGpu: 2,
        },
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(
        screen.getByText('Resources are below required and exceed quota'),
      ).toBeInTheDocument();
    });

    it('should show warning alert when total memory exceeds quota', () => {
      renderComponent({
        currentResources: {
          gpus: 2,
          memoryPerGpu: 20, // Total: 2 * 20 = 40 GB, exceeds quota of 32
          cpuPerGpu: 4,
        },
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(
        screen.getByText('Resources exceed quota limits'),
      ).toBeInTheDocument();
    });

    it('should show warning alert when total CPU exceeds quota', () => {
      renderComponent({
        currentResources: {
          gpus: 2,
          memoryPerGpu: 8,
          cpuPerGpu: 10, // Total: 2 * 10 = 20 vCPUs, exceeds quota of 16
        },
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(
        screen.getByText('Resources exceed quota limits'),
      ).toBeInTheDocument();
    });

    it('should show danger alert when total memory is below required', () => {
      renderComponent({
        currentResources: {
          gpus: 2,
          memoryPerGpu: 2, // Total: 2 * 2 = 4 GB
          cpuPerGpu: 4,
        },
        requiredResources: {
          gpus: 1,
          memoryPerGpu: 5, // Component compares totalMemory (4) < requiredMemoryPerGpu (5)
          cpuPerGpu: 2,
        },
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(
        screen.getByText('Resources are below required minimum'),
      ).toBeInTheDocument();
    });

    it('should show danger alert when total CPU is below required', () => {
      renderComponent({
        currentResources: {
          gpus: 2,
          memoryPerGpu: 8,
          cpuPerGpu: 1, // Total: 2 * 1 = 2 vCPUs
        },
        requiredResources: {
          gpus: 1,
          memoryPerGpu: 4,
          cpuPerGpu: 3, // Component compares totalCpu (2) < requiredCpuPerGpu (3)
        },
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(
        screen.getByText('Resources are below required minimum'),
      ).toBeInTheDocument();
    });
  });

  describe('Resource Calculations', () => {
    it('should calculate total memory correctly', () => {
      renderComponent({
        currentResources: {
          gpus: 3,
          memoryPerGpu: 16,
          cpuPerGpu: 8,
        },
      });

      const ramLine = screen.getByTestId('table-line-ram');
      expect(ramLine).toHaveTextContent('16'); // memoryPerGpu value
      expect(ramLine).toHaveTextContent('3'); // multiplier (gpus)
    });

    it('should calculate total CPU correctly', () => {
      renderComponent({
        currentResources: {
          gpus: 4,
          memoryPerGpu: 8,
          cpuPerGpu: 6,
        },
      });

      const cpuLine = screen.getByTestId('table-line-cpu');
      expect(cpuLine).toHaveTextContent('6'); // cpuPerGpu value
      expect(cpuLine).toHaveTextContent('4'); // multiplier (gpus)
    });
  });

  describe('Edge Cases', () => {
    it('should handle zero GPUs', () => {
      renderComponent({
        currentResources: {
          gpus: 0,
          memoryPerGpu: 8,
          cpuPerGpu: 4,
        },
      });

      const gpuLine = screen.getByTestId('table-line-gpu');
      expect(gpuLine).toHaveTextContent('0');

      // With 0 GPUs, multiplier should be 1 due to Math.max(gpus, 1) to prevent division by zero
      const ramLine = screen.getByTestId('table-line-ram');
      expect(ramLine).toHaveTextContent('1'); // multiplier
    });

    it('should handle zero quota values', () => {
      renderComponent({
        quota: {
          gpus: 0,
          memory: 0,
          cpu: 0,
        },
      });

      const gpuLine = screen.getByTestId('table-line-gpu');
      expect(gpuLine).toHaveTextContent('0'); // quota

      const ramLine = screen.getByTestId('table-line-ram');
      expect(ramLine).toHaveTextContent('0'); // quota

      const cpuLine = screen.getByTestId('table-line-cpu');
      expect(cpuLine).toHaveTextContent('0'); // quota
    });

    it('should handle zero required resources', () => {
      renderComponent({
        requiredResources: {
          gpus: 0,
          memoryPerGpu: 0,
          cpuPerGpu: 0,
        },
      });

      const gpuLine = screen.getByTestId('table-line-gpu');
      expect(gpuLine).toHaveTextContent('0'); // req

      const ramLine = screen.getByTestId('table-line-ram');
      expect(ramLine).toHaveTextContent('0'); // req

      const cpuLine = screen.getByTestId('table-line-cpu');
      expect(cpuLine).toHaveTextContent('0'); // req
    });
  });

  describe('Memoization', () => {
    it('should recalculate totals when GPU count changes', () => {
      const { rerender } = renderComponent({
        currentResources: {
          gpus: 2,
          memoryPerGpu: 8,
          cpuPerGpu: 4,
        },
      });

      let ramLine = screen.getByTestId('table-line-ram');
      expect(ramLine).toHaveTextContent('2'); // multiplier

      rerender(
        <ResourceAllocationInformer
          {...defaultProps}
          currentResources={{
            gpus: 4,
            memoryPerGpu: 8,
            cpuPerGpu: 4,
          }}
        />,
      );

      ramLine = screen.getByTestId('table-line-ram');
      expect(ramLine).toHaveTextContent('4'); // updated multiplier
    });

    it('should recalculate alert status when resources change', () => {
      const { rerender } = renderComponent({
        currentResources: {
          gpus: 2, // Within quota
          memoryPerGpu: 8,
          cpuPerGpu: 4,
        },
      });

      expect(screen.queryByRole('alert')).not.toBeInTheDocument();

      rerender(
        <ResourceAllocationInformer
          {...defaultProps}
          currentResources={{
            gpus: 5, // Exceeds quota
            memoryPerGpu: 8,
            cpuPerGpu: 4,
          }}
        />,
      );

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(
        screen.getByText('Resources exceed quota limits'),
      ).toBeInTheDocument();
    });
  });

  describe('Alert Icon', () => {
    it('should render alert when alert is shown', () => {
      renderComponent({
        currentResources: {
          gpus: 5, // Exceeds quota
          memoryPerGpu: 8,
          cpuPerGpu: 4,
        },
      });

      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveAttribute('data-status', 'warning');
    });
  });
});
