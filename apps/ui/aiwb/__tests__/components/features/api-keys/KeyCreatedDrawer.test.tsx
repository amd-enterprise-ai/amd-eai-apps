// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { KeyCreatedDrawer } from '@/components/features/api-keys/KeyCreatedDrawer';

import { generateMockFullApiKey } from '@/__mocks__/utils/api-keys-mock';

import '@testing-library/jest-dom';

// Mock clipboard API
const mockWriteText = vi.fn();
Object.assign(navigator, {
  clipboard: {
    writeText: mockWriteText,
  },
});

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@amdenterpriseai/hooks', () => ({
  useSystemToast: () => ({
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

const mockApiKey = generateMockFullApiKey({
  displayName: 'test-api-key',
  truncatedKey: 'amd_aim_api_key_••••••••1234',
  ttl: '24h',
  fullKey: 'amd_aim_api_key_3bb1211ab8c5fee8fc88bbaf89383f08',
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('KeyCreatedDrawer', () => {
  it('renders the drawer with API key information', () => {
    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={true}
          apiKey={mockApiKey}
          onClose={vi.fn()}
        />,
      );
    });

    expect(screen.getByText('form.keyCreated.title')).toBeInTheDocument();
    expect(screen.getByText('form.keyCreated.description')).toBeInTheDocument();
    expect(screen.getByText('form.keyCreated.warning')).toBeInTheDocument();
  });

  it('displays the API key name in a read-only input', () => {
    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={true}
          apiKey={mockApiKey}
          onClose={vi.fn()}
        />,
      );
    });

    const nameInput = screen.getByDisplayValue('test-api-key');
    expect(nameInput).toBeInTheDocument();
    expect(nameInput).toHaveAttribute('readonly');
  });

  it('displays the full API key in a read-only input', () => {
    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={true}
          apiKey={mockApiKey}
          onClose={vi.fn()}
        />,
      );
    });

    const keyInput = screen.getByDisplayValue(
      'amd_aim_api_key_3bb1211ab8c5fee8fc88bbaf89383f08',
    );
    expect(keyInput).toBeInTheDocument();
    expect(keyInput).toHaveAttribute('readonly');
  });

  it('displays warning section with danger styling', () => {
    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={true}
          apiKey={mockApiKey}
          onClose={vi.fn()}
        />,
      );
    });

    const warningText = screen.getByText('form.keyCreated.warning');
    expect(warningText).toBeInTheDocument();

    // HeroUI v3 Alert no longer exposes role="alert"; assert warning is inside the alert root.
    const alertElement = warningText.closest('[data-slot="alert-root"]');
    expect(alertElement).toBeInTheDocument();
  });

  it('calls onClose when Done button is clicked', () => {
    const onClose = vi.fn();

    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={true}
          apiKey={mockApiKey}
          onClose={onClose}
        />,
      );
    });

    const doneButton = screen.getByText('form.keyCreated.action.done');
    act(() => {
      fireEvent.click(doneButton);
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not render when apiKey is null', () => {
    const { container } = render(
      <KeyCreatedDrawer isOpen={true} apiKey={null} onClose={vi.fn()} />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('does not render when drawer is closed', () => {
    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={false}
          apiKey={mockApiKey}
          onClose={vi.fn()}
        />,
      );
    });

    expect(screen.queryByText('form.keyCreated.title')).not.toBeInTheDocument();
  });

  it('renders field labels correctly', () => {
    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={true}
          apiKey={mockApiKey}
          onClose={vi.fn()}
        />,
      );
    });

    expect(
      screen.getByText('form.keyCreated.field.name.label'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('form.keyCreated.field.key.label'),
    ).toBeInTheDocument();
  });

  it('renders Alert component with icon in warning section', () => {
    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={true}
          apiKey={mockApiKey}
          onClose={vi.fn()}
        />,
      );
    });

    const alertElement = screen
      .getByText('form.keyCreated.warning')
      .closest('[data-slot="alert-root"]');
    const icon = alertElement?.querySelector('svg');

    expect(alertElement).toBeInTheDocument();
    expect(icon).toBeInTheDocument();
  });

  it('copies API key to clipboard when copy button is clicked', async () => {
    mockWriteText.mockResolvedValue(undefined);

    act(() => {
      render(
        <KeyCreatedDrawer
          isOpen={true}
          apiKey={mockApiKey}
          onClose={vi.fn()}
        />,
      );
    });

    const copyButton = screen.getByRole('button', {
      name: 'actions.copy.title',
    });

    await act(async () => {
      fireEvent.click(copyButton);
    });

    expect(mockWriteText).toHaveBeenCalledWith(
      'amd_aim_api_key_3bb1211ab8c5fee8fc88bbaf89383f08',
    );
  });
});
