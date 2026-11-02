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

import { createStorage } from '@/services/app';

import { generateMockProjects } from '@/__mocks__/utils/project-mock';
import { generateMockSecrets } from '@/__mocks__/utils/secrets-mock';
import { generateMockStorages } from '@/__mocks__/utils/storages-mock';

import { StorageScope } from '@/types/enums/storages';
import { StorageType } from '@/types/enums/storages';
import { SecretUseCase } from '@amdenterpriseai/types';

import { AddS3Storage } from '@/components/features/storages/AddS3Storage';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock } from 'vitest';
import { fetchSecrets } from '@/services/app';

const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
};
vi.mock('@amdenterpriseai/hooks', () => ({
  useSystemToast: () => ({ toast: mockToast }),
  // biome-ignore lint/style/useNamingConvention: framework convention
  __esModule: true,
}));

vi.mock('@/services/app', () => ({
  createStorage: vi.fn(),
  fetchSecrets: vi.fn(),
}));

// Test data
const projects = generateMockProjects(2);

type FillFormParams = {
  name?: string;
  bucketUrl?: string;
  accessKeyName?: string;
  secretKeyName?: string;
  projectName?: string;
  secretName?: string;
};

const fillFormAndSubmit = async ({
  name,
  bucketUrl,
  accessKeyName,
  secretKeyName,
  secretName,
  projectName,
}: FillFormParams) => {
  // fill name input
  if (typeof name !== 'undefined') {
    await fireEvent.change(
      screen.getByRole('textbox', { name: /form.add.field.name.label/i }),
      {
        target: { value: name },
      },
    );
  }

  if (typeof bucketUrl !== 'undefined') {
    await fireEvent.change(
      screen.getByRole('textbox', { name: /form.add.field.bucketUrl.label/i }),
      {
        target: { value: bucketUrl },
      },
    );
  }

  if (typeof accessKeyName !== 'undefined') {
    await fireEvent.change(
      screen.getByRole('textbox', {
        name: /form.add.field.accessKeyName.label/i,
      }),
      {
        target: { value: accessKeyName },
      },
    );
  }

  if (typeof secretKeyName !== 'undefined') {
    await fireEvent.change(
      screen.getByRole('textbox', {
        name: /form.add.field.secretKeyName.label/i,
      }),
      {
        target: { value: secretKeyName },
      },
    );
  }

  if (typeof secretName !== 'undefined') {
    await fireEvent.click(
      screen.getByRole('button', {
        name: /form.add.field.secretId.label/i,
      }),
    );
    await fireEvent.click(
      await screen.findByRole('option', { name: secretName }),
    );
  }

  if (typeof projectName !== 'undefined') {
    await fireEvent.click(
      screen.getByRole('button', {
        name: /form.add.field.projectIds.label/i,
      }),
    );
    await fireEvent.click(
      await screen.findByRole('option', { name: projectName }),
    );
  }

  await fireEvent.click(screen.getByText('form.add.actions.add.label'));
};

