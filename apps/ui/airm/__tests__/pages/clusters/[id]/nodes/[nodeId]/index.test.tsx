// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, waitFor } from '@testing-library/react';

import { getServerSession } from 'next-auth';
import { serverSideTranslations } from 'next-i18next/serverSideTranslations';

import {
  fetchNodeGpuUtilization,
  fetchNodeGpuVramUtilization,
  fetchNodePcieBandwidth,
  fetchNodePowerUsage,
} from '@/services/app';
import { getCluster, getClusterNode } from '@/services/server';

import NodeDetailPage, {
  getServerSideProps,
} from '@/pages/clusters/[id]/nodes/[nodeId]';

import {
  generateClusterNodesMock,
  generateNodeGpuUtilizationMock,
  generateNodePcieBandwidthMock,
  generateNodePowerUsageMock,
} from '@/__mocks__/utils/cluster-mock';
import wrapper from '@/__tests__/ProviderWrapper';
import '@testing-library/jest-dom';

const [mockNode, nodeWithoutGpu] = generateClusterNodesMock(2);

vi.mock('next/router', () => ({
  useRouter: () => ({
    query: { id: 'cluster-1', nodeId: 'gpu-m350-0001' },
    isReady: true,
    back: vi.fn(),
    push: vi.fn(),
  }),
}));

vi.mock('next-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next-i18next')>();
  return {
    ...actual,
    useTranslation: (ns?: string | string[]) => ({
      t: (key: string) => key,
      i18n: { language: 'en' },
    }),
  };
});

vi.mock('next-auth', () => ({
  getServerSession: vi.fn(),
}));

vi.mock('next-i18next/serverSideTranslations', () => ({
  serverSideTranslations: vi.fn().mockResolvedValue({
    _nextI18Next: {
      initialI18nStore: {
        en: { clusters: { title: 'Clusters' } },
      },
    },
  }),
}));

vi.mock('@/services/server', () => ({
  getCluster: vi.fn(),
  getClusterNode: vi.fn(),
}));

vi.mock('@/services/app', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/app')>()),
  fetchNodeGpuUtilization: vi.fn(),
  fetchNodeGpuVramUtilization: vi.fn(),
  fetchNodePcieBandwidth: vi.fn(),
  fetchNodePowerUsage: vi.fn(),
  fetchNodeWorkloadsMetrics: vi.fn().mockResolvedValue({ data: [] }),
  getClusterProjects: vi.fn().mockResolvedValue({ data: [] }),
}));

const mockNodeGpuUtilizationEmpty = generateNodeGpuUtilizationMock(0);
const mockPowerUsageEmpty = generateNodePowerUsageMock(0);
const mockPcieBandwidthEmpty = generateNodePcieBandwidthMock(0);

