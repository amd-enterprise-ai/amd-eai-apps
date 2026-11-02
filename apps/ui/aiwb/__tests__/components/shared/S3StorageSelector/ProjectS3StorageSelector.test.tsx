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
import { Mock, vi } from 'vitest';

import { ProjectS3StorageSelector } from '@/components/shared/S3StorageSelector';
import { fetchProjectSecrets } from '@/lib/app/secrets';
import { createProjectStorage, fetchProjectStorages } from '@/lib/app/storages';

import wrapper from '@/__tests__/ProviderWrapper';

vi.mock('@/lib/app/storages', async (importOriginal) => ({
  ...(await importOriginal()),
  fetchProjectStorages: vi.fn(),
  createProjectStorage: vi.fn(),
}));

vi.mock('@/lib/app/secrets', async (importOriginal) => ({
  ...(await importOriginal()),
  fetchProjectSecrets: vi.fn(),
}));

// The create dialog's secret picker is a React Aria Select nested inside the
// popover overlay, which does not open reliably in jsdom (the codebase mocks
// Select for the same reason; see HuggingFaceTokenSelector.selection.test.tsx).
// Replace FormSelect with a native <select> wired to react-hook-form the same
// way the real one is, so selecting a secret drives the form through its normal
// change/validation path. Everything else (outer Select, Popover, ManagedForm,
// FormInput) stays real.
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  const React = await vi.importActual<typeof import('react')>('react');

  const MockFormSelect = ({ form, name, ...rest }: any) =>
    React.createElement(
      'select',
      { ...form.register(name), 'data-testid': rest['data-testid'] },
      [
        React.createElement('option', { key: 'none', value: '' }, ''),
        React.createElement(
          'option',
          { key: 's3-creds', value: 's3-creds' },
          's3-creds',
        ),
      ],
    );

  return { ...actual, FormSelect: MockFormSelect };
});

const storage = (name: string, displayName = name) => ({
  name,
  displayName,
  project: 'project1',
  type: 'S3',
  secretName: 's3-creds',
  spec: { bucketUrl: 'https://s3.example.com/bucket', region: 'us-east-1' },
});

const secret = (name: string, displayName: string) => ({
  metadata: { name, namespace: 'project1' },
  displayName,
  useCase: 'S3',
});

const renderSelector = (
  namespace = 'project1',
  onChange: (name: string) => void = vi.fn(),
  value: string | null = null,
  allowCreate = true,
) => {
  render(
    <ProjectS3StorageSelector
      namespace={namespace}
      value={value}
      onChange={onChange}
      allowCreate={allowCreate}
    />,
    { wrapper },
  );
  return onChange;
};

const trigger = () =>
  within(screen.getByTestId('project-s3-storage-selector')).getByRole('button');

