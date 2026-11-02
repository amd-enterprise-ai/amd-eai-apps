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
import { vi } from 'vitest';

import {
  HuggingFaceTokenSelector,
  HuggingFaceTokenSelectorLabels,
  HuggingFaceTokenSelectorProps,
} from '@/components/shared/HuggingFaceTokenSelector/HuggingFaceTokenSelector';

const VALID_HF_TOKEN = 'hf_abcdefghijklmnopqrstuvwxyz123456';

const defaultLabels: HuggingFaceTokenSelectorLabels = {
  selectLabel: 'Hugging Face token',
  selectPlaceholder: 'Select a token',
  addNewItemLabel: 'Add new token',
  dialogTitle: 'Add Hugging Face token',
  dialogNameLabel: 'Name',
  dialogNamePlaceholder: 'my-hf-token',
  dialogTokenLabel: 'Token',
  dialogTokenPlaceholder: 'hf_...',
  dialogCancelLabel: 'Cancel',
  dialogSubmitLabel: 'Add',
  validation: {
    nameRequired: 'Name is required when entering a new token',
    invalidSecretName:
      "The secret name must be lowercase alphanumeric characters, '-' or '.', and must start and end with an alphanumeric character",
    tokenRequired: 'Token is required when entering a new token',
    invalidTokenFormat:
      "Please enter a valid Hugging Face token (starts with 'hf_')",
    duplicateName: 'A secret with this name already exists.',
  },
};

const existingTokens = [
  { name: 'token-1-hf', displayName: 'token-1-hf' },
  { name: 'token-2-hf', displayName: 'token-2-hf' },
];

const renderSelector = (
  overrides: Partial<HuggingFaceTokenSelectorProps> = {},
) => {
  const onChange = vi.fn();
  const onCreateToken = vi.fn(
    async ({ displayName }: { displayName: string }) => ({
      secretName: displayName,
    }),
  );

  render(
    <HuggingFaceTokenSelector
      value={null}
      onChange={onChange}
      existingTokens={existingTokens}
      onCreateToken={onCreateToken}
      labels={defaultLabels}
      {...overrides}
    />,
  );

  return { onChange, onCreateToken };
};

const openDropdown = async () => {
  const trigger = screen.getByRole('button', { name: /Hugging Face token/i });
  await act(async () => {
    fireEvent.click(trigger);
  });
};

const clickAddNew = async () => {
  await waitFor(() => {
    expect(screen.getByTestId('hf-token-selector-add-new')).toBeInTheDocument();
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId('hf-token-selector-add-new'));
  });
  await waitFor(() => {
    expect(screen.getByText('Add Hugging Face token')).toBeInTheDocument();
  });
};

const fillCreateForm = async (name: string, token: string) => {
  fireEvent.change(screen.getByTestId('hf-token-selector-dialog-name'), {
    target: { value: name },
  });
  fireEvent.change(screen.getByTestId('hf-token-selector-dialog-token'), {
    target: { value: token },
  });
};