describe('AddS3Storage', () => {
  const mockSecret = generateMockSecrets(1)[0];
  mockSecret.name = 'secret-001';
  mockSecret.id = 'secret-001-uuid';
  mockSecret.useCase = SecretUseCase.S3;

  const mockProject = generateMockProjects(1)[0];
  mockProject.id = 'project-001-uuid';
  mockProject.name = 'project-001';

  const mockOpenAddSecret = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open and displays form fields', () => {
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[]}
          isOpen
          projects={projects}
          onClose={vi.fn()}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    expect(screen.getByText('form.add.title')).toBeInTheDocument();
    expect(
      screen.getAllByText('form.add.field.secretId.label')[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('form.add.field.name.label')[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('form.add.field.bucketUrl.label')[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('form.add.field.accessKeyName.label')[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('form.add.field.secretKeyName.label')[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('form.add.field.projectIds.label')[0],
    ).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    const { container } = render(
      <AddS3Storage
        storages={[]}
        secrets={[]}
        isOpen={false}
        projects={projects}
        onClose={vi.fn()}
        openAddSecret={mockOpenAddSecret}
      />,
      { wrapper },
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('fetchSecret to have been called on render', () => {
    const { container } = render(
      <AddS3Storage
        storages={[]}
        secrets={[]}
        isOpen={false}
        projects={projects}
        onClose={vi.fn()}
        openAddSecret={mockOpenAddSecret}
      />,
      { wrapper },
    );
    expect(fetchSecrets).toHaveBeenCalled();
  });

  it('calls onClose when cancel is clicked', () => {
    const onClose = vi.fn();

    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[]}
          isOpen
          projects={projects}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });
    fireEvent.click(screen.getByText('form.add.actions.cancel.label'));
    expect(onClose).toHaveBeenCalled();
  });

  it('checks for invalid name', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage 1',
      bucketUrl: 'http://test/test-bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.name.error.invalidName'),
      ).toBeInTheDocument();
    });
  });

  it('checks for duplicate name', async () => {
    const mockStorage = generateMockStorages(1)[0];
    mockStorage.name = 'test-storage-1';

    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[mockStorage]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'http://test/test-bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.name.error.duplicateName'),
      ).toBeInTheDocument();
    });
  });

  it('checks for min length on name', async () => {
    const mockStorage = generateMockStorages(1)[0];
    mockStorage.name = 'test-storage-1';

    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[mockStorage]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: '1',
      bucketUrl: 'http://test/test-bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.name.error.minLength'),
      ).toBeInTheDocument();
    });
  });

  it('checks for max length on name', async () => {
    const mockStorage = generateMockStorages(1)[0];
    mockStorage.name = 'test-storage-1';

    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[mockStorage]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'a'.repeat(254),
      bucketUrl: 'http://test/test-bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.name.error.maxLength'),
      ).toBeInTheDocument();
    });
  });

  it('checks valid url format on bucketUrl', async () => {
    const mockStorage = generateMockStorages(1)[0];
    mockStorage.name = 'test-storage-1';

    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'http://amd.com/bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.queryByText('form.add.field.bucketUrl.error.invalidUrl'),
      ).not.toBeInTheDocument();
    });
  });

  it('checks invalid url format on bucketUrl', async () => {
    const mockStorage = generateMockStorages(1)[0];
    mockStorage.name = 'test-storage-1';

    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'invalid',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.bucketUrl.error.invalidUrl'),
      ).toBeInTheDocument();
    });
  });

  it('calls mutate and onClose on form submit', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'http://amd.com/bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(createStorage).toHaveBeenCalledWith({
        projectIds: ['project-001-uuid'],
        name: 'test-storage-1',
        secretId: 'secret-001-uuid',
        scope: StorageScope.ORGANIZATION,
        type: StorageType.S3,
        spec: {
          bucketUrl: 'http://amd.com/bucket',
          accessKeyName: 'test-access-key',
          secretKeyName: 'test-secret-key',
        },
      });
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('shows bucket url required error when bucket url does not start with http:// or https://', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'ftp://test',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.bucketUrl.error.invalidUrl'),
      ).toBeInTheDocument();
    });
  });

  it('shows bucket url required error when bucket url exceeds max 2043 characters', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'http://' + 'a'.repeat(2040),
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.bucketUrl.error.maxLength'),
      ).toBeInTheDocument();
    });
  });

  it('shows bucket url required error when bucket url is required', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    // change to make the form dirty first before filling blank
    await fireEvent.change(
      screen.getByRole('textbox', { name: /form.add.field.bucketUrl.label/i }),
      {
        target: { value: 'http://amd.com/s3' },
      },
    );

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: '',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(
        screen.getByText('form.add.field.bucketUrl.error.required'),
      ).toBeInTheDocument();
    });
  });

  it('calls mutate with correct project id when project is in props and onClose on form submit', async () => {
    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'http://amd.com/bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('shows error toast on mutation error', async () => {
    (createStorage as Mock).mockRejectedValueOnce(new Error('fail'));

    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'http://amd.com/bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'form.add.notification.error',
        expect.any(Error),
      );
    });
  });

  it('shows success toast on success create api call', async () => {
    (createStorage as Mock).mockResolvedValueOnce({});

    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fillFormAndSubmit({
      name: 'test-storage-1',
      bucketUrl: 'http://amd.com/bucket',
      accessKeyName: 'test-access-key',
      secretKeyName: 'test-secret-key',
      secretName: 'secret-001',
      projectName: 'project-001',
    });

    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalledWith(
        'form.add.notification.success',
      );
    });
  });

  it('create secret button will open openAddSecret props callback', async () => {
    (createStorage as Mock).mockResolvedValueOnce({});

    const onClose = vi.fn();
    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={[mockSecret]}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    await fireEvent.click(
      screen.getByText('form.add.field.secretId.actions.createSecret'),
    );

    expect(mockOpenAddSecret).toHaveBeenCalled();
  });

  it('only displays secrets with S3 use case in the secret dropdown', async () => {
    const mockSecrets = generateMockSecrets(3);

    // Create secrets with different use cases
    mockSecrets[0].name = 's3-secret-1';
    mockSecrets[0].useCase = SecretUseCase.S3;

    mockSecrets[1].name = 'generic-secret';
    mockSecrets[1].useCase = SecretUseCase.GENERIC;

    mockSecrets[2].name = 'huggingface-secret';
    mockSecrets[2].useCase = SecretUseCase.HUGGING_FACE;

    const onClose = vi.fn();

    act(() => {
      render(
        <AddS3Storage
          storages={[]}
          secrets={mockSecrets}
          isOpen
          projects={[mockProject]}
          onClose={onClose}
          openAddSecret={mockOpenAddSecret}
        />,
        {
          wrapper,
        },
      );
    });

    // Open the secret dropdown
    await fireEvent.click(
      screen.getByRole('button', {
        name: /form.add.field.secretId.label/i,
      }),
    );

    // Verify S3 secret IS visible
    const s3SecretOptions = await screen.findAllByText('s3-secret-1');
    expect(s3SecretOptions.length).toBeGreaterThan(0);

    // Verify non-S3 secrets are NOT visible
    expect(
      screen.queryByRole('option', { name: 'generic-secret' }),
    ).not.toBeInTheDocument();

    expect(
      screen.queryByRole('option', { name: 'huggingface-secret' }),
    ).not.toBeInTheDocument();
  });
});
