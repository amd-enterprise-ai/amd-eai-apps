// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DebugInfo } from '@/types/chat';
import { Message } from '@/types/chat';

import { DebugInfoModal } from '@/components/features/chat/DebugInfoModal';
import ProviderWrapper from '@/__tests__/ProviderWrapper';

import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock adapter components (Modal, Accordion) while preserving other exports
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    Modal: ({ children, onClose, title, subTitle, size }: any) => (
      <div data-testid="modal" data-size={size}>
        <div data-testid="modal-header">
          <h2 data-testid="modal-title">{title}</h2>
          <p data-testid="modal-subtitle">{subTitle}</p>
          <button data-testid="close-button" onClick={onClose}>
            Close
          </button>
        </div>
        <div data-testid="modal-body">{children}</div>
      </div>
    ),
    Accordion: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="accordion">{children}</div>
    ),
    AccordionItem: ({
      title,
      children,
    }: {
      title: string;
      children: React.ReactNode;
    }) => (
      <div data-testid="accordion-item">
        <button
          data-testid={`accordion-toggle-${title.toLowerCase().replace(/\s+/g, '-')}`}
        >
          {title}
        </button>
        <div
          data-testid={`accordion-content-${title.toLowerCase().replace(/\s+/g, '-')}`}
        >
          {children}
        </div>
      </div>
    ),
  };
});

// Mock the MemoizedChatMessage component
vi.mock('@/components/features/chat/MemoizedChatMessage', () => ({
  MemoizedChatMessage: ({ message }: { message: Message }) => {
    const content =
      typeof message.content === 'string'
        ? message.content
        : JSON.stringify(message.content);
    return (
      <div data-testid="chat-message" data-role={message.role}>
        {content}
      </div>
    );
  },
}));

// Mock next-i18next
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'debugInfoModal.title': 'Debug Information',
        'debugInfoModal.subTitle':
          'Detailed debugging data for this conversation',
        'debugInfoModal.promptsTitle': 'Prompts',
        'debugInfoModal.promptsDescription':
          'System and user prompts used in this conversation',
        'debugInfoModal.tokenUsageTitle': 'Token Usage',
        'debugInfoModal.promptTokens': 'Prompt Tokens:',
        'debugInfoModal.completionTokens': 'Completion Tokens:',
        'debugInfoModal.totalTokens': 'Total Tokens:',
        'debugInfoModal.noPromptMessages': 'No prompt messages available',
        'debugInfoModal.noTokenUsage': 'Token usage information not available',
      };
      return translations[key] || key;
    },
  }),
}));

