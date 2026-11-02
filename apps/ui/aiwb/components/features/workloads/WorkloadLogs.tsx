// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Select,
  SelectItem,
  Spinner,
  Switch,
} from '@amdenterpriseai/components';

import { PageLoader } from '@/components/shared/PageLoader';

import { useTranslation } from 'next-i18next';

import type { LogLevel, Workload } from '@/types/workloads';
import type { EnrichedWorkloadMetrics } from '@/types/projects';
import type { components } from '@/types/api';

import { useQuery } from '@tanstack/react-query';
import { getWorkloadLogs } from '@/lib/app/workloads';
import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { throttle } from 'lodash';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { useWorkloadLogsStream } from '@/hooks/useWorkloadLogsStream';
import Ansi from 'ansi-to-react';
import { getLogLevelColor } from '@/lib/app/logs';

type LogType = components['schemas']['LogType'];

const LOG_LEVELS = [
  'trace',
  'debug',
  'info',
  'unknown',
  'warning',
  'error',
  'critical',
] as const satisfies readonly LogLevel[];
const LOG_TYPES = ['workload', 'event'] as const satisfies readonly LogType[];
const WORKLOAD_LOG_RANGE_MS = 24 * 60 * 60 * 1000;

interface Props {
  workload: Workload | EnrichedWorkloadMetrics | undefined;
  isOpen: boolean;
  namespace: string;
}

