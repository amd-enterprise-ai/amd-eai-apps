// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { QueryClient, useQueryClient } from '@tanstack/react-query';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { Mock } from 'vitest';

import { DeployProfileFields } from '@/components/features/models/DeployProfileFields';
import wrapper from '@/__tests__/ProviderWrapper';
import { listCustomProfiles } from '@/lib/app/custom-profiles';
import type { CustomProfileResponse } from '@/lib/app/custom-profiles';

vi.mock('@/lib/app/custom-profiles', async (importOriginal) => ({
  ...(await importOriginal()),
  listCustomProfiles: vi.fn(),
}));

// React Aria measures layout to build its listbox, which jsdom cannot do, so
// the real Select renders no options. Stand-in renders items as buttons.
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  const React = await vi.importActual<typeof import('react')>('react');

  const itemKey = (item: { key: React.Key | null }) =>
    String(item.key).replace(/^\.\$/, '');

  const MockSelect = ({
    children,
    selectedKeys,
    onSelectionChange,
    disabledKeys,
    bottomContent,
    isDisabled,
    isInvalid,
    errorMessage,
    placeholder,
    ...rest
  }: any) => {
    const items = React.Children.toArray(children) as Array<
      React.ReactElement<any> & { key: React.Key | null }
    >;
    const disabled = new Set((disabledKeys ?? []) as string[]);
    const selected = String(Array.from(selectedKeys ?? [])[0] ?? '');
    return React.createElement(
      'div',
      { 'data-testid': rest['data-testid'] },
      React.createElement(
        'button',
        { type: 'button', disabled: Boolean(isDisabled) },
        selected || placeholder,
      ),
      items.map((item) =>
        React.createElement(
          'button',
          {
            key: itemKey(item),
            type: 'button',
            'data-testid': item.props['data-testid'],
            'aria-disabled': disabled.has(itemKey(item)) ? 'true' : 'false',
            onClick: () =>
              disabled.has(itemKey(item))
                ? undefined
                : onSelectionChange?.(new Set([itemKey(item)])),
          },
          item.props.children,
        ),
      ),
      isInvalid ? React.createElement('span', {}, errorMessage) : null,
      bottomContent,
    );
  };

  return {
    ...actual,
    Select: MockSelect,
    SelectItem: ({ children }: { children: React.ReactNode }) => children,
  };
});

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

type ProfileForm = { profileName?: string; profileReady?: boolean };

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

let form: UseFormReturn<ProfileForm>;
let queryClient: QueryClient;

type HarnessProps = {
  isDisabled?: boolean;
  initialProfile?: CustomProfileResponse;
};

const Harness = ({ isDisabled, initialProfile }: HarnessProps) => {
  form = useForm<ProfileForm>({
    defaultValues: { profileName: '', profileReady: false },
  });
  queryClient = useQueryClient();
  return (
    <DeployProfileFields
      form={form}
      project="project1"
      modelId="model-1"
      modelName="Model one"
      initialProfile={initialProfile}
      isDisabled={isDisabled}
    />
  );
};

const renderFields = (props: HarnessProps = {}) =>
  render(<Harness {...props} />, { wrapper });

const trigger = () =>
  within(screen.getByTestId('deploy-profile-select')).getAllByRole('button')[0];