describe('Node detail page', () => {
  beforeEach(() => {
    vi.mocked(fetchNodeGpuUtilization).mockResolvedValue(
      mockNodeGpuUtilizationEmpty as any,
    );
    vi.mocked(fetchNodeGpuVramUtilization).mockResolvedValue(
      mockNodeGpuUtilizationEmpty as any,
    );
    vi.mocked(fetchNodePowerUsage).mockResolvedValue(
      mockPowerUsageEmpty as any,
    );
    vi.mocked(fetchNodePcieBandwidth).mockResolvedValue(
      mockPcieBandwidthEmpty as any,
    );
  });

  it('renders breadcrumb via props and does not duplicate in body', () => {
    render(<NodeDetailPage node={mockNode} />, {
      wrapper,
    });
    expect(screen.getByText('gpu-m350-0001 node')).toBeInTheDocument();
  });

  it('renders node name and status (icon only with aria-label)', () => {
    render(<NodeDetailPage node={mockNode} />, {
      wrapper,
    });
    expect(screen.getByText('gpu-m350-0001 node')).toBeInTheDocument();
    expect(
      screen.getByLabelText('clusters:nodes.detail.status.unhealthy'),
    ).toBeInTheDocument();
  });

  it('renders Device metrics section with title', () => {
    render(<NodeDetailPage node={mockNode} />, {
      wrapper,
    });
    expect(
      screen.getByText('clusters:nodes.detail.deviceMetrics.title'),
    ).toBeInTheDocument();
  });

  it('renders time range selector (1 hour, 24 hours, 7 days)', () => {
    render(<NodeDetailPage node={mockNode} />, {
      wrapper,
    });
    expect(
      screen.getByRole('tablist', {
        name: 'timeRange.description',
      }),
    ).toBeInTheDocument();
  });

  it('renders GPU device selector', () => {
    render(<NodeDetailPage node={mockNode} />, {
      wrapper,
    });
    const selector = screen.getByRole('button', {
      name: /clusters:nodes.detail.deviceMetrics.gpuDevice.label/,
    });
    expect(selector).toBeInTheDocument();
  });

  it('does not render a separate metrics dropdown', () => {
    render(<NodeDetailPage node={mockNode} />, {
      wrapper,
    });
    const gpuDeviceButtons = screen.getAllByRole('button', {
      name: /gpuDevice\.label/,
    });
    expect(gpuDeviceButtons).toHaveLength(1);
  });

  it('renders back button', () => {
    render(<NodeDetailPage node={mockNode} />, {
      wrapper,
    });
    const backButton = screen.getByRole('button', {
      name: 'common:actions.back.title',
    });
    expect(backButton).toBeInTheDocument();
  });

  it('renders GPU Type card with node gpuInfo name when node has GPU', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(screen.getByText('Instinct M1350')).toBeInTheDocument();
  });

  it('renders GPU Type as dash when node has no GPU', () => {
    render(<NodeDetailPage node={nodeWithoutGpu} />, { wrapper });
    const dashes = screen.getAllByText('-');
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it('renders GPU Memory with human-readable value when node has GPU', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(screen.getByText(/2\.00 TB/)).toBeInTheDocument();
  });

  it('renders CPU Cores from node cpuMilliCores', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('renders System Memory with human-readable value', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(screen.getByText(/25\.00 GB/)).toBeInTheDocument();
  });

  it('renders spec card titles', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(
      screen.getByText('clusters:nodes.detail.specs.gpuType.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('clusters:nodes.detail.specs.gpuMemory.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('clusters:nodes.detail.specs.cpuCores.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('clusters:nodes.detail.specs.systemMemory.title'),
    ).toBeInTheDocument();
  });

  it('shows GPU utilization no-data message when query returns no devices', async () => {
    vi.mocked(fetchNodeGpuUtilization).mockResolvedValue(
      mockNodeGpuUtilizationEmpty as any,
    );
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    await waitFor(() => {
      const noDataMessages = screen.getAllByText(
        'clusters:nodes.detail.deviceMetrics.noData',
      );
      expect(noDataMessages.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('calls fetchNodeGpuVramUtilization on initial load (default Memory tab)', async () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    await waitFor(() => {
      expect(fetchNodeGpuVramUtilization).toHaveBeenCalled();
    });
    expect(fetchNodeGpuVramUtilization).toHaveBeenCalledWith(
      'cluster-1',
      'gpu-m350-0001',
      expect.any(Date),
      expect.any(Date),
    );
    expect(fetchNodeGpuUtilization).not.toHaveBeenCalled();
  });

  it('renders GPU utilization tab labels (Memory, Clock, GPU usage)', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(
      screen.getByText(
        'clusters:nodes.detail.deviceMetrics.gpuUtilization.tabMemoryUtilization',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'clusters:nodes.detail.deviceMetrics.gpuUtilization.tabClockSpeed',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'clusters:nodes.detail.deviceMetrics.gpuUtilization.tabGpuUsage',
      ),
    ).toBeInTheDocument();
  });

  it('renders GPU Power Consumption title', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(
      screen.getByText(
        'clusters:nodes.detail.deviceMetrics.gpuPowerConsumption.title',
      ),
    ).toBeInTheDocument();
  });

  it('shows power consumption no-data message when query returns no devices', async () => {
    vi.mocked(fetchNodePowerUsage).mockResolvedValue(
      mockPowerUsageEmpty as any,
    );
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByText('clusters:nodes.detail.deviceMetrics.noPowerData'),
      ).toBeInTheDocument();
    });
  });

  it('calls fetchNodePowerUsage with clusterId, nodeId, and time range when router is ready', async () => {
    vi.mocked(fetchNodePowerUsage).mockResolvedValue(
      mockPowerUsageEmpty as any,
    );
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    await waitFor(() => {
      expect(fetchNodePowerUsage).toHaveBeenCalled();
    });
    expect(fetchNodePowerUsage).toHaveBeenCalledWith(
      'cluster-1',
      'gpu-m350-0001',
      expect.any(Date),
      expect.any(Date),
    );
  });

  it('renders PCIe Traffic section title', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(
      screen.getByText('clusters:nodes.detail.deviceMetrics.pcieTraffic.title'),
    ).toBeInTheDocument();
  });

  it('renders PCIe Traffic tab labels (bandwidth and performance)', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(
      screen.getByText(
        'clusters:nodes.detail.deviceMetrics.pcieTraffic.tabBandwidth',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'clusters:nodes.detail.deviceMetrics.pcieTraffic.tabPerformance',
      ),
    ).toBeInTheDocument();
  });

  it('calls fetchNodePcieBandwidth with clusterId, nodeId, and time range when router is ready', async () => {
    vi.mocked(fetchNodePcieBandwidth).mockResolvedValue(
      mockPcieBandwidthEmpty as any,
    );
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    await waitFor(() => {
      expect(fetchNodePcieBandwidth).toHaveBeenCalled();
    });
    expect(fetchNodePcieBandwidth).toHaveBeenCalledWith(
      'cluster-1',
      'gpu-m350-0001',
      expect.any(Date),
      expect.any(Date),
    );
  });

  it('renders Workloads on Node section title', () => {
    render(<NodeDetailPage node={mockNode} />, { wrapper });
    expect(
      screen.getByText('clusters:nodes.detail.workloads.title'),
    ).toBeInTheDocument();
  });
});

