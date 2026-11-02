// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CustomProfileDrawer } from '@/components/features/models/CustomProfiles/CustomProfileDrawer';
import type { RuntimeProfileCatalogState } from '@/hooks/useRuntimeProfileCatalog';
import {
  createCustomProfile,
  CustomProfileConflictError,
  listCustomProfiles,
  updateCustomProfile,
  type CustomProfileResponse,
} from '@/lib/app/custom-profiles';

import wrapper from '@/__tests__/ProviderWrapper';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockToast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => ({ toast: mockToast }),
}));

vi.mock('@/lib/app/custom-profiles', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/app/custom-profiles')>();
  return {
    ...actual,
    listCustomProfiles: vi.fn(),
    createCustomProfile: vi.fn(),
    updateCustomProfile: vi.fn(),
  };
});

const catalog = {
  imageFamilies: [
    {
      familyId: 'aim-base',
      displayName: 'aim-base',
      repository: 'amdenterpriseai/aim-base',
      tags: ['0.11'],
    },
  ],
  accelerators: [
    {
      deviceId: '74a1',
      productName: 'AMD Instinct MI300X',
      allocatableCount: 8,
      acceleratorModel: 'MI300X',
    },
  ],
  runtimeOptions: null as RuntimeProfileCatalogState['runtimeOptions'],
  isLoading: false,
  isError: false,
  error: null,
  invalidateCatalog: vi.fn(),
};

vi.mock('@/hooks/useRuntimeProfileCatalog', () => ({
  useRuntimeProfileCatalog: () => catalog,
}));

// The catalog-driven selectors have their own tests, and the real ones seed their
// defaults from the catalog. The stub does the same so the form reaches a
// submittable state, keeping this test on the drawer's own behaviour. It has to
// register the fields as the real inputs do, because the shared form unregisters
// on unmount and drops unregistered values from the submitted set.
vi.mock('@/components/features/models/runtime-profile', async () => {
  const React = await import('react');
  const fields = [
    'containerImage',
    'containerVersion',
    'acceleratorType',
    'accelerator',
    'acceleratorCount',
    'modelPrecision',
  ];
  return {
    RuntimeProfileFields: ({ form }: { form: any }) => {
      React.useEffect(() => {
        for (const field of fields) {
          form.register(field);
        }
        if (!form.getValues('accelerator')) {
          form.setValue('containerImage', 'aim-base');
          form.setValue('containerVersion', '0.11');
          form.setValue('accelerator', '74a1');
        }
      });
      return <div data-testid="runtime-profile-fields-stub" />;
    },
  };
});

const mockListCustomProfiles = vi.mocked(listCustomProfiles);
const mockCreateCustomProfile = vi.mocked(createCustomProfile);
const mockUpdateCustomProfile = vi.mocked(updateCustomProfile);
const onClose = vi.fn();

const savedProfile: CustomProfileResponse = {
  name: 'high-speed-7f3b6c8e',
  displayName: 'High speed',
  isDefault: false,
  resourceName: 'high-speed-7f3b6c8e',
  inUseBy: [],
  selector: {
    acceleratorModel: 'MI300X',
    acceleratorCount: 8,
    metric: 'latency',
    precision: 'fp8',
  },
  customProfile: {
    image: 'amdenterpriseai/aim-base:0.11',
    engineArgs: { 'max-model-len': 32768 },
  },
};

const defaultProfile: CustomProfileResponse = {
  name: 'default',
  displayName: 'Default',
  isDefault: true,
  resourceName: 'default',
  inUseBy: [],
  selector: {
    acceleratorModel: 'MI300X',
    acceleratorCount: 4,
    metric: 'throughput',
    precision: 'fp8',
  },
  customProfile: {
    image: 'amdenterpriseai/aim-base:0.11',
    engineArgs: { 'max-model-len': 8192 },
  },
};

const props = {
  isOpen: true,
  onClose,
  project: 'team-alpha',
  modelId: 'model-a',
  modelName: 'Llama 3.1 8B',
};

const renderDrawer = async (
  profileName?: string,
  extra: { onSaveAndDeploy?: (profile: CustomProfileResponse) => void } = {},
) => {
  await act(async () => {
    render(
      <CustomProfileDrawer {...props} profileName={profileName} {...extra} />,
      { wrapper },
    );
  });
};

const pressButton = async (label: string) => {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: label }));
  });
};

const nameInput = () =>
  screen.getByPlaceholderText('fields.displayName.placeholder');

const submit = () => {
  fireEvent.submit(document.querySelector('form')!);
};

