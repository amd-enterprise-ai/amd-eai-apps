// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, waitFor } from '@testing-library/react';
import { Mock, vi } from 'vitest';

import { SecretUseCase } from '@amdenterpriseai/types';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { ProjectHuggingFaceTokenSelector } from '@/components/shared/HuggingFaceTokenSelector/ProjectHuggingFaceTokenSelector';
import { createProjectSecret, fetchProjectSecrets } from '@/lib/app/secrets';
import wrapper from '@/__tests__/ProviderWrapper';

vi.mock('@/lib/app/secrets', () => ({
  fetchProjectSecrets: vi.fn(),
  createProjectSecret: vi.fn(),
}));

/**
 * Stand-in for the local `HuggingFaceTokenSelector`. It surfaces the props
 * that the project-scoped wrapper threads through so the test can drive
 * `onCreateToken` directly without needing the real dropdown/dialog UI.
 */
let capturedProps: {
  existingTokens?: Array<{ displayName: string }>;
  onCreateToken?: (input: {
    displayName: string;
    token: string;
  }) => Promise<unknown>;
  isDisabled?: boolean;
} = {};

vi.mock(
  '@/components/shared/HuggingFaceTokenSelector/HuggingFaceTokenSelector',
  () => ({
    HuggingFaceTokenSelector: (props: {
      existingTokens: Array<{ displayName: string }>;
      onCreateToken: (input: {
        displayName: string;
        token: string;
      }) => Promise<unknown>;
      isDisabled?: boolean;
    }) => {
      capturedProps = props;
      return (
        <div
          data-testid="hf-token-selector-stub"
          data-disabled={props.isDisabled ? 'true' : 'false'}
        >
          {props.existingTokens.map((t) => (
            <span key={t.displayName} data-testid="hf-token-row">
              {t.displayName}
            </span>
          ))}
        </div>
      );
    },
  }),
);

const NAMESPACE = 'demo-project';

const hfSecret = {
  id: 'sec-hf',
  displayName: 'hf-prod',
  metadata: { name: 'hf-prod' },
  useCase: SecretUseCase.HUGGING_FACE,
};
const otherSecret = {
  id: 'sec-img',
  displayName: 'docker-creds',
  metadata: { name: 'docker-creds' },
  useCase: SecretUseCase.IMAGE_PULL_SECRET,
};

const renderSelector = (overrides: Partial<{ value: string | null }> = {}) =>
  render(
    <ProjectHuggingFaceTokenSelector
      namespace={NAMESPACE}
      value={overrides.value ?? null}
      onChange={vi.fn()}
    />,
    { wrapper },
  );

describe('ProjectHuggingFaceTokenSelector', () => {
  beforeEach(() => {
    capturedProps = {};
    vi.resetAllMocks();
  });

  it('filters fetched project secrets down to HuggingFace tokens', async () => {
    (fetchProjectSecrets as Mock).mockResolvedValue({
      data: [hfSecret, otherSecret],
    });

    renderSelector();

    await waitFor(() => {
      expect(fetchProjectSecrets).toHaveBeenCalledWith(NAMESPACE);
    });

    await waitFor(() => {
      const rows = screen.getAllByTestId('hf-token-row');
      expect(rows).toHaveLength(1);
      expect(rows[0]).toHaveTextContent('hf-prod');
    });
  });

  it('skips the secrets query and disables the selector while the namespace is empty', async () => {
    (fetchProjectSecrets as Mock).mockResolvedValue({ data: [] });

    render(
      <ProjectHuggingFaceTokenSelector
        namespace=""
        value={null}
        onChange={vi.fn()}
      />,
      { wrapper },
    );

    expect(fetchProjectSecrets).not.toHaveBeenCalled();
    expect(screen.getByTestId('hf-token-selector-stub')).toHaveAttribute(
      'data-disabled',
      'true',
    );

    await waitFor(() => {
      expect(capturedProps.onCreateToken).toBeTypeOf('function');
    });
    await expect(
      capturedProps.onCreateToken!({ displayName: 'hf-new', token: 'hf_x' }),
    ).rejects.toBeInstanceOf(APIRequestError);
    expect(createProjectSecret).not.toHaveBeenCalled();
  });

  it('propagates a consumer-supplied isDisabled even when the namespace is set', () => {
    (fetchProjectSecrets as Mock).mockResolvedValue({ data: [] });

    render(
      <ProjectHuggingFaceTokenSelector
        namespace={NAMESPACE}
        value={null}
        onChange={vi.fn()}
        isDisabled
      />,
      { wrapper },
    );

    expect(screen.getByTestId('hf-token-selector-stub')).toHaveAttribute(
      'data-disabled',
      'true',
    );
  });

  it('optimistically adds a newly created HuggingFace secret to the token list', async () => {
    (fetchProjectSecrets as Mock).mockResolvedValue({ data: [] });
    (createProjectSecret as Mock).mockResolvedValue({
      displayName: 'hf-new',
      metadata: { name: 'wb-secret-abc12345' },
      useCase: SecretUseCase.HUGGING_FACE,
    });

    renderSelector();

    await waitFor(() => {
      expect(capturedProps.onCreateToken).toBeTypeOf('function');
    });

    const result = await capturedProps.onCreateToken!({
      displayName: 'hf-new',
      token: 'hf_secret_value',
    });
    expect(result).toEqual({ secretName: 'wb-secret-abc12345' });

    expect(createProjectSecret).toHaveBeenCalledTimes(1);
    const [callNamespace, payload] = (createProjectSecret as Mock).mock
      .calls[0];
    expect(callNamespace).toBe(NAMESPACE);
    expect(payload).toMatchObject({ useCase: SecretUseCase.HUGGING_FACE });

    await waitFor(() => {
      const rows = screen.getAllByTestId('hf-token-row');
      expect(rows).toHaveLength(1);
      expect(rows[0]).toHaveTextContent('hf-new');
      expect(fetchProjectSecrets).toHaveBeenCalledTimes(1);
    });
  });

  it('throws an APIRequestError when the created secret has no name', async () => {
    (fetchProjectSecrets as Mock).mockResolvedValue({ data: [] });
    (createProjectSecret as Mock).mockResolvedValue({ metadata: {} });

    renderSelector();

    await waitFor(() => {
      expect(capturedProps.onCreateToken).toBeTypeOf('function');
    });

    await expect(
      capturedProps.onCreateToken!({ displayName: 'broken', token: 'hf_x' }),
    ).rejects.toBeInstanceOf(APIRequestError);
  });
});
