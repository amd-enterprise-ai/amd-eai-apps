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

import router from 'next/router';

import { deleteUser as deleteUserAPI } from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { DeleteUser } from '@/components/features/user';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock } from 'vitest';

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: {
      user: {
        id: 'test',
        email: 'testing@test.com',
        roles: [],
      },
    },
    update: vi.fn(),
  }),
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('@/services/app', () => ({
  deleteUser: vi.fn(),
}));

const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();
vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => {
    const toast = vi.fn() as any;
    toast.success = toastSuccessMock;
    toast.error = toastErrorMock;
    return { toast };
  },
}));

describe('DeleteUser', () => {
  beforeEach(() => {
    toastSuccessMock.mockClear();
    toastErrorMock.mockClear();
  });
  const setup = async () => {
    return render(<DeleteUser id="1" email="test@test.com" />, { wrapper });
  };

  it('should render delete button', () => {
    setup();
    expect(
      screen.getByRole('button', { name: 'detail.delete.action.label' }),
    ).toBeInTheDocument();
  });

  it('should open confirmation modal on delete button click', () => {
    setup();
    fireEvent.click(
      screen.getByRole('button', { name: 'detail.delete.action.label' }),
    );
    expect(
      screen.getByText('detail.delete.confirmation.title'),
    ).toBeInTheDocument();
  });

  it('should call deleteUserAPI and handle success', async () => {
    (deleteUserAPI as Mock).mockResolvedValueOnce({});

    const mockRouterPush = vi.fn();
    vi.spyOn(router, 'push').mockImplementation(mockRouterPush);

    await act(setup);

    await fireEvent.click(
      screen.getByRole('button', { name: 'detail.delete.action.label' }),
    );
    await fireEvent.click(
      screen.getByRole('button', { name: 'actions.confirm.title' }),
    );

    await waitFor(() => {
      expect(deleteUserAPI).toHaveBeenCalledWith('1', expect.any(Object));
      expect(mockRouterPush).toHaveBeenCalledWith('/users');
      expect(toastSuccessMock).toHaveBeenCalledWith(
        'detail.delete.notification.success',
      );
    });
  });

  it('should handle error', async () => {
    const mockError = new APIRequestError('test error', 400);
    (deleteUserAPI as Mock).mockRejectedValueOnce(mockError);
    await act(setup);
    await fireEvent.click(
      screen.getByRole('button', { name: 'detail.delete.action.label' }),
    );
    await fireEvent.click(
      screen.getByRole('button', { name: 'actions.confirm.title' }),
    );

    await waitFor(() => {
      expect(deleteUserAPI).toHaveBeenCalledWith('1', expect.any(Object));
      expect(toastErrorMock).toHaveBeenCalledWith(
        'detail.delete.notification.error',
        mockError,
      );
    });
  });

  it('should disable the delete button if the user is the currently logged in user', async () => {
    await act(() => {
      return render(<DeleteUser id="1" email="testing@test.com" />, {
        wrapper,
      });
    });
    // HeroUI v3 wraps a disabled tooltip trigger in an extra focusable node, so
    // the accessible name now matches more than one element. Assert on the real
    // <button> element specifically.
    const deleteButton = screen
      .getAllByRole('button', { name: 'detail.delete.action.label' })
      .find((el): el is HTMLButtonElement => el.tagName === 'BUTTON');
    expect(deleteButton).toBeDefined();
    expect(deleteButton?.disabled).toBeTruthy();
  });
});
