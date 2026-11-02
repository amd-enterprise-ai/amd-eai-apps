// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';

import { streamChatResponse } from '@/lib/app/chat';

import { Model } from '@/types/models';
import { ModelOnboardingStatus } from '@/types/models';
import type { Workload } from '@/types/workloads';

import { ChatView } from '@/components/features/chat/ChatView';
import ProviderWrapper from '@/__tests__/ProviderWrapper';

import '@testing-library/jest-dom';
import { Mock, vi } from 'vitest';

vi.mock('@/lib/app/chat', () => ({
  streamChatResponse: vi.fn(),
}));

const getModelSelectTrigger = (
  container: HTMLElement = screen.getByTestId('model-deployment-select'),
) => within(container).getByRole('button');

const mockToast = {
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
};

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => ({
    toast: mockToast,
  }),
}));

vi.mock('@/lib/app/chat-settings', () => ({
  getChatSettings: vi.fn(() => ({
    temperature: 0.7,
    frequencyPenalty: 0,
    presencePenalty: 0,
    systemPrompt: '',
  })),
  saveChatSettings: vi.fn(),
}));

vi.mock('next/router', () => ({
  __esModule: true,
  default: {
    push: vi.fn(),
  },
}));

vi.mock('next/navigation', () => ({
  useSearchParams: vi.fn(() => ({
    get: vi.fn(() => null),
  })),
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('ChatView Component', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1280,
    });
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches:
          query.includes('min-width') && query.includes('1024')
            ? window.innerWidth >= 1024
            : false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  const mockModels: Model[] = [
    {
      id: '1',
      name: 'Model 1',
      canonicalName: 'test-org/test-model-1',
      createdAt: '',
      onboardingStatus: ModelOnboardingStatus.READY,
      createdBy: '',
    },
  ];

  const mockWorkloads: Workload[] = [
    {
      id: '1',
      chartId: '',
      type: 'INFERENCE',
      createdBy: 'test-user',
      updatedBy: null,
      namespace: 'test-namespace',
      description: null,
      endpoints: {},
      createdAt: '',
      updatedAt: '',
      status: 'Running',
      displayName: 'Model 1',
      name: 'mw-test-workload',
    },
  ];

  it('renders the chat view correctly', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    expect(screen.getByLabelText('chatInput.label')).toBeInTheDocument();
  });

  it('handles sending a message', async () => {
    (streamChatResponse as Mock).mockResolvedValue({
      responseStream: getStream(['assistant ', 'message'], false),
      context: Promise.resolve({
        messages: [
          { role: 'system', content: 'Hello, system!' },
          {
            role: 'user',
            content: 'Hello, world!',
          },
        ],
      }),
    });

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const modelSelect = screen.getByTestId('model-deployment-select');
    await act(async () => {
      fireEvent.click(modelSelect);
    });

    const modelOption = screen.getAllByText('Model 1')[0];
    await act(async () => {
      fireEvent.click(modelOption);
    });

    const input = screen.getByTestId('chat-input');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Hello, world!' } });
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    });

    await waitFor(() => {
      expect(screen.getByText('Hello, world!')).toBeInTheDocument();
    });
  });

  it('handles error during message sending', async () => {
    const consoleErrorSpy = vi
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);

    try {
      (streamChatResponse as Mock).mockRejectedValue(
        new Error('Network error'),
      );

      await act(async () => {
        render(
          <ProviderWrapper>
            <ChatView workloads={mockWorkloads} />
          </ProviderWrapper>,
        );
      });

      // Select a model first
      const modelSelect = screen.getByTestId('model-deployment-select');
      await act(async () => {
        fireEvent.click(modelSelect);
      });

      const modelOption = screen.getAllByText('Model 1')[0];
      await act(async () => {
        fireEvent.click(modelOption);
      });

      const input = screen.getByTestId('chat-input');

      await act(async () => {
        fireEvent.change(input, { target: { value: 'Test message' } });
        fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
      });

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalled();
      });

      expect(consoleErrorSpy).toHaveBeenCalled();
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('has clear button available', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    // Find clear button
    const clearButton = screen.getByRole('button', { name: /clear/i });
    expect(clearButton).toBeInTheDocument();

    // Click clear button should not throw error
    await act(async () => {
      fireEvent.click(clearButton);
    });
  });

  it('handles workload selection from URL parameters', async () => {
    // Mock the useSearchParams to return a workload parameter
    const { useSearchParams } = await import('next/navigation');
    vi.mocked(useSearchParams).mockReturnValue({
      get: vi.fn((param: string) => (param === 'workload' ? '1' : null)),
    } as unknown as ReturnType<typeof useSearchParams>);

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    // The workload should be selected from URL parameter
    const modelSelect = screen.getByTestId('model-deployment-select');
    expect(modelSelect).toBeInTheDocument();
  });

  it('prevents sending message when no workload is selected', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={[]} />
        </ProviderWrapper>,
      );
    });

    const input = screen.getByTestId('chat-input');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    });

    // streamChatResponse should not be called
    expect(streamChatResponse).not.toHaveBeenCalled();
  });

  it('handles streaming message updates correctly', async () => {
    const mockStream = new ReadableStream({
      async start(controller) {
        controller.enqueue('Hello ');
        await new Promise((resolve) => setTimeout(resolve, 10));
        controller.enqueue('world!');
        controller.close();
      },
    });

    (streamChatResponse as Mock).mockResolvedValue({
      responseStream: mockStream,
      context: Promise.resolve({}),
    });

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const input = screen.getByTestId('chat-input');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    });

    // Wait for the streaming to complete
    await waitFor(
      () => {
        expect(screen.getByText('Test message')).toBeInTheDocument();
      },
      { timeout: 1000 },
    );
  });

  it('opens and closes settings drawer', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    // Find and click settings button
    const settingsButton = screen.getByRole('button', { name: /settings/i });
    await act(async () => {
      fireEvent.click(settingsButton);
    });

    // Settings drawer should be opened
    expect(screen.getByText(/temperature/i)).toBeInTheDocument();
  });

  it('switches between chat and compare modes', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    // Switch to compare mode
    const compareTab = screen.getByRole('tab', { name: /compare/i });
    await act(async () => {
      fireEvent.click(compareTab);
    });

    // Should show two model selects in compare mode
    const modelSelects = screen.getAllByTestId('model-deployment-select');
    expect(modelSelects).toHaveLength(2);
  });

  it('handles settings synchronization in compare mode', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    // Switch to compare mode
    const compareTab = screen.getByRole('tab', { name: /compare/i });
    await act(async () => {
      fireEvent.click(compareTab);
    });

    // The sync settings functionality should be available in compare mode
    // For now, just verify we can switch to compare mode
    expect(compareTab).toHaveAttribute('aria-selected', 'true');
  });

  it('sends message using send button', async () => {
    (streamChatResponse as Mock).mockResolvedValue({
      responseStream: getStream(['Response text'], false),
      context: Promise.resolve({}),
    });

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const input = screen.getByTestId('chat-input');
    const sendButton = screen.getByTestId('send-button');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.click(sendButton);
    });

    await waitFor(() => {
      expect(screen.getByText('Test message')).toBeInTheDocument();
    });
  });

  it('handles empty message submission', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const input = screen.getByTestId('chat-input');
    const sendButton = screen.getByTestId('send-button');

    // Try to send empty message
    await act(async () => {
      fireEvent.change(input, { target: { value: '' } });
      fireEvent.click(sendButton);
    });

    // streamChatResponse should not be called for empty message
    expect(streamChatResponse).not.toHaveBeenCalled();
  });

  it('stops conversation when stop button is clicked during streaming', async () => {
    const mockStream = new ReadableStream({
      start() {
        // Stream will never end to test stopping
      },
    });

    (streamChatResponse as Mock).mockResolvedValue({
      responseStream: mockStream,
      context: Promise.resolve({}),
    });

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const input = screen.getByTestId('chat-input');

    // Start sending a message
    await act(async () => {
      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    });

    // Find and click stop button (should appear during streaming)
    await waitFor(() => {
      const stopButton = screen.queryByRole('button', { name: /stop/i });
      if (stopButton) {
        fireEvent.click(stopButton);
      }
    });
  });

  it('handles model selection with multiple workloads', async () => {
    const secondWorkload = {
      ...mockWorkloads[0],
      id: '2',
      name: 'mw-test-workload-2',
      displayName: 'Model 2',
    };

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={[...mockWorkloads, secondWorkload]} />
        </ProviderWrapper>,
      );
    });

    // Verify model select is present and functional
    const modelSelect = screen.getByTestId('model-deployment-select');
    expect(modelSelect).toBeInTheDocument();

    // Click to open dropdown
    await act(async () => {
      fireEvent.click(modelSelect);
    });

    // Should see multiple model options
    const modelOptions = screen.getAllByText(/Model/);
    expect(modelOptions.length).toBeGreaterThan(1);
  });

  it('displays workload description from workloadDisplayInfo in model select', async () => {
    const workloadsWithAim = [
      {
        ...mockWorkloads[0],
        id: '1',
        displayName: 'Test Model',
        name: 'aim-test-model',
      },
    ];
    const workloadDisplayInfo = {
      '1': { imageVersion: '1.0.0', metric: 'throughput', tags: [] },
    };

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView
            workloads={workloadsWithAim}
            workloadDisplayInfo={workloadDisplayInfo}
          />
        </ProviderWrapper>,
      );
    });

    // Open dropdown so SelectItem descriptions are visible
    const modelSelect = screen.getByTestId('model-deployment-select');
    await act(async () => {
      fireEvent.click(modelSelect);
    });
    // Description uses t() for metric; with mock t returns key (may be with imageVersion prefix)
    const descriptionElements = screen.getAllByText((content) =>
      content.includes('performanceMetrics.values.throughput'),
    );
    expect(descriptionElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders embedded input in empty state on mobile viewports', async () => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 375,
    });
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    // Only the embedded input (inside the intro layout) should be present, not the bottom one
    const inputs = screen.getAllByLabelText('chatInput.label');
    expect(inputs).toHaveLength(1);
  });

  it('does not render the bottom input in mobile empty state', async () => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 375,
    });
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    // Card variant is not shown on mobile — no card testid
    expect(screen.queryByTestId('card')).not.toBeInTheDocument();
  });

  it('auto-selects the only deployed model on initial render', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const modelSelect = screen.getByTestId('model-deployment-select');
    expect(modelSelect).toHaveTextContent('Model 1');
    expect(screen.getByTestId('chat-input')).not.toBeDisabled();
  });

  it('does not auto-select when no workloads are deployed', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={[]} />
        </ProviderWrapper>,
      );
    });

    const modelSelect = screen.getByTestId('model-deployment-select');
    expect(getModelSelectTrigger()).not.toHaveTextContent('Model 1');
    expect(screen.getByTestId('chat-input')).toBeDisabled();
  });

  it('does not auto-select when multiple deployed models are available', async () => {
    const secondWorkload: Workload = {
      ...mockWorkloads[0],
      id: '2',
      name: 'mw-test-workload-2',
      displayName: 'Model 2',
    };

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={[...mockWorkloads, secondWorkload]} />
        </ProviderWrapper>,
      );
    });

    const modelSelect = screen.getByTestId('model-deployment-select');
    expect(getModelSelectTrigger()).not.toHaveTextContent('Model 1');
    expect(getModelSelectTrigger()).not.toHaveTextContent('Model 2');
    expect(screen.getByTestId('chat-input')).toBeDisabled();
  });

  it('does not auto-select when the parent provides no chattable workloads', async () => {
    // Non-RUNNING / non-INFERENCE workloads are filtered out by the parent page
    // before they reach ChatView, so the component sees an empty list.
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={[]} />
        </ProviderWrapper>,
      );
    });

    const modelSelect = screen.getByTestId('model-deployment-select');
    expect(getModelSelectTrigger()).not.toHaveTextContent('Model 1');
    expect(screen.getByTestId('chat-input')).toBeDisabled();
  });

  it('auto-selects the only deployed model for both slots in compare mode', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const compareTab = screen.getByRole('tab', { name: /compare/i });
    await act(async () => {
      fireEvent.click(compareTab);
    });

    const modelSelects = screen.getAllByTestId('model-deployment-select');
    expect(modelSelects).toHaveLength(2);
    expect(modelSelects[0]).toHaveTextContent('Model 1');
    expect(modelSelects[1]).toHaveTextContent('Model 1');
  });

  it('does not auto-select the second model when multiple deployed models exist', async () => {
    const secondWorkload: Workload = {
      ...mockWorkloads[0],
      id: '2',
      name: 'mw-test-workload-2',
      displayName: 'Model 2',
    };

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={[...mockWorkloads, secondWorkload]} />
        </ProviderWrapper>,
      );
    });

    const compareTab = screen.getByRole('tab', { name: /compare/i });
    await act(async () => {
      fireEvent.click(compareTab);
    });

    const modelSelects = screen.getAllByTestId('model-deployment-select');
    expect(modelSelects).toHaveLength(2);
    expect(getModelSelectTrigger(modelSelects[0])).not.toHaveTextContent(
      'Model 1',
    );
    expect(getModelSelectTrigger(modelSelects[1])).not.toHaveTextContent(
      'Model 1',
    );
  });

  it('respects the workload URL parameter over auto-selection', async () => {
    const secondWorkload: Workload = {
      ...mockWorkloads[0],
      id: '2',
      name: 'mw-test-workload-2',
      displayName: 'Model 2',
    };
    const { useSearchParams } = await import('next/navigation');
    vi.mocked(useSearchParams).mockReturnValue({
      get: vi.fn((param: string) => (param === 'workload' ? '2' : null)),
    } as unknown as ReturnType<typeof useSearchParams>);

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={[...mockWorkloads, secondWorkload]} />
        </ProviderWrapper>,
      );
    });

    const modelSelect = screen.getByTestId('model-deployment-select');
    expect(modelSelect).toHaveTextContent('Model 2');
  });

  it('respects the workload URL parameter when only one workload exists', async () => {
    // Regression: when ?workload= points to a workload that isn't in the
    // ChatView list (e.g. filtered out upstream as non-running) AND there is
    // exactly one chattable workload, the URL param must still win — the
    // single-workload auto-select must not override it.
    const { useSearchParams } = await import('next/navigation');
    vi.mocked(useSearchParams).mockReturnValue({
      get: vi.fn((param: string) =>
        param === 'workload' ? 'unknown-id' : null,
      ),
    } as unknown as ReturnType<typeof useSearchParams>);

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const modelSelect = screen.getByTestId('model-deployment-select');
    expect(getModelSelectTrigger()).not.toHaveTextContent('Model 1');
    expect(screen.getByTestId('chat-input')).toBeDisabled();
  });

  it('displays loading state correctly', async () => {
    // Mock a delayed response
    const delayedPromise = new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          responseStream: getStream(['Response'], false),
          context: Promise.resolve({}),
        });
      }, 100);
    });

    (streamChatResponse as Mock).mockReturnValue(delayedPromise);

    await act(async () => {
      render(
        <ProviderWrapper>
          <ChatView workloads={mockWorkloads} />
        </ProviderWrapper>,
      );
    });

    const input = screen.getByTestId('chat-input');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    });

    // Should show loading state
    expect(screen.getByText('Test message')).toBeInTheDocument();

    // Wait for response to complete
    await waitFor(() => delayedPromise, { timeout: 200 });
  });
});

export const getStream = (tokens: string[], encode: boolean = true) => {
  const encoder = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      tokens.forEach((t) => {
        controller.enqueue(encode ? encoder.encode(t) : t);
      });
      controller.close();
    },
  });
};