describe('Node detail page getServerSideProps', () => {
  const context = {
    req: {},
    res: {},
    locale: 'en',
    params: { id: 'cluster-123', nodeId: 'node-456' },
  };

  const mockCluster = { id: 'cluster-123', name: 'Production Cluster' };
  const translationsProp = {
    _nextI18Next: {
      initialI18nStore: {
        en: { clusters: { title: 'Clusters' } },
      },
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (getServerSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      user: { email: 'test@example.com' },
      accessToken: 'access-token',
    });
    (getCluster as ReturnType<typeof vi.fn>).mockResolvedValue(mockCluster);
    (serverSideTranslations as ReturnType<typeof vi.fn>).mockResolvedValue(
      translationsProp,
    );
  });

  it('calls getClusterNode with clusterId, nodeId, and accessToken', async () => {
    (getClusterNode as ReturnType<typeof vi.fn>).mockResolvedValue(mockNode);

    await getServerSideProps(context as any);

    expect(getClusterNode).toHaveBeenCalledTimes(1);
    expect(getClusterNode).toHaveBeenCalledWith(
      'cluster-123',
      'node-456',
      'access-token',
    );
  });

  it('returns node and pageBreadcrumb when getClusterNode succeeds', async () => {
    (getClusterNode as ReturnType<typeof vi.fn>).mockResolvedValue(mockNode);

    const result = await getServerSideProps(context as any);

    expect(getCluster).toHaveBeenCalledWith('cluster-123', 'access-token');
    expect(result).toHaveProperty('props');
    expect((result as any).props).toHaveProperty('node', mockNode);
    expect((result as any).props.pageBreadcrumb).toEqual([
      { title: 'Clusters', href: '/clusters' },
      { title: 'Production Cluster', href: '/clusters/cluster-123' },
      { title: 'gpu-m350-0001' },
    ]);
  });

  it('redirects to cluster page when getCluster throws', async () => {
    (getClusterNode as ReturnType<typeof vi.fn>).mockResolvedValue(mockNode);
    (getCluster as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Cluster not found'),
    );

    const result = await getServerSideProps(context as any);

    expect(result).toEqual({
      redirect: {
        destination: '/clusters/cluster-123',
        permanent: false,
      },
    });
  });

  it('redirects to cluster page when getClusterNode throws', async () => {
    (getClusterNode as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Not found'),
    );

    const result = await getServerSideProps(context as any);

    expect(result).toEqual({
      redirect: {
        destination: '/clusters/cluster-123',
        permanent: false,
      },
    });
  });

  it('redirects to / when getClusterNode throws and params.id is missing', async () => {
    (getClusterNode as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Not found'),
    );

    const result = await getServerSideProps({
      ...context,
      params: { id: undefined, nodeId: 'node-456' },
    } as any);

    expect(result).toEqual({
      redirect: { destination: '/', permanent: false },
    });
  });
});