describe('DeployProfileFields', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createdProfileRef.current = null;
    (listCustomProfiles as Mock).mockResolvedValue([
      defaultProfile,
      fastProfile,
    ]);
  });

  it('starts on the Default, which is what an unqualified deploy would serve', async () => {
    renderFields();
    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('default');
    });
    expect(form.getValues('profileReady')).toBe(true);
  });

  it('stays on the Default while it reconciles rather than moving to a ready sibling', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([
      { ...defaultProfile, status: { state: 'Pending', message: '' } },
      fastProfile,
    ]);
    renderFields();

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('default');
    });
    expect(form.getValues('profileReady')).toBe(false);
    // The option itself is what says so now, in place of a standing alert.
    expect(
      screen.getByTestId('deploy-profile-option-default'),
    ).toHaveTextContent('unavailable');
  });

  it('starts on the profile the deploy was begun from', async () => {
    renderFields({ initialProfile: fastProfile });

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('fast');
    });
    expect(form.getValues('profileReady')).toBe(true);
  });

  it('keeps the profile it was started from when no refresh carries it yet', async () => {
    // A profile saved for deploying is not listed for a refresh or two, and
    // falling back to the Default would deploy something else entirely.
    renderFields({
      initialProfile: profileRow({
        name: 'brand-new',
        displayName: 'Brand new',
        status: { state: 'Pending', message: '' },
      }),
    });

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('brand-new');
    });
    expect(form.getValues('profileReady')).toBe(false);
    expect(
      await screen.findByTestId('deploy-profile-option-brand-new'),
    ).toBeInTheDocument();
  });

  it('lets the list speak for the profile it was started from once it lands', async () => {
    const brandNew = profileRow({
      name: 'brand-new',
      displayName: 'Brand new',
    });
    renderFields({
      initialProfile: {
        ...brandNew,
        status: { state: 'Pending', message: '' },
      } as CustomProfileResponse,
    });
    await waitFor(() => {
      expect(form.getValues('profileReady')).toBe(false);
    });

    (listCustomProfiles as Mock).mockResolvedValue([defaultProfile, brandNew]);
    await queryClient.invalidateQueries();

    await waitFor(() => {
      expect(form.getValues('profileReady')).toBe(true);
    });
    expect(form.getValues('profileName')).toBe('brand-new');
  });

  it('starts on a ready profile when the model has no Default', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([fastProfile]);
    renderFields();

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('fast');
    });
  });

  it('summarises what each profile runs alongside its name', async () => {
    renderFields();

    const option = await screen.findByTestId('deploy-profile-option-fast');
    expect(option).toHaveTextContent('High speed');
    expect(option).toHaveTextContent('MI300X');
    expect(option).toHaveTextContent('fp8');
  });

  it('offers a profile that is not ready as unavailable', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([
      defaultProfile,
      unreadyProfile,
    ]);
    renderFields();

    const option = await screen.findByTestId('deploy-profile-option-pending');
    expect(option).toHaveAttribute('aria-disabled', 'true');
    expect(option).toHaveTextContent('unavailable');
  });

  it('takes the profile the user picks', async () => {
    renderFields();

    fireEvent.click(await screen.findByTestId('deploy-profile-option-fast'));

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('fast');
    });
  });

  it('describes what the selected profile will run', async () => {
    renderFields();

    const details = await screen.findByTestId('deploy-profile-details');
    expect(within(details).getByText('MI300X')).toBeInTheDocument();
    expect(within(details).getByText('fp8')).toBeInTheDocument();
    expect(within(details).getByText('2')).toBeInTheDocument();
    expect(
      within(details).getByText('max-model-len: 4096'),
    ).toBeInTheDocument();
    expect(within(details).getByText('VLLM_USE_V1: 1')).toBeInTheDocument();
  });

  it('selects nothing when no profile is ready', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([unreadyProfile]);
    renderFields();

    const option = await screen.findByTestId('deploy-profile-option-pending');
    expect(option).toHaveAttribute('aria-disabled', 'true');
    expect(form.getValues('profileName')).toBe('');
  });

  it('starts on the Default as soon as the list carries one', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([]);
    renderFields();

    await waitFor(() => {
      expect(trigger()).not.toBeDisabled();
    });
    expect(form.getValues('profileName')).toBe('');

    (listCustomProfiles as Mock).mockResolvedValue([defaultProfile]);
    await queryClient.invalidateQueries();

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('default');
    });
    expect(form.getValues('profileReady')).toBe(true);
  });

  it('stays usable with no profiles so a first one can be added', async () => {
    (listCustomProfiles as Mock).mockResolvedValue([]);
    renderFields();

    await waitFor(() => {
      expect(trigger()).not.toBeDisabled();
    });
    expect(screen.getByTestId('deploy-profile-add-new')).toBeInTheDocument();
  });

  it('adopts a profile created from the selector', async () => {
    createdProfileRef.current = profileRow({
      name: 'brand-new',
      displayName: 'Brand new',
    });
    renderFields();

    fireEvent.click(await screen.findByTestId('deploy-profile-add-new'));
    fireEvent.click(await screen.findByTestId('create-profile-stub'));

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('brand-new');
    });
    expect(form.getValues('profileReady')).toBe(true);
  });

  it('adopts a created profile that has not reconciled, but not as deployable', async () => {
    createdProfileRef.current = profileRow({
      name: 'brand-new',
      displayName: 'Brand new',
      status: { state: '', message: '' },
    });
    renderFields();

    fireEvent.click(await screen.findByTestId('deploy-profile-add-new'));
    fireEvent.click(await screen.findByTestId('create-profile-stub'));

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('brand-new');
    });
    expect(form.getValues('profileReady')).toBe(false);
  });

  it('stops holding back a created profile once it has reconciled', async () => {
    const brandNew = profileRow({
      name: 'brand-new',
      displayName: 'Brand new',
    });
    createdProfileRef.current = {
      ...brandNew,
      status: { state: '', message: '' },
    } as CustomProfileResponse;
    renderFields();

    fireEvent.click(await screen.findByTestId('deploy-profile-add-new'));
    fireEvent.click(await screen.findByTestId('create-profile-stub'));
    await waitFor(() => {
      expect(form.getValues('profileReady')).toBe(false);
    });

    (listCustomProfiles as Mock).mockResolvedValue([defaultProfile, brandNew]);
    await queryClient.invalidateQueries();

    await waitFor(() => {
      expect(form.getValues('profileReady')).toBe(true);
    });
    expect(form.getValues('profileName')).toBe('brand-new');
  });

  it('moves off a selection whose profile has gone away', async () => {
    renderFields();
    fireEvent.click(await screen.findByTestId('deploy-profile-option-fast'));
    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('fast');
    });

    (listCustomProfiles as Mock).mockResolvedValue([defaultProfile]);
    await queryClient.invalidateQueries();

    await waitFor(() => {
      expect(form.getValues('profileName')).toBe('default');
    });
    expect(form.getValues('profileReady')).toBe(true);
  });

  it('stops offering a new profile while a deploy is in flight', async () => {
    renderFields({ isDisabled: true });

    await waitFor(() => {
      expect(screen.getByTestId('deploy-profile-add-new')).toBeDisabled();
    });
  });

  it('reports a failed profile read', async () => {
    (listCustomProfiles as Mock).mockRejectedValue(new Error('boom'));
    renderFields();

    expect(
      await screen.findByTestId('deploy-profile-load-error'),
    ).toBeInTheDocument();
  });
});
