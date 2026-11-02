// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';

import { ScalingStatusCard } from '@/components/features/workloads/ScalingStatusCard';
import type { components } from '@/types/api';
import wrapper from '@/__tests__/ProviderWrapper';

type AIMServiceSpec = components['schemas']['AIMServiceSpec'];

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@amdenterpriseai/hooks', () => ({
  useSystemToast: () => ({
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

vi.mock('@amdenterpriseai/components', () => ({
  Card: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    [key: string]: unknown;
  }) => <div {...props}>{children}</div>,
  CardHeader: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    [key: string]: unknown;
  }) => <div {...props}>{children}</div>,
  CardBody: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    [key: string]: unknown;
  }) => <div {...props}>{children}</div>,
  ClientSideDataTable: ({ data }: { data: { name: string }[] }) => (
    <div data-testid="replicas-table">
      {data.map((r) => (
        <div key={r.name} data-testid={`replica-${r.name}`}>
          {r.name}
        </div>
      ))}
    </div>
  ),
  DateDisplay: ({ date }: { date: string }) => <span>{date}</span>,
  NoDataDisplay: () => <span data-testid="no-data">—</span>,
  StatusDisplay: ({ type }: { type: string }) => <span>{type}</span>,
  Button: ({ children, onPress, onClick, ...props }: any) => (
    <button onClick={onPress ?? onClick} {...props}>
      {children}
    </button>
  ),
  ButtonGroup: ({ children }: any) => <fieldset>{children}</fieldset>,
}));

vi.mock('@/lib/app/inference', () => ({
  updateInferenceScaling: vi.fn(),
}));

vi.mock('@/lib/app/aims', () => ({
  updateWorkloadScaling: vi.fn(),
  AIM_MAX_REPLICAS: 30,
  SCALING_METRIC_KEYS: [
    { key: 'vllm:num_requests_running', translationKey: 'runningRequests' },
    { key: 'vllm:num_requests_waiting', translationKey: 'waitingRequests' },
  ],
  AGGREGATION_OPTION_KEYS: [
    { key: 'avg', translationKey: 'avg' },
    { key: 'max', translationKey: 'max' },
    { key: 'min', translationKey: 'min' },
  ],
  TARGET_TYPE_OPTION_KEYS: [
    { key: 'Value', translationKey: 'value' },
    { key: 'AverageValue', translationKey: 'averageValue' },
    { key: 'Utilization', translationKey: 'utilization' },
  ],
  DEFAULT_AUTOSCALING: {
    minReplicas: 1,
    maxReplicas: 3,
    metricQuery: 'vllm:num_requests_waiting',
    operationOverTime: 'avg',
    targetType: 'AverageValue',
    targetValue: 1,
  },
}));

// Mock DeploymentSettingsDrawer
vi.mock('@/components/features/workloads/DeploymentSettingsDrawer', () => ({
  DeploymentSettingsDrawer: vi.fn(
    ({ isOpen, onClose, onSuccess, id, namespace, initialValues }) => (
      <div data-testid="deployment-settings-drawer">
        <div data-testid="drawer-is-open">{isOpen ? 'open' : 'closed'}</div>
        <div data-testid="drawer-workload-id">{id}</div>
        <div data-testid="drawer-workload-name">
          {namespace && id ? 'My Workload' : ''}
        </div>
        <div data-testid="drawer-initial-values">
          {JSON.stringify(initialValues)}
        </div>
        <button data-testid="close-drawer" onClick={onClose}>
          Close
        </button>
        <button
          data-testid="save-settings"
          onClick={() => onSuccess?.(initialValues)}
        >
          Save
        </button>
      </div>
    ),
  ),
}));

