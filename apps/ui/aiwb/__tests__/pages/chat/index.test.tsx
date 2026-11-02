// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, render, screen, waitFor } from '@testing-library/react';

import { listChattableWorkloads } from '@/lib/app/chat';

import type { Workload } from '@/types/workloads';

import ChatPage from '@/pages/[project]/chat';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock, vi } from 'vitest';
import { mockWorkloads } from '@/__mocks__/services/app/workloads.data';

vi.mock('@/lib/app/chat', () => ({
  listChattableWorkloads: vi.fn(),
}));

vi.mock('@amdenterpriseai/hooks', () => ({
  __esModule: true,
  useSystemToast: () => ({
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock ChatView as a simple component
vi.mock('@/components/features/chat/ChatView', () => ({
  ChatView: ({
    workloads,
  }: {
    workloads: Workload[];
    workloadDisplayInfo?: Record<
      string,
      { imageVersion: string; metric: string }
    >;
  }) => (
    <div data-testid="chat-view">
      <div data-testid="workload-count">{workloads.length}</div>
      {workloads.map((workload) => (
        <div key={workload.id} data-testid={`workload-${workload.id}`}>
          {workload.displayName}
        </div>
      ))}
    </div>
  ),
}));

describe('Chat Page', () => {
  const chattableWorkloads: Workload[] = [mockWorkloads[0]];
  const chattableData = {
    workloads: chattableWorkloads,
    workloadDisplayInfo: {} as Record<
      string,
      { imageVersion: string; metric: string }
    >,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (listChattableWorkloads as Mock).mockResolvedValue(chattableData);
  });

  it('renders the chat page', async () => {
    await act(async () => {
      render(<ChatPage />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByTestId('chat-view')).toBeInTheDocument();
    });
  });

  it('loads chattable workloads with correct parameters', async () => {
    await act(async () => {
      render(<ChatPage />, { wrapper });
    });

    await waitFor(() => {
      expect(listChattableWorkloads).toHaveBeenCalledWith('project1');
    });
  });

  it('passes workloads from listChattableWorkloads to ChatView', async () => {
    await act(async () => {
      render(<ChatPage />, { wrapper });
    });

    await waitFor(() => {
      expect(listChattableWorkloads).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByTestId('chat-view')).toBeInTheDocument();
    });

    expect(screen.getByTestId('workload-count')).toHaveTextContent('1');
    expect(screen.getByTestId('workload-workload-1')).toBeInTheDocument();
  });

  it('does not mount ChatView while workloads are loading', async () => {
    (listChattableWorkloads as Mock).mockReturnValue(new Promise(() => {}));

    await act(async () => {
      render(<ChatPage />, { wrapper });
    });

    expect(screen.queryByTestId('chat-view')).not.toBeInTheDocument();
  });

  it('handles chattable workloads loading error', async () => {
    const mockError = new Error('Failed to load chattable workloads');
    (listChattableWorkloads as Mock).mockRejectedValue(mockError);

    await act(async () => {
      render(<ChatPage />, { wrapper });
    });

    await waitFor(() => {
      expect(listChattableWorkloads).toHaveBeenCalled();
    });

    // ChatView should still render with empty workloads
    await waitFor(() => {
      expect(screen.getByTestId('chat-view')).toBeInTheDocument();
    });
    expect(screen.getByTestId('workload-count')).toHaveTextContent('0');
  });

  it('shows empty workloads when no chat models are available', async () => {
    (listChattableWorkloads as Mock).mockResolvedValue({
      workloads: [],
      workloadDisplayInfo: {},
    });

    await act(async () => {
      render(<ChatPage />, { wrapper });
    });

    await waitFor(() => {
      expect(listChattableWorkloads).toHaveBeenCalled();
    });

    // Verify ChatView renders with no workloads
    await waitFor(() => {
      expect(screen.getByTestId('chat-view')).toBeInTheDocument();
    });

    expect(screen.getByTestId('workload-count')).toHaveTextContent('0');
  });

  it('shows all matching workloads when multiple chat models are available', async () => {
    const multipleWorkloads = [mockWorkloads[0], mockWorkloads[10]];
    (listChattableWorkloads as Mock).mockResolvedValue({
      workloads: multipleWorkloads,
      workloadDisplayInfo: {},
    });

    await act(async () => {
      render(<ChatPage />, { wrapper });
    });

    await waitFor(() => {
      expect(listChattableWorkloads).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByTestId('chat-view')).toBeInTheDocument();
    });

    expect(screen.getByTestId('workload-count')).toHaveTextContent('2');
  });

  it('uses optimized chattable endpoint instead of filtering client-side', async () => {
    await act(async () => {
      render(<ChatPage />, { wrapper });
    });

    await waitFor(() => {
      expect(listChattableWorkloads).toHaveBeenCalledTimes(1);
      expect(listChattableWorkloads).toHaveBeenCalledWith('project1');
    });
  });
});
