// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

import { SystemToastContainer } from '@amdenterpriseai/components';

vi.mock('@heroui/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@heroui/react')>();

  return {
    ...actual,
    toastQueue: { getQueue: vi.fn() },
    Toast: {
      ...actual.Toast,
      Provider: ({
        placement,
        width,
        queue,
      }: {
        placement: string;
        width: number;
        queue: unknown;
      }) => (
        <div
          data-testid="toast-provider"
          data-placement={placement}
          data-width={width}
          data-has-queue={queue ? 'true' : 'false'}
        />
      ),
    },
  };
});

describe('SystemToastContainer', () => {
  it('renders Toast.Provider with correct placement and width', () => {
    render(<SystemToastContainer />);
    const toastProvider = screen.getByTestId('toast-provider');
    expect(toastProvider).toBeInTheDocument();
    expect(toastProvider).toHaveAttribute('data-placement', 'top end');
    expect(toastProvider).toHaveAttribute('data-width', '460');
    expect(toastProvider).toHaveAttribute('data-has-queue', 'true');
  });
});
