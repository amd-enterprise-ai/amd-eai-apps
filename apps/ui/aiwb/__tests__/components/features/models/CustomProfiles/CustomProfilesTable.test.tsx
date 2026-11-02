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
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CustomProfilesTable } from '@/components/features/models/CustomProfiles/CustomProfilesTable';
import {
  deleteCustomProfile,
  listCustomProfiles,
  type CustomProfileResponse,
} from '@/lib/app/custom-profiles';

import wrapper from '@/__tests__/ProviderWrapper';

vi.mock('@/lib/app/custom-profiles', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/app/custom-profiles')>();
  return {
    ...actual,
    listCustomProfiles: vi.fn(),
    deleteCustomProfile: vi.fn(),
  };
});

const mockToastError = vi.fn();
vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => ({
    toast: { success: vi.fn(), error: mockToastError, info: vi.fn() },
  }),
}));

const mockPush = vi.fn();
vi.mock('next/router', () => ({
  useRouter: () => ({ push: mockPush, query: { project: 'team-alpha' } }),
}));

const mockListCustomProfiles = vi.mocked(listCustomProfiles);
const mockDeleteCustomProfile = vi.mocked(deleteCustomProfile);
const mockOnEditProfile = vi.fn();
const mockOnDeployProfile = vi.fn();

const defaultProfile: CustomProfileResponse = {
  name: 'default',
  displayName: 'Default',
  isDefault: true,
  resourceName: 'llama-3-8b-default',
  createdAt: '2026-07-02T11:04:19Z',
  createdBy: 'onboarding@example.com',
  inUseBy: [],
  status: { state: 'Ready', message: '' },
  profile: {
    metadata: { name: 'default-profile' },
    spec: {
      aimId: 'aim-1',
      metric: 'throughput',
      precision: 'fp8',
      acceleratorModel: 'MI300X',
      acceleratorCount: 8,
      acceleratorType: 'gpu',
    },
  },
};

const namedProfile: CustomProfileResponse = {
  name: 'low-latency-7f3b6c8e',
  displayName: 'Low latency',
  isDefault: false,
  resourceName: 'low-latency-7f3b6c8e',
  createdAt: '2026-07-18T09:22:41Z',
  createdBy: 'user@example.com',
  inUseBy: [],
  status: { state: 'Ready', message: '' },
  profile: {
    metadata: { name: 'low-latency-profile' },
    spec: {
      aimId: 'aim-1',
      metric: 'latency',
      precision: 'bf16',
      acceleratorModel: 'MI325X',
      acceleratorCount: 4,
      acceleratorType: 'gpu',
    },
  },
};

const inUseProfile: CustomProfileResponse = {
  ...namedProfile,
  name: 'in-use-1a2b3c4d',
  displayName: 'In use',
  inUseBy: [{ serviceId: 'svc-1', displayName: 'summarizer-prod' }],
};

const reconcilingProfile: CustomProfileResponse = {
  ...namedProfile,
  name: 'reconciling-9e8d7c6b',
  displayName: 'Still preparing',
  status: { state: 'Pending', message: 'Reconciling' },
};

const props = {
  project: 'team-alpha',
  modelId: 'model-a',
  onEditProfile: mockOnEditProfile,
  onDeployProfile: mockOnDeployProfile,
  isModelDeployable: true,
};

const renderTable = async (overrides: Partial<typeof props> = {}) => {
  await act(async () => {
    render(<CustomProfilesTable {...props} {...overrides} />, { wrapper });
  });
};

const openRowActions = async (rowIndex: number) => {
  const triggers = screen.getAllByLabelText('list.actions.label');
  await act(async () => {
    fireEvent.click(triggers[rowIndex]);
  });
};

beforeEach(() => {
  vi.clearAllMocks();
  mockListCustomProfiles.mockResolvedValue([defaultProfile, namedProfile]);
  mockDeleteCustomProfile.mockResolvedValue();
});

