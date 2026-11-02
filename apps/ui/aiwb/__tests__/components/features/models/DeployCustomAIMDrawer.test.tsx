// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { Mock } from 'vitest';

import { DeployCustomAIMDrawer } from '@/components/features/models/DeployCustomAIMDrawer';
import wrapper from '@/__tests__/ProviderWrapper';
import { deployInference } from '@/lib/app/inference';
import { listCustomProfiles } from '@/lib/app/custom-profiles';
import type { CustomProfileResponse } from '@/lib/app/custom-profiles';
import { AIMDeployPayload } from '@/types/aims';
import { Model } from '@/types/models';
import {
  invalidateQueriesSpy,
  wrapQueryClientWithInvalidateSpy,
} from '@/__tests__/testUtils/queryClientSpy';

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return {
    ...actual,
    useQueryClient: () =>
      wrapQueryClientWithInvalidateSpy(actual.useQueryClient()),
  };
});

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
};

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => ({
    toast: mockToast,
  }),
}));

vi.mock('@/lib/app/inference', () => ({
  deployInference: vi.fn(),
}));

vi.mock('@/lib/app/custom-profiles', async (importOriginal) => ({
  ...(await importOriginal()),
  listCustomProfiles: vi.fn(),
}));

// Stubbed: only its onCreated callback matters here.
const { createdProfileRef } = vi.hoisted(() => ({
  createdProfileRef: { current: null as CustomProfileResponse | null },
}));

vi.mock(
  '@/components/features/models/CustomProfiles/CustomProfileDrawer',
  () => ({
    CustomProfileDrawer: ({
      onCreated,
    }: {
      onCreated?: (profile: CustomProfileResponse) => void;
    }) => (
      <button
        type="button"
        data-testid="create-profile-stub"
        onClick={() => onCreated?.(createdProfileRef.current!)}
      >
        create
      </button>
    ),
  }),
);

const profileRow = (
  overrides: Partial<CustomProfileResponse> & { name: string },
): CustomProfileResponse =>
  ({
    displayName: overrides.name,
    isDefault: false,
    resourceName: `${overrides.name}-resource`,
    inUseBy: [],
    selector: {},
    customProfile: {},
    status: { state: 'Ready', message: '' },
    profile: {
      metadata: { name: `${overrides.name}-derived` },
      spec: {
        metric: 'throughput',
        precision: 'fp8',
        acceleratorModel: 'MI300X',
        acceleratorCount: 2,
        engineArgs: { 'max-model-len': 4096 },
        engineEnv: { VLLM_USE_V1: '1' },
      },
      status: { status: 'Ready' },
    },
    ...overrides,
  }) as unknown as CustomProfileResponse;

const defaultProfile = profileRow({
  name: 'default',
  displayName: 'Default',
  isDefault: true,
});
const fastProfile = profileRow({ name: 'fast', displayName: 'High speed' });
const unreadyProfile = profileRow({
  name: 'pending',
  displayName: 'Still preparing',
  status: { state: 'Pending', message: 'Reconciling' },
});

const model: Model = {
  id: '1',
  name: 'model-1',
  canonicalName: 'org/model-1',
  resourceName: 'model-1',
  status: 'Complete',
};
const namespace = 'test-namespace';
const sourceUri = 'hf://org/model-1';
const onClose = vi.fn();

let queryClient: QueryClient;

const CaptureQueryClient = () => {
  queryClient = useQueryClient();
  return null;
};

const renderDrawer = (
  overrides: Partial<Parameters<typeof DeployCustomAIMDrawer>[0]> = {},
) =>
  render(
    <>
      <CaptureQueryClient />
      <DeployCustomAIMDrawer
        model={model}
        namespace={namespace}
        sourceUri={sourceUri}
        isOpen={true}
        onClose={onClose}
        {...overrides}
      />
    </>,
    { wrapper },
  );

