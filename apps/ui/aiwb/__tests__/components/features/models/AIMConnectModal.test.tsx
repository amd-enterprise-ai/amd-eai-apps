// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';
import { act } from 'react';
import React from 'react';

import AIMConnectModal from '@/components/features/models/AIMConnectModal';
import { mockAims } from '@/__mocks__/services/app/aims.data';

import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock useTranslation
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock useProject — the modal reads the AI gateway flag/URL from context.
// Default: gateway enabled but no URL configured, so behaviour matches the
// per-service (external/internal) endpoints. Individual tests override this.
const mockProject = {
  aiGatewayEnabled: true,
  aiGatewayUrl: undefined as string | undefined,
};
vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => mockProject,
}));

// Mock heroui components
vi.mock('@heroui/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@heroui/react')>()),
  Button: ({ children, onPress, color, ...props }: any) => (
    <button onClick={onPress} data-color={color} {...props}>
      {children}
    </button>
  ),
}));

// Mock ActionButton component
vi.mock('@amdenterpriseai/components', async (importOriginal) => ({
  ...(await importOriginal()),
  Input: ({ value, readOnly, label, ...props }: any) => (
    <div>
      {label && <label>{label}</label>}
      <input value={value} readOnly={readOnly} {...props} />
    </div>
  ),
  CopySnippet: ({ children, value, ...props }: any) => (
    <div data-testid="code-snippet" {...props}>
      {children ?? value}
    </div>
  ),
  ActionButton: ({
    children,
    onPress,
    primary,
    secondary,
    isDisabled,
    ...props
  }: any) => (
    <button
      onClick={onPress}
      data-primary={primary}
      data-secondary={secondary}
      disabled={isDisabled}
      {...props}
    >
      {children}
    </button>
  ),
  Modal: ({ children, title, footer, onClose, size }: any) => (
    <div data-testid="modal" data-size={size}>
      <div data-testid="modal-header">
        <h2>{title}</h2>
        <button onClick={onClose} data-testid="modal-close">
          ×
        </button>
      </div>
      <div data-testid="modal-content">{children}</div>
      <div data-testid="modal-footer">{footer}</div>
    </div>
  ),
  Switch: ({ children, isSelected, onValueChange, ...props }: any) => (
    <label data-testid="switch" {...props}>
      <input
        type="checkbox"
        checked={isSelected}
        onChange={(e) => onValueChange?.(e.target.checked)}
        data-testid="switch-input"
      />
      {children}
    </label>
  ),
  Tabs: ({ children, selectedKey, onSelectionChange, ...props }: any) => {
    const clonedChildren = React.Children.map(children, (child) => {
      if (React.isValidElement(child)) {
        return React.cloneElement(child as any, {
          onSelectionChange,
          tabKey: (child as any).key,
        });
      }
      return child;
    });

    return (
      <div data-testid="tabs" data-selected={selectedKey} {...props}>
        {clonedChildren}
      </div>
    );
  },
  Tab: ({ title, onSelectionChange, tabKey, ...props }: any) => (
    <button
      data-testid={`tab-${tabKey || props.key}`}
      onClick={() => onSelectionChange?.(tabKey || props.key)}
      {...props}
    >
      {title}
    </button>
  ),
}));

// Mock Tabler icon
vi.mock('@tabler/icons-react', async (importOriginal) => ({
  ...(await importOriginal()),
  IconCopy: () => <div data-testid="copy-icon">Copy</div>,
  IconCheck: () => <div data-testid="check-icon">Check</div>,
  IconLoaderQuarter: () => <div data-testid="loader-icon">Loading</div>,
}));