describe('CustomProfilesTable', () => {
  it('renders all six columns', async () => {
    await renderTable();

    await waitFor(() => {
      expect(
        screen.getByText('list.headers.displayName.title'),
      ).toBeInTheDocument();
    });
    for (const column of [
      'accelerator',
      'metric',
      'precision',
      'createdBy',
      'createdAt',
    ]) {
      expect(
        screen.getByText(`list.headers.${column}.title`),
      ).toBeInTheDocument();
    }
  });

  it('lists the profiles for the model', async () => {
    await renderTable();

    await waitFor(() => {
      expect(screen.getByText('Default')).toBeInTheDocument();
    });
    expect(screen.getByText('Low latency')).toBeInTheDocument();
    expect(mockListCustomProfiles).toHaveBeenCalledWith(
      'team-alpha',
      'model-a',
    );
  });

  it('lists Default first even when a named profile has no creation timestamp', async () => {
    mockListCustomProfiles.mockResolvedValue([
      { ...namedProfile, createdAt: null },
      defaultProfile,
    ]);

    await renderTable();

    await waitFor(() => {
      expect(screen.getByText('Default')).toBeInTheDocument();
    });
    const [, ...bodyRows] = screen.getAllByRole('row');
    expect(bodyRows[0]).toHaveTextContent('Default');
    expect(bodyRows[1]).toHaveTextContent('Low latency');
  });

  it('filters profiles by the toolbar search', async () => {
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('Low latency')).toBeInTheDocument();
    });

    fireEvent.change(
      screen.getByPlaceholderText('filters.search.placeholder'),
      { target: { value: 'low latency' } },
    );

    await waitFor(() => {
      expect(screen.queryByText('Default')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Low latency')).toBeInTheDocument();
  });

  it('refreshes the profile list from the toolbar', async () => {
    await renderTable();
    await waitFor(() => {
      expect(mockListCustomProfiles).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'actions.refresh.title' }),
    );

    await waitFor(() => {
      expect(mockListCustomProfiles).toHaveBeenCalledTimes(2);
    });
  });

  it('renders the accelerator count and model together, and the translated metric', async () => {
    await renderTable();

    await waitFor(() => {
      expect(screen.getByText('8x MI300X')).toBeInTheDocument();
    });
    expect(screen.getByText('4x MI325X')).toBeInTheDocument();
    expect(
      screen.getByText('performanceMetrics.values.throughput'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('performanceMetrics.values.latency'),
    ).toBeInTheDocument();
    expect(screen.getByText('fp8')).toBeInTheDocument();
  });

  it('falls back to a no-data cell when a profile carries no spec', async () => {
    mockListCustomProfiles.mockResolvedValue([
      { ...namedProfile, profile: null, createdBy: null },
    ]);

    await renderTable();

    await waitFor(() => {
      expect(screen.getByText('Low latency')).toBeInTheDocument();
    });
    expect(screen.queryByText('4x MI325X')).not.toBeInTheDocument();
  });

  it('opens the edit drawer for a saved profile', async () => {
    mockListCustomProfiles.mockResolvedValue([namedProfile]);
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('Low latency')).toBeInTheDocument();
    });

    await openRowActions(0);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.edit.label'));
    });

    expect(mockOnEditProfile).toHaveBeenCalledWith(namedProfile.name);
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('sends the Default profile to model settings instead of the drawer', async () => {
    mockListCustomProfiles.mockResolvedValue([defaultProfile]);
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('Default')).toBeInTheDocument();
    });

    await openRowActions(0);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.edit.label'));
    });

    expect(mockPush).toHaveBeenCalledWith(
      '/team-alpha/models/custom-models/model-a/edit',
    );
    expect(mockOnEditProfile).not.toHaveBeenCalled();
  });

  it('prevents editing a profile a deployment still references', async () => {
    mockListCustomProfiles.mockResolvedValue([inUseProfile]);
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('In use')).toBeInTheDocument();
    });

    await openRowActions(0);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.edit.label'));
    });

    expect(mockOnEditProfile).not.toHaveBeenCalled();
  });

  it('prevents deleting the Default profile', async () => {
    mockListCustomProfiles.mockResolvedValue([defaultProfile]);
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('Default')).toBeInTheDocument();
    });

    await openRowActions(0);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.delete.label'));
    });

    expect(screen.queryByTestId('confirm-button')).not.toBeInTheDocument();
    expect(mockDeleteCustomProfile).not.toHaveBeenCalled();
  });

  it('prevents deleting a profile a deployment still references', async () => {
    mockListCustomProfiles.mockResolvedValue([inUseProfile]);
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('In use')).toBeInTheDocument();
    });

    await openRowActions(0);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.delete.label'));
    });

    expect(screen.queryByTestId('confirm-button')).not.toBeInTheDocument();
    expect(mockDeleteCustomProfile).not.toHaveBeenCalled();
  });

  it('deletes a saved profile once the confirmation is accepted', async () => {
    mockListCustomProfiles.mockResolvedValue([namedProfile]);
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('Low latency')).toBeInTheDocument();
    });

    await openRowActions(0);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.delete.label'));
    });
    expect(screen.getByTestId('confirmation-modal')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId('confirm-button'));
    });

    // The AIMProfileSet resource name the API deletes by, not the display name
    // the row shows.
    expect(mockDeleteCustomProfile).toHaveBeenCalledWith(
      'team-alpha',
      'model-a',
      'low-latency-7f3b6c8e',
    );
  });

  it('starts a deploy on the profile the row belongs to', async () => {
    mockListCustomProfiles.mockResolvedValue([defaultProfile, namedProfile]);
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('Low latency')).toBeInTheDocument();
    });

    await openRowActions(1);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.deploy.label'));
    });

    // The whole profile, so the deploy drawer can show it before its own read
    // of the list has landed.
    expect(mockOnDeployProfile).toHaveBeenCalledWith(namedProfile);
  });

  it('refuses to deploy a profile that has not reconciled', async () => {
    mockListCustomProfiles.mockResolvedValue([reconcilingProfile]);
    await renderTable();
    await waitFor(() => {
      expect(screen.getByText('Still preparing')).toBeInTheDocument();
    });

    await openRowActions(0);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.deploy.label'));
    });

    expect(mockOnDeployProfile).not.toHaveBeenCalled();
  });

  it('refuses to deploy a ready profile of a model that cannot serve it', async () => {
    mockListCustomProfiles.mockResolvedValue([defaultProfile, namedProfile]);
    await renderTable({ isModelDeployable: false });
    await waitFor(() => {
      expect(screen.getByText('Low latency')).toBeInTheDocument();
    });

    await openRowActions(1);
    await act(async () => {
      fireEvent.click(screen.getByText('actions.deploy.label'));
    });

    expect(mockOnDeployProfile).not.toHaveBeenCalled();
  });

  it('surfaces a load failure as an error toast', async () => {
    mockListCustomProfiles.mockRejectedValue(new Error('upstream down'));

    await renderTable();

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('notifications.loadError');
    });
  });
});