describe('ScalingStatusCard', () => {
  const mockOnSettingsSaved = vi.fn();

  const mockSpec: AIMServiceSpec = {
    model: {
      name: 'ghcr.io/silogen/aim-meta-llama-llama-3-1-8b-instruct:0.7.0',
    },
    replicas: 1,
    routing: {
      annotations: {},
      enabled: false,
    },
    runtimeConfigName: 'default',
    minReplicas: 1,
    maxReplicas: 5,
    autoScaling: {
      metrics: [
        {
          type: 'PodMetric',
          podmetric: {
            metric: {
              backend: 'opentelemetry',
              metricNames: ['vllm:num_requests_running'],
              query: 'vllm:num_requests_running',
              operationOverTime: 'avg',
            },
            target: {
              type: 'Value',
              value: '10',
            },
          },
        },
      ],
    },
  };

  const mockSpecWithoutAutoscaling: AIMServiceSpec = {
    model: {
      name: 'test-model',
    },
    replicas: 1,
    routing: {
      annotations: {},
      enabled: false,
    },
    runtimeConfigName: 'default',
    minReplicas: 1,
    maxReplicas: 1,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders the card with title', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        {
          wrapper,
        },
      );

      expect(screen.getByText('title')).toBeInTheDocument();
    });

    it('renders settings button', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        {
          wrapper,
        },
      );

      expect(screen.getByText('actions.settings')).toBeInTheDocument();
    });

    it('displays current/desired and Replicas (minimum) when runtime is provided', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          runtime={{ currentReplicas: 2, desiredReplicas: 4, maxReplicas: 5 }}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText(/\/ 5/)).toBeInTheDocument();
      expect(screen.getByText('replicasMinimum')).toBeInTheDocument();
    });

    it('displays scaling metric label', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        {
          wrapper,
        },
      );

      expect(screen.getByText('scalingMetric.label')).toBeInTheDocument();
      expect(
        screen.getByText('scalingMetric.options.runningRequests'),
      ).toBeInTheDocument();
    });

    it('displays target value with operation over time', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        {
          wrapper,
        },
      );

      expect(screen.getByText('targetValue.label')).toBeInTheDocument();
      expect(screen.getByText('10 (avg)')).toBeInTheDocument();
    });
  });

  describe('Spec Parsing', () => {
    it('handles waiting requests metric', () => {
      const specWithWaiting: AIMServiceSpec = {
        ...mockSpec,
        autoScaling: {
          metrics: [
            {
              type: 'PodMetric',
              podmetric: {
                metric: {
                  backend: 'opentelemetry',
                  metricNames: ['vllm:num_requests_waiting'],
                  query: 'vllm:num_requests_waiting',
                  operationOverTime: 'max',
                },
                target: {
                  type: 'AverageValue',
                  value: '5',
                },
              },
            },
          ],
        },
      };

      render(
        <ScalingStatusCard
          spec={specWithWaiting}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(
        screen.getByText('scalingMetric.options.waitingRequests'),
      ).toBeInTheDocument();
      expect(screen.getByText('5 (max)')).toBeInTheDocument();
    });

    it('handles unknown metric query', () => {
      const specWithUnknown: AIMServiceSpec = {
        ...mockSpec,
        autoScaling: {
          metrics: [
            {
              type: 'PodMetric',
              podmetric: {
                metric: {
                  backend: 'opentelemetry',
                  metricNames: ['custom:metric'],
                  query: 'custom:metric',
                  operationOverTime: 'min',
                },
                target: {
                  type: 'Value',
                  value: '20',
                },
              },
            },
          ],
        },
      };

      render(
        <ScalingStatusCard
          spec={specWithUnknown}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      // Falls back to showing the raw query
      expect(screen.getByText('custom:metric')).toBeInTheDocument();
    });

    it('handles spec without autoscaling', () => {
      render(
        <ScalingStatusCard
          spec={mockSpecWithoutAutoscaling}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      // Should show default/empty target value
      expect(screen.getByText('0 (avg)')).toBeInTheDocument();
    });

    it('handles spec with empty metrics array', () => {
      const specWithEmptyMetrics: AIMServiceSpec = {
        ...mockSpec,
        autoScaling: {
          metrics: [],
        },
      };

      render(
        <ScalingStatusCard
          spec={specWithEmptyMetrics}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(screen.getByText('title')).toBeInTheDocument();
    });
  });

  describe('Drawer Interaction', () => {
    it('drawer is initially closed', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        {
          wrapper,
        },
      );

      expect(screen.getByTestId('drawer-is-open')).toHaveTextContent('closed');
    });

    it('opens drawer when settings button is clicked', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        {
          wrapper,
        },
      );

      const settingsButton = screen.getByText('actions.settings');
      fireEvent.click(settingsButton);

      expect(screen.getByTestId('drawer-is-open')).toHaveTextContent('open');
    });

    it('closes drawer when onClose is called', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        {
          wrapper,
        },
      );

      // Open drawer
      const settingsButton = screen.getByText('actions.settings');
      fireEvent.click(settingsButton);
      expect(screen.getByTestId('drawer-is-open')).toHaveTextContent('open');

      // Close drawer
      const closeButton = screen.getByTestId('close-drawer');
      fireEvent.click(closeButton);
      expect(screen.getByTestId('drawer-is-open')).toHaveTextContent('closed');
    });

    it('passes workloadId to drawer', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          id="test-workload-123"
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(screen.getByTestId('drawer-workload-id')).toHaveTextContent(
        'test-workload-123',
      );
    });

    it('passes workloadName to drawer', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          namespace="test-namespace"
          id="test-workload-123"
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(screen.getByTestId('drawer-workload-name')).toHaveTextContent(
        'My Workload',
      );
    });

    it('passes initial values to drawer based on spec', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        {
          wrapper,
        },
      );

      const initialValues = JSON.parse(
        screen.getByTestId('drawer-initial-values').textContent || '{}',
      );

      expect(initialValues).toEqual({
        minReplicas: 1,
        maxReplicas: 5,
        metricQuery: 'vllm:num_requests_running',
        operationOverTime: 'avg',
        targetType: 'Value',
        targetValue: 10,
      });
    });

    it('calls onSettingsSaved with all form values when drawer saves', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      const settingsButton = screen.getByText('actions.settings');
      fireEvent.click(settingsButton);
      const saveButton = screen.getByTestId('save-settings');
      fireEvent.click(saveButton);

      expect(mockOnSettingsSaved).toHaveBeenCalledWith({
        minReplicas: 1,
        maxReplicas: 5,
        metricQuery: 'vllm:num_requests_running',
        operationOverTime: 'avg',
        targetType: 'Value',
        targetValue: 10,
      });
    });
  });

  describe('Different Replica Configurations', () => {
    it('displays current replicas and Replicas (minimum) for high replica spec when runtime provided', () => {
      const highReplicaSpec: AIMServiceSpec = {
        ...mockSpec,
        minReplicas: 5,
        maxReplicas: 30,
      };

      render(
        <ScalingStatusCard
          spec={highReplicaSpec}
          runtime={{
            currentReplicas: 10,
            desiredReplicas: 15,
            maxReplicas: 30,
          }}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(screen.getByText('10')).toBeInTheDocument();
      expect(screen.getByText('replicasMinimum')).toBeInTheDocument();
    });

    it('passes min/max replicas to drawer initial values', () => {
      const sameReplicaSpec: AIMServiceSpec = {
        ...mockSpec,
        minReplicas: 3,
        maxReplicas: 3,
      };

      render(
        <ScalingStatusCard
          spec={sameReplicaSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      const initialValues = JSON.parse(
        screen.getByTestId('drawer-initial-values').textContent || '{}',
      );
      expect(initialValues.minReplicas).toBe(3);
      expect(initialValues.maxReplicas).toBe(3);
    });
  });

  describe('Replicas Accordion', () => {
    const mockReplicas = [
      {
        metadata: {
          name: 'pod-abc-1',
          creationTimestamp: '2024-01-01T00:00:00Z',
        },
        status: { phase: 'Running', containerStatuses: [{ ready: true }] },
        spec: {
          containers: [{ resources: { limits: { 'amd.com/gpu': '2' } } }],
        },
      },
      {
        metadata: { name: 'pod-abc-2' },
        status: { phase: 'Pending', containerStatuses: [{ ready: false }] },
        spec: { containers: [{ resources: { limits: {} } }] },
      },
    ];

    it('does not show chevron when replicas prop is not provided', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(
        screen.queryByRole('button', { name: 'replicas.toggle' }),
      ).not.toBeInTheDocument();
    });

    it('shows chevron when replicas prop is provided', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          replicas={mockReplicas}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(
        screen.getByRole('button', { name: 'replicas.toggle' }),
      ).toBeInTheDocument();
    });

    it('accordion is collapsed by default', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          replicas={mockReplicas}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      expect(
        screen.getByRole('button', { name: 'replicas.toggle' }),
      ).toHaveAttribute('aria-expanded', 'false');
    });

    it('clicking chevron expands the replicas table', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          replicas={mockReplicas}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      fireEvent.click(screen.getByRole('button', { name: 'replicas.toggle' }));

      expect(
        screen.getByRole('button', { name: 'replicas.toggle' }),
      ).toHaveAttribute('aria-expanded', 'true');
    });

    it('clicking chevron again collapses the table', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          replicas={mockReplicas}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      const toggle = screen.getByRole('button', { name: 'replicas.toggle' });
      fireEvent.click(toggle);
      fireEvent.click(toggle);

      expect(toggle).toHaveAttribute('aria-expanded', 'false');
    });

    it('shows replica names in the table after expanding', () => {
      render(
        <ScalingStatusCard
          spec={mockSpec}
          replicas={mockReplicas}
          onSettingsSaved={mockOnSettingsSaved}
        />,
        { wrapper },
      );

      fireEvent.click(screen.getByRole('button', { name: 'replicas.toggle' }));

      expect(screen.getByTestId('replica-pod-abc-1')).toBeInTheDocument();
      expect(screen.getByTestId('replica-pod-abc-2')).toBeInTheDocument();
    });
  });
});
