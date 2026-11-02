// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useCallback, useEffect, useRef, useState } from 'react';

import { LogEntry } from '@/types/workloads';
import type { operations } from '@/types/api';

type WorkloadLogStreamParams = NonNullable<
  operations['stream_workload_logs']['parameters']['query']
>;

export interface UseWorkloadLogsStreamOptions {
  projectId: string;
  workloadId: string;
}

export interface UseWorkloadLogsStreamReturn {
  data: LogEntry[];
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  startStreaming: (params: WorkloadLogStreamParams) => void;
  stopStreaming: () => void;
  clearLogs: () => void;
}

/**
 * Build SSE stream URL with query parameters
 */
const buildStreamUrl = (
  projectId: string,
  workloadId: string,
  params: WorkloadLogStreamParams = {},
): string => {
  const urlParams = new URLSearchParams();
  if (params.startTime) urlParams.append('startTime', params.startTime);
  if (params.level) urlParams.append('level', params.level);
  if (params.logType) urlParams.append('logType', params.logType);

  const queryString = urlParams.toString();
  return `/api/projects/${projectId}/workloads/${workloadId}/logs/stream${queryString ? `?${queryString}` : ''}`;
};

export const useWorkloadLogsStream = ({
  projectId,
  workloadId,
}: UseWorkloadLogsStreamOptions): UseWorkloadLogsStreamReturn => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const paramsRef = useRef<WorkloadLogStreamParams>({});

  const stopStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setIsStreaming(false);
    setIsLoading(false);
  }, []);

  const connect = useCallback(
    (params: WorkloadLogStreamParams) => {
      paramsRef.current = params;
      // Close existing connection if any
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      const url = buildStreamUrl(projectId, workloadId, params);

      setIsStreaming(true);
      setIsLoading(true);
      setLogs([]);

      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsLoading(false);
        setError(null);
      };

      eventSource.onmessage = (event) => {
        try {
          // Handle special markers
          if (event.data === '[DONE]') {
            stopStreaming();
            return;
          } else if (event.data === '[HEARTBEAT]') {
            return;
          }

          const logEntry: LogEntry = JSON.parse(event.data);
          setLogs((prev) => [...prev, logEntry]);
        } catch (err: any) {
          console.error('[SSE] Failed to parse message:', err);
          setError(`[SSE] Failed to parse message ${err?.message}`);
        }
      };

      eventSource.onerror = (event) => {
        console.error('[SSE] Connection error:', event);
        stopStreaming();
        setError('Log streaming connection error. Please try again later.');
      };
    },
    [projectId, workloadId, stopStreaming],
  );

  const startStreaming = useCallback(
    (params: WorkloadLogStreamParams = {}) => {
      // Prevent starting if already connected
      if (isStreaming && eventSourceRef.current) {
        return;
      }

      connect(params);
    },
    [isStreaming, connect],
  );

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopStreaming();
    };
  }, [stopStreaming]);

  return {
    data: logs,
    isLoading,
    isStreaming,
    error,
    startStreaming,
    stopStreaming,
    clearLogs,
  };
};