describe('HuggingFaceTokenSelector', () => {
  // jsdom has no `CSS.supports`; simulate a browser that supports
  // `-webkit-text-security` so the token field's password-manager-prompt
  // avoidance (via PasswordInput's `preventPasswordManagerPrompt`) behaves
  // as it does in Chrome/Safari.
  beforeEach(() => {
    vi.stubGlobal('CSS', {
      ...(globalThis.CSS ?? {}),
      supports: vi.fn().mockReturnValue(true),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the select with the configured label and placeholder', () => {
    renderSelector();
    expect(screen.getAllByText('Hugging Face token').length).toBeGreaterThan(0);
    expect(screen.getByText('Select a token')).toBeInTheDocument();
  });

  it('lists existing tokens and the add-new action in bottom content', async () => {
    renderSelector();
    await openDropdown();

    await waitFor(() => {
      expect(screen.getAllByText('token-1-hf').length).toBeGreaterThan(0);
      expect(screen.getAllByText('token-2-hf').length).toBeGreaterThan(0);
      expect(
        screen.getByTestId('hf-token-selector-add-new'),
      ).toBeInTheDocument();
      expect(screen.getByText('Add new token')).toBeInTheDocument();
    });
  });

  it('opens the add-new popover when the bottom action is clicked', async () => {
    renderSelector();
    await openDropdown();
    await clickAddNew();

    expect(screen.getByText('Add Hugging Face token')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('hf-token-selector-dialog-name')).toHaveFocus();
    });
  });

  it('never renders the token field as a native password input, so the browser cannot offer to save it', async () => {
    renderSelector();
    await openDropdown();
    await clickAddNew();

    const tokenInput = screen.getByTestId('hf-token-selector-dialog-token');
    expect(tokenInput).not.toHaveAttribute('type', 'password');
    expect(tokenInput).toHaveAttribute('type', 'text');
  });

  it('submits a new token, auto-selects it, and closes the popover on success', async () => {
    const onCreateToken = vi.fn(
      async ({ displayName }: { displayName: string }) => ({
        secretName: displayName,
      }),
    );
    const onChange = vi.fn();

    render(
      <HuggingFaceTokenSelector
        value={null}
        onChange={onChange}
        existingTokens={existingTokens}
        onCreateToken={onCreateToken}
        labels={defaultLabels}
      />,
    );

    await openDropdown();
    await clickAddNew();
    await fillCreateForm('my-new-token', VALID_HF_TOKEN);

    await waitFor(() => {
      expect(
        screen.getByTestId('hf-token-selector-dialog-submit'),
      ).not.toBeDisabled();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('hf-token-selector-dialog-submit'));
    });

    await waitFor(() => {
      expect(onCreateToken).toHaveBeenCalledWith({
        displayName: 'my-new-token',
        token: VALID_HF_TOKEN,
      });
      expect(onChange).toHaveBeenCalledWith('my-new-token');
    });
    expect(
      screen.queryByTestId('hf-token-selector-dialog-name'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('hf-token-selector-add-new'),
    ).not.toBeInTheDocument();
  });

  it('shows an error message and stays open when create fails', async () => {
    const onCreateToken = vi
      .fn<HuggingFaceTokenSelectorProps['onCreateToken']>()
      .mockRejectedValue(new Error('Server rejected'));

    renderSelector({ onCreateToken });

    await openDropdown();
    await clickAddNew();
    await fillCreateForm('broken', VALID_HF_TOKEN);

    await waitFor(() => {
      expect(
        screen.getByTestId('hf-token-selector-dialog-submit'),
      ).not.toBeDisabled();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('hf-token-selector-dialog-submit'));
    });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Server rejected');
      expect(screen.getByText('Add Hugging Face token')).toBeInTheDocument();
    });
  });

  it('disables submit until the schema is valid', async () => {
    renderSelector();

    await openDropdown();
    await clickAddNew();

    const submit = screen.getByTestId('hf-token-selector-dialog-submit');
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByTestId('hf-token-selector-dialog-name'), {
      target: { value: 'name-only' },
    });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByTestId('hf-token-selector-dialog-token'), {
      target: { value: 'hf_x' },
    });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByTestId('hf-token-selector-dialog-token'), {
      target: { value: VALID_HF_TOKEN },
    });
    await waitFor(() => {
      expect(submit).not.toBeDisabled();
    });
  });

  it('shows token format error for invalid tokens', async () => {
    renderSelector();

    await openDropdown();
    await clickAddNew();
    await fillCreateForm('my-new-token', 'not-a-token');

    await waitFor(() => {
      expect(
        screen.getByText(defaultLabels.validation.invalidTokenFormat),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('hf-token-selector-dialog-submit'),
    ).toBeDisabled();
  });

  it('shows duplicate name error for existing display names', async () => {
    renderSelector();

    await openDropdown();
    await clickAddNew();
    await fillCreateForm('token-1-hf', VALID_HF_TOKEN);

    await waitFor(() => {
      expect(
        screen.getByText(defaultLabels.validation.duplicateName),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('hf-token-selector-dialog-submit'),
    ).toBeDisabled();
  });

  it('does not dismiss the popover when clicking outside', async () => {
    renderSelector();

    await openDropdown();
    await clickAddNew();

    await act(async () => {
      fireEvent.mouseDown(document.body);
      fireEvent.click(document.body);
    });

    expect(screen.getByText('Add Hugging Face token')).toBeInTheDocument();
  });

  it('closes the popover and reopens the select when Cancel is pressed', async () => {
    renderSelector();

    await openDropdown();
    await clickAddNew();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    });

    await waitFor(() => {
      expect(
        screen.queryByTestId('hf-token-selector-dialog-name'),
      ).not.toBeInTheDocument();
      expect(
        screen.getByTestId('hf-token-selector-add-new'),
      ).toBeInTheDocument();
    });
  });
});