describe('DebugInfoModal Component', () => {
  const mockMessages: Message[] = [
    {
      role: 'system',
      content: 'You are a helpful assistant.',
    },
    {
      role: 'user',
      content: 'What is the weather like today?',
    },
    {
      role: 'assistant',
      content: 'I can help you with weather information.',
    },
  ];

  const mockDebugInfo: DebugInfo = {
    messages: mockMessages,
    usage: {
      prompt_tokens: 150,
      completion_tokens: 75,
      total_tokens: 225,
    },
  };

  const defaultProps = {
    debugInfo: mockDebugInfo,
    onClose: vi.fn(),
    isOpen: true,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders the modal when isOpen is true', () => {
      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(screen.getByTestId('modal')).toBeInTheDocument();
      expect(screen.getByTestId('modal-title')).toHaveTextContent(
        'Debug Information',
      );
      expect(screen.getByTestId('modal-subtitle')).toHaveTextContent(
        'Detailed debugging data for this conversation',
      );
    });

    it('does not render the modal when isOpen is false', () => {
      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} isOpen={false} />
        </ProviderWrapper>,
      );

      expect(screen.queryByTestId('modal')).not.toBeInTheDocument();
    });

    it('renders with correct modal size', () => {
      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(screen.getByTestId('modal')).toHaveAttribute('data-size', 'lg');
    });

    it('renders accordion with both sections', () => {
      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(screen.getByTestId('accordion')).toBeInTheDocument();
      expect(screen.getByTestId('accordion-toggle-prompts')).toHaveTextContent(
        'Prompts',
      );
      expect(
        screen.getByTestId('accordion-toggle-token-usage'),
      ).toHaveTextContent('Token Usage');
    });
  });

  describe('Close Functionality', () => {
    it('calls onClose when close button is clicked', async () => {
      const onCloseMock = vi.fn();
      const user = userEvent.setup();

      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} onClose={onCloseMock} />
        </ProviderWrapper>,
      );

      const closeButton = screen.getByTestId('close-button');
      await user.click(closeButton);

      expect(onCloseMock).toHaveBeenCalled();
    });
  });

  describe('Prompts Section', () => {
    it('renders prompts section with messages', () => {
      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} />
        </ProviderWrapper>,
      );

      const promptsContent = screen.getByTestId('accordion-content-prompts');
      expect(promptsContent).toBeInTheDocument();

      // Check for description
      expect(
        screen.getByText('System and user prompts used in this conversation'),
      ).toBeInTheDocument();

      // Check for chat messages
      const chatMessages = screen.getAllByTestId('chat-message');
      expect(chatMessages).toHaveLength(3);

      expect(chatMessages[0]).toHaveAttribute('data-role', 'system');
      expect(chatMessages[1]).toHaveAttribute('data-role', 'user');
      expect(chatMessages[2]).toHaveAttribute('data-role', 'assistant');
    });

    it('renders message content correctly', () => {
      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} />
        </ProviderWrapper>,
      );

      expect(
        screen.getByText('You are a helpful assistant.'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('What is the weather like today?'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('I can help you with weather information.'),
      ).toBeInTheDocument();
    });

    it('renders empty messages section when messages array is empty', () => {
      const debugInfoWithoutMessages: DebugInfo = {
        ...mockDebugInfo,
        messages: [],
      };

      render(
        <ProviderWrapper>
          <DebugInfoModal
            {...defaultProps}
            debugInfo={debugInfoWithoutMessages}
          />
        </ProviderWrapper>,
      );

      const promptsContent = screen.getByTestId('accordion-content-prompts');
      expect(promptsContent).toBeInTheDocument();

      // Should show description but no messages (since the array is empty but truthy)
      expect(
        screen.getByText('System and user prompts used in this conversation'),
      ).toBeInTheDocument();

      // Should not show any chat messages
      expect(screen.queryAllByTestId('chat-message')).toHaveLength(0);
    });

    it('renders no messages when messages is falsy', () => {
      const debugInfoWithoutMessages: DebugInfo = {
        ...mockDebugInfo,
        messages: undefined as any,
      };

      render(
        <ProviderWrapper>
          <DebugInfoModal
            {...defaultProps}
            debugInfo={debugInfoWithoutMessages}
          />
        </ProviderWrapper>,
      );

      expect(
        screen.getByText('No prompt messages available'),
      ).toBeInTheDocument();
    });
  });

  describe('Token Usage Section', () => {
    it('renders token usage information when available', () => {
      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} />
        </ProviderWrapper>,
      );

      const tokenUsageContent = screen.getByTestId(
        'accordion-content-token-usage',
      );
      expect(tokenUsageContent).toBeInTheDocument();

      expect(screen.getByText('Prompt Tokens:')).toBeInTheDocument();
      expect(screen.getByText('150')).toBeInTheDocument();

      expect(screen.getByText('Completion Tokens:')).toBeInTheDocument();
      expect(screen.getByText('75')).toBeInTheDocument();

      expect(screen.getByText('Total Tokens:')).toBeInTheDocument();
      expect(screen.getByText('225')).toBeInTheDocument();
    });

    it('renders no token usage message when usage is not available', () => {
      const debugInfoWithoutUsage: DebugInfo = {
        ...mockDebugInfo,
        usage: undefined,
      };

      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} debugInfo={debugInfoWithoutUsage} />
        </ProviderWrapper>,
      );

      expect(
        screen.getByText('Token usage information not available'),
      ).toBeInTheDocument();
    });

    it('renders token usage with zero values correctly', () => {
      const debugInfoWithZeroUsage: DebugInfo = {
        ...mockDebugInfo,
        usage: {
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0,
        },
      };

      render(
        <ProviderWrapper>
          <DebugInfoModal
            {...defaultProps}
            debugInfo={debugInfoWithZeroUsage}
          />
        </ProviderWrapper>,
      );

      // Should render all zeros
      const zeroElements = screen.getAllByText('0');
      expect(zeroElements).toHaveLength(3);
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('handles empty debugInfo gracefully', () => {
      const emptyDebugInfo: DebugInfo = {
        messages: [],
      };

      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} debugInfo={emptyDebugInfo} />
        </ProviderWrapper>,
      );

      // Should render all sections but with empty content
      expect(
        screen.getByText('System and user prompts used in this conversation'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('Token usage information not available'),
      ).toBeInTheDocument();

      // Should not have any messages
      expect(screen.queryAllByTestId('chat-message')).toHaveLength(0);
    });

    it('handles debugInfo with only some properties', () => {
      const partialDebugInfo: DebugInfo = {
        messages: mockMessages,
        // No usage
      };

      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} debugInfo={partialDebugInfo} />
        </ProviderWrapper>,
      );

      // Should show messages
      expect(screen.getAllByTestId('chat-message')).toHaveLength(3);

      // Should show no token usage
      expect(
        screen.getByText('Token usage information not available'),
      ).toBeInTheDocument();
    });

    it('handles large token usage values', () => {
      const debugInfoWithLargeUsage: DebugInfo = {
        ...mockDebugInfo,
        usage: {
          prompt_tokens: 1000000,
          completion_tokens: 500000,
          total_tokens: 1500000,
        },
      };

      render(
        <ProviderWrapper>
          <DebugInfoModal
            {...defaultProps}
            debugInfo={debugInfoWithLargeUsage}
          />
        </ProviderWrapper>,
      );

      expect(screen.getByText('1000000')).toBeInTheDocument();
      expect(screen.getByText('500000')).toBeInTheDocument();
      expect(screen.getByText('1500000')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('provides proper structure for screen readers', () => {
      render(
        <ProviderWrapper>
          <DebugInfoModal {...defaultProps} />
        </ProviderWrapper>,
      );

      // Modal should have proper title
      expect(screen.getByTestId('modal-title')).toBeInTheDocument();

      // Accordion sections should have proper labels
      expect(
        screen.getByTestId('accordion-toggle-prompts'),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('accordion-toggle-token-usage'),
      ).toBeInTheDocument();
    });
  });

  describe('Performance', () => {
    it('handles large number of messages efficiently', () => {
      const manyMessages: Message[] = Array.from({ length: 50 }, (_, i) => ({
        role: (i % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
        content: `Message ${i} content`,
      }));

      const debugInfoWithManyMessages: DebugInfo = {
        ...mockDebugInfo,
        messages: manyMessages,
      };

      expect(() =>
        render(
          <ProviderWrapper>
            <DebugInfoModal
              {...defaultProps}
              debugInfo={debugInfoWithManyMessages}
            />
          </ProviderWrapper>,
        ),
      ).not.toThrow();

      // Should render all messages
      const chatMessages = screen.getAllByTestId('chat-message');
      expect(chatMessages).toHaveLength(50);
    });
  });
});
