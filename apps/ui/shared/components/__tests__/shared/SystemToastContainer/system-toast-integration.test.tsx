// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect } from 'react';
import { toast, toastQueue } from '@heroui/react';

import { SystemToastContainer } from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';

function ToastTrigger({ message }: { message: string }) {
  const { toast: showToast } = useSystemToast();

  return (
    <button type="button" onClick={() => showToast.success(message)}>
      Show toast
    </button>
  );
}

describe('SystemToast integration', () => {
  beforeEach(() => {
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
  });

  afterEach(() => {
    toast.clear();
  });

  it('uses the same toastQueue singleton that Toast.Provider subscribes to', () => {
    expect(toast.getQueue()).toBe(toastQueue.getQueue());
  });

  it('renders a success toast from useSystemToast through SystemToastContainer', async () => {
    const user = userEvent.setup();
    const message = 'Secret added successfully.';

    render(
      <>
        <SystemToastContainer />
        <ToastTrigger message={message} />
      </>,
    );

    await user.click(screen.getByRole('button', { name: 'Show toast' }));

    await waitFor(() => {
      expect(screen.getByText(message)).toBeInTheDocument();
    });
  });

  it('renders an error toast from useSystemToast through SystemToastContainer', async () => {
    const user = userEvent.setup();
    const message = 'Failed to add secret.';

    function ErrorToastTrigger() {
      const { toast: showToast } = useSystemToast();

      return (
        <button type="button" onClick={() => showToast.error(message)}>
          Show error toast
        </button>
      );
    }

    render(
      <>
        <SystemToastContainer />
        <ErrorToastTrigger />
      </>,
    );

    await user.click(screen.getByRole('button', { name: 'Show error toast' }));

    await waitFor(() => {
      expect(screen.getByText(message)).toBeInTheDocument();
    });
  });

  it('renders a success toast when triggered on mount', async () => {
    const message = 'Dataset successfully uploaded';

    function ImmediateToastTrigger() {
      const { toast: showToast } = useSystemToast();

      useEffect(() => {
        showToast.success(message);
      }, [showToast]);

      return null;
    }

    render(
      <>
        <SystemToastContainer />
        <ImmediateToastTrigger />
      </>,
    );

    await waitFor(() => {
      expect(screen.getByText(message)).toBeInTheDocument();
    });
  });
});