describe('DeployCustomAIMDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    invalidateQueriesSpy.mockClear();
    (deployInference as Mock).mockResolvedValue({});
    (listCustomProfiles as Mock).mockResolvedValue([defaultProfile]);
    createdProfileRef.current = null;
  });

  it('renders drawer when open', () => {
    renderDrawer();
    expect(screen.getByText('deployCustomAIMDrawer.title')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    renderDrawer({ isOpen: false });
    expect(
      screen.queryByText('deployCustomAIMDrawer.title'),
    ).not.toBeInTheDocument();
  });

  it('renders the header with model name, deploy target and source URI', () => {
    renderDrawer();
    expect(screen.getByText(model.name)).toBeInTheDocument();
    // The deploy-target namespace is interpolated into this label (the i18n mock
    // returns the key, so assert the label is present rather than the raw value).
    expect(
      screen.getByText('deployCustomAIMDrawer.header.deployingInto'),
    ).toBeInTheDocument();
    expect(screen.getByText(sourceUri)).toBeInTheDocument();
  });

  it('renders the display-name input', () => {
    renderDrawer();
    expect(
      screen.getByPlaceholderText(
        'deployCustomAIMDrawer.fields.displayName.placeholder',
      ),
    ).toBeInTheDocument();
  });

  it('offers no profile selection for a model without profiles', () => {
    renderDrawer();
    expect(screen.getByTestId('runtime-profile-slot')).toBeInTheDocument();
    expect(
      screen.queryByTestId('deploy-profile-select'),
    ).not.toBeInTheDocument();
    expect(listCustomProfiles).not.toHaveBeenCalled();
  });

  it('reveals autoscaling fields when the toggle is enabled', async () => {
    renderDrawer();
    expect(
      screen.queryByTestId('replica-range-slider'),
    ).not.toBeInTheDocument();
    const toggle = screen
      .getByTestId('autoscaling-toggle')
      .querySelector('input')!;
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(screen.getByTestId('replica-range-slider')).toBeInTheDocument();
    });
  });

  it('deploys with the expected payload and omits profile override fields', async () => {
    renderDrawer();
    fireEvent.submit(document.querySelector('form')!);
    await waitFor(() => {
      expect(deployInference).toHaveBeenCalledWith(namespace, {
        model: model.resourceName,
        displayName: undefined,
        replicas: 1,
      });
    });
    const payload = (deployInference as Mock).mock.calls[0][1];
    expect(payload).not.toHaveProperty('nodePool');
    // Runtime config is resolved from the model, never sent in the deploy body,
    // and profileName is refused for a model without selectable profiles.
    const profileOverrideKeys = [
      'metric',
      'precision',
      'gpuModel',
      'gpuCount',
      'profileName',
      'imagePullSecrets',
      'hfToken',
    ] as const satisfies ReadonlyArray<keyof AIMDeployPayload>;
    for (const key of profileOverrideKeys) {
      expect(payload).not.toHaveProperty(key);
    }
  });

  it('shows success toast and closes on successful deploy', async () => {
    renderDrawer();
    fireEvent.submit(document.querySelector('form')!);
    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalledWith(
        'deployCustomAIMDrawer.notifications.success',
      );
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('invalidates the inferenceModel cache after a successful deploy', async () => {
    renderDrawer();

    fireEvent.submit(document.querySelector('form')!);

    await waitFor(() => {
      expect(invalidateQueriesSpy).toHaveBeenCalledWith({
        queryKey: ['inferenceModel'],
      });
    });
    // Existing per-namespace services cache is still invalidated alongside.
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({
      queryKey: ['project', namespace, 'aim-services'],
    });
  });

  it('shows error toast and keeps the drawer open on failed deploy', async () => {
    (deployInference as Mock).mockRejectedValue(new Error('Deploy failed'));
    renderDrawer();
    fireEvent.submit(document.querySelector('form')!);
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalled();
    });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText('deployCustomAIMDrawer.title')).toBeInTheDocument();
  });
});