const WorkloadLogs = ({ workload, isOpen, namespace }: Props) => {
  const { t } = useTranslation('workloads');

  const [isStreamingMode, setIsStreamingMode] = useState(false);
  const [selectedLogLevel, setSelectedLogLevel] = useState<LogLevel | ''>('');
  const [selectedLogType, setSelectedLogType] = useState<LogType>(() =>
    workload?.status === 'Pending' ? 'event' : 'workload',
  );
  const [currentStartDate, setCurrentStartDate] = useState<string | undefined>(
    undefined,
  );
  const [pagination, setPagination] = useState<
    components['schemas']['PaginationMetadataResponse'] | undefined
  >(undefined);
  const [allLogs, setAllLogs] = useState<components['schemas']['LogEntry'][]>(
    [],
  );
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const previousScrollTopRef = useRef<number>(0);
  const previousScrollHeightRef = useRef<number>(0);
  const { toast } = useSystemToast();
  const workloadId = workload?.id;

  const streamParams = useMemo(
    () => ({
      level: selectedLogLevel || undefined,
      logType: selectedLogType,
    }),
    [selectedLogLevel, selectedLogType],
  );

  const {
    data: streamLogs,
    isLoading: isStreamingLoading,
    isStreaming,
    error: streamError,
    startStreaming,
    stopStreaming,
    clearLogs: clearStreamLogs,
  } = useWorkloadLogsStream({
    projectId: namespace || '',
    workloadId: workloadId || '',
  });

  const {
    data: workloadLogsResponse,
    isLoading: isLogsLoading,
    error: logsError,
  } = useQuery({
    queryKey: [
      'workloadLogs',
      namespace,
      workloadId,
      currentStartDate,
      selectedLogLevel,
      selectedLogType,
    ],
    queryFn: async () => {
      if (!workloadId) return;
      const end = new Date();
      const start = new Date(end.getTime() - WORKLOAD_LOG_RANGE_MS);
      return await getWorkloadLogs(namespace!, workloadId, {
        start: start.toISOString(),
        end: end.toISOString(),
        direction: 'backward' as const,
        pageToken: currentStartDate,
        level: selectedLogLevel || undefined,
        logType: selectedLogType,
      });
    },
    enabled: !!workloadId && isOpen && !isStreamingMode,
  });

  const logLevelOptions = useMemo(() => {
    return [
      {
        key: '',
        label: t('list.actions.logs.modal.logLevelFilter.allLevels'),
      },
      ...LOG_LEVELS.map((level) => ({
        key: level,
        label: level.toUpperCase(),
      })),
    ];
  }, [t]);

  const logTypeOptions = useMemo(() => {
    return LOG_TYPES.map((type) => ({
      key: type,
      label: t(`list.actions.logs.modal.logTypeFilter.${type}`),
    }));
  }, [t]);

  // Get the appropriate logs based on mode
  const currentLogs = isStreamingMode ? streamLogs : allLogs;
  const isCurrentlyLoading = isStreaming
    ? isStreamingLoading
    : isLogsLoading && allLogs.length === 0;
  const isPaginationLoading = isStreamingMode
    ? false
    : isLogsLoading && allLogs.length > 0;

  const handleScroll = useCallback(() => {
    const container = logsContainerRef.current;
    if (!container || isLogsLoading || !pagination?.hasMore || isStreamingMode)
      return;

    const { scrollTop } = container;
    const previousScrollTop = previousScrollTopRef.current;

    // Only trigger when scrolling up
    if (scrollTop >= previousScrollTop) {
      previousScrollTopRef.current = scrollTop;
      return;
    }

    previousScrollTopRef.current = scrollTop;
    const scrollThreshold = 100; // Trigger 100px before reaching the top

    if (scrollTop < scrollThreshold) {
      const throttledLoadMore = throttle(() => {
        setCurrentStartDate(pagination?.pageToken ?? undefined);
      }, 300);
      throttledLoadMore();
    }
  }, [isLogsLoading, isStreamingMode, pagination]);

  const clearLogsData = useCallback(() => {
    setAllLogs([]);
    setPagination(undefined);
    setCurrentStartDate(undefined);
  }, []);

  const handleCleanup = useCallback(() => {
    clearLogsData();
    setSelectedLogLevel('');
    setSelectedLogType(workload?.status === 'Pending' ? 'event' : 'workload');
    setIsStreamingMode(false);

    stopStreaming();
    clearStreamLogs();

    if (logsContainerRef.current) {
      logsContainerRef.current.removeEventListener('scroll', handleScroll);
    }
  }, [
    workload?.status,
    stopStreaming,
    clearStreamLogs,
    clearLogsData,
    handleScroll,
  ]);

  const handleLogTypeChange = (logType: string) => {
    if (logType !== 'workload' && logType !== 'event') return;
    setSelectedLogType(logType);
    clearLogsData();
  };

  // Clean up when component unmounts or isOpen becomes false
  useEffect(() => {
    if (!isOpen) {
      handleCleanup();
    }
  }, [isOpen, handleCleanup]);

  /**
   * Error notifications for non-streaming error and streaming errors.
   */
  useEffect(() => {
    if (logsError) {
      toast.error(t('notifications.logs.error', { error: logsError.message }));
    }
    if (streamError) {
      toast.error(t('notifications.logs.error', { error: streamError }));
    }
  }, [logsError, streamError, toast, t]);

  /**
   * Handle the non-streaming logs and its pagination.
   */
  useEffect(() => {
    if (workloadLogsResponse?.data && !isStreamingMode) {
      const sortedLogs = [...workloadLogsResponse.data].sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      );

      if (currentStartDate) {
        // Store the current scroll height before adding new logs
        const container = logsContainerRef.current;
        if (container) {
          previousScrollHeightRef.current = container.scrollHeight;
        }
        // Prepend older page and re-sort so full list stays chronological (API page boundaries can mix runs)
        setAllLogs((prevLogs) => {
          const combined = [...sortedLogs, ...prevLogs];
          return combined.sort(
            (a, b) =>
              new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
          );
        });
      } else {
        // This is the initial request, replace all logs
        setAllLogs(sortedLogs);
      }
      setPagination(workloadLogsResponse.pagination);
    }
  }, [workloadLogsResponse, isStreamingMode, currentStartDate]);

  const handleStreamingToggle = async (enabled: boolean) => {
    setIsStreamingMode(enabled);
  };

  const handleLogLevelChange = (logLevel: LogLevel | '') => {
    setSelectedLogLevel(logLevel);
  };

  /**
   * The actual streaming logs handler, which is called when the streaming mode is toggled or the log level is changed.
   */
  useEffect(() => {
    if (!isStreamingMode || !workloadId) {
      stopStreaming();
      return;
    }

    if (isStreaming) {
      stopStreaming();
      clearStreamLogs();
    }

    startStreaming(streamParams);
  }, [isStreamingMode, selectedLogLevel, selectedLogType]);

  useEffect(() => {
    const container = logsContainerRef.current;
    if (!container) return;

    const throttledHandleScroll = throttle(handleScroll, 100);
    container.addEventListener('scroll', throttledHandleScroll);

    return () => {
      container.removeEventListener('scroll', throttledHandleScroll);
      throttledHandleScroll.cancel();
    };
  }, [handleScroll, isStreamingMode]);

  // Auto-scroll to bottom when new streaming logs arrive
  useEffect(() => {
    if (isStreamingMode && streamLogs.length > 0) {
      const container = logsContainerRef.current;
      if (container) {
        // Small delay to ensure DOM is updated
        setTimeout(() => {
          container.scrollTop = container.scrollHeight;
        }, 10);
      }
    }
  }, [isStreamingMode, streamLogs.length]);

  // Auto-scroll to bottom when logs are loaded in pagination mode
  useEffect(() => {
    if (!isStreamingMode && allLogs.length > 0 && !currentStartDate) {
      const container = logsContainerRef.current;
      if (container) {
        // Small delay to ensure DOM is updated
        setTimeout(() => {
          container.scrollTop = container.scrollHeight;
        }, 10);
      }
    }
  }, [isStreamingMode, allLogs.length, currentStartDate]);

  // Restore scroll position after loading more logs (pagination)
  useEffect(() => {
    if (!isStreamingMode && currentStartDate && allLogs.length > 0) {
      const container = logsContainerRef.current;
      if (container && previousScrollHeightRef.current > 0) {
        // Calculate the difference in scroll height and adjust scroll position
        setTimeout(() => {
          const heightDifference =
            container.scrollHeight - previousScrollHeightRef.current;
          container.scrollTop = container.scrollTop + heightDifference;
          previousScrollHeightRef.current = 0; // Reset
        }, 10);
      }
    }
  }, [isStreamingMode, currentStartDate, allLogs.length]);

  if (!workload) {
    return (
      <div className="p-4 text-foreground">
        {t('list.actions.logs.modal.workloadNotFound')}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="mb-4 shrink-0">
        <div className="text-foreground mb-4">
          {t('list.actions.logs.modal.description', {
            workload: workload.displayName,
          })}
        </div>
        <div className="flex items-center gap-4">
          <div>
            <Select
              aria-label={t('list.actions.logs.modal.logTypeFilter.label')}
              placeholder={t('list.actions.logs.modal.logTypeFilter.label')}
              className="min-w-[130px]"
              selectedKeys={[selectedLogType]}
              onSelectionChange={(keys) => {
                const selectedKey = Array.from(keys)[0] as string;
                handleLogTypeChange(selectedKey);
              }}
            >
              {logTypeOptions.map((option) => (
                <SelectItem key={option.key}>{option.label}</SelectItem>
              ))}
            </Select>
          </div>
          <div>
            <Select
              aria-label={t('list.actions.logs.modal.logLevelFilter.label')}
              placeholder={t('list.actions.logs.modal.logLevelFilter.label')}
              className="min-w-[140px]"
              selectedKeys={selectedLogLevel ? [selectedLogLevel] : []}
              onSelectionChange={(keys) => {
                const selectedKey = (Array.from(keys)[0] ?? '') as
                  | LogLevel
                  | '';
                handleLogLevelChange(selectedKey);
              }}
              isDisabled={selectedLogType === 'event'}
            >
              {logLevelOptions.map((option) => (
                <SelectItem key={option.key}>{option.label}</SelectItem>
              ))}
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              isSelected={isStreamingMode}
              onValueChange={handleStreamingToggle}
              size="sm"
              color="primary"
            />
            {t('list.actions.logs.modal.streaming')}
          </div>
        </div>
      </div>
      <div
        className="bg-gray-100 dark:bg-gray-950 rounded-lg p-4 text-xs flex-1 overflow-y-auto min-h-64"
        ref={logsContainerRef}
        data-testid="workload-logs-container"
        style={{
          fontFamily:
            '"SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {/* Loading indicator for infinite scroll (pagination mode only) */}
        {isPaginationLoading && (
          <div className="flex justify-center items-center py-4">
            <Spinner size="sm" color="primary" />
          </div>
        )}
        {isCurrentlyLoading ? (
          <PageLoader
            label={t('list.actions.logs.modal.loading')}
            testId="workload-logs-loading"
            className="h-64"
          />
        ) : currentLogs.length === 0 ? (
          <div
            className="flex justify-center items-center h-64 text-gray-500"
            data-testid="workload-logs-empty"
          >
            {selectedLogType === 'event'
              ? t('list.actions.logs.modal.noEvents')
              : t('list.actions.logs.modal.noLogs')}
          </div>
        ) : (
          <div className="space-y-0 leading-relaxed">
            {currentLogs.map((log, index: number) => {
              const timestamp = new Date(log.timestamp).toLocaleString();

              return (
                <div
                  key={`${log.timestamp}-${index}`}
                  className="flex gap-2 hover:bg-gray-200/30 dark:hover:bg-gray-800/30"
                >
                  <span className="text-gray-400 dark:text-gray-500 shrink-0">
                    {timestamp}
                  </span>
                  {selectedLogType !== 'event' && (
                    <span
                      className="uppercase font-semibold inline-block shrink-0"
                      style={{
                        color: getLogLevelColor(log.level),
                        width: '70px',
                        textAlign: 'center',
                      }}
                    >
                      {log.level === 'unknown' ? '-' : log.level}
                    </span>
                  )}
                  <div className="flex-1 break-all whitespace-pre-wrap text-gray-700 dark:text-gray-200">
                    <Ansi>{log.message}</Ansi>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkloadLogs;