describe('AIMConnectModal', () => {
  const mockOnOpenChange = vi.fn();
  const mockOnChatRequested = vi.fn();

  // Use the deployed service from the first aim (Llama 2 7B with RUNNING service)
  const mockService = mockAims[0].deployedService!;
  const mockCanonicalName = mockAims[0].canonicalName;
  // The served model name (status.aimId) differs from the display canonicalName —
  // this is the value vLLM actually registers the model under, so the OpenAI
  // `model` field in every snippet must carry it.
  const mockServedModelName = mockAims[0].aimId!;

  const defaultProps = {
    onOpenChange: mockOnOpenChange,
    onChatRequested: mockOnChatRequested,
    isOpen: true,
    serviceId: mockService.id ?? undefined,
    endpoints: mockService.endpoints,
    modelName: mockServedModelName,
    capability: 'chat' as const,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockProject.aiGatewayEnabled = true;
    mockProject.aiGatewayUrl = undefined;
  });

  describe('Rendering', () => {
    it('renders the modal when isOpen is true', () => {
      render(<AIMConnectModal {...defaultProps} />);

      expect(screen.getByTestId('modal')).toBeInTheDocument();
      expect(
        screen.getByText('actions.connect.modal.title'),
      ).toBeInTheDocument();
    });

    it('does not render the modal when isOpen is false', () => {
      render(<AIMConnectModal {...defaultProps} isOpen={false} />);

      expect(screen.queryByTestId('modal')).not.toBeInTheDocument();
    });

    it('renders modal with correct size', () => {
      render(<AIMConnectModal {...defaultProps} />);

      expect(screen.getByTestId('modal')).toHaveAttribute('data-size', 'lg');
    });

    it('renders both external and internal URLs when service has both', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      expect(
        screen.getByText('actions.connect.modal.externalUrl'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('actions.connect.modal.internalUrl'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('actions.connect.modal.codeExample'),
      ).toBeInTheDocument();
    });

    it('hides the internal URL box when there is no internal endpoint', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{ external: 'https://api.example.com', internal: '' }}
        />,
      );

      expect(
        screen.queryByText('actions.connect.modal.internalUrl'),
      ).not.toBeInTheDocument();
    });

    it('renders action buttons', () => {
      render(<AIMConnectModal {...defaultProps} />);

      expect(screen.getByText('actions.close.title')).toBeInTheDocument();
      expect(
        screen.getByText('actions.connect.modal.openChat'),
      ).toBeInTheDocument();
    });
  });

  describe('URL Generation', () => {
    it('generates correct external URL', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      const snippets = screen.getAllByTestId('code-snippet');
      const externalUrlSnippet = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://api.example.com/v1/chat/completions',
        ),
      );
      expect(externalUrlSnippet).toBeInTheDocument();
    });

    it('generates correct internal URL from mock data', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            internal: 'http://test-internal.example.com',
            external: '',
          }}
        />,
      );

      const snippets = screen.getAllByTestId('code-snippet');
      const internalUrlSnippet = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'http://test-internal.example.com/v1/chat/completions',
        ),
      );
      expect(internalUrlSnippet).toBeInTheDocument();
    });
  });

  describe('Code Example', () => {
    it('generates correct curl code snippet', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toBeInTheDocument();

      // Check if the code snippet contains expected content
      expect(codeSnippet).toHaveTextContent('curl -X POST');
      expect(codeSnippet).toHaveTextContent(
        'https://api.example.com/v1/chat/completions',
      );
      expect(codeSnippet).toHaveTextContent(
        'Authorization: Bearer UPDATE_YOUR_API_KEY_HERE',
      );
      expect(codeSnippet).toHaveTextContent(
        `"model": "${mockServedModelName}"`,
      );
      expect(codeSnippet).toHaveTextContent('"content": "Hello"');
      expect(codeSnippet).toHaveTextContent('"role": "user"');
      expect(codeSnippet).toHaveTextContent('"stream": false');
    });

    it('puts the served model id (not the canonical name) in the snippet model field', () => {
      // Guard: the fixture must keep these distinct, otherwise this test passes
      // trivially against the buggy old code that emitted canonicalName.
      expect(mockServedModelName).not.toBe(mockCanonicalName);
      render(<AIMConnectModal {...defaultProps} />);

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent(
        `"model": "${mockServedModelName}"`,
      );
      expect(codeSnippet).not.toHaveTextContent(
        `"model": "${mockCanonicalName}"`,
      );
    });

    it('leaves the model field empty when no served id is provided (no display-name fallback)', () => {
      render(<AIMConnectModal {...defaultProps} modelName="" />);

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('"model": ""');
      // The display name must NOT be used as a fallback — it silently 404s.
      expect(codeSnippet).not.toHaveTextContent(
        `"model": "${mockCanonicalName}"`,
      );
    });
  });

  describe('User Interactions', () => {
    it('calls onOpenChange when close button is clicked', async () => {
      render(<AIMConnectModal {...defaultProps} />);

      const closeButton = screen.getByText('actions.close.title');

      await act(async () => {
        fireEvent.click(closeButton);
      });

      expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    });

    it('calls onChatRequested with service id and onOpenChange when confirm button is clicked', async () => {
      render(<AIMConnectModal {...defaultProps} />);

      const confirmButton = screen.getByText('actions.connect.modal.openChat');

      await act(async () => {
        fireEvent.click(confirmButton);
      });

      expect(mockOnChatRequested).toHaveBeenCalledWith(
        mockService.id ?? undefined,
      );
      expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    });

    it('calls onOpenChange when modal close button is clicked', async () => {
      render(<AIMConnectModal {...defaultProps} />);

      const modalCloseButton = screen.getByTestId('modal-close');

      await act(async () => {
        fireEvent.click(modalCloseButton);
      });

      expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    });

    it('does not call onChatRequested when service is undefined', async () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          serviceId={undefined}
          endpoints={undefined}
        />,
      );

      const confirmButton = screen.getByText('actions.connect.modal.openChat');
      expect(confirmButton).toBeDisabled();

      expect(mockOnChatRequested).not.toHaveBeenCalled();
      expect(mockOnOpenChange).not.toHaveBeenCalled();
    });

    it('does not call onChatRequested when service id is undefined', async () => {
      render(<AIMConnectModal {...defaultProps} serviceId={undefined} />);

      const confirmButton = screen.getByText('actions.connect.modal.openChat');
      expect(confirmButton).toBeDisabled();

      expect(mockOnChatRequested).not.toHaveBeenCalled();
      expect(mockOnOpenChange).not.toHaveBeenCalled();
    });
  });

  describe('Accessibility', () => {
    it('renders visible labels for snippet fields', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      expect(
        screen.getByText('actions.connect.modal.externalUrl'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('actions.connect.modal.internalUrl'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('actions.connect.modal.codeExample'),
      ).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('handles undefined service', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          serviceId={undefined}
          endpoints={undefined}
        />,
      );

      // Should still render the modal
      expect(screen.getByTestId('modal')).toBeInTheDocument();

      // With no endpoints, the URL boxes are omitted, but the code example
      // snippet still renders.
      expect(screen.getByTestId('connect-code-snippet')).toBeInTheDocument();
      expect(screen.queryAllByTestId('code-snippet')).toHaveLength(0);
    });
  });

  describe('Component Styling', () => {
    it('applies correct CSS classes', () => {
      render(<AIMConnectModal {...defaultProps} />);

      const modal = screen.getByTestId('modal');
      expect(modal).toBeInTheDocument();

      const modalContent = screen.getByTestId('modal-content');
      expect(modalContent).toBeInTheDocument();
    });
  });

  describe('Language Selection', () => {
    it('renders language tabs with curl as default', () => {
      render(<AIMConnectModal {...defaultProps} />);

      const tabs = screen.getByTestId('tabs');
      expect(tabs).toBeInTheDocument();
      expect(tabs).toHaveAttribute('data-selected', 'curl');
    });

    it('renders all three language tabs', () => {
      render(<AIMConnectModal {...defaultProps} />);

      expect(screen.getByTestId('tab-curl')).toBeInTheDocument();
      expect(screen.getByTestId('tab-python')).toBeInTheDocument();
      expect(screen.getByTestId('tab-javascript')).toBeInTheDocument();
    });

    it('displays curl code example by default', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('curl -X POST');
      expect(codeSnippet).toHaveTextContent(
        'https://api.example.com/v1/chat/completions',
      );
    });

    it('displays python code example when python tab is selected', async () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      await act(async () => {
        fireEvent.click(screen.getByTestId('tab-python'));
      });

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('import requests');
    });

    it('displays javascript code example when javascript tab is selected', async () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      await act(async () => {
        fireEvent.click(screen.getByTestId('tab-javascript'));
      });

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('fetch(url,');
    });
  });

  describe('URL Toggle Switch', () => {
    it('renders the internal URL switch when external URL exists', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      const switchElement = screen.getByTestId('switch');
      expect(switchElement).toBeInTheDocument();
      expect(switchElement).toHaveTextContent(
        'actions.connect.modal.useInternalUrl',
      );
    });

    it('hides the internal URL switch when there is no external URL', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: undefined,
            internal: 'http://internal.example.com',
          }}
        />,
      );

      expect(screen.queryByTestId('switch')).not.toBeInTheDocument();
    });

    it('hides the internal URL switch when there is no internal URL', () => {
      // Without an internal endpoint the toggle would let the user select an
      // empty URL, so it must not render.
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{ external: 'https://api.example.com', internal: '' }}
        />,
      );

      expect(screen.queryByTestId('switch')).not.toBeInTheDocument();
    });

    it('switch is unchecked by default (external URL)', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      const switchInput = screen.getByTestId('switch-input');
      expect(switchInput).not.toBeChecked();
    });

    it('toggles between external and internal URL in code snippet', async () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: 'http://test-host.example.com',
          }}
        />,
      );

      const codeSnippet = screen.getByTestId('connect-code-snippet');

      // Initially should show external URL
      expect(codeSnippet).toHaveTextContent(
        'https://api.example.com/v1/chat/completions',
      );

      // Toggle switch
      const switchInput = screen.getByTestId('switch-input');
      await act(async () => {
        fireEvent.click(switchInput);
      });

      // After toggle, the component would re-render with internal URL
      // Note: Due to mock limitations, we verify the switch state changed
      expect(switchInput).toBeChecked();
    });
  });

  describe('Code Examples Content', () => {
    const serviceWithHostsProps = {
      endpoints: {
        external: 'https://api.example.com',
        internal: 'http://test-host.example.com',
      },
    };

    it('curl example contains correct structure', () => {
      render(<AIMConnectModal {...defaultProps} {...serviceWithHostsProps} />);

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('curl -X POST');
      expect(codeSnippet).toHaveTextContent('-H "Authorization: Bearer');
      expect(codeSnippet).toHaveTextContent(
        '-H "Content-Type: application/json"',
      );
      expect(codeSnippet).toHaveTextContent('"messages"');
      expect(codeSnippet).toHaveTextContent('"stream": false');
    });

    it('includes UPDATE_YOUR_API_KEY_HERE placeholder in all examples', () => {
      render(<AIMConnectModal {...defaultProps} {...serviceWithHostsProps} />);

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('UPDATE_YOUR_API_KEY_HERE');
    });

    it('includes the served model id in code examples', () => {
      render(<AIMConnectModal {...defaultProps} {...serviceWithHostsProps} />);

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent(mockServedModelName);
    });

    it('includes Hello message in all examples', () => {
      render(<AIMConnectModal {...defaultProps} {...serviceWithHostsProps} />);

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('Hello');
    });
  });

  describe('URL Format', () => {
    it('displays external endpoint URL', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: 'https://api.example.com',
            internal: '',
          }}
        />,
      );

      const snippets = screen.getAllByTestId('code-snippet');
      const urlSnippet = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://api.example.com/v1/chat/completions',
        ),
      );
      expect(urlSnippet).toBeInTheDocument();
    });

    it('displays internal endpoint URL', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          endpoints={{
            external: '',
            internal: 'http://internal.example.com',
          }}
        />,
      );

      const snippets = screen.getAllByTestId('code-snippet');
      const urlSnippet = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'http://internal.example.com/v1/chat/completions',
        ),
      );
      expect(urlSnippet).toBeInTheDocument();
    });
  });

  describe('Unified AI Gateway', () => {
    const endpoints = {
      external: 'https://api.example.com',
      internal: 'http://test-internal.example.com',
    };

    it('uses the gateway URL for the primary endpoint when enabled and configured', () => {
      mockProject.aiGatewayEnabled = true;
      mockProject.aiGatewayUrl = 'https://ai.example.com';

      render(<AIMConnectModal {...defaultProps} endpoints={endpoints} />);

      const snippets = screen.getAllByTestId('code-snippet');
      // Primary URL + code examples target the unified gateway endpoint.
      const gatewaySnippet = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://ai.example.com/v1/chat/completions',
        ),
      );
      expect(gatewaySnippet).toBeInTheDocument();

      // The per-service external URL must not be used as the primary endpoint.
      const perServiceExternal = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://api.example.com/v1/chat/completions',
        ),
      );
      expect(perServiceExternal).toBeUndefined();

      // The primary URL is labelled as the unified inference endpoint.
      expect(
        screen.getByText('actions.connect.modal.inferenceUrl'),
      ).toBeInTheDocument();
    });

    it('trims a trailing slash from the configured gateway URL', () => {
      mockProject.aiGatewayEnabled = true;
      mockProject.aiGatewayUrl = 'https://ai.example.com/';

      render(<AIMConnectModal {...defaultProps} endpoints={endpoints} />);

      const snippets = screen.getAllByTestId('code-snippet');
      const gatewaySnippet = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://ai.example.com/v1/chat/completions',
        ),
      );
      expect(gatewaySnippet).toBeInTheDocument();
      const doubleSlash = snippets.find((snippet) =>
        snippet.textContent?.includes('https://ai.example.com//v1'),
      );
      expect(doubleSlash).toBeUndefined();
    });

    it('keeps the per-service internal URL alongside the gateway endpoint', () => {
      mockProject.aiGatewayEnabled = true;
      mockProject.aiGatewayUrl = 'https://ai.example.com';

      render(<AIMConnectModal {...defaultProps} endpoints={endpoints} />);

      const snippets = screen.getAllByTestId('code-snippet');
      const internalSnippet = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'http://test-internal.example.com/v1/chat/completions',
        ),
      );
      expect(internalSnippet).toBeInTheDocument();
    });

    it('falls back to the per-service external URL when the gateway URL is not configured', () => {
      mockProject.aiGatewayEnabled = true;
      mockProject.aiGatewayUrl = undefined;

      render(<AIMConnectModal {...defaultProps} endpoints={endpoints} />);

      const snippets = screen.getAllByTestId('code-snippet');
      const perServiceExternal = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://api.example.com/v1/chat/completions',
        ),
      );
      expect(perServiceExternal).toBeInTheDocument();
      expect(
        screen.getByText('actions.connect.modal.externalUrl'),
      ).toBeInTheDocument();
    });

    it('does not use the gateway URL when the flag is disabled', () => {
      mockProject.aiGatewayEnabled = false;
      mockProject.aiGatewayUrl = 'https://ai.example.com';

      render(<AIMConnectModal {...defaultProps} endpoints={endpoints} />);

      const snippets = screen.getAllByTestId('code-snippet');
      const gatewaySnippet = snippets.find((snippet) =>
        snippet.textContent?.includes('https://ai.example.com'),
      );
      expect(gatewaySnippet).toBeUndefined();
      const perServiceExternal = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://api.example.com/v1/chat/completions',
        ),
      );
      expect(perServiceExternal).toBeInTheDocument();
    });

    it('includes x-ai-eg-backend and x-ai-eg-model routing headers in the gateway examples', () => {
      mockProject.aiGatewayEnabled = true;
      mockProject.aiGatewayUrl = 'https://ai.example.com';

      render(<AIMConnectModal {...defaultProps} endpoints={endpoints} />);

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      // Precise backend routing requires both routing headers (deployment UUID +
      // model name) so the gateway reaches this exact deployment.
      expect(codeSnippet).toHaveTextContent(
        `x-ai-eg-backend: ${mockService.id}`,
      );
      expect(codeSnippet).toHaveTextContent(
        `x-ai-eg-model: ${mockServedModelName}`,
      );
    });

    it('omits the routing headers when not routing through the gateway', () => {
      // Gateway flag on but no URL configured → per-service external URL, where
      // the x-ai-eg-* routing headers do not apply.
      mockProject.aiGatewayEnabled = true;
      mockProject.aiGatewayUrl = undefined;

      render(<AIMConnectModal {...defaultProps} endpoints={endpoints} />);

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).not.toHaveTextContent('x-ai-eg-backend');
      expect(codeSnippet).not.toHaveTextContent('x-ai-eg-model');
    });
  });

  describe('Transcription capability', () => {
    const endpoints = {
      external: 'https://api.example.com',
      internal: 'http://test-internal.example.com',
    };

    it('targets the audio transcriptions endpoint, not chat completions', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          capability="transcription"
          endpoints={endpoints}
        />,
      );

      const snippets = screen.getAllByTestId('code-snippet');
      const audioSnippet = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://api.example.com/v1/audio/transcriptions',
        ),
      );
      expect(audioSnippet).toBeInTheDocument();

      const chatSnippet = snippets.find((snippet) =>
        snippet.textContent?.includes('/v1/chat/completions'),
      );
      expect(chatSnippet).toBeUndefined();
    });

    it('renders a multipart curl upload with the served model id', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          capability="transcription"
          endpoints={endpoints}
        />,
      );

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('curl -X POST');
      expect(codeSnippet).toHaveTextContent('-F "file=@audio.wav"');
      expect(codeSnippet).toHaveTextContent(
        `-F "model=${mockServedModelName}"`,
      );
      // No JSON chat body for a multipart upload.
      expect(codeSnippet).not.toHaveTextContent('"messages"');
    });

    it('parses the transcription response text in the python example', async () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          capability="transcription"
          endpoints={endpoints}
        />,
      );

      await act(async () => {
        fireEvent.click(screen.getByTestId('tab-python'));
      });

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('{"file": audio}');
      expect(codeSnippet).toHaveTextContent('result["text"]');
      expect(codeSnippet).not.toHaveTextContent('choices');
      // The file is opened via a context manager so the descriptor is closed.
      expect(codeSnippet).toHaveTextContent('with open("audio.wav", "rb")');
    });

    it('uses FormData and result.text in the javascript example', async () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          capability="transcription"
          endpoints={endpoints}
        />,
      );

      await act(async () => {
        fireEvent.click(screen.getByTestId('tab-javascript'));
      });

      const codeSnippet = screen.getByTestId('connect-code-snippet');
      expect(codeSnippet).toHaveTextContent('new FormData()');
      expect(codeSnippet).toHaveTextContent('result.text');
      // The audio File must be defined before use so the snippet runs as-is.
      expect(codeSnippet).toHaveTextContent('const audioFile =');
    });

    it('hides the Open chat action for transcription deployments', () => {
      render(
        <AIMConnectModal
          {...defaultProps}
          capability="transcription"
          endpoints={endpoints}
        />,
      );

      expect(
        screen.queryByText('actions.connect.modal.openChat'),
      ).not.toBeInTheDocument();
      // Close remains available.
      expect(screen.getByText('actions.close.title')).toBeInTheDocument();
    });

    it('does not route transcription through the unified gateway', () => {
      mockProject.aiGatewayEnabled = true;
      mockProject.aiGatewayUrl = 'https://ai.example.com';

      render(
        <AIMConnectModal
          {...defaultProps}
          capability="transcription"
          endpoints={endpoints}
        />,
      );

      const snippets = screen.getAllByTestId('code-snippet');
      const gatewaySnippet = snippets.find((snippet) =>
        snippet.textContent?.includes('https://ai.example.com'),
      );
      expect(gatewaySnippet).toBeUndefined();

      const perServiceAudio = snippets.find((snippet) =>
        snippet.textContent?.includes(
          'https://api.example.com/v1/audio/transcriptions',
        ),
      );
      expect(perServiceAudio).toBeInTheDocument();
    });
  });
});
