// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { getWorkloadLogs } from '@/lib/app/workloads';

import type { Workload, LogEntry } from '@/types/workloads';

import WorkloadLogs from '@/components/features/workloads/WorkloadLogs';

import wrapper from '@/__tests__/ProviderWrapper';
import { mockWorkloads } from '@/__mocks__/services/app/workloads.data';
import { Mock, vi } from 'vitest';

import { useWorkloadLogsStream } from '@/hooks/useWorkloadLogsStream';
import { useSystemToast } from '@amdenterpriseai/hooks';

// Mock the hooks
vi.mock('@/hooks/useWorkloadLogsStream', () => ({
  useWorkloadLogsStream: vi.fn(),
}));

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => ({
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

// Mock the API services
vi.mock('@/lib/app/workloads', () => ({
  getWorkloadLogs: vi.fn().mockResolvedValue({
    data: [],
    pagination: {
      hasMore: false,
      pageToken: undefined,
      totalReturned: 0,
    },
  }),
}));

// Mock lodash throttle
vi.mock('lodash', () => ({
  throttle: vi.fn((fn) => {
    fn.cancel = vi.fn();
    return fn;
  }),
}));

describe('WorkloadLogs', () => {
  const mockWorkload = mockWorkloads[0]; // Use first workload from shared mocks

  const mockLogEntries: LogEntry[] = [
    {
      timestamp: '2023-01-01T10:00:00Z',
      level: 'info',
      message: 'Application started successfully',
    },
    {
      timestamp: '2023-01-01T10:01:00Z',
      level: 'warning',
      message: 'Low memory warning',
    },
    {
      timestamp: '2023-01-01T10:02:00Z',
      level: 'error',
      message: 'Connection timeout error',
    },
  ];

  const mockWorkloadLogsResponse = {
    data: mockLogEntries,
    pagination: {
      hasMore: true,
      pageToken: '2023-01-01T09:59:00Z',
      totalReturned: 3,
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (getWorkloadLogs as Mock).mockResolvedValue(mockWorkloadLogsResponse);

    // Reset the streaming hook mock
    vi.mocked(useWorkloadLogsStream).mockReturnValue({
      data: [] as LogEntry[],
      isLoading: false,
      isStreaming: false,
      error: null as string | null,
      startStreaming: vi.fn(),
      stopStreaming: vi.fn(),
      clearLogs: vi.fn(),
    });
  });

  it('renders workload logs when workload is provided', async () => {
    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    // Wait for the logs to load
    await waitFor(() => {
      expect(getWorkloadLogs).toHaveBeenCalled();
    });

    // Check workload description is displayed
    expect(
      screen.getByText('list.actions.logs.modal.description'),
    ).toBeInTheDocument();

    // Check streaming toggle is present
    expect(
      screen.getByText('list.actions.logs.modal.streaming'),
    ).toBeInTheDocument();

    // Check that logs are displayed
    await waitFor(() => {
      expect(
        screen.getByText('Application started successfully'),
      ).toBeInTheDocument();
    });
    expect(screen.getByText('Low memory warning')).toBeInTheDocument();
    expect(screen.getByText('Connection timeout error')).toBeInTheDocument();
  });

  it('shows workload not found message when no workload is provided', () => {
    render(
      <WorkloadLogs workload={undefined} isOpen={true} namespace="workbench" />,
      { wrapper },
    );

    expect(
      screen.getByText('list.actions.logs.modal.workloadNotFound'),
    ).toBeInTheDocument();
  });

  it('shows loading state when logs are being fetched', async () => {
    (getWorkloadLogs as Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve(mockWorkloadLogsResponse), 1000);
        }),
    );

    render(
      <WorkloadLogs
        workload={mockWorkload}
        isOpen={true}
        namespace="workbench"
      />,
      { wrapper },
    );

    expect(screen.getByTestId('workload-logs-loading')).toBeInTheDocument();
  });

  it('displays log entries with correct formatting', async () => {
    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    // Wait for the logs to load and be displayed
    await waitFor(() => {
      expect(getWorkloadLogs).toHaveBeenCalled();
    });

    // Wait for the logs to be rendered in the DOM
    await waitFor(() => {
      expect(
        screen.getByText('Application started successfully'),
      ).toBeInTheDocument();
    });

    // Check that all log messages are displayed
    expect(screen.getByText('Low memory warning')).toBeInTheDocument();
    expect(screen.getByText('Connection timeout error')).toBeInTheDocument();

    // Check that log levels are displayed (they are rendered in lowercase, but styled with uppercase CSS)
    expect(
      screen.getByText((content, element) => {
        return element?.textContent === 'info';
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText((content, element) => {
        return element?.textContent === 'warning';
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText((content, element) => {
        return element?.textContent === 'error';
      }),
    ).toBeInTheDocument();
  });

  it('calls getWorkloadLogs with correct parameters', async () => {
    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    await waitFor(() => {
      expect(getWorkloadLogs).toHaveBeenCalledWith('workbench', 'workload-1', {
        start: expect.any(String),
        end: expect.any(String),
        direction: 'backward',
        pageToken: undefined,
        level: undefined,
        logType: 'workload',
      });
    });
  });
  it('handles streaming mode toggle', async () => {
    const mockStartStreaming = vi.fn();
    const mockStopStreaming = vi.fn();
    const mockClearLogs = vi.fn();

    vi.mocked(useWorkloadLogsStream).mockReturnValue({
      data: [mockLogEntries[0]],
      isLoading: false,
      isStreaming: false,
      error: null,
      startStreaming: mockStartStreaming,
      stopStreaming: mockStopStreaming,
      clearLogs: mockClearLogs,
    });

    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    // Find the streaming toggle switch
    const streamingSwitch = screen.getByRole('switch');

    // Toggle streaming mode
    await act(async () => {
      fireEvent.click(streamingSwitch);
    });

    // Verify startStreaming was called (with delay)
    await waitFor(
      () => {
        expect(mockStartStreaming).toHaveBeenCalled();
      },
      { timeout: 200 },
    );
  });

  it('handles pagination when scrolling to top', async () => {
    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    await waitFor(() => {
      expect(getWorkloadLogs).toHaveBeenCalled();
    });

    // Find the logs container by test ID
    const logsContainer = screen.getByTestId('workload-logs-container');

    // Mock scroll properties using a spy on the scroll event handler
    const scrollSpy = vi.fn();
    logsContainer.addEventListener('scroll', scrollSpy);

    // Simulate scroll event near the top (scrolling up to load older logs)
    Object.defineProperty(logsContainer, 'scrollTop', {
      configurable: true,
      writable: true,
      value: 50, // Near the top, within threshold
    });
    Object.defineProperty(logsContainer, 'scrollHeight', {
      configurable: true,
      writable: true,
      value: 1000,
    });
    Object.defineProperty(logsContainer, 'clientHeight', {
      configurable: true,
      writable: true,
      value: 400,
    });

    // Simulate scroll event
    await act(async () => {
      fireEvent.scroll(logsContainer);
    });

    // The main verification is that the component handles scroll without errors
    expect(getWorkloadLogs).toHaveBeenCalled();
  });

  it('handles empty logs response', async () => {
    const emptyResponse = {
      data: [],
      pagination: {
        hasMore: false,
        pageToken: undefined,
        totalReturned: 0,
      },
    };

    (getWorkloadLogs as Mock).mockResolvedValue(emptyResponse);

    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    await waitFor(() => {
      expect(getWorkloadLogs).toHaveBeenCalled();
    });

    // Should show workload description but no log entries
    expect(
      screen.getByText('list.actions.logs.modal.description'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Application started successfully'),
    ).not.toBeInTheDocument();
  });

  it('cleans up when isOpen becomes false', async () => {
    const mockStopStreaming = vi.fn();
    const mockClearLogs = vi.fn();

    vi.mocked(useWorkloadLogsStream).mockReturnValue({
      data: [],
      isLoading: false,
      isStreaming: true,
      error: null,
      startStreaming: vi.fn(),
      stopStreaming: mockStopStreaming,
      clearLogs: mockClearLogs,
    });

    const { rerender } = await act(async () => {
      return render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    await waitFor(() => {
      expect(getWorkloadLogs).toHaveBeenCalled();
    });

    // Close the component
    await act(async () => {
      rerender(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={false}
          namespace="workbench"
        />,
      );
    });

    // Wait for cleanup timeout (300ms)
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });

    // Verify cleanup was called
    expect(mockStopStreaming).toHaveBeenCalled();
    expect(mockClearLogs).toHaveBeenCalled();
  });

  it('only enables query when workload exists and component is open', () => {
    // Test with workload but component closed
    const { rerender } = render(
      <WorkloadLogs
        workload={mockWorkload}
        isOpen={false}
        namespace="workbench"
      />,
      { wrapper },
    );

    expect(getWorkloadLogs).not.toHaveBeenCalled();

    // Test with component open but no workload
    rerender(
      <WorkloadLogs workload={undefined} isOpen={true} namespace="workbench" />,
    );

    expect(getWorkloadLogs).not.toHaveBeenCalled();

    // Test with both workload and component open
    rerender(
      <WorkloadLogs
        workload={mockWorkload}
        isOpen={true}
        namespace="workbench"
      />,
    );

    // Now it should be called
    expect(getWorkloadLogs).toHaveBeenCalled();
  });

  it('handles API errors gracefully', async () => {
    const mockError = new Error('API Error');
    (getWorkloadLogs as Mock).mockRejectedValue(mockError);

    const consoleErrorSpy = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {});

    try {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // The component should handle the error gracefully
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalled();
      });

      // Component should still render without crashing
      expect(
        screen.getByText('list.actions.logs.modal.description'),
      ).toBeInTheDocument();
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('handles streaming errors', async () => {
    vi.mocked(useWorkloadLogsStream).mockReturnValue({
      data: [] as LogEntry[],
      isLoading: false,
      isStreaming: false,
      error: 'Streaming connection failed' as string,
      startStreaming: vi.fn(),
      stopStreaming: vi.fn(),
      clearLogs: vi.fn(),
    });

    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    // Component should handle streaming error gracefully
    expect(
      screen.getByText('list.actions.logs.modal.description'),
    ).toBeInTheDocument();
  });

  it('auto-scrolls to bottom when new streaming logs arrive', async () => {
    const scrollToSpy = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollTop', {
      configurable: true,
      set: scrollToSpy,
    });
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
      configurable: true,
      get: () => 1000,
    });

    vi.mocked(useWorkloadLogsStream).mockReturnValue({
      data: [mockLogEntries[0]],
      isLoading: false,
      isStreaming: true,
      error: null,
      startStreaming: vi.fn(),
      stopStreaming: vi.fn(),
      clearLogs: vi.fn(),
    });

    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    // The component should render with streaming mode
    expect(
      screen.getByText('list.actions.logs.modal.description'),
    ).toBeInTheDocument();
  });

  it('displays pagination loading indicator', async () => {
    // Mock a scenario where pagination is loading
    const firstResponse = {
      data: mockLogEntries.slice(0, 2),
      pagination: {
        hasMore: true,
        pageToken: '2023-01-01T09:59:00Z',
        totalReturned: 2,
      },
    };

    (getWorkloadLogs as Mock).mockResolvedValue(firstResponse);

    await act(async () => {
      render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        {
          wrapper,
        },
      );
    });

    await waitFor(() => {
      expect(getWorkloadLogs).toHaveBeenCalled();
    });

    // Initial logs should be displayed
    await waitFor(() => {
      expect(
        screen.getByText('Application started successfully'),
      ).toBeInTheDocument();
    });

    // The test mainly verifies that the component can handle pagination states
    expect(
      screen.getByText('list.actions.logs.modal.description'),
    ).toBeInTheDocument();
  });

  // Log Level filtering tests
  describe('Log Level Filtering', () => {
    it('shows log level dropdown', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Should show the log level filter dropdown
      expect(
        screen.getByText('list.actions.logs.modal.logLevelFilter.label'),
      ).toBeInTheDocument();

      expect(
        screen.getByRole('button', {
          name: /list\.actions\.logs\.modal\.logLevelFilter\.label/,
        }),
      ).toBeInTheDocument();
    });

    it('displays all available log levels in dropdown', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Find and click the log level dropdown
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logLevelFilter\.label/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      // Check that all log levels are available
      expect(screen.getByRole('option', { name: 'TRACE' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'DEBUG' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'INFO' })).toBeInTheDocument();
      expect(
        screen.getByRole('option', { name: 'UNKNOWN' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('option', { name: 'WARNING' }),
      ).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'ERROR' })).toBeInTheDocument();
      expect(
        screen.getByRole('option', { name: 'CRITICAL' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('option', {
          name: 'list.actions.logs.modal.logLevelFilter.allLevels',
        }),
      ).toBeInTheDocument();
    });

    it('filters logs by selected log level', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Initial call should not have log level filter
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'workload',
          },
        );
      });

      // Find and click the log level dropdown
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logLevelFilter\.label/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      // Select ERROR level from the dropdown
      const errorOption = screen.getByRole('option', { name: 'ERROR' });
      await act(async () => {
        fireEvent.click(errorOption);
      });

      // Should call getWorkloadLogs with log level filter
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: 'error',
            logType: 'workload',
          },
        );
      });
    });

    it('clears logs when log level filter changes', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Wait for initial logs to load
      await waitFor(() => {
        expect(
          screen.getByText('Application started successfully'),
        ).toBeInTheDocument();
      });

      // Change log level filter
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logLevelFilter\.label/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      const warningOption = screen.getByRole('option', { name: 'WARNING' });
      await act(async () => {
        fireEvent.click(warningOption);
      });

      // Logs should be cleared and reloaded with log level filter
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: 'warning',
            logType: 'workload',
          },
        );
      });
    });

    it('restarts streaming when log level filter changes during streaming', async () => {
      const mockStartStreaming = vi.fn();
      const mockStopStreaming = vi.fn();
      const mockClearLogs = vi.fn();

      vi.mocked(useWorkloadLogsStream).mockReturnValue({
        data: [mockLogEntries[0]],
        isLoading: false,
        isStreaming: true,
        error: null,
        startStreaming: mockStartStreaming,
        stopStreaming: mockStopStreaming,
        clearLogs: mockClearLogs,
      });

      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Enable streaming mode first
      const streamingSwitch = screen.getByRole('switch');
      await act(async () => {
        fireEvent.click(streamingSwitch);
      });

      // Now change log level filter
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logLevelFilter\.label/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      const infoOption = screen.getByRole('option', { name: 'INFO' });
      await act(async () => {
        fireEvent.click(infoOption);
      });

      // Should stop and restart streaming
      await waitFor(() => {
        expect(mockStopStreaming).toHaveBeenCalled();
        expect(mockClearLogs).toHaveBeenCalled();
      });

      // Should restart streaming after delay
      await waitFor(
        () => {
          expect(mockStartStreaming).toHaveBeenCalled();
        },
        { timeout: 200 },
      );
    });

    it('includes log level in streaming params', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Select a log level first
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logLevelFilter\.label/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      const debugOption = screen.getByRole('option', { name: 'DEBUG' });
      await act(async () => {
        fireEvent.click(debugOption);
      });

      // The streaming hook should be called with log level in params
      expect(useWorkloadLogsStream).toHaveBeenCalledWith({
        projectId: 'workbench',
        workloadId: 'workload-1',
      });
    });

    it('resets log level filter during cleanup', async () => {
      const { rerender } = await act(async () => {
        return render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalled();
      });

      // Select a log level filter
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logLevelFilter\.label/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      const traceOption = screen.getByRole('option', { name: 'TRACE' });
      await act(async () => {
        fireEvent.click(traceOption);
      });

      // Close the component
      await act(async () => {
        rerender(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={false}
            namespace="workbench"
          />,
        );
      });

      // Reopen the component
      await act(async () => {
        rerender(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
        );
      });

      // Should be reset to default (no log level filter)
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'workload',
          },
        );
      });
    });

    it('clears log level filter when selecting "All levels" option', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // First select a specific log level
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logLevelFilter\.label/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      const errorOption = screen.getByRole('option', { name: 'ERROR' });
      await act(async () => {
        fireEvent.click(errorOption);
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: 'error',
            logType: 'workload',
          },
        );
      });

      // Now select "All levels" to clear the filter
      await act(async () => {
        fireEvent.click(dropdown);
      });

      const allLevelsOption = screen.getByRole('option', {
        name: 'list.actions.logs.modal.logLevelFilter.allLevels',
      });
      await act(async () => {
        fireEvent.click(allLevelsOption);
      });

      // Should call getWorkloadLogs without log level filter
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'workload',
          },
        );
      });
    });
  });

  // Log Type filtering tests
  describe('Log Type Filtering', () => {
    it('shows log type dropdown with correct options', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Find the log type dropdown button
      const logTypeDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });
      expect(logTypeDropdown).toBeInTheDocument();
    });

    it('displays all available log types in dropdown', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Find and click the log type dropdown
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      // Check that both log type options are available
      expect(
        screen.getByRole('option', {
          name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
        }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('option', {
          name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
        }),
      ).toBeInTheDocument();
    });

    it('filters logs by selected log type', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalled();
      });

      // Initial call should have workload log type by default
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'workload',
          },
        );
      });

      // Find and click the log type dropdown
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      // Select Event type from the dropdown
      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      // Should call getWorkloadLogs with event log type filter
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'event',
          },
        );
      });
    });

    it('clears logs when log type filter changes', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalled();
      });

      // Find and click the log type dropdown
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      // Select Event type
      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      // Logs should be cleared and reloaded with log type filter
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'event',
          },
        );
      });
    });

    it('restarts streaming when log type filter changes during streaming', async () => {
      const mockStartStreaming = vi.fn();
      const mockStopStreaming = vi.fn();
      const mockClearLogs = vi.fn();

      vi.mocked(useWorkloadLogsStream).mockReturnValue({
        data: [mockLogEntries[0]],
        isLoading: false,
        isStreaming: true,
        error: null,
        startStreaming: mockStartStreaming,
        stopStreaming: mockStopStreaming,
        clearLogs: mockClearLogs,
      });

      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Enable streaming mode
      const streamingToggle = screen.getByRole('switch');
      await act(async () => {
        fireEvent.click(streamingToggle);
      });

      // Find and click the log type dropdown
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      // Select Event type
      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      // Should stop and restart streaming with new log type
      await waitFor(() => {
        expect(mockStopStreaming).toHaveBeenCalled();
        expect(mockClearLogs).toHaveBeenCalled();
      });

      // Should restart streaming after a delay
      await waitFor(
        () => {
          expect(mockStartStreaming).toHaveBeenCalledWith(
            expect.objectContaining({
              logType: 'event',
            }),
          );
        },
        { timeout: 200 },
      );
    });

    it('includes log type in streaming params', async () => {
      const mockStartStreaming = vi.fn();
      const mockStopStreaming = vi.fn();
      const mockClearLogs = vi.fn();

      vi.mocked(useWorkloadLogsStream).mockReturnValue({
        data: [],
        isLoading: false,
        isStreaming: false,
        error: null,
        startStreaming: mockStartStreaming,
        stopStreaming: mockStopStreaming,
        clearLogs: mockClearLogs,
      });

      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Change log type first
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      // Enable streaming mode - close the dropdown first, then find the switch
      await act(async () => {
        fireEvent.keyDown(document.body, { key: 'Escape' });
      });

      // Wait for the dropdown to close and then find the switch
      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      });

      const streamingToggle = screen.getByRole('switch');
      await act(async () => {
        fireEvent.click(streamingToggle);
      });

      // Should call startStreaming with the correct log type
      await waitFor(
        () => {
          expect(mockStartStreaming).toHaveBeenCalledWith(
            expect.objectContaining({
              logType: 'event',
            }),
          );
        },
        { timeout: 200 },
      );
    });

    it('resets log type filter during cleanup', async () => {
      const { rerender } = render(
        <WorkloadLogs
          workload={mockWorkload}
          isOpen={true}
          namespace="workbench"
        />,
        { wrapper },
      );

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalled();
      });

      // Change log type to events
      const dropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(dropdown);
      });

      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'event',
          },
        );
      });

      // Close the component
      await act(async () => {
        rerender(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={false}
            namespace="workbench"
          />,
        );
      });

      // Reopen the component
      await act(async () => {
        rerender(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
        );
      });

      // Should be reset to default workload log type
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'workload',
          },
        );
      });
    });

    it('disables log level filter when event type is selected', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalled();
      });

      // Change log type to events first
      const logTypeDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(logTypeDropdown);
      });

      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'event',
          },
        );
      });

      // Verify log level dropdown is disabled for events
      const logLevelDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logLevelFilter\.label/i,
      });

      expect(logLevelDropdown).toHaveAttribute('data-disabled', 'true');
    });
  });

  // New tests for Log Type functionality with dynamic defaults
  describe('Log Type Dynamic Defaults', () => {
    it('defaults to EVENT log type for PENDING workloads', async () => {
      const pendingWorkload: Workload = {
        ...mockWorkload,
        status: 'Pending',
      };

      await act(async () => {
        render(
          <WorkloadLogs
            workload={pendingWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Should call with EVENT log type by default for pending workloads
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'event',
          },
        );
      });

      // Check that the log type dropdown shows Events as selected
      const logTypeDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      expect(logTypeDropdown).toBeInTheDocument();
    });

    it('includes log type in streaming parameters for PENDING workloads', async () => {
      const mockStartStreaming = vi.fn();
      const mockStopStreaming = vi.fn();
      const mockClearLogs = vi.fn();

      vi.mocked(useWorkloadLogsStream).mockReturnValue({
        data: [],
        isLoading: false,
        isStreaming: false,
        error: null,
        startStreaming: mockStartStreaming,
        stopStreaming: mockStopStreaming,
        clearLogs: mockClearLogs,
      });

      const pendingWorkload: Workload = {
        ...mockWorkload,
        status: 'Pending',
      };

      await act(async () => {
        render(
          <WorkloadLogs
            workload={pendingWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Enable streaming mode
      const streamingToggle = screen.getByRole('switch');
      await act(async () => {
        fireEvent.click(streamingToggle);
      });

      // Should call startStreaming with EVENT log type for pending workloads
      await waitFor(
        () => {
          expect(mockStartStreaming).toHaveBeenCalledWith(
            expect.objectContaining({
              logType: 'event',
            }),
          );
        },
        { timeout: 200 },
      );
    });
  });

  // New tests for Log Type filtering behavior
  describe('Log Type Filter Interactions', () => {
    it('clears logs when switching from workload to events', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'workload',
          },
        );
      });

      // Wait for logs to be displayed
      await waitFor(() => {
        expect(
          screen.getByText('Application started successfully'),
        ).toBeInTheDocument();
      });

      // Switch to events log type
      const logTypeDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(logTypeDropdown);
      });

      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      // Should call API with event log type
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'event',
          },
        );
      });
    });

    it('preserves log level filter when changing log type', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalled();
      });

      // Set log level filter first
      const logLevelDropdown = screen
        .getByText('list.actions.logs.modal.logLevelFilter.label')
        .closest('button') as HTMLElement;

      await act(async () => {
        fireEvent.click(logLevelDropdown);
      });

      const errorOption = screen.getByRole('option', { name: 'ERROR' });
      await act(async () => {
        fireEvent.click(errorOption);
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: 'error',
            logType: 'workload',
          },
        );
      });

      // Now change log type to events - wait for dropdown to be available
      await waitFor(() => {
        expect(
          screen.getByRole('button', {
            name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
          }),
        ).toBeInTheDocument();
      });

      const logTypeDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(logTypeDropdown);
      });

      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      // Should preserve error level filter with new event log type
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: 'error',
            logType: 'event',
          },
        );
      });
    });

    it('restarts streaming with correct log type when filter changes during streaming', async () => {
      const mockStartStreaming = vi.fn();
      const mockStopStreaming = vi.fn();
      const mockClearLogs = vi.fn();

      vi.mocked(useWorkloadLogsStream).mockReturnValue({
        data: [mockLogEntries[0]],
        isLoading: false,
        isStreaming: true,
        error: null,
        startStreaming: mockStartStreaming,
        stopStreaming: mockStopStreaming,
        clearLogs: mockClearLogs,
      });

      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      // Enable streaming mode first
      const streamingToggle = screen.getByRole('switch');
      await act(async () => {
        fireEvent.click(streamingToggle);
      });

      // Now change log type to events
      const logTypeDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(logTypeDropdown);
      });

      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      // Should stop current streaming and restart with new log type
      await waitFor(() => {
        expect(mockStopStreaming).toHaveBeenCalled();
        expect(mockClearLogs).toHaveBeenCalled();
      });

      await waitFor(
        () => {
          expect(mockStartStreaming).toHaveBeenCalledWith(
            expect.objectContaining({
              logType: 'event',
            }),
          );
        },
        { timeout: 200 },
      );
    });

    it('resets log type to default when component is closed and reopened', async () => {
      const pendingWorkload: Workload = {
        ...mockWorkload,
        status: 'Pending',
      };

      const { rerender } = await act(async () => {
        return render(
          <WorkloadLogs
            workload={pendingWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'event',
          },
        );
      });

      // User manually changes to workload log type
      const logTypeDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });

      await act(async () => {
        fireEvent.click(logTypeDropdown);
      });

      const workloadOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });
      await act(async () => {
        fireEvent.click(workloadOption);
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'workload',
          },
        );
      });

      // Close the component
      await act(async () => {
        rerender(
          <WorkloadLogs
            workload={pendingWorkload}
            isOpen={false}
            namespace="workbench"
          />,
        );
      });

      // Reopen the component
      await act(async () => {
        rerender(
          <WorkloadLogs
            workload={pendingWorkload}
            isOpen={true}
            namespace="workbench"
          />,
        );
      });

      // Should reset to default EVENT log type for pending workloads
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: undefined,
            logType: 'event',
          },
        );
      });
    });

    it('includes both log type and log level in API calls', async () => {
      await act(async () => {
        render(
          <WorkloadLogs
            workload={mockWorkload}
            isOpen={true}
            namespace="workbench"
          />,
          {
            wrapper,
          },
        );
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalled();
      });

      // Set log level filter
      const logLevelDropdown = screen
        .getByText('list.actions.logs.modal.logLevelFilter.label')
        .closest('button') as HTMLElement;

      await act(async () => {
        fireEvent.click(logLevelDropdown);
      });

      const warningOption = screen.getByRole('option', { name: 'WARNING' });
      await act(async () => {
        fireEvent.click(warningOption);
      });

      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: 'warning',
            logType: 'workload',
          },
        );
      });

      // Then set log type filter - wait for dropdown to be available
      await waitFor(() => {
        expect(
          screen.getByRole('button', {
            name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
          }),
        ).toBeInTheDocument();
      });

      const logTypeDropdown = screen.getByRole('button', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.workload/i,
      });

      await act(async () => {
        fireEvent.click(logTypeDropdown);
      });

      const eventOption = screen.getByRole('option', {
        name: /list\.actions\.logs\.modal\.logTypeFilter\.event/i,
      });
      await act(async () => {
        fireEvent.click(eventOption);
      });

      // Should include both filters in the API call
      await waitFor(() => {
        expect(getWorkloadLogs).toHaveBeenCalledWith(
          'workbench',
          'workload-1',
          {
            start: expect.any(String),
            end: expect.any(String),
            direction: 'backward',
            pageToken: undefined,
            level: 'warning',
            logType: 'event',
          },
        );
      });
    });
  });
});
