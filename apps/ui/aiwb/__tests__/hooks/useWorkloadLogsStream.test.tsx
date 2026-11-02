// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

import { useWorkloadLogsStream } from '@/hooks/useWorkloadLogsStream';

import { LogEntry } from '@/types/workloads';

/**
 * Mock log entries for testing workload logs
 */
const mockWorkloadLogEntries: LogEntry[] = [
  {
    timestamp: '2023-01-01T00:00:00Z',
    level: 'info',
    message: 'First log entry',
  },
  {
    timestamp: '2023-01-01T00:00:01Z',
    level: 'warning',
    message: 'Second log entry',
  },
  {
    timestamp: '2023-01-01T00:00:02Z',
    level: 'error',
    message: 'Third log entry',
  },
];

// Mock EventSource
class MockEventSource {
  public onopen: ((event: Event) => void) | null = null;
  public onmessage: ((event: MessageEvent) => void) | null = null;
  public onerror: ((event: Event) => void) | null = null;
  public readyState: number = 0;
  public url: string;

  public static instances: MockEventSource[] = [];

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this.readyState = 2; // CLOSED
  }

  static getLatestInstance(): MockEventSource | undefined {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }

  static clearInstances() {
    MockEventSource.instances = [];
  }

  static simulateOpen() {
    const instance = MockEventSource.getLatestInstance();
    if (instance?.onopen) {
      instance.readyState = 1; // OPEN
      instance.onopen(new Event('open'));
    }
  }

  static simulateMessage(data: string) {
    const instance = MockEventSource.getLatestInstance();
    if (instance?.onmessage) {
      const event = new MessageEvent('message', { data });
      instance.onmessage(event);
    }
  }

  static simulateError() {
    const instance = MockEventSource.getLatestInstance();
    if (instance?.onerror) {
      instance.onerror(new Event('error'));
    }
  }
}

// Replace global EventSource with mock
global.EventSource = MockEventSource as any;

