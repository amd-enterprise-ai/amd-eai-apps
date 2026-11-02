// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  fetchClusterWorkloadsMetrics,
  fetchClusterWorkloadsStatusStats,
  fetchNodeGpuClockSpeed,
  fetchNodeGpuJunctionTemperature,
  fetchNodeGpuMemoryTemperature,
  fetchNodeGpuUtilization,
  fetchNodeGpuVramUtilization,
  fetchNodePowerUsage,
  fetchNodeWorkloadsMetrics,
} from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

vi.mock('@amdenterpriseai/utils/app', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/utils/app')>();
  return {
    ...actual,
    getErrorMessage: vi.fn().mockResolvedValue('error message'),
    buildQueryParams: vi.fn().mockReturnValue('page=1&pageSize=10'),
  };
});

const mockJson = vi.fn();
const mockFetch = vi.fn();

globalThis.fetch = mockFetch as any;

beforeEach(() => {
  mockFetch.mockReset();
  mockJson.mockReset();
});

describe('fetchClusterWorkloadsMetrics', () => {
  it('returns data when response is ok', async () => {
    const data = {
      data: [
        {
          id: 'workload1',
          displayName: 'Test Workload',
          status: 'Running',
        },
      ],
      pagination: {
        total: 1,
        page: 1,
        pageSize: 10,
      },
    };
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(data),
    });

    const clusterId = 'cluster-123';
    const params = {
      page: 1,
      pageSize: 10,
      sort: [],
      filter: [],
    };

    const res = await fetchClusterWorkloadsMetrics(clusterId, params);
    expect(res).toEqual(data);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/clusters/${clusterId}/workloads/metrics`),
    );
  });

  it('throws error when response is not ok', async () => {
    mockFetch.mockResolvedValue({ ok: false });
    const clusterId = 'cluster-123';
    const params = {
      page: 1,
      pageSize: 10,
      sort: [],
      filter: [],
    };

    await expect(
      fetchClusterWorkloadsMetrics(clusterId, params),
    ).rejects.toThrow(APIRequestError);
  });
});

describe('fetchClusterWorkloadsStatusStats', () => {
  it('returns data when response is ok', async () => {
    const data = {
      name: 'Test Cluster',
      totalWorkloads: 15,
      statusCounts: [
        { status: 'Running', count: 5 },
        { status: 'Pending', count: 3 },
        { status: 'Complete', count: 7 },
      ],
    };
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(data),
    });

    const clusterId = 'cluster-123';
    const res = await fetchClusterWorkloadsStatusStats(clusterId);
    expect(res).toEqual(data);
    expect(mockFetch).toHaveBeenCalledWith(
      `/api/clusters/${clusterId}/workloads/stats`,
    );
  });

  it('throws error when response is not ok', async () => {
    mockFetch.mockResolvedValue({ ok: false });
    const clusterId = 'cluster-123';

    await expect(fetchClusterWorkloadsStatusStats(clusterId)).rejects.toThrow(
      APIRequestError,
    );
  });
});

describe('fetchNodeGpuUtilization', () => {
  it('includes step parameter when provided', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue({
        gpuDevices: [],
        range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
      }),
    });

    const clusterId = 'cluster-123';
    const nodeId = 'node-456';
    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    await fetchNodeGpuUtilization(clusterId, nodeId, start, end, 60);

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step=60'));
  });

  it('passes different step values correctly', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue({
        gpuDevices: [],
        range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
      }),
    });

    const clusterId = 'cluster-123';
    const nodeId = 'node-456';
    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    await fetchNodeGpuUtilization(clusterId, nodeId, start, end, 300);

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step=300'));
  });
});

const nodeMetricRawResponse = {
  gpuDevices: [
    {
      gpuUuid: 'uuid-1',
      gpuId: '0',
      hostname: 'node-1',
      metric: {
        seriesLabel: 'vramUtilizationPct',
        values: [{ timestamp: '2024-01-01T00:00:00Z', value: 42 }],
      },
    },
  ],
  range: { start: '2024-01-01T00:00:00Z', end: '2024-01-01T01:00:00Z' },
};

describe('fetchNodeGpuVramUtilization', () => {
  const clusterId = 'cluster-1';
  const nodeId = 'node-1';
  const start = new Date('2024-01-01T00:00:00Z');
  const end = new Date('2024-01-01T01:00:00Z');

  it('returns normalized data when response is ok', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(nodeMetricRawResponse),
    });

    const res = await fetchNodeGpuVramUtilization(
      clusterId,
      nodeId,
      start,
      end,
    );

    expect(res).toEqual(nodeMetricRawResponse);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        `/api/clusters/${clusterId}/nodes/${nodeId}/metrics/gpu-utilization/memory-utilization`,
      ),
    );
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        `start=${encodeURIComponent(start.toISOString())}`,
      ),
    );
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(`end=${encodeURIComponent(end.toISOString())}`),
    );
  });

  it('includes step parameter when provided', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(nodeMetricRawResponse),
    });

    await fetchNodeGpuVramUtilization(clusterId, nodeId, start, end, 60);

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step=60'));
  });

  it('throws APIRequestError when response is not ok', async () => {
    mockFetch.mockResolvedValue({ ok: false });

    await expect(
      fetchNodeGpuVramUtilization(clusterId, nodeId, start, end),
    ).rejects.toThrow(APIRequestError);
  });
});

describe('fetchNodeGpuClockSpeed', () => {
  const clusterId = 'cluster-1';
  const nodeId = 'node-1';
  const start = new Date('2024-01-01T00:00:00Z');
  const end = new Date('2024-01-01T01:00:00Z');

  const clockRawResponse = {
    gpuDevices: [
      {
        gpuUuid: 'uuid-1',
        gpuId: '0',
        hostname: 'node-1',
        metric: {
          seriesLabel: 'clockSpeedMhz',
          values: [{ timestamp: '2024-01-01T00:00:00Z', value: 1800 }],
        },
      },
    ],
    range: { start: '2024-01-01T00:00:00Z', end: '2024-01-01T01:00:00Z' },
  };

  it('returns normalized data when response is ok', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(clockRawResponse),
    });

    const res = await fetchNodeGpuClockSpeed(clusterId, nodeId, start, end);

    expect(res).toEqual(clockRawResponse);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        `/api/clusters/${clusterId}/nodes/${nodeId}/metrics/gpu-utilization/clock-speed`,
      ),
    );
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        `start=${encodeURIComponent(start.toISOString())}`,
      ),
    );
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(`end=${encodeURIComponent(end.toISOString())}`),
    );
  });

  it('includes step parameter when provided', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(clockRawResponse),
    });

    await fetchNodeGpuClockSpeed(clusterId, nodeId, start, end, 60);

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step=60'));
  });

  it('throws APIRequestError when response is not ok', async () => {
    mockFetch.mockResolvedValue({ ok: false });

    await expect(
      fetchNodeGpuClockSpeed(clusterId, nodeId, start, end),
    ).rejects.toThrow(APIRequestError);
  });
});

describe('fetchNodePowerUsage', () => {
  it('calls power-usage endpoint and always passes step param', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue({
        gpuDevices: [],
        range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
      }),
    });

    const clusterId = 'cluster-123';
    const nodeId = 'node-456';
    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    await fetchNodePowerUsage(clusterId, nodeId, start, end);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        '/api/clusters/cluster-123/nodes/node-456/metrics/power-usage',
      ),
    );
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step='));
  });

  it('calculates step to produce 12 intervals for 1h range', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue({
        gpuDevices: [],
        range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
      }),
    });

    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    await fetchNodePowerUsage('c1', 'n1', start, end);

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step=300'));
  });

  it('throws error when response is not ok', async () => {
    mockFetch.mockResolvedValue({ ok: false });

    await expect(
      fetchNodePowerUsage('c1', 'n1', new Date(), new Date()),
    ).rejects.toThrow(APIRequestError);
  });
});

describe('fetchNodeGpuJunctionTemperature', () => {
  it('calls junction temperature endpoint and always passes step param', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue({
        gpuDevices: [],
        range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
      }),
    });

    const clusterId = 'cluster-123';
    const nodeId = 'node-456';
    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    await fetchNodeGpuJunctionTemperature(clusterId, nodeId, start, end);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        '/api/clusters/cluster-123/nodes/node-456/metrics/temperature/junction',
      ),
    );
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step='));
  });

  it('calculates step to produce 12 intervals for 1h range', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue({
        gpuDevices: [],
        range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
      }),
    });

    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    await fetchNodeGpuJunctionTemperature('c1', 'n1', start, end);

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step=300'));
  });

  it('returns normalized data when response is ok', async () => {
    const rawResponse = {
      gpuDevices: [
        {
          gpuUuid: 'uuid-1',
          gpuId: '0',
          hostname: 'node-1',
          metric: {
            seriesLabel: 'junctionTemperatureCelsius',
            values: [{ timestamp: '2025-01-01T00:00:00Z', value: 72.5 }],
          },
        },
      ],
      range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
    };
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(rawResponse),
    });

    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    const res = await fetchNodeGpuJunctionTemperature('c1', 'n1', start, end);

    expect(res.gpuDevices).toHaveLength(1);
    expect(res.gpuDevices[0].metric.seriesLabel).toBe(
      'junctionTemperatureCelsius',
    );
    expect(res.gpuDevices[0].metric.values[0].value).toBe(72.5);
  });

  it('throws error when response is not ok', async () => {
    mockFetch.mockResolvedValue({ ok: false });

    await expect(
      fetchNodeGpuJunctionTemperature('c1', 'n1', new Date(), new Date()),
    ).rejects.toThrow(APIRequestError);
  });
});

describe('fetchNodeGpuMemoryTemperature', () => {
  it('calls memory temperature endpoint and always passes step param', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue({
        gpuDevices: [],
        range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
      }),
    });

    const clusterId = 'cluster-123';
    const nodeId = 'node-456';
    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    await fetchNodeGpuMemoryTemperature(clusterId, nodeId, start, end);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        '/api/clusters/cluster-123/nodes/node-456/metrics/temperature/memory',
      ),
    );
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step='));
  });

  it('calculates step to produce 12 intervals for 1h range', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue({
        gpuDevices: [],
        range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
      }),
    });

    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    await fetchNodeGpuMemoryTemperature('c1', 'n1', start, end);

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('step=300'));
  });

  it('returns normalized data when response is ok', async () => {
    const rawResponse = {
      gpuDevices: [
        {
          gpuUuid: 'uuid-1',
          gpuId: '0',
          hostname: 'node-1',
          metric: {
            seriesLabel: 'memoryTemperatureCelsius',
            values: [{ timestamp: '2025-01-01T00:00:00Z', value: 65.5 }],
          },
        },
      ],
      range: { start: '2025-01-01T00:00:00Z', end: '2025-01-01T01:00:00Z' },
    };
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(rawResponse),
    });

    const start = new Date('2025-01-01T00:00:00Z');
    const end = new Date('2025-01-01T01:00:00Z');

    const res = await fetchNodeGpuMemoryTemperature('c1', 'n1', start, end);

    expect(res.gpuDevices).toHaveLength(1);
    expect(res.gpuDevices[0].metric.seriesLabel).toBe(
      'memoryTemperatureCelsius',
    );
    expect(res.gpuDevices[0].metric.values[0].value).toBe(65.5);
  });

  it('throws error when response is not ok', async () => {
    mockFetch.mockResolvedValue({ ok: false });

    await expect(
      fetchNodeGpuMemoryTemperature('c1', 'n1', new Date(), new Date()),
    ).rejects.toThrow(APIRequestError);
  });
});

describe('fetchNodeWorkloadsMetrics', () => {
  it('returns data when response is ok', async () => {
    const data = {
      data: [
        {
          id: 'workload-1',
          displayName: 'Test Workload',
          status: 'Running',
          gpuDevices: [{ gpuId: '0', hostname: 'worker-1' }],
        },
      ],
    };
    mockFetch.mockResolvedValue({
      ok: true,
      json: mockJson.mockResolvedValue(data),
    });

    const clusterId = 'cluster-123';
    const nodeId = 'node-456';

    const res = await fetchNodeWorkloadsMetrics(clusterId, nodeId);
    expect(res).toEqual(data);
    expect(mockFetch).toHaveBeenCalledWith(
      `/api/clusters/${clusterId}/nodes/${nodeId}/workloads/metrics`,
    );
  });

  it('throws APIRequestError when response is not ok', async () => {
    mockFetch.mockResolvedValue({ ok: false });

    await expect(
      fetchNodeWorkloadsMetrics('cluster-123', 'node-456'),
    ).rejects.toThrow(APIRequestError);
  });
});
