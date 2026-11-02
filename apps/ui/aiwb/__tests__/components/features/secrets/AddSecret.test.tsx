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
import { Mock, vi } from 'vitest';

import { AddSecret } from '@/components/features/secrets/AddSecret';
import { createProjectSecret } from '@/lib/app/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';

import wrapper from '@/__tests__/ProviderWrapper';

const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
};

vi.mock('@amdenterpriseai/hooks', () => ({
  useSystemToast: () => ({ toast: mockToast }),
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/lib/app/secrets', () => ({
  createProjectSecret: vi.fn(),
}));

const mockCreateProjectSecret = vi.mocked(createProjectSecret);

async function selectUseCase(useCase: SecretUseCase): Promise<void> {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /Use Case/i }));
  });
  await act(async () => {
    fireEvent.click(screen.getByRole('option', { name: `useCase.${useCase}` }));
  });
}

async function submitForm(): Promise<void> {
  await act(async () => {
    fireEvent.click(
      screen.getByRole('button', { name: 'form.add.action.add' }),
    );
  });
}

describe('AddSecret S3 flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (mockCreateProjectSecret as Mock).mockResolvedValue({});
  });

  it('shows S3 in use case options', async () => {
    await act(async () => {
      render(
        <AddSecret
          isOpen
          namespace="workbench"
          secrets={[]}
          onClose={vi.fn()}
        />,
        { wrapper },
      );
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Use Case/i }));
    });

    expect(
      screen.getByRole('option', { name: 'useCase.S3' }),
    ).toBeInTheDocument();
  });

  it('submits S3 secret with only access and secret keys', async () => {
    const onClose = vi.fn();
    await act(async () => {
      render(
        <AddSecret
          isOpen
          namespace="workbench"
          secrets={[]}
          onClose={onClose}
        />,
        { wrapper },
      );
    });

    fireEvent.change(screen.getByRole('textbox', { name: 'Display Name' }), {
      target: { value: 'my-s3-secret' },
    });
    await selectUseCase(SecretUseCase.S3);
    fireEvent.change(
      screen.getByRole('textbox', {
        name: 'form.add.field.s3.accessKeyIdLabel',
      }),
      { target: { value: 'AKIAEXAMPLE' } },
    );
    fireEvent.change(
      screen.getByLabelText('form.add.field.s3.secretAccessKeyLabel'),
      { target: { value: 'secret-value' } },
    );
    await submitForm();

    await waitFor(() => {
      expect(mockCreateProjectSecret).toHaveBeenCalledWith('workbench', {
        displayName: 'my-s3-secret',
        useCase: SecretUseCase.S3,
        data: {
          accessKeyId: Buffer.from('AKIAEXAMPLE', 'utf-8').toString('base64'),
          secretAccessKey: Buffer.from('secret-value', 'utf-8').toString(
            'base64',
          ),
        },
      });
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('blocks S3 submit when secret access key is missing', async () => {
    await act(async () => {
      render(
        <AddSecret
          isOpen
          namespace="workbench"
          secrets={[]}
          onClose={vi.fn()}
        />,
        { wrapper },
      );
    });

    fireEvent.change(screen.getByRole('textbox', { name: 'Display Name' }), {
      target: { value: 'my-s3-secret-invalid' },
    });
    await selectUseCase(SecretUseCase.S3);
    fireEvent.change(
      screen.getByRole('textbox', {
        name: 'form.add.field.s3.accessKeyIdLabel',
      }),
      { target: { value: 'AKIAEXAMPLE' } },
    );

    await submitForm();

    await waitFor(() => {
      expect(
        screen.getByText('form.add.validation.s3SecretKeyRequired'),
      ).toBeInTheDocument();
    });
    expect(mockCreateProjectSecret).not.toHaveBeenCalled();
  });
});