describe('useWorkloadLogsStream', () => {
  // Use imported mock log entries for testing
  const [mockLogEntry1, mockLogEntry2, mockLogEntry3] = mockWorkloadLogEntries;

  beforeEach(() => {
    vi.clearAllMocks();
    MockEventSource.clearInstances();
  });

  afterEach(() => {
    vi.clearAllTimers();
    MockEventSource.clearInstances();
  });

  describe('initial state', () => {
    it('should initialize with correct default values', () => {
      const { result } = renderHook(() =>
        useWorkloadLogsStream({
          projectId: 'test-namespace',
          workloadId: 'test-workload-id',
        }),
      );

      expect(result.current.data).toEqual([]);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isStreaming).toBe(false);
      expect(result.current.error).toBeNull();
      expect(typeof result.current.startStreaming).toBe('function');
      expect(typeof result.current.stopStreaming).toBe('function');
      expect(typeof result.current.clearLogs).toBe('function');
    });
  });

  describe('startStreaming', () => {
    it('should start streaming and accumulate log entries', async () => {
      const params = {
        startTime: '2023-01-01',
        level: 'error' as const,
      };

      const { result } = renderHook(() =>
        useWorkloadLogsStream({
          projectId: 'test-namespace',
          workloadId: 'test-workload-id',
        }),
      );

      act(() => {
        result.current.startStreaming(params);
      });

      // Should be loading initially
      expect(result.current.isLoading).toBe(true);

      // Simulate connection open
      act(() => {
        MockEventSource.simulateOpen();
      });

      await waitFor(() => {
        expect(result.current.isStreaming).toBe(true);
        expect(result.current.isLoading).toBe(false);
      });

      // Simulate receiving messages
      act(() => {
        MockEventSource.simulateMessage(JSON.stringify(mockLogEntry1));
      });

      act(() => {
        MockEventSource.simulateMessage(JSON.stringify(mockLogEntry2));
      });

      act(() => {
        MockEventSource.simulateMessage(JSON.stringify(mockLogEntry3));
      });

      await waitFor(() => {
        expect(result.current.data).toHaveLength(3);
      });

      expect(result.current.data).toEqual([
        mockLogEntry1,
        mockLogEntry2,
        mockLogEntry3,
      ]);
    });

    it('should build correct URL with parameters', () => {
      const params = {
        startTime: '2023-01-01',
        level: 'error' as const,
      };

      const { result } = renderHook(() =>
        useWorkloadLogsStream({
          projectId: 'test-namespace',
          workloadId: 'test-workload-id',
        }),
      );

      act(() => {
        result.current.startStreaming(params);
      });

      const instance = MockEventSource.getLatestInstance();
      expect(instance?.url).toBe(
        '/api/projects/test-namespace/workloads/test-workload-id/logs/stream?startTime=2023-01-01&level=error',
      );
    });

    it('should handle [DONE] marker and stop streaming', async () => {
      const { result } = renderHook(() =>
        useWorkloadLogsStream({
          projectId: 'test-namespace',
          workloadId: 'test-workload-id',
        }),
      );

      act(() => {
        result.current.startStreaming({});
      });

      act(() => {
        MockEventSource.simulateOpen();
      });

      await waitFor(() => {
        expect(result.current.isStreaming).toBe(true);
      });

      // Send log entries
      act(() => {
        MockEventSource.simulateMessage(JSON.stringify(mockLogEntry1));
      });

      await waitFor(() => {
        expect(result.current.data).toHaveLength(1);
      });

      // Send [DONE] marker
      act(() => {
        MockEventSource.simulateMessage('[DONE]');
      });

      await waitFor(() => {
        expect(result.current.isStreaming).toBe(false);
      });

      expect(result.current.data).toHaveLength(1); // Should not add [DONE] to logs
    });

    it('should not start if already streaming', async () => {
      const { result } = renderHook(() =>
        useWorkloadLogsStream({
          projectId: 'test-namespace',
          workloadId: 'test-workload-id',
        }),
      );

      act(() => {
        result.current.startStreaming({});
      });

      act(() => {
        MockEventSource.simulateOpen();
      });

      await waitFor(() => {
        expect(result.current.isStreaming).toBe(true);
      });

      const instanceCount = MockEventSource.getLatestInstance();

      // Try to start again
      act(() => {
        result.current.startStreaming({});
      });

      // Should not create a new instance
      expect(MockEventSource.getLatestInstance()).toBe(instanceCount);
    });

    it('should handle invalid JSON gracefully', async () => {
      const consoleErrorSpy = vi
        .spyOn(console, 'error')
        .mockImplementation(() => {});

      try {
        const { result } = renderHook(() =>
          useWorkloadLogsStream({
            projectId: 'test-namespace',
            workloadId: 'test-workload-id',
          }),
        );

        act(() => {
          result.current.startStreaming({});
        });

        act(() => {
          MockEventSource.simulateOpen();
        });

        await waitFor(() => {
          expect(result.current.isStreaming).toBe(true);
        });

        // Send valid log
        act(() => {
          MockEventSource.simulateMessage(JSON.stringify(mockLogEntry1));
        });

        // Send invalid JSON
        act(() => {
          MockEventSource.simulateMessage('invalid json {');
        });

        // Send another valid log
        act(() => {
          MockEventSource.simulateMessage(JSON.stringify(mockLogEntry2));
        });

        await waitFor(() => {
          expect(result.current.data).toHaveLength(2);
        });

        // Should only have valid logs
        expect(result.current.data).toEqual([mockLogEntry1, mockLogEntry2]);
        expect(consoleErrorSpy).toHaveBeenCalled();
      } finally {
        consoleErrorSpy.mockRestore();
      }
    });
  });

  describe('stopStreaming', () => {
    it('should stop active stream', async () => {
      const { result } = renderHook(() =>
        useWorkloadLogsStream({
          projectId: 'test-namespace',
          workloadId: 'test-workload-id',
        }),
      );

      act(() => {
        result.current.startStreaming({});
      });

      act(() => {
        MockEventSource.simulateOpen();
      });

      await waitFor(() => {
        expect(result.current.isStreaming).toBe(true);
      });

      act(() => {
        result.current.stopStreaming();
      });

      expect(result.current.isStreaming).toBe(false);
      expect(result.current.isLoading).toBe(false);

      const instance = MockEventSource.getLatestInstance();
      expect(instance?.readyState).toBe(2); // CLOSED
    });
  });

  describe('clearLogs', () => {
    it('should clear accumulated logs', async () => {
      const { result } = renderHook(() =>
        useWorkloadLogsStream({
          projectId: 'test-namespace',
          workloadId: 'test-workload-id',
        }),
      );

      act(() => {
        result.current.startStreaming({});
      });

      act(() => {
        MockEventSource.simulateOpen();
      });

      await waitFor(() => {
        expect(result.current.isStreaming).toBe(true);
      });

      // Add some logs
      act(() => {
        MockEventSource.simulateMessage(JSON.stringify(mockLogEntry1));
        MockEventSource.simulateMessage(JSON.stringify(mockLogEntry2));
      });

      await waitFor(() => {
        expect(result.current.data.length).toBeGreaterThan(0);
      });

      act(() => {
        result.current.clearLogs();
      });

      expect(result.current.data).toEqual([]);
    });
  });

  describe('cleanup on unmount', () => {
    it('should close EventSource on unmount', async () => {
      const { result, unmount } = renderHook(() =>
        useWorkloadLogsStream({
          projectId: 'test-namespace',
          workloadId: 'test-workload-id',
        }),
      );

      act(() => {
        result.current.startStreaming({});
      });

      act(() => {
        MockEventSource.simulateOpen();
      });

      await waitFor(() => {
        expect(result.current.isStreaming).toBe(true);
      });

      const instance = MockEventSource.getLatestInstance();

      unmount();

      expect(instance?.readyState).toBe(2); // CLOSED
    });
  });
});