describe('ProjectS3StorageSelector', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (fetchProjectStorages as Mock).mockResolvedValue({
      data: [storage('team-bucket', 'Team bucket')],
    });
    (fetchProjectSecrets as Mock).mockResolvedValue({
      data: [secret('s3-creds', 'Team bucket credentials')],
    });
  });

  it('requests only the storages usable for S3', async () => {
    renderSelector();
    await waitFor(() => {
      expect(fetchProjectStorages).toHaveBeenCalledWith('project1', 'S3');
    });
  });

  it('skips querying when no namespace is provided', () => {
    renderSelector('');
    expect(fetchProjectStorages).not.toHaveBeenCalled();
  });

  it('shows the selected storage name', async () => {
    renderSelector('project1', vi.fn(), 'team-bucket');
    await waitFor(() => {
      expect(trigger()).toHaveTextContent('Team bucket');
    });
  });

  it('shows a loading placeholder while storages are fetched', async () => {
    let resolveStorages: (value: { data: unknown[] }) => void = () => {};
    (fetchProjectStorages as Mock).mockReturnValue(
      new Promise<{ data: unknown[] }>((resolve) => {
        resolveStorages = resolve;
      }),
    );

    renderSelector();
    expect(await screen.findByText('loading')).toBeInTheDocument();

    await act(async () => {
      resolveStorages({ data: [] });
    });

    expect(await screen.findByText('placeholder')).toBeInTheDocument();
  });

  it('stays openable when empty so the create flow is reachable', async () => {
    // Regression: React Aria disables a Select whose collection is empty, which
    // would hide the "Add new" affordance in bottomContent when the project has
    // no storages. The selector must remain enabled and reveal the create action.
    (fetchProjectStorages as Mock).mockResolvedValue({ data: [] });
    renderSelector();
    await waitFor(() => {
      expect(fetchProjectStorages).toHaveBeenCalledWith('project1', 'S3');
    });
    await waitFor(() => {
      expect(trigger()).not.toBeDisabled();
    });

    await act(async () => {
      fireEvent.click(trigger());
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('s3-storage-selector-add-new'),
      ).toBeInTheDocument();
    });
  });

  it('disables selector when no options exist and creating is disallowed', async () => {
    (fetchProjectStorages as Mock).mockResolvedValue({ data: [] });
    renderSelector('project1', vi.fn(), null, false);
    await waitFor(() => {
      expect(fetchProjectStorages).toHaveBeenCalledWith('project1', 'S3');
    });
    await waitFor(() => {
      expect(trigger()).toBeDisabled();
    });
  });

  it('creates a new storage from the popover and auto-selects it', async () => {
    // Start from an empty project: the natural path for creating a storage, and
    // the one where the dropdown reliably opens in jsdom. Its empty state renders
    // a placeholder item so the Select stays openable, whereas a real selectable
    // option does not open via fireEvent.click here.
    (fetchProjectStorages as Mock).mockResolvedValue({ data: [] });
    const created = storage('my-config-k8s', 'My Config');
    (createProjectStorage as Mock).mockResolvedValue(created);
    const onChange = renderSelector();

    // Let the storages query settle before opening: React Aria only wires up the
    // trigger's press handling once the collection is populated, so clicking
    // before then is a no-op and the dropdown never opens.
    await waitFor(() => {
      expect(fetchProjectStorages).toHaveBeenCalledWith('project1', 'S3');
    });
    await waitFor(() => {
      expect(trigger()).not.toBeDisabled();
    });
    await act(async () => {
      fireEvent.click(trigger());
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('s3-storage-selector-add-new'),
      ).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('s3-storage-selector-add-new'));
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('s3-storage-selector-dialog-name'),
      ).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('s3-storage-selector-dialog-name'), {
      target: { value: 'My Config' },
    });
    fireEvent.change(
      screen.getByTestId('s3-storage-selector-dialog-bucket-url'),
      { target: { value: 'https://s3.example.com/bucket' } },
    );
    fireEvent.change(screen.getByTestId('s3-storage-selector-dialog-region'), {
      target: { value: 'us-east-1' },
    });

    // FormSelect is stubbed to a native <select> that registers with the form.
    await act(async () => {
      fireEvent.change(
        screen.getByTestId('s3-storage-selector-dialog-secret'),
        {
          target: { value: 's3-creds' },
        },
      );
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('s3-storage-selector-dialog-submit'),
      ).not.toBeDisabled();
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('s3-storage-selector-dialog-submit'));
    });

    await waitFor(() => {
      expect(createProjectStorage).toHaveBeenCalledWith('project1', {
        displayName: 'My Config',
        type: 'S3',
        secretName: 's3-creds',
        spec: {
          bucketUrl: 'https://s3.example.com/bucket',
          region: 'us-east-1',
        },
      });
      expect(onChange).toHaveBeenCalledWith('my-config-k8s');
    });
  });

  it('blocks create when display name exceeds 253 characters', async () => {
    (fetchProjectStorages as Mock).mockResolvedValue({ data: [] });
    const overlongName = 'a'.repeat(254);
    renderSelector();

    await waitFor(() => {
      expect(fetchProjectStorages).toHaveBeenCalledWith('project1', 'S3');
    });
    await waitFor(() => {
      expect(trigger()).not.toBeDisabled();
    });
    await act(async () => {
      fireEvent.click(trigger());
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('s3-storage-selector-add-new'),
      ).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('s3-storage-selector-add-new'));
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('s3-storage-selector-dialog-name'),
      ).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('s3-storage-selector-dialog-name'), {
      target: { value: overlongName },
    });
    await act(async () => {
      fireEvent.change(
        screen.getByTestId('s3-storage-selector-dialog-secret'),
        {
          target: { value: 's3-creds' },
        },
      );
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('s3-storage-selector-dialog-submit'),
      ).toBeDisabled();
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('s3-storage-selector-dialog-submit'));
    });
    await waitFor(() => {
      expect(createProjectStorage).not.toHaveBeenCalled();
    });
  });
});