beforeEach(() => {
  vi.clearAllMocks();
  catalog.isError = false;
  catalog.isLoading = false;
  catalog.runtimeOptions = null;
  mockListCustomProfiles.mockResolvedValue([savedProfile]);
  mockCreateCustomProfile.mockResolvedValue(savedProfile);
  mockUpdateCustomProfile.mockResolvedValue(savedProfile);
});

describe('CustomProfileDrawer', () => {
  it('names the model it is creating a profile for', async () => {
    await renderDrawer();

    expect(screen.getByTestId('custom-profile-heading')).toHaveTextContent(
      'heading.create',
    );
    expect(nameInput()).toHaveValue('');
  });

  it('creates a profile from the entered values', async () => {
    await renderDrawer();

    fireEvent.change(nameInput(), { target: { value: 'Low latency' } });
    submit();

    await waitFor(() => {
      expect(mockCreateCustomProfile).toHaveBeenCalledWith(
        'team-alpha',
        'model-a',
        expect.objectContaining({
          displayName: 'Low latency',
          acceleratorModel: 'MI300X',
          precision: 'bf16',
          metric: 'latency',
          image: 'amdenterpriseai/aim-base:0.11',
        }),
      );
    });
    expect(mockToast.success).toHaveBeenCalledWith('notifications.created');
    expect(onClose).toHaveBeenCalled();
  });

  it('hands a profile straight to a deploy when saved that way', async () => {
    const onSaveAndDeploy = vi.fn();
    await renderDrawer(undefined, { onSaveAndDeploy });

    fireEvent.change(nameInput(), { target: { value: 'Low latency' } });
    await pressButton('actions.saveAndDeploy');

    await waitFor(() => {
      expect(onSaveAndDeploy).toHaveBeenCalledWith(savedProfile);
    });
    expect(mockCreateCustomProfile).toHaveBeenCalled();
  });

  it('leaves a plain save out of a deploy', async () => {
    const onSaveAndDeploy = vi.fn();
    await renderDrawer(undefined, { onSaveAndDeploy });

    fireEvent.change(nameInput(), { target: { value: 'Low latency' } });
    await pressButton('actions.save');

    await waitFor(() => {
      expect(mockCreateCustomProfile).toHaveBeenCalled();
    });
    expect(onSaveAndDeploy).not.toHaveBeenCalled();
  });

  it('forgets a refused deploy so the next save is only a save', async () => {
    const onSaveAndDeploy = vi.fn();
    await renderDrawer(undefined, { onSaveAndDeploy });

    await pressButton('actions.saveAndDeploy');
    await waitFor(() => {
      expect(screen.getByText('errors.nameRequired')).toBeInTheDocument();
    });
    expect(mockCreateCustomProfile).not.toHaveBeenCalled();

    fireEvent.change(nameInput(), { target: { value: 'Low latency' } });
    await pressButton('actions.save');

    await waitFor(() => {
      expect(mockCreateCustomProfile).toHaveBeenCalled();
    });
    expect(onSaveAndDeploy).not.toHaveBeenCalled();
  });

  it('does not offer to deploy a profile it is only editing', async () => {
    await renderDrawer(savedProfile.name, { onSaveAndDeploy: vi.fn() });

    expect(
      screen.queryByRole('button', { name: 'actions.saveAndDeploy' }),
    ).not.toBeInTheDocument();
  });

  it('prefills from the saved profile and updates it in place', async () => {
    await renderDrawer(savedProfile.name);

    await waitFor(() => {
      expect(nameInput()).toHaveValue('High speed');
    });
    expect(screen.getByTestId('custom-profile-heading')).toHaveTextContent(
      'heading.edit',
    );
    expect(screen.getByTestId('custom-profile-engine-args-yaml')).toHaveValue(
      'max-model-len: 32768',
    );

    submit();

    await waitFor(() => {
      expect(mockUpdateCustomProfile).toHaveBeenCalledWith(
        'team-alpha',
        'model-a',
        'high-speed-7f3b6c8e',
        expect.objectContaining({
          displayName: 'High speed',
          precision: 'fp8',
          acceleratorCount: 8,
        }),
      );
    });
    expect(mockCreateCustomProfile).not.toHaveBeenCalled();
  });

  it('starts a new profile from the Default profile axes', async () => {
    // Only a four-axis tuple that resolves to exactly one base profile is
    // accepted, and the per-axis option lists cannot say which values coexist.
    // The Default was derived from one base profile, so an untouched form saves.
    mockListCustomProfiles.mockResolvedValue([defaultProfile, savedProfile]);
    await renderDrawer();
    await waitFor(() => {
      expect(mockListCustomProfiles).toHaveBeenCalled();
    });

    fireEvent.change(nameInput(), { target: { value: 'Long context' } });
    submit();

    await waitFor(() => {
      expect(mockCreateCustomProfile).toHaveBeenCalledWith(
        'team-alpha',
        'model-a',
        expect.objectContaining({
          displayName: 'Long context',
          acceleratorModel: 'MI300X',
          acceleratorCount: 4,
          precision: 'fp8',
          metric: 'throughput',
          // The Default's own engine arguments stay behind: a new profile starts
          // from its axes, not from overrides the user never asked for.
          customProfile: { acceleratorType: 'gpu' },
        }),
      );
    });
  });

  it('creates with a metric the base template actually emits', async () => {
    // The API resolves the four axes to exactly one base profile, so a base that
    // emits only throughput refuses the static default metric. The form has to
    // follow the project's matrix rather than offer both metrics regardless.
    catalog.runtimeOptions = {
      metrics: ['throughput'],
      profilesAvailable: false,
    };
    await renderDrawer();

    fireEvent.change(nameInput(), { target: { value: 'High throughput' } });
    submit();

    await waitFor(() => {
      expect(mockCreateCustomProfile).toHaveBeenCalledWith(
        'team-alpha',
        'model-a',
        expect.objectContaining({ metric: 'throughput' }),
      );
    });
  });

  it('narrows the metric to the one the selected combination emits', async () => {
    // The seeded accelerator/count/precision tuple only coexists with throughput
    // in the matrix, so the static default metric (latency) must give way even
    // though the project as a whole offers both metrics.
    catalog.runtimeOptions = {
      acceleratorModels: ['MI300X'],
      precisions: ['bf16'],
      acceleratorCounts: [1],
      optimizationClasses: [],
      metrics: ['latency', 'throughput'],
      combinations: [
        {
          acceleratorModel: 'MI300X',
          acceleratorCount: 1,
          precision: 'bf16',
          metric: 'throughput',
        },
      ],
      profilesAvailable: true,
    };
    await renderDrawer();

    fireEvent.change(nameInput(), { target: { value: 'Only throughput' } });
    submit();

    await waitFor(() => {
      expect(mockCreateCustomProfile).toHaveBeenCalledWith(
        'team-alpha',
        'model-a',
        expect.objectContaining({ metric: 'throughput' }),
      );
    });
  });

  it('keeps Save disabled until the runtime catalog is usable', async () => {
    // The runtime controls are unmounted while the catalog is loading or failed,
    // so a save then fails validation on required fields whose error UI is
    // unmounted too, and the button would look inert.
    catalog.isLoading = true;
    let rerender: ((ui: React.ReactElement) => void) | undefined;
    await act(async () => {
      ({ rerender } = render(<CustomProfileDrawer {...props} />, { wrapper }));
    });
    const save = () => screen.getByRole('button', { name: 'actions.save' });

    expect(save()).toBeDisabled();

    catalog.isLoading = false;
    catalog.isError = true;
    await act(async () => {
      rerender!(<CustomProfileDrawer {...props} />);
    });

    expect(save()).toBeDisabled();

    catalog.isError = false;
    await act(async () => {
      rerender!(<CustomProfileDrawer {...props} />);
    });

    expect(save()).toBeEnabled();
  });

  it('waits for a failed catalog to recover before prefilling', async () => {
    catalog.isError = true;
    let rerender: ((ui: React.ReactElement) => void) | undefined;
    await act(async () => {
      ({ rerender } = render(
        <CustomProfileDrawer {...props} profileName={savedProfile.name} />,
        { wrapper },
      ));
    });

    // Wait for the saved profile to arrive, so the drawer has something it could
    // prefill from and the assertion is about the catalog state rather than about
    // a query still in flight.
    await waitFor(() => {
      expect(mockListCustomProfiles).toHaveBeenCalled();
    });
    // A failed catalog leaves the option lists empty, so mapping the saved
    // profile against them now would drop its selections for good: the prefill
    // runs once, and would refuse to run again after a successful retry.
    expect(nameInput()).toHaveValue('');

    catalog.isError = false;
    await act(async () => {
      rerender!(
        <CustomProfileDrawer {...props} profileName={savedProfile.name} />,
      );
    });

    await waitFor(() => {
      expect(nameInput()).toHaveValue('High speed');
    });
    expect(screen.getByTestId('custom-profile-engine-args-yaml')).toHaveValue(
      'max-model-len: 32768',
    );
  });

  it('rejects a duplicate name where the locale lowercases differently', async () => {
    // Stands in for a Turkish-locale browser, which lowercases 'I' to 'ı'. The
    // check has to agree with the server's locale-independent comparison, or the
    // user is told the name is free and then refused on save.
    const lowercase = String.prototype.toLocaleLowerCase;
    String.prototype.toLocaleLowerCase = function (this: string) {
      return lowercase.call(this, 'tr');
    };
    try {
      await renderDrawer();
      await waitFor(() => {
        expect(mockListCustomProfiles).toHaveBeenCalled();
      });

      fireEvent.change(nameInput(), { target: { value: 'HIGH SPEED' } });
      submit();

      await waitFor(() => {
        expect(screen.getByText('errors.nameTaken')).toBeInTheDocument();
      });
      expect(mockCreateCustomProfile).not.toHaveBeenCalled();
    } finally {
      String.prototype.toLocaleLowerCase = lowercase;
    }
  });

  it('reads the list screen cache rather than refetching it when opened', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(
      ['project', 'team-alpha', 'custom-model', 'model-a', 'profiles'],
      [savedProfile],
    );

    await act(async () => {
      render(
        <CustomProfileDrawer {...props} profileName={savedProfile.name} />,
        {
          wrapper: ({ children }: { children: ReactNode }) => (
            <QueryClientProvider client={queryClient}>
              {children}
            </QueryClientProvider>
          ),
        },
      );
    });

    await waitFor(() => {
      expect(nameInput()).toHaveValue('High speed');
    });
    expect(mockListCustomProfiles).not.toHaveBeenCalled();
  });

  it('rejects a name a sibling profile already uses, before submitting', async () => {
    await renderDrawer();
    await waitFor(() => {
      expect(mockListCustomProfiles).toHaveBeenCalled();
    });

    fireEvent.change(nameInput(), { target: { value: 'high speed' } });
    submit();

    await waitFor(() => {
      expect(screen.getByText('errors.nameTaken')).toBeInTheDocument();
    });
    expect(mockCreateCustomProfile).not.toHaveBeenCalled();
  });

  it('rejects the reserved Default name, before submitting', async () => {
    await renderDrawer();

    fireEvent.change(nameInput(), { target: { value: 'Default' } });
    submit();

    await waitFor(() => {
      expect(screen.getByText('errors.nameReserved')).toBeInTheDocument();
    });
    expect(mockCreateCustomProfile).not.toHaveBeenCalled();
  });

  it('accepts the edited profile keeping its own name', async () => {
    await renderDrawer(savedProfile.name);

    await waitFor(() => {
      expect(nameInput()).toHaveValue('High speed');
    });

    expect(screen.queryByText('errors.nameTaken')).not.toBeInTheDocument();
  });

  it('requires a name', async () => {
    await renderDrawer();

    submit();

    await waitFor(() => {
      expect(screen.getByText('errors.nameRequired')).toBeInTheDocument();
    });
    expect(mockCreateCustomProfile).not.toHaveBeenCalled();
  });

  it('rejects engine arguments that are not a YAML mapping', async () => {
    await renderDrawer();

    fireEvent.change(nameInput(), { target: { value: 'Low latency' } });
    fireEvent.change(screen.getByTestId('custom-profile-engine-args-yaml'), {
      target: { value: '- not a mapping' },
    });
    submit();

    await waitFor(() => {
      expect(
        screen.getByText('errors.invalidEngineArgsYaml'),
      ).toBeInTheDocument();
    });
    expect(mockCreateCustomProfile).not.toHaveBeenCalled();
  });

  it('explains up front that an in-use profile cannot be changed', async () => {
    mockListCustomProfiles.mockResolvedValue([
      {
        ...savedProfile,
        inUseBy: [{ serviceId: 'svc-1', displayName: 'summarizer-prod' }],
      },
    ]);

    await renderDrawer(savedProfile.name);

    await waitFor(() => {
      expect(
        screen.getByTestId('custom-profile-in-use-notice'),
      ).toBeInTheDocument();
    });
    // Awaited so the async resolver and the mutation it would trigger settle
    // before asserting nothing was saved.
    await act(async () => {
      submit();
    });
    expect(mockUpdateCustomProfile).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('keeps the drawer open and reports a name taken between list and save', async () => {
    mockCreateCustomProfile.mockRejectedValue(
      new CustomProfileConflictError('name taken', []),
    );
    await renderDrawer();

    fireEvent.change(nameInput(), { target: { value: 'Low latency' } });
    submit();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'notifications.conflictName',
      );
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('names the blocking deployments when a save races a new deployment', async () => {
    mockUpdateCustomProfile.mockRejectedValue(
      new CustomProfileConflictError('in use', ['summarizer-prod']),
    );
    await renderDrawer(savedProfile.name);
    await waitFor(() => {
      expect(nameInput()).toHaveValue('High speed');
    });

    submit();

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'notifications.conflictInUse',
      );
    });
    expect(onClose).not.toHaveBeenCalled();
  });
});
