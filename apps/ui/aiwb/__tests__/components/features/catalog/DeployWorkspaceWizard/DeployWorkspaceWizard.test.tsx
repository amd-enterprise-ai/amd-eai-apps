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
import '@testing-library/jest-dom';
import type { ComponentProps } from 'react';
import { Mock, vi } from 'vitest';

import { DeployWorkspaceWizard } from '@/components/features/catalog/DeployWorkspaceWizard/DeployWorkspaceWizard';
import { getChart } from '@/lib/app/charts';
import { getClusterResources } from '@/lib/app/cluster';
import { fetchProjectSecrets } from '@/lib/app/secrets';
import { deployWorkspace } from '@/lib/app/workloads';
import type { WorkspaceCatalogTableItem } from '@/types/workspaces';
import { SecretUseCase } from '@amdenterpriseai/types';

import wrapper from '@/__tests__/ProviderWrapper';

type ClusterResources = Awaited<ReturnType<typeof getClusterResources>>['data'];

vi.mock('@/lib/app/cluster', () => ({
  getClusterResources: vi.fn(),
}));

vi.mock('@/lib/app/charts', () => ({
  getChart: vi.fn(),
}));

vi.mock('@/lib/app/secrets', () => ({
  fetchProjectSecrets: vi.fn(),
}));

vi.mock('@/lib/app/workloads', () => ({
  deployWorkspace: vi.fn(),
}));

const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => {
    const toast = vi.fn() as ReturnType<typeof vi.fn> & {
      success: typeof toastSuccessMock;
      error: typeof toastErrorMock;
    };
    toast.success = toastSuccessMock;
    toast.error = toastErrorMock;
    return { toast };
  },
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, number>) => {
      if (key === 'deployModal.summary.allocationSummary' && options) {
        return `${options.gpuCount} GPUs / ${options.cpuCount} CPUs / ${options.ramGb} GB RAM`;
      }
      return key;
    },
  }),
}));

vi.mock('next/image', () => ({
  default: ({
    unoptimized: _unoptimized,
    alt,
    ...props
  }: ComponentProps<'img'> & { unoptimized?: boolean }) => (
    // biome-ignore lint/performance/noImgElement: jsdom cannot use Next's image loader.
    <img alt={alt} {...props} />
  ),
}));

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: 'project1',
    projectUrl: (path: string) =>
      `/project1${path.startsWith('/') ? path : `/${path}`}`,
  }),
}));

const mockCatalogItem: WorkspaceCatalogTableItem = {
  id: 'item-1',
  name: 'test-workload',
  displayName: 'Test Workload',
  slug: 'vscode',
  description: 'A test workload for deployment',
  longDescription:
    'This is a longer description of the test workload.\nIt supports multiple lines.',
  type: 'WORKSPACE',
  category: 'development',
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
  createdBy: null,
  updatedBy: null,
  usageScope: 'user',
  tags: ['test', 'development'],
  featuredImage: 'test-image.png',
  requiredResources: {
    gpuCount: 2,
    gpuMemory: 16,
    cpuCoreCount: 4,
    systemMemory: 8,
  },
  available: true,
  externalUrl: 'https://example.com',
  workloadsCount: 0,
  workloads: [],
};

const mockCatalogItemDetails = {
  ...mockCatalogItem,
  signature: { image: 'ghcr.io/example/image:latest' },
  files: [],
};

const mockClusterResources: ClusterResources = {
  availableResources: {
    gpuCount: 10,
    memoryBytes: 206158430208,
    cpuMilliCores: 32000,
    ephemeralStorageBytes: 0,
  },
  totalNodeCount: 4,
};

const mockOnClose = vi.fn();
const mockOnDeploying = vi.fn();

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
};

const renderWizard = (
  props: Partial<ComponentProps<typeof DeployWorkspaceWizard>> = {},
) =>
  render(
    <DeployWorkspaceWizard
      catalogItem={mockCatalogItem}
      onClose={mockOnClose}
      {...props}
    />,
    { wrapper },
  );