// Picking is covered in DeployProfileFields.test.tsx; these cover what the
// drawer does with the resulting selection.
describe('DeployCustomAIMDrawer profile selection', () => {
  const renderWithProfiles = () =>
    renderDrawer({ supportsProfileSelection: true });

  const deployedProfileName = () =>
    (deployInference as Mock).mock.calls[0][1].profileName;

  beforeEach(() => {
    vi.clearAllMocks();
    invalidateQueriesSpy.mockClear();
    (deployInference as Mock).mockResolvedValue({});
    (listCustomProfiles as Mock).mockResolvedValue([
      defaultProfile,
      fastProfile,
    ]);
    createdProfileRef.current = null;
  });

  it('deploys the Default when the user picks nothing', async () => {
    renderWithProfiles();
    await waitFor(() => {
      expect(listCustomProfiles).toHaveBeenCalledWith(
        namespace,
        model.resourceName,
      );
    });
    await screen.findByTestId('deploy-profile-details');

    fireEvent.submit(document.querySelector('form')!);

    await waitFor(() => {
      expect(deployedProfileName()).toBe('default');
    });
  });

  it('deploys a profile other than the Default when that is the selection', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([fastProfile]);
    renderWithProfiles();
    await screen.findByTestId('deploy-profile-details');

    fireEvent.submit(document.querySelector('form')!);

    await waitFor(() => {
      expect(deployedProfileName()).toBe('fast');
    });
  });

  it('refuses to deploy the Default while it is still reconciling', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([
      { ...defaultProfile, status: { state: 'Pending', message: '' } },
      fastProfile,
    ]);
    renderWithProfiles();
    await screen.findByTestId('deploy-profile-details');

    // Offered as unavailable in the list, but still shown as the selection.
    expect(screen.getByTestId('deploy-profile-select').textContent).toContain(
      'Default',
    );

    fireEvent.submit(document.querySelector('form')!);

    await waitFor(() => {
      expect(
        screen.getByText(
          'deployCustomAIMDrawer.fields.profile.errors.notReady',
        ),
      ).toBeInTheDocument();
    });
    expect(deployInference).not.toHaveBeenCalled();
  });

  it('refuses to deploy when no profile is ready', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([unreadyProfile]);
    renderWithProfiles();
    // An unready-only list leaves nothing to preselect, so there is no selection
    // to wait for — only the read itself.
    await waitFor(() => {
      expect(listCustomProfiles).toHaveBeenCalled();
    });

    fireEvent.submit(document.querySelector('form')!);

    await waitFor(() => {
      expect(
        screen.getByText(
          'deployCustomAIMDrawer.fields.profile.errors.required',
        ),
      ).toBeInTheDocument();
    });
    expect(deployInference).not.toHaveBeenCalled();
  });

  it('stops refusing the chosen profile once it reconciles again', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([defaultProfile]);
    renderWithProfiles();
    await screen.findByTestId('deploy-profile-details');

    (listCustomProfiles as Mock).mockResolvedValue([
      { ...defaultProfile, status: { state: 'Pending', message: '' } },
    ]);
    await queryClient.invalidateQueries();
    await waitFor(() => {
      expect(listCustomProfiles).toHaveBeenCalledTimes(2);
    });

    fireEvent.submit(document.querySelector('form')!);
    const notReady = 'deployCustomAIMDrawer.fields.profile.errors.notReady';
    await waitFor(() => {
      expect(screen.getByText(notReady)).toBeInTheDocument();
    });
    expect(deployInference).not.toHaveBeenCalled();

    (listCustomProfiles as Mock).mockResolvedValue([defaultProfile]);
    await queryClient.invalidateQueries();

    await waitFor(() => {
      expect(screen.queryByText(notReady)).not.toBeInTheDocument();
    });
  });
});