const clickWizardNext = () => {
  fireEvent.click(screen.getByRole('button', { name: 'actions.next' }));
};

const waitForSettingsStep = async () => {
  await waitFor(() => {
    expect(
      screen.getByLabelText('deployModal.settings.containerImage.label'),
    ).toBeInTheDocument();
  });
};

const advanceToTargetStep = async () => {
  await waitForSettingsStep();
  await waitFor(() => {
    expect(
      screen.getByRole('button', { name: 'actions.next' }),
    ).not.toBeDisabled();
  });
  clickWizardNext();
  await waitFor(() => {
    expect(screen.getByTestId('resource-allocation-card')).toBeInTheDocument();
  });
};

const advanceToDeployStep = async () => {
  await advanceToTargetStep();
  await waitFor(() => {
    expect(
      screen.getByRole('button', { name: 'actions.next' }),
    ).not.toBeDisabled();
  });
  clickWizardNext();
  await waitFor(() => {
    expect(
      screen.getByRole('button', { name: 'actions.submit.title' }),
    ).toBeInTheDocument();
  });
};

describe('DeployWorkspaceWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toastSuccessMock.mockClear();
    toastErrorMock.mockClear();

    (getClusterResources as Mock).mockResolvedValue({
      data: {
        availableResources: mockClusterResources.availableResources,
        totalNodeCount: mockClusterResources.totalNodeCount,
      },
    });
    (deployWorkspace as Mock).mockResolvedValue({ id: 'workload-1' });
    (getChart as Mock).mockResolvedValue(mockCatalogItemDetails);
    (fetchProjectSecrets as Mock).mockResolvedValue({ data: [] });
  });

  it('renders wizard when open with catalog item information', async () => {
    renderWizard();

    expect(screen.getByText('deployModal.title')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Test Workload')).toBeInTheDocument();
      expect(
        screen.getByText('A test workload for deployment'),
      ).toBeInTheDocument();
    });
  });

  it('renders settings while catalog item details are loading', () => {
    const chartRequest = deferred<typeof mockCatalogItemDetails>();
    (getChart as Mock).mockReturnValue(chartRequest.promise);

    renderWizard();

    expect(screen.getByText('Test Workload')).toBeInTheDocument();
    expect(
      screen.getByLabelText('deployModal.settings.containerImage.label'),
    ).toBeInTheDocument();
  });

  it('sets the container image when catalog item details load', async () => {
    const chartRequest = deferred<typeof mockCatalogItemDetails>();
    (getChart as Mock).mockReturnValue(chartRequest.promise);
    renderWizard();

    const imageInput = screen.getByLabelText(
      'deployModal.settings.containerImage.label',
    );
    expect(imageInput).toHaveValue('');

    await act(async () => {
      chartRequest.resolve(mockCatalogItemDetails);
    });

    await waitFor(() => {
      expect(imageInput).toHaveValue(mockCatalogItemDetails.signature.image);
    });
  });

  it('preserves a container image edited while catalog item details load', async () => {
    const chartRequest = deferred<typeof mockCatalogItemDetails>();
    (getChart as Mock).mockReturnValue(chartRequest.promise);
    renderWizard();

    const imageInput = screen.getByLabelText(
      'deployModal.settings.containerImage.label',
    );
    fireEvent.change(imageInput, {
      target: { value: 'ghcr.io/other/image:tag' },
    });

    await act(async () => {
      chartRequest.resolve(mockCatalogItemDetails);
    });

    expect(imageInput).toHaveValue('ghcr.io/other/image:tag');
  });

  it('defaults the workload name to the catalog item display name', async () => {
    renderWizard();

    await advanceToTargetStep();

    const workloadNameInput = screen.getByLabelText(
      'deployModal.settings.displayName.label',
    ) as HTMLInputElement;
    expect(workloadNameInput.value).toBe(mockCatalogItem.displayName);
  });

  it('allows editing workload name', async () => {
    renderWizard();

    await advanceToTargetStep();
    const workloadNameInput = screen.getByLabelText(
      'deployModal.settings.displayName.label',
    );
    fireEvent.change(workloadNameInput, {
      target: { value: 'custom-workload-name' },
    });
    expect(workloadNameInput).toHaveValue('custom-workload-name');
  });

  it('enables resource customization when switch is toggled', async () => {
    renderWizard();

    await advanceToTargetStep();

    const customizeSwitch = screen.getByRole('switch', {
      name: 'deployModal.settings.resourceAllocation.label',
    });
    fireEvent.click(customizeSwitch);

    await waitFor(() => {
      expect(
        screen.getByText('deployModal.settings.resourceAllocation.gpuCount'),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          'deployModal.settings.resourceAllocation.systemMemory',
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          'deployModal.settings.resourceAllocation.cpuCoreCount',
        ),
      ).toBeInTheDocument();
    });
  });

  it('disables resource customization when enableResourceAllocation is false', async () => {
    renderWizard({ enableResourceAllocation: false });

    await advanceToTargetStep();

    const customizeSwitch = screen.getByRole('switch', {
      name: 'deployModal.settings.resourceAllocation.label',
    });
    expect(customizeSwitch).toBeDisabled();
  });

  it('shows resource allocation warnings when values are below requirements', async () => {
    const highRequirementItem = {
      ...mockCatalogItem,
      requiredResources: {
        ...mockCatalogItem.requiredResources!,
        gpuCount: 8,
        systemMemory: 25,
        cpuCoreCount: 16,
      },
    };

    renderWizard({ catalogItem: highRequirementItem });

    await advanceToTargetStep();

    const customizeSwitch = screen.getByRole('switch', {
      name: 'deployModal.settings.resourceAllocation.label',
    });
    fireEvent.click(customizeSwitch);

    await waitFor(() => {
      const gpuSlider = screen.getByRole('slider', {
        name: 'deployModal.settings.resourceAllocation.gpuCount',
      });
      fireEvent.change(gpuSlider, { target: { value: '4' } });
    });

    await waitFor(() => {
      expect(screen.getByText('belowRequiredWarning')).toBeInTheDocument();
    });
  });

  it('handles workload deployment successfully', async () => {
    renderWizard({ onDeploying: mockOnDeploying });

    await advanceToDeployStep();

    fireEvent.click(
      screen.getByRole('button', { name: 'actions.submit.title' }),
    );

    await waitFor(() => {
      expect(deployWorkspace).toHaveBeenCalledWith(
        'project1',
        expect.objectContaining({
          displayName: mockCatalogItem.displayName,
          template: mockCatalogItem.slug,
          gpus: mockCatalogItem.requiredResources!.gpuCount,
          memoryPerGpu: mockCatalogItem.requiredResources!.systemMemory,
          cpuPerGpu: mockCatalogItem.requiredResources!.cpuCoreCount,
          image: mockCatalogItemDetails.signature.image,
        }),
      );
    });

    expect(toastSuccessMock).toHaveBeenCalledWith(
      expect.objectContaining({
        props: expect.objectContaining({
          message: 'notifications.deployWorkload.success',
          href: '/project1/workloads/workload-1',
        }),
      }),
    );
    expect(mockOnDeploying).toHaveBeenCalled();
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('handles deployment errors', async () => {
    const consoleErrorSpy = vi
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);

    try {
      (deployWorkspace as Mock).mockRejectedValue(
        new Error('Deployment failed'),
      );

      renderWizard();

      await advanceToDeployStep();
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.submit.title' }),
      );

      await waitFor(() => {
        expect(toastErrorMock).toHaveBeenCalledWith(
          'notifications.deployWorkload.error',
        );
      });
      expect(consoleErrorSpy).toHaveBeenCalled();
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('calls onClose when cancel button is clicked', async () => {
    renderWizard();

    await waitForSettingsStep();
    fireEvent.click(
      screen.getByRole('button', { name: 'actions.cancel.title' }),
    );
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('fetches only image pull secrets for the imagePullSecrets dropdown', async () => {
    renderWizard();

    await waitFor(() => {
      expect(fetchProjectSecrets).toHaveBeenCalledWith(
        'project1',
        SecretUseCase.IMAGE_PULL_SECRET,
      );
    });
  });

  it('deploys with every selected image pull secret, labelled by display name', async () => {
    (fetchProjectSecrets as Mock).mockResolvedValue({
      data: [
        {
          metadata: {
            name: 'wb-secret-aaaa1111',
            namespace: 'project1',
            creationTimestamp: '2024-01-01T00:00:00Z',
          },
          useCase: SecretUseCase.IMAGE_PULL_SECRET,
          displayName: 'Registry A',
        },
        {
          metadata: {
            name: 'wb-secret-bbbb2222',
            namespace: 'project1',
            creationTimestamp: '2024-01-01T00:00:00Z',
          },
          useCase: SecretUseCase.IMAGE_PULL_SECRET,
          displayName: 'Registry B',
        },
      ],
    });
    renderWizard();

    await waitForSettingsStep();
    const pullSecretsSelect = await screen.findByRole('button', {
      name: /deployModal\.settings\.imagePullSecrets\.placeholder/,
    });
    await act(async () => {
      fireEvent.click(pullSecretsSelect);
    });
    await act(async () => {
      fireEvent.click(
        await screen.findByRole('option', { name: 'Registry A' }),
      );
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: 'Registry B' }));
    });
    await act(async () => {
      fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Escape' });
    });
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    await advanceToDeployStep();
    expect(
      screen.getByText('deployModal.summary.imagePullSecrets').parentElement,
    ).toHaveTextContent('Registry A, Registry B');
    expect(screen.queryByText(/wb-secret-/)).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'actions.submit.title' }),
    );

    await waitFor(() => {
      expect(deployWorkspace).toHaveBeenCalledWith(
        'project1',
        expect.objectContaining({
          imagePullSecrets: ['wb-secret-aaaa1111', 'wb-secret-bbbb2222'],
        }),
      );
    });
  });

  it('displays long description with line breaks', async () => {
    renderWizard();

    await waitFor(() => {
      expect(
        screen.getByText(
          /This is a longer description of the test workload\.\s*It supports multiple lines\./,
        ),
      ).toBeInTheDocument();
    });
  });

  it('renders and allows editing the custom workload image input', async () => {
    const mockSignatureImage = mockCatalogItemDetails.signature.image;

    renderWizard();

    await waitForSettingsStep();

    const imageInput = screen.getByLabelText(
      'deployModal.settings.containerImage.label',
    ) as HTMLInputElement;
    await waitFor(() => {
      expect(imageInput.value).toBe(mockSignatureImage);
    });

    fireEvent.change(imageInput, {
      target: { value: 'ghcr.io/other/image:tag' },
    });
    expect(imageInput.value).toBe('ghcr.io/other/image:tag');

    await advanceToDeployStep();

    fireEvent.click(
      screen.getByRole('button', { name: 'actions.submit.title' }),
    );

    await waitFor(() => {
      expect(deployWorkspace).toHaveBeenCalledWith(
        'project1',
        expect.objectContaining({
          image: 'ghcr.io/other/image:tag',
        }),
      );
    });
  });

  it('shows summary on the check step', async () => {
    renderWizard();

    await advanceToDeployStep();

    expect(screen.getByText('2 GPUs / 8 CPUs / 16 GB RAM')).toBeInTheDocument();
  });

  it('keeps next disabled when display name is empty', async () => {
    renderWizard();

    await advanceToTargetStep();
    const workloadNameInput = screen.getByLabelText(
      'deployModal.settings.displayName.label',
    );
    fireEvent.change(workloadNameInput, { target: { value: '' } });
    fireEvent.blur(workloadNameInput);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'actions.next' }),
      ).toBeDisabled();
    });
  });
});
