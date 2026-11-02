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
import { SecretUseCase } from '@amdenterpriseai/types';
import { focusManager } from '@tanstack/react-query';
import { DeployAIMWizard } from '@/components/features/models/DeployAIMWizard';
import { hasIncompatiblePersonalizationProfile } from '@/components/features/models/DeployAIMWizard/DeployAIMWizard';
import {
  mockAims,
  mockAggregatedAims,
  mockMixedSupportAggregatedAim,
} from '@/__mocks__/services/app/aims.data';
import wrapper from '@/__tests__/ProviderWrapper';
import { fetchProjectSecrets, createProjectSecret } from '@/lib/app/secrets';
import { Mock } from 'vitest';
import type { UseFormReturn } from 'react-hook-form';
import type {
  AdvancedProfileOptions,
  DeployAIMFormValues,
} from '@/components/features/models/DeployAIMWizard/types';
import { AIMClusterProfile, AIMService, ParsedAIM } from '@/types/aims';
import type { LoraAdapter } from '@/types/artifacts';
import * as aimsLib from '@/lib/app/aims';
import * as inferenceLib from '@/lib/app/inference';
import { listAllAdapterArtifacts } from '@/lib/app/artifacts';
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

vi.mock('@/components/shared/ModelIcons', () => ({
  ModelIcon: ({ iconName, width, height }: any) => (
    <div
      data-testid={`model-icon-${iconName || 'default'}`}
      style={{ width: `${width}px`, height: `${height}px` }}
    >
      {iconName || 'default'} icon
    </div>
  ),
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

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: 'test-project',
    projects: [{ id: 'test-project', name: 'Test Project' }],
  }),
}));

vi.mock('@/lib/app/secrets', () => ({
  fetchProjectSecrets: vi.fn(),
  createProjectSecret: vi.fn(),
}));

vi.mock('@/lib/app/artifacts', () => ({
  listAllAdapterArtifacts: vi.fn(),
}));

// Scoped to DeployAIMWizard's own payload-building wiring. Search/rank
// rendering behavior of the real table lives in
// LoraAdapterSelectionTable.test.tsx and toggle/rank-recompute behavior lives
// in PersonalizationStep.test.tsx; neither is duplicated here.
vi.mock('@/components/features/loras/LoraAdapterSelectionTable', () => ({
  LoraAdapterSelectionTable: ({
    adapters,
    selectedNames,
    onSelectionChange,
  }: {
    adapters: LoraAdapter[];
    selectedNames: string[];
    onSelectionChange: (names: string[]) => void;
  }) => (
    <div>
      {adapters.map((adapter) => (
        <button
          key={adapter.name}
          type="button"
          data-unservable={String(adapter.servable === false)}
          data-not-ready={String(adapter.readiness !== 'Ready')}
          onClick={() =>
            onSelectionChange(
              selectedNames.includes(adapter.name)
                ? selectedNames.filter((name) => name !== adapter.name)
                : [...selectedNames, adapter.name],
            )
          }
        >
          Select {adapter.displayName}
        </button>
      ))}
    </div>
  ),
}));

// The real Advanced profile table builds HeroUI Select collections, which the
// SelectItem mock below cannot satisfy. Pinning a profile and reading back the
// offered parameter values is all this suite needs from it; the table itself is
// covered by AdvancedProfileFields.test.tsx.
vi.mock(
  '@/components/features/models/DeployAIMWizard/AdvancedProfileFields',
  () => ({
    AdvancedProfileFields: ({
      form,
      advancedProfileOptions,
      filteredProfiles,
    }: {
      form: UseFormReturn<DeployAIMFormValues>;
      advancedProfileOptions: AdvancedProfileOptions;
      filteredProfiles: AIMClusterProfile[];
    }) => (
      <div>
        <div data-testid="advancedProfileParamPrecisions">
          {advancedProfileOptions.precisions.map((precision) => (
            <span key={precision}>{precision}</span>
          ))}
        </div>
        {advancedProfileOptions.gpuModels.map((gpuModel) => (
          <button
            key={gpuModel}
            type="button"
            onClick={() =>
              form.setValue('gpuModel', gpuModel, {
                shouldDirty: true,
                shouldValidate: true,
              })
            }
          >
            {`Set GPU ${gpuModel}`}
          </button>
        ))}
        {filteredProfiles.map((profile) => (
          <button
            key={profile.metadata.name}
            type="button"
            onClick={() =>
              form.setValue('profileName', profile.metadata.name, {
                shouldDirty: true,
                shouldValidate: true,
              })
            }
          >
            {`Pin ${profile.metadata.name}`}
          </button>
        ))}
      </div>
    ),
  }),
);

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const React = await import('react');
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();

  const FormSelectMock = ({
    form,
    name,
    children,
    onSelectionChange,
    label,
    placeholder,
    selectionMode,
    disallowEmptySelection: _dES,
    isDisabled,
    isRequired: _req,
    isInvalid: _inv,
    errorMessage: _err,
    description: _desc,
    ...rest
  }: any) => {
    const testId = rest['data-testid'];
    React.useEffect(() => {
      form?.register(name);
    }, [form, name]);
    const currentValue = form?.watch(name);

    const clickableItems = React.Children.map(children, (child: any) => {
      if (!React.isValidElement(child)) return child;
      const itemKey = child.key as string;
      return React.cloneElement(child as React.ReactElement<any>, {
        onItemSelect: () => {
          if (!isDisabled) {
            // Mirror the real FormSelect, which stores multi-select values as a
            // comma-joined string of toggled keys.
            const current = String(form?.getValues(name) ?? '')
              .split(',')
              .filter(Boolean);
            const next = current.includes(itemKey)
              ? current.filter((key) => key !== itemKey)
              : [...current, itemKey];
            form?.setValue(
              name,
              selectionMode === 'multiple' ? next.join(',') : itemKey,
              {
                shouldValidate: true,
                shouldDirty: true,
              },
            );
            onSelectionChange?.(new Set([itemKey]));
          }
        },
      });
    });

    const triggerSpans = React.Children.map(children, (child: any) => {
      if (!React.isValidElement(child)) return null;
      const selected = child.key === String(currentValue);
      return React.createElement(
        'span',
        {
          key: child.key,
          'data-trigger-item': 'true',
          'data-selected': selected ? 'true' : undefined,
        },
        (child as any).props.children,
      );
    });

    const selectedSpan = React.Children.toArray(children).find(
      (c: any) => React.isValidElement(c) && c.key === String(currentValue),
    ) as React.ReactElement<any> | undefined;
    const displayText =
      selectedSpan?.props?.children ??
      placeholder ??
      (typeof label === 'string' ? label : '');

    const labelId = testId ? `${testId}-label` : undefined;
    return React.createElement(
      React.Fragment,
      null,
      typeof label === 'string'
        ? React.createElement(
            'span',
            { id: labelId, 'data-select-label': 'true' },
            label,
          )
        : null,
      React.createElement(
        'button',
        {
          'data-testid': testId,
          'aria-label': typeof label === 'string' ? label : undefined,
          'aria-labelledby': labelId,
          type: 'button',
        },
        triggerSpans,
        React.createElement('span', { 'data-display': 'true' }, displayText),
      ),
      React.createElement(
        'div',
        { 'data-testid': testId ? `${testId}-items` : undefined },
        clickableItems,
      ),
    );
  };
  FormSelectMock.displayName = 'FormSelect';

  const SelectItemMock = ({
    children,
    onItemSelect,
    description: _d,
    ...rest
  }: any) =>
    React.createElement(
      'div',
      { ...rest, onClick: onItemSelect, role: 'option' },
      children,
    );
  SelectItemMock.displayName = 'SelectItem';

  const TabsMock = ({
    children,
    onSelectionChange: _oSC,
    selectedKey: _sk,
    defaultSelectedKey: _dsk,
    ...rest
  }: any) =>
    React.createElement(
      'div',
      { role: 'tablist', 'data-testid': rest['data-testid'] },
      children,
    );
  TabsMock.displayName = 'Tabs';

  const TabMock = ({ children, title: _title, ...rest }: any) =>
    React.createElement('div', { role: 'tab', ...rest }, children);
  TabMock.displayName = 'Tab';

  return {
    ...actual,
    FormSelect: FormSelectMock,
    SelectItem: SelectItemMock,
    Tabs: TabsMock,
    Tab: TabMock,
  };
});

const mockServiceProfiles: AIMClusterProfile[] = [
  {
    metadata: { name: 'profile-latency', labels: {} },
    spec: { aimId: 'test-model', modelName: 'test-model', metric: 'latency' },
    status: { status: 'Ready' },
  },
  {
    metadata: { name: 'profile-throughput', labels: {} },
    spec: {
      aimId: 'test-model',
      modelName: 'test-model',
      metric: 'throughput',
    },
    status: { status: 'Ready' },
  },
];

const aggregatedAimWithoutHf = (base = mockAggregatedAims[0]) => {
  const parsedNoHf = base.parsedAIMs.map((a) => ({
    ...a,
    isHfTokenRequired: false,
  }));
  return {
    ...base,
    parsedAIMs: parsedNoHf,
    latestAim: parsedNoHf[0],
    aggregated: { ...base.aggregated, isHfTokenRequired: false },
  };
};

const clickWizardNext = () => {
  fireEvent.click(screen.getByRole('button', { name: 'actions.next' }));
};

const advanceToPerformanceStep = async () => {
  await waitFor(() => {
    expect(
      screen.getByRole('button', { name: 'actions.next' }),
    ).not.toBeDisabled();
  });
  clickWizardNext();
  await waitFor(() => {
    expect(
      screen.getByText('deployAIM.fields.metric.title'),
    ).toBeInTheDocument();
  });
};

const advanceToDeployStep = async () => {
  await waitFor(() => {
    expect(
      screen.getByRole('button', { name: 'actions.next' }),
    ).not.toBeDisabled();
  });
  clickWizardNext();
  await waitFor(() => {
    expect(
      screen.getByText('deployAIM.fields.metric.title'),
    ).toBeInTheDocument();
  });
  await waitFor(() => {
    expect(
      screen.getByRole('button', { name: 'actions.next' }),
    ).not.toBeDisabled();
  });
  clickWizardNext();
  await waitFor(() => {
    expect(screen.getByTestId('autoscaling-toggle')).toBeInTheDocument();
  });
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

describe('DeployAIMWizard', () => {
  let getAimClusterProfilesSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockToast.success.mockClear();
    mockToast.error.mockClear();
    invalidateQueriesSpy.mockClear();
    (fetchProjectSecrets as Mock).mockResolvedValue({ data: [] });
    (createProjectSecret as Mock).mockResolvedValue({
      id: 'new-secret-id',
      name: 'test-hf-token',
    });
    vi.mocked(listAllAdapterArtifacts).mockResolvedValue([]);
    getAimClusterProfilesSpy = vi
      .spyOn(aimsLib, 'getAimClusterProfiles')
      .mockResolvedValue([]);
  });

  it('renders wizard when open', () => {
    const aggregatedAim = mockAggregatedAims[0];
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    expect(screen.getByText('deployAIM.title')).toBeInTheDocument();
  });

  it('calls onClose from the wizard close button', () => {
    const aggregatedAim = mockAggregatedAims[0];
    const onClose = vi.fn();
    render(
      <DeployAIMWizard onClose={onClose} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('renders HuggingFace token field when isHfTokenRequired is true', async () => {
    const aimWithTokenRequired = {
      ...mockAims[0],
      isHfTokenRequired: true,
      isLatest: true,
    };
    const aggregatedAim = {
      ...mockAggregatedAims[0],
      parsedAIMs: [aimWithTokenRequired],
      latestAim: aimWithTokenRequired,
    };
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await waitFor(() => {
      expect(
        screen.getByText('deployAIM.fields.huggingFaceToken.title'),
      ).toBeInTheDocument();
    });
    expect(screen.getByTestId('project-hf-token-selector')).toBeInTheDocument();
  });

  it('does not render HuggingFace token field when isHfTokenRequired is false', async () => {
    const aimWithoutTokenRequired = {
      ...mockAims[0],
      isHfTokenRequired: false,
      isLatest: true,
    };
    const aggregatedAim = {
      ...mockAggregatedAims[0],
      parsedAIMs: [aimWithoutTokenRequired],
      latestAim: aimWithoutTokenRequired,
    };
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await waitFor(() => {
      expect(screen.getByText('deployAIM.title')).toBeInTheDocument();
    });

    expect(
      screen.queryByText('deployAIM.fields.huggingFaceToken.title'),
    ).not.toBeInTheDocument();
  });

  it('displays aim information correctly on the model step', () => {
    const aggregatedAim = mockAggregatedAims[0];
    const displayAim =
      aggregatedAim.latestAim ??
      aggregatedAim.parsedAIMs.find((a) => a.status === 'Ready') ??
      aggregatedAim.parsedAIMs[0]!;
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    expect(screen.getByText(displayAim.title)).toBeInTheDocument();
    expect(screen.getByText(displayAim.description.short)).toBeInTheDocument();
  });

  it('renders performance metric radios on the Target step when profiles are available', async () => {
    getAimClusterProfilesSpy.mockResolvedValueOnce(mockServiceProfiles);

    const aggregatedAim = aggregatedAimWithoutHf();
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await advanceToPerformanceStep();

    expect(
      screen.getByTestId('deployAimPerformanceModeGroup'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('deployAimPerformanceMode-latency'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('deployAimPerformanceMode-throughput'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('deployAimPerformanceMode-advanced'),
    ).toBeInTheDocument();
  });

  it('renders the Target step even when no profiles are available', async () => {
    const aggregatedAim = mockAggregatedAims[0];
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await waitFor(() => {
      expect(getAimClusterProfilesSpy).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'actions.next' }),
      ).toBeDisabled();
    });

    expect(
      screen.queryByText('deployAIM.fields.metric.title'),
    ).not.toBeInTheDocument();
  });

  it('disables next on the model step when no profiles are available', async () => {
    const aggregatedAim = mockAggregatedAims[0];
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'deployAIM.notifications.noProfilesDescription',
      );
    });

    const nextButton = screen.getByRole('button', { name: 'actions.next' });
    expect(nextButton).toBeDisabled();
  });

  it('shows error toast when no service templates are available', async () => {
    const aggregatedAim = mockAggregatedAims[0];
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'deployAIM.notifications.noProfilesDescription',
      );
    });
  });

  it('enables next on the model step when ready profiles are available', async () => {
    getAimClusterProfilesSpy.mockResolvedValueOnce([
      {
        metadata: { name: 'template-latency', labels: {} },
        spec: {
          aimId: 'test-model',
          modelName: 'test-model',
          metric: 'latency',
        },
        status: { status: 'Ready' },
      },
    ]);

    const aggregatedAim = aggregatedAimWithoutHf();
    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    const nextButton = await screen.findByRole('button', {
      name: 'actions.next',
    });
    await waitFor(() => {
      expect(nextButton).not.toBeDisabled();
    });

    expect(mockToast.error).not.toHaveBeenCalled();
  });

  it('invalidates the inferenceModel cache after a successful deploy', async () => {
    const deployAimSpy = vi
      .spyOn(inferenceLib, 'deployInference')
      .mockResolvedValue(undefined as unknown as AIMService);

    const base = mockAggregatedAims[0];
    const aggregatedAim = aggregatedAimWithoutHf(base);

    getAimClusterProfilesSpy.mockResolvedValueOnce([
      {
        metadata: { name: 'template-latency', labels: {} },
        spec: {
          aimId: 'test-model',
          modelName: 'test-model',
          metric: 'latency',
        },
        status: { status: 'Ready' },
      },
    ]);

    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await advanceToDeployStep();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'actions.submit.title',
      }),
    );

    await waitFor(() => {
      expect(deployAimSpy).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(invalidateQueriesSpy).toHaveBeenCalledWith({
        queryKey: ['inferenceModel'],
      });
    });

    deployAimSpy.mockRestore();
  });

  it('passes a single selected image pull secret to deployInference', async () => {
    const deployAimSpy = vi
      .spyOn(inferenceLib, 'deployInference')
      .mockResolvedValue(undefined as unknown as AIMService);

    const base = mockAggregatedAims[0];
    const parsedNoHf = base.parsedAIMs.map((a) => ({
      ...a,
      isHfTokenRequired: false,
    }));
    const aggregatedAim = {
      ...base,
      parsedAIMs: parsedNoHf,
      latestAim: parsedNoHf[0],
      aggregated: { ...base.aggregated, isHfTokenRequired: false },
    };

    const pullSecretName = 'registry-pull-one';
    (fetchProjectSecrets as Mock).mockResolvedValue({
      data: [
        {
          metadata: {
            name: pullSecretName,
            namespace: 'test-project',
            creationTimestamp: '2023-01-01T00:00:00Z',
          },
          useCase: SecretUseCase.IMAGE_PULL_SECRET,
        },
      ],
    });

    getAimClusterProfilesSpy.mockResolvedValueOnce([
      {
        metadata: { name: 'template-latency', labels: {} },
        spec: {
          aimId: 'test-model',
          modelName: 'test-model',
          metric: 'latency',
        },
        status: { status: 'Ready' },
      },
    ]);

    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'actions.next' }),
      ).not.toBeDisabled();
    });

    // Match FinetuneWizard (data-testid + fireEvent); role-based queries time out for this Select in jsdom.
    fireEvent.click(screen.getByTestId('deployAimImagePullSecretsSelect'));
    fireEvent.click(
      await screen.findByTestId(
        `deployAimImagePullSecretOption-${pullSecretName}`,
      ),
    );

    await advanceToDeployStep();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'actions.submit.title',
      }),
    );

    await waitFor(() => {
      expect(deployAimSpy).toHaveBeenCalled();
    });

    expect(deployAimSpy).toHaveBeenCalledWith(
      'test-project',
      expect.objectContaining({
        imagePullSecrets: [pullSecretName],
      }),
    );

    deployAimSpy.mockRestore();
  });

  it('passes every image pull secret picked by display name to deployInference', async () => {
    const deployAimSpy = vi
      .spyOn(inferenceLib, 'deployInference')
      .mockResolvedValue(undefined as unknown as AIMService);

    const base = mockAggregatedAims[0];
    const parsedNoHf = base.parsedAIMs.map((a) => ({
      ...a,
      isHfTokenRequired: false,
    }));
    const aggregatedAim = {
      ...base,
      parsedAIMs: parsedNoHf,
      latestAim: parsedNoHf[0],
      aggregated: { ...base.aggregated, isHfTokenRequired: false },
    };

    const pullSecrets = [
      { name: 'wb-secret-aaaa1111', displayName: 'Registry One' },
      { name: 'wb-secret-bbbb2222', displayName: 'Registry Two' },
    ];
    (fetchProjectSecrets as Mock).mockResolvedValue({
      data: pullSecrets.map(({ name, displayName }) => ({
        metadata: {
          name,
          namespace: 'test-project',
          creationTimestamp: '2023-01-01T00:00:00Z',
        },
        displayName,
        useCase: SecretUseCase.IMAGE_PULL_SECRET,
      })),
    });

    getAimClusterProfilesSpy.mockResolvedValueOnce([
      {
        metadata: { name: 'template-latency', labels: {} },
        spec: {
          aimId: 'test-model',
          modelName: 'test-model',
          metric: 'latency',
        },
        status: { status: 'Ready' },
      },
    ]);

    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'actions.next' }),
      ).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('deployAimImagePullSecretsSelect'));
    for (const { displayName } of pullSecrets) {
      fireEvent.click(await screen.findByRole('option', { name: displayName }));
    }

    await advanceToDeployStep();
    expect(screen.getByText('Registry One, Registry Two')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'actions.submit.title',
      }),
    );

    await waitFor(() => {
      expect(deployAimSpy).toHaveBeenCalledWith(
        'test-project',
        expect.objectContaining({
          imagePullSecrets: pullSecrets.map(({ name }) => name),
        }),
      );
    });

    deployAimSpy.mockRestore();
  });

  it('deploys with the model preferred precision when precision is automatic', async () => {
    const deployAimSpy = vi
      .spyOn(inferenceLib, 'deployInference')
      .mockResolvedValue(undefined as unknown as AIMService);

    const base = mockAggregatedAims[0];
    const parsedNoHf = base.parsedAIMs.map((aim) => ({
      ...aim,
      isHfTokenRequired: false,
    }));
    const aggregatedAim = {
      ...base,
      parsedAIMs: parsedNoHf,
      latestAim: parsedNoHf[0],
      aggregated: {
        ...base.aggregated,
        isHfTokenRequired: false,
        preferredPrecision: 'fp8',
      },
    };

    getAimClusterProfilesSpy.mockResolvedValueOnce([
      {
        metadata: { name: 'profile-fp8', labels: {} },
        spec: {
          aimId: 'test-model',
          modelName: 'test-model',
          metric: 'latency',
          precision: 'fp8',
          type: 'optimized',
        },
        status: { status: 'Ready' },
      },
    ]);

    render(
      <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
      {
        wrapper,
      },
    );

    await advanceToDeployStep();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'actions.submit.title',
      }),
    );

    await waitFor(() => {
      expect(deployAimSpy).toHaveBeenCalledWith(
        'test-project',
        expect.objectContaining({ precision: 'fp8' }),
      );
    });

    deployAimSpy.mockRestore();
  });

  describe('unoptimized profile logic', () => {
    it('shows warning Alert on the performance step when all templates are unoptimized', async () => {
      getAimClusterProfilesSpy.mockResolvedValueOnce([
        {
          metadata: { name: 'template-latency', labels: {} },
          spec: {
            aimId: 'test-model',
            modelName: 'test-model',
            metric: 'latency',
          },
          status: { status: 'Ready' },
        },
      ]);

      const aggregatedAim = aggregatedAimWithoutHf();
      render(
        <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
        {
          wrapper,
        },
      );

      await advanceToPerformanceStep();

      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.notOptimized'),
        ).toBeInTheDocument();
      });
    });

    it('does not show warning Alert when at least one template is optimized and no metric selected', async () => {
      getAimClusterProfilesSpy.mockResolvedValueOnce([
        {
          metadata: { name: 'profile-latency', labels: {} },
          spec: {
            aimId: 'test-model',
            modelName: 'test-model',
            metric: 'latency',
            type: 'optimized',
          },
          status: { status: 'Ready' },
        },
        {
          metadata: { name: 'profile-throughput', labels: {} },
          spec: {
            aimId: 'test-model',
            modelName: 'test-model',
            metric: 'throughput',
            type: 'preview',
          },
          status: { status: 'Ready' },
        },
      ]);

      const aggregatedAim = aggregatedAimWithoutHf();
      render(
        <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
        {
          wrapper,
        },
      );

      await advanceToPerformanceStep();

      expect(
        screen.queryByText('deployAIM.fields.metric.notOptimized'),
      ).not.toBeInTheDocument();
    });
  });

  it('defaults to latest supported version for mixed-support models', () => {
    render(
      <DeployAIMWizard
        onClose={vi.fn()}
        aggregatedAim={mockMixedSupportAggregatedAim}
      />,
      { wrapper },
    );

    const supportedVersion = mockMixedSupportAggregatedAim.parsedAIMs.find(
      (aim) => aim.isLatest,
    );
    expect(screen.getByText(supportedVersion!.title)).toBeInTheDocument();
  });

  it('renders the version dropdown with both supported and unsupported versions', () => {
    render(
      <DeployAIMWizard
        onClose={vi.fn()}
        aggregatedAim={mockMixedSupportAggregatedAim}
      />,
      { wrapper },
    );

    const versionLabels = screen.getAllByText('deployAIM.fields.version.title');
    expect(versionLabels.length).toBeGreaterThan(0);
  });

  describe('version-scoped serving profiles', () => {
    // Two published versions of one model. They share the architecture-level
    // aimId the profile endpoint is keyed by, so the pooled response it returns
    // is the only place the per-version provenance label can be read from.
    const baseAim = aggregatedAimWithoutHf().parsedAIMs[0]!;
    const adapterCapableVersion = {
      ...baseAim,
      model: 'aim-demo-model-0-13-0',
      aimId: 'org/demo',
      imageVersion: '0.13.0',
      isLatest: true,
      isHfTokenRequired: false,
    };
    const plainVersion = {
      ...baseAim,
      model: 'aim-demo-model-0-11-1',
      aimId: 'org/demo',
      imageVersion: '0.11.1',
      isLatest: false,
      isHfTokenRequired: false,
    };

    const pooledProfiles: AIMClusterProfile[] = [
      {
        metadata: {
          name: 'profile-a-adapters',
          labels: { 'aim.eai.amd.com/source-model': 'aim-demo-model-0-13-0' },
        },
        spec: {
          aimId: 'org/demo',
          metric: 'latency',
          features: ['adapters'],
          type: 'optimized',
          acceleratorModel: 'MI300X',
          acceleratorCount: 8,
          precision: 'fp8',
        },
        status: { status: 'Ready' },
      },
      {
        metadata: {
          name: 'profile-b-plain',
          labels: { 'aim.eai.amd.com/source-model': 'aim-demo-model-0-11-1' },
        },
        spec: {
          aimId: 'org/demo',
          metric: 'throughput',
          type: 'optimized',
          acceleratorModel: 'MI300X',
          acceleratorCount: 8,
          precision: 'fp16',
        },
        status: { status: 'Ready' },
      },
    ];

    const renderWithVersions = (versions: ParsedAIM[]) =>
      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={{
            ...aggregatedAimWithoutHf(),
            parsedAIMs: versions,
            latestAim: versions[0]!,
          }}
        />,
        { wrapper },
      );

    beforeEach(() => {
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([]);
      // Every version resolves to the same query key, so the pooled list has to
      // answer each of them — a one-shot mock would starve the second fetch.
      getAimClusterProfilesSpy.mockResolvedValue(pooledProfiles);
    });

    // Personalization sits between Model and Performance only for versions that
    // can serve adapters, so how many steps Performance is away depends on the
    // version under test; walking forward keeps that out of the assertions.
    const advancePastOptionalPersonalizationStep = async () => {
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.next' }),
        ).not.toBeDisabled();
      });
      clickWizardNext();
      if (
        screen.queryByRole('switch', {
          name: 'deployAIM.personalization.enable',
        })
      ) {
        clickWizardNext();
      }
      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.title'),
        ).toBeInTheDocument();
      });
    };

    const expectNoPersonalizationSwitch = () => {
      expect(
        screen.queryByRole('switch', {
          name: 'deployAIM.personalization.enable',
        }),
      ).not.toBeInTheDocument();
    };

    it('does not offer the Personalization step for a version whose own profiles cannot serve adapters', async () => {
      renderWithVersions([plainVersion, adapterCapableVersion]);

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.next' }),
        ).not.toBeDisabled();
      });
      // The wizard mounts only the step it is on, so landing straight on
      // Performance is what proves Personalization was never inserted.
      clickWizardNext();
      expectNoPersonalizationSwitch();
      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.title'),
        ).toBeInTheDocument();
      });
    });

    it("lists only the selected version's profiles in the advanced parameters", async () => {
      renderWithVersions([plainVersion, adapterCapableVersion]);

      await advancePastOptionalPersonalizationStep();
      fireEvent.click(
        screen.getByRole('radio', {
          name: 'deployAIM.fields.metric.options.advanced.label',
        }),
      );

      const precisions = await screen.findByTestId(
        'advancedProfileParamPrecisions',
      );
      expect(within(precisions).getByText('fp16')).toBeInTheDocument();
      expect(within(precisions).queryByText('fp8')).not.toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Pin profile-b-plain' }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: 'Pin profile-a-adapters' }),
      ).not.toBeInTheDocument();
    });

    it('changes the profile list when the user switches version rather than reusing the pooled one', async () => {
      renderWithVersions([adapterCapableVersion, plainVersion]);

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.next' }),
        ).not.toBeDisabled();
      });
      clickWizardNext(); // model -> personalization
      expect(
        await screen.findByRole('switch', {
          name: 'deployAIM.personalization.enable',
        }),
      ).toBeInTheDocument();

      fireEvent.click(
        screen.getByRole('button', { name: 'actions.back.title' }),
      );
      fireEvent.click(await screen.findByRole('option', { name: '0.11.1' }));

      expect(
        screen.queryByText('deployAIM.steps.personalization.label'),
      ).not.toBeInTheDocument();
      clickWizardNext(); // model -> performance
      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.title'),
        ).toBeInTheDocument();
      });
      expectNoPersonalizationSwitch();
      // Both versions share the architecture id the endpoint is keyed by, so
      // the narrowing has to come from the one pooled response, not a refetch.
      expect(getAimClusterProfilesSpy).toHaveBeenCalledWith('org/demo');
      expect(
        getAimClusterProfilesSpy.mock.calls.every(
          ([aimId]: [string]) => aimId === 'org/demo',
        ),
      ).toBe(true);
    });

    // Back to the Model step from wherever the walk-forward left off. The
    // version dropdown only exists on that step, so its options are what says
    // we have arrived — and how many steps back it is depends on whether
    // Personalization was inserted for the version under test.
    const backToModelStep = async () => {
      for (let step = 0; step < 4; step += 1) {
        if (screen.queryByRole('option', { name: '0.11.1' })) return;
        fireEvent.click(
          screen.getByRole('button', { name: 'actions.back.title' }),
        );
      }
      expect(
        await screen.findByRole('option', { name: '0.11.1' }),
      ).toBeInTheDocument();
    };

    const selectAdvancedPerformanceMode = () => {
      fireEvent.click(
        screen.getByRole('radio', {
          name: 'deployAIM.fields.metric.options.advanced.label',
        }),
      );
    };

    it('drops a pinned profile the newly selected version does not publish', async () => {
      const deployAimSpy = vi
        .spyOn(inferenceLib, 'deployInference')
        .mockResolvedValue(undefined as unknown as AIMService);

      renderWithVersions([adapterCapableVersion, plainVersion]);

      await advancePastOptionalPersonalizationStep();
      selectAdvancedPerformanceMode();
      fireEvent.click(
        await screen.findByRole('button', { name: 'Pin profile-a-adapters' }),
      );

      await backToModelStep();
      fireEvent.click(screen.getByRole('option', { name: '0.11.1' }));

      // 0.11.1 publishes only profile-b-plain, so the pin taken on 0.13.0 is
      // no longer on offer and must not reach the payload.
      await waitFor(() => {
        expect(
          screen.queryByText('deployAIM.steps.personalization.label'),
        ).not.toBeInTheDocument();
      });
      await advanceToDeployStep();
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.submit.title' }),
      );

      await waitFor(() => {
        expect(deployAimSpy).toHaveBeenCalled();
      });
      const payload = deployAimSpy.mock.calls[0]![1];
      expect(payload).toEqual(
        expect.objectContaining({ model: 'aim-demo-model-0-11-1' }),
      );
      expect(payload).not.toHaveProperty('profileName');

      deployAimSpy.mockRestore();
    });

    it('keeps an advanced choice the newly selected version still publishes', async () => {
      const deployAimSpy = vi
        .spyOn(inferenceLib, 'deployInference')
        .mockResolvedValue(undefined as unknown as AIMService);

      renderWithVersions([adapterCapableVersion, plainVersion]);

      await advancePastOptionalPersonalizationStep();
      selectAdvancedPerformanceMode();
      fireEvent.click(
        await screen.findByRole('button', { name: 'Set GPU MI300X' }),
      );

      await backToModelStep();
      fireEvent.click(screen.getByRole('option', { name: '0.11.1' }));

      // Both versions publish MI300X, so re-validating has nothing to drop —
      // a blanket reset on every version switch would lose this choice.
      await waitFor(() => {
        expect(
          screen.queryByText('deployAIM.steps.personalization.label'),
        ).not.toBeInTheDocument();
      });
      await advanceToDeployStep();
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.submit.title' }),
      );

      await waitFor(() => {
        expect(deployAimSpy).toHaveBeenCalledWith(
          'test-project',
          expect.objectContaining({ gpuModel: 'MI300X' }),
        );
      });

      deployAimSpy.mockRestore();
    });

    describe('no-profiles warning', () => {
      // Neither version is named by any label on the pooled response, so each
      // of them narrows to an empty ready list.
      const profilelessEarlyVersion = {
        ...baseAim,
        model: 'aim-demo-model-0-9-0',
        aimId: 'org/demo',
        imageVersion: '0.9.0',
        isLatest: false,
        isHfTokenRequired: false,
      };
      const profilelessLaterVersion = {
        ...baseAim,
        model: 'aim-demo-model-0-8-0',
        aimId: 'org/demo',
        imageVersion: '0.8.0',
        isLatest: false,
        isHfTokenRequired: false,
      };

      it('warns again when switching to another version with no ready profiles', async () => {
        renderWithVersions([profilelessEarlyVersion, profilelessLaterVersion]);

        // The version the wizard opens on has nothing to serve with, so the
        // warning is raised once before any switch happens.
        await waitFor(() => {
          expect(mockToast.error).toHaveBeenCalledWith(
            'deployAIM.notifications.noProfilesDescription',
          );
        });
        mockToast.error.mockClear();

        fireEvent.click(await screen.findByRole('option', { name: '0.8.0' }));

        // Keyed on the version rather than the aimId the two share: a guard
        // that remembered the aimId would treat this switch as already warned
        // about and leave the user on a version that cannot deploy with no
        // indication of why.
        await waitFor(() => {
          expect(mockToast.error).toHaveBeenCalledWith(
            'deployAIM.notifications.noProfilesDescription',
          );
        });
      });
    });
  });

  describe('personalization', () => {
    const adapter: LoraAdapter = {
      id: 'adapter-1',
      name: 'adapter-1',
      displayName: 'Support LoRA',
      compatibleWith: ['aim-llama-2-7b-v2'],
      rank: 100,
      readiness: 'Ready',
    };

    // The catalog entry groups every quantised variant under one aimId; the
    // profile names the weights the adapter was actually trained against.
    const adaptersCapableProfile: AIMClusterProfile = {
      metadata: { name: 'profile-adapters', labels: {} },
      spec: {
        aimId: 'test-model',
        modelId: 'aim-llama-2-7b-v2',
        modelName: 'test-model',
        metric: 'latency',
        features: ['adapters'],
      },
      status: { status: 'Ready' },
    };

    const incompatibleProfile: AIMClusterProfile = {
      metadata: { name: 'profile-no-adapters', labels: {} },
      spec: {
        aimId: 'test-model',
        modelName: 'test-model',
        metric: 'throughput',
      },
      status: { status: 'Ready' },
    };

    it('rejects a pinned non-adapter profile when dynamic personalization has no selected adapters', () => {
      expect(
        hasIncompatiblePersonalizationProfile(
          true,
          true,
          incompatibleProfile.metadata.name,
          [adaptersCapableProfile, incompatibleProfile],
        ),
      ).toBe(true);
    });

    const acceptedProfileCases: Array<
      [string, boolean, boolean, string | undefined]
    > = [
      [
        'no profile of the model supports adapters',
        false,
        true,
        incompatibleProfile.metadata.name,
      ],
      [
        'personalization is disabled',
        true,
        false,
        incompatibleProfile.metadata.name,
      ],
      ['profile selection is left automatic', true, true, undefined],
    ];

    it.each(acceptedProfileCases)(
      'accepts a non-adapter profile when %s',
      (_label, supportsAdapters, personalizationEnabled, profileName) => {
        expect(
          hasIncompatiblePersonalizationProfile(
            supportsAdapters,
            personalizationEnabled,
            profileName,
            [adaptersCapableProfile, incompatibleProfile],
          ),
        ).toBe(false);
      },
    );

    it('blocks the deploy when personalization is enabled after a non-adapter profile was pinned', async () => {
      const deployAimSpy = vi
        .spyOn(inferenceLib, 'deployInference')
        .mockResolvedValue(undefined as unknown as AIMService);
      getAimClusterProfilesSpy.mockResolvedValueOnce([
        adaptersCapableProfile,
        incompatibleProfile,
      ]);

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.next' }),
        ).not.toBeDisabled();
      });
      clickWizardNext(); // model -> personalization
      await screen.findByRole('switch', {
        name: 'deployAIM.personalization.enable',
      });
      clickWizardNext(); // personalization -> performance
      // The Performance step only restricts the profile table once
      // personalization is on, so pin the non-adapter profile first and flip
      // the toggle afterwards — the submit guard is the last line of defence.
      fireEvent.click(
        await screen.findByRole('radio', {
          name: 'deployAIM.fields.metric.options.advanced.label',
        }),
      );
      fireEvent.click(
        await screen.findByRole('button', { name: 'Pin profile-no-adapters' }),
      );
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.back.title' }),
      );
      fireEvent.click(
        await screen.findByRole('switch', {
          name: 'deployAIM.personalization.enable',
        }),
      );
      clickWizardNext(); // personalization -> performance
      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.title'),
        ).toBeInTheDocument();
      });
      clickWizardNext(); // performance -> scaling
      await waitFor(() => {
        expect(screen.getByTestId('autoscaling-toggle')).toBeInTheDocument();
      });
      clickWizardNext(); // scaling -> review
      fireEvent.click(
        await screen.findByRole('button', { name: 'actions.submit.title' }),
      );

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith(
          'deployAIM.personalization.validation.profile',
        );
      });
      expect(deployAimSpy).not.toHaveBeenCalled();

      deployAimSpy.mockRestore();
    });

    const advanceThroughPersonalizationToDeployStep = async ({
      selectAdapterButtonName,
    }: {
      selectAdapterButtonName?: string;
    } = {}) => {
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.next' }),
        ).not.toBeDisabled();
      });
      clickWizardNext(); // model -> personalization
      await screen.findByRole('switch', {
        name: 'deployAIM.personalization.enable',
      });
      if (selectAdapterButtonName) {
        fireEvent.click(
          screen.getByRole('switch', {
            name: 'deployAIM.personalization.enable',
          }),
        );
        fireEvent.click(
          await screen.findByRole('button', { name: selectAdapterButtonName }),
        );
      }
      clickWizardNext(); // personalization -> performance
      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.title'),
        ).toBeInTheDocument();
      });
      clickWizardNext(); // performance -> scaling
      await waitFor(() => {
        expect(screen.getByTestId('autoscaling-toggle')).toBeInTheDocument();
      });
      clickWizardNext(); // scaling -> review
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.submit.title' }),
        ).toBeInTheDocument();
      });
    };

    // The catalog lists one entry per model family, so a deploy can only be
    // served by one of the quantised variants the profiles name.
    const CATALOG_AIM_ID = 'meta-llama/Llama-3.1-8B-Instruct';
    const QUANTISED_MODEL_ID = 'amd/Llama-3.1-8B-Instruct-FP8-KV';

    const quantisedAdapterProfile: AIMClusterProfile = {
      metadata: { name: 'profile-fp8-adapters', labels: {} },
      spec: {
        aimId: CATALOG_AIM_ID,
        modelId: QUANTISED_MODEL_ID,
        modelName: 'test-model',
        metric: 'latency',
        features: ['adapters'],
      },
      status: { status: 'Ready' },
    };

    const openPersonalizationStep = async () => {
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.next' }),
        ).not.toBeDisabled();
      });
      clickWizardNext(); // model -> personalization
      fireEvent.click(
        await screen.findByRole('switch', {
          name: 'deployAIM.personalization.enable',
        }),
      );
    };

    it('offers an adapter a servable variant of the model can load', async () => {
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([
        { ...adapter, compatibleWith: [QUANTISED_MODEL_ID] },
      ]);
      getAimClusterProfilesSpy.mockResolvedValueOnce([quantisedAdapterProfile]);

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();

      expect(
        await screen.findByRole('button', { name: 'Select Support LoRA' }),
      ).toBeInTheDocument();
    });

    it('offers an adapter that names only the catalog entry', async () => {
      // Coarser than the weights the profile serves, but every producer still
      // writes it and the deploy endpoint accepts it — hiding it here would
      // withhold an adapter the API would have taken. Flip this with the aimId
      // arm of `canProfilesServeAdapter`.
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([
        { ...adapter, compatibleWith: [CATALOG_AIM_ID] },
      ]);
      getAimClusterProfilesSpy.mockResolvedValueOnce([quantisedAdapterProfile]);

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();

      expect(
        await screen.findByRole('button', { name: 'Select Support LoRA' }),
      ).toBeInTheDocument();
    });

    it('hides an adapter no servable variant of the model can load', async () => {
      // The adapter names neither the weights the profile serves nor the
      // catalog entry they belong to, so no profile on offer could load it.
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([
        { ...adapter, compatibleWith: ['some-other-org/unrelated-model'] },
      ]);
      getAimClusterProfilesSpy.mockResolvedValueOnce([quantisedAdapterProfile]);

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();

      await waitFor(() => {
        expect(listAllAdapterArtifacts).toHaveBeenCalled();
      });
      expect(
        screen.queryByRole('button', { name: 'Select Support LoRA' }),
      ).not.toBeInTheDocument();
    });

    // Published at two precisions, one of which the model prefers — the shape
    // that makes an automatic precision choice narrower than it looks.
    const FP16_MODEL_ID = 'amd/Llama-3.1-8B-Instruct-FP16';
    const precisionProfile = (
      name: string,
      modelId: string,
      precision: string,
    ): AIMClusterProfile => ({
      metadata: { name, labels: {} },
      spec: {
        aimId: CATALOG_AIM_ID,
        modelId,
        modelName: 'test-model',
        metric: 'latency',
        precision,
        features: ['adapters'],
      },
      status: { status: 'Ready' },
    });

    const aggregatedAimPreferringFp8 = () => {
      const base = aggregatedAimWithoutHf();
      return {
        ...base,
        aggregated: { ...base.aggregated, preferredPrecision: 'fp8' },
      };
    };

    const preferredPrecisionProfiles = [
      precisionProfile('profile-fp16', FP16_MODEL_ID, 'fp16'),
      precisionProfile('profile-fp8', QUANTISED_MODEL_ID, 'fp8'),
    ];

    const fp16OnlyAdapter = {
      ...adapter,
      compatibleWith: [FP16_MODEL_ID],
    };
    const fp8OnlyAdapter = {
      ...adapter,
      id: 'adapter-2',
      name: 'adapter-2',
      displayName: 'Preferred LoRA',
      compatibleWith: [QUANTISED_MODEL_ID],
    };

    it('hides an adapter only the non-preferred precision can load while the precision choice is automatic', async () => {
      // Automatic does not leave the precision open: submit pins the model's
      // preferred one, so offering against every published precision keeps an
      // adapter on the list the deploy would then refuse to load.
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([
        fp16OnlyAdapter,
        fp8OnlyAdapter,
      ]);
      getAimClusterProfilesSpy.mockResolvedValueOnce(
        preferredPrecisionProfiles,
      );

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimPreferringFp8()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();

      expect(
        await screen.findByRole('button', { name: 'Select Preferred LoRA' }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: 'Select Support LoRA' }),
      ).not.toBeInTheDocument();
    });

    // Narrows the candidate profiles after the adapters were picked, which is
    // the only way a selection made on an open precision choice can stop being
    // servable.
    const pinPrecisionProfile = async (name: string) => {
      clickWizardNext(); // personalization -> performance
      fireEvent.click(
        await screen.findByRole('radio', {
          name: 'deployAIM.fields.metric.options.advanced.label',
        }),
      );
      fireEvent.click(
        await screen.findByRole('button', { name: `Pin ${name}` }),
      );
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.back.title' }),
      );
      await screen.findByRole('switch', {
        name: 'deployAIM.personalization.enable',
      });
    };

    const submitFromPersonalizationStep = async () => {
      clickWizardNext(); // personalization -> performance
      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.title'),
        ).toBeInTheDocument();
      });
      clickWizardNext(); // performance -> scaling
      await waitFor(() => {
        expect(screen.getByTestId('autoscaling-toggle')).toBeInTheDocument();
      });
      clickWizardNext(); // scaling -> review
      fireEvent.click(
        await screen.findByRole('button', { name: 'actions.submit.title' }),
      );
    };

    it('keeps a selected adapter on the list once the narrowed profiles can no longer serve it', async () => {
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([
        fp16OnlyAdapter,
        fp8OnlyAdapter,
      ]);
      getAimClusterProfilesSpy.mockResolvedValueOnce(
        preferredPrecisionProfiles,
      );

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();
      fireEvent.click(
        await screen.findByRole('button', { name: 'Select Support LoRA' }),
      );

      await pinPrecisionProfile('profile-fp8');

      // Withdrawing the row here is how a deploy loses an adapter nobody
      // noticed going away: the selection would be dropped with no warning and
      // nothing left on screen to act on.
      const retainedRow = await screen.findByRole('button', {
        name: 'Select Support LoRA',
      });
      expect(retainedRow).toHaveAttribute('data-unservable', 'true');
      expect(
        screen.getByTestId('unservable-adapters-warning'),
      ).toBeInTheDocument();
    });

    it('withdraws the retained row once the user clears the selection', async () => {
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([
        fp16OnlyAdapter,
        fp8OnlyAdapter,
      ]);
      getAimClusterProfilesSpy.mockResolvedValueOnce(
        preferredPrecisionProfiles,
      );

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();
      fireEvent.click(
        await screen.findByRole('button', { name: 'Select Support LoRA' }),
      );
      await pinPrecisionProfile('profile-fp8');

      fireEvent.click(
        await screen.findByRole('button', { name: 'Select Support LoRA' }),
      );

      await waitFor(() => {
        expect(
          screen.queryByRole('button', { name: 'Select Support LoRA' }),
        ).not.toBeInTheDocument();
      });
      expect(
        screen.queryByTestId('unservable-adapters-warning'),
      ).not.toBeInTheDocument();
    });

    it('blocks the deploy and names the selected adapters the profiles cannot serve', async () => {
      const deployAimSpy = vi
        .spyOn(inferenceLib, 'deployInference')
        .mockResolvedValue(undefined as unknown as AIMService);
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([
        fp16OnlyAdapter,
        fp8OnlyAdapter,
      ]);
      getAimClusterProfilesSpy.mockResolvedValueOnce(
        preferredPrecisionProfiles,
      );

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();
      fireEvent.click(
        await screen.findByRole('button', { name: 'Select Support LoRA' }),
      );
      await pinPrecisionProfile('profile-fp8');

      await submitFromPersonalizationStep();

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith(
          'deployAIM.personalization.validation.adapters',
        );
      });
      expect(mockToast.error).not.toHaveBeenCalledWith(
        'deployAIM.personalization.validation.notReadyAdapters',
      );
      expect(deployAimSpy).not.toHaveBeenCalled();

      deployAimSpy.mockRestore();
    });

    // A refetch is the only thing that can take an adapter's weights away
    // mid-wizard, and React Query issues one whenever the window regains focus.
    const refetchAdaptersAs = async (next: LoraAdapter[]) => {
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue(next);
      act(() => focusManager.setFocused(false));
      act(() => focusManager.setFocused(true));
      await waitFor(() => {
        expect(listAllAdapterArtifacts).toHaveBeenCalledTimes(2);
      });
    };

    it('keeps a selected adapter on the list once its weights go back to importing', async () => {
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([fp8OnlyAdapter]);
      // Not `...Once`: the focus-driven refetch below re-runs every query, and
      // an empty second answer would take the personalization step away.
      getAimClusterProfilesSpy.mockResolvedValue([quantisedAdapterProfile]);

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();
      fireEvent.click(
        await screen.findByRole('button', { name: 'Select Preferred LoRA' }),
      );

      await refetchAdaptersAs([{ ...fp8OnlyAdapter, readiness: 'NotReady' }]);

      // Silently dropping it is worse than the lineage case, because waiting
      // is all it takes to make the adapter deployable again.
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'Select Preferred LoRA' }),
        ).toHaveAttribute('data-not-ready', 'true');
      });
      expect(
        screen.getByTestId('not-ready-adapters-warning'),
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId('unservable-adapters-warning'),
      ).not.toBeInTheDocument();
    });

    it('blocks the deploy and names the selected adapters still importing their weights', async () => {
      const deployAimSpy = vi
        .spyOn(inferenceLib, 'deployInference')
        .mockResolvedValue(undefined as unknown as AIMService);
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([fp8OnlyAdapter]);
      // Not `...Once`: the focus-driven refetch below re-runs every query, and
      // an empty second answer would take the personalization step away.
      getAimClusterProfilesSpy.mockResolvedValue([quantisedAdapterProfile]);

      render(
        <DeployAIMWizard
          onClose={vi.fn()}
          aggregatedAim={aggregatedAimWithoutHf()}
        />,
        { wrapper },
      );
      await openPersonalizationStep();
      fireEvent.click(
        await screen.findByRole('button', { name: 'Select Preferred LoRA' }),
      );
      await refetchAdaptersAs([{ ...fp8OnlyAdapter, readiness: 'NotReady' }]);
      await waitFor(() => {
        expect(
          screen.getByTestId('not-ready-adapters-warning'),
        ).toBeInTheDocument();
      });

      await submitFromPersonalizationStep();

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith(
          'deployAIM.personalization.validation.notReadyAdapters',
        );
      });
      // The lineage still matches, so naming it as unservable would send the
      // user off to widen a performance selection that is not the problem.
      expect(mockToast.error).not.toHaveBeenCalledWith(
        'deployAIM.personalization.validation.adapters',
      );
      expect(deployAimSpy).not.toHaveBeenCalled();

      deployAimSpy.mockRestore();
    });

    it('includes adapterMode, selected adapters, and maxLoraRank in the deploy payload', async () => {
      const deployAimSpy = vi
        .spyOn(inferenceLib, 'deployInference')
        .mockResolvedValue(undefined as unknown as AIMService);
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([adapter]);
      getAimClusterProfilesSpy.mockResolvedValueOnce([adaptersCapableProfile]);

      const aggregatedAim = aggregatedAimWithoutHf();
      render(
        <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
        { wrapper },
      );

      await advanceThroughPersonalizationToDeployStep({
        selectAdapterButtonName: 'Select Support LoRA',
      });

      fireEvent.click(
        screen.getByRole('button', { name: 'actions.submit.title' }),
      );

      await waitFor(() => {
        expect(deployAimSpy).toHaveBeenCalled();
      });
      expect(deployAimSpy).toHaveBeenCalledWith(
        'test-project',
        expect.objectContaining({
          adapterMode: 'dynamic',
          adapters: ['adapter-1'],
          // rank 100 has no exact tier; the next supported ceiling is 128.
          maxLoraRank: 128,
        }),
      );

      deployAimSpy.mockRestore();
    });

    it('keeps the Advanced radio enabled once personalization is enabled, before any adapter is selected', async () => {
      const nonAdapterProfile: AIMClusterProfile = {
        metadata: { name: 'profile-no-adapters', labels: {} },
        spec: {
          aimId: 'test-model',
          modelName: 'test-model',
          metric: 'throughput',
        },
        status: { status: 'Ready' },
      };
      getAimClusterProfilesSpy.mockResolvedValueOnce([
        adaptersCapableProfile,
        nonAdapterProfile,
      ]);

      const aggregatedAim = aggregatedAimWithoutHf();
      render(
        <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
        { wrapper },
      );

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.next' }),
        ).not.toBeDisabled();
      });
      clickWizardNext(); // model -> personalization
      fireEvent.click(
        await screen.findByRole('switch', {
          name: 'deployAIM.personalization.enable',
        }),
      );
      // Enabling personalization always sends adapterMode: 'dynamic' on
      // submit regardless of whether an adapter has been picked yet, so the
      // Performance step must already restrict profile choices to
      // adapter-capable ones at this point — not only after an adapter is
      // selected. The restricted set still has one adapter-capable profile,
      // so Advanced stays reachable; PerformanceStepFields.test.tsx covers
      // that the restricted table itself excludes the non-adapter profile.
      clickWizardNext(); // personalization -> performance
      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.title'),
        ).toBeInTheDocument();
      });
      expect(
        screen.getByRole('radio', {
          name: 'deployAIM.fields.metric.options.advanced.label',
        }),
      ).toBeEnabled();
    });

    it('clears personalization when switching to a model without adapter support', async () => {
      const deployAimSpy = vi
        .spyOn(inferenceLib, 'deployInference')
        .mockResolvedValue(undefined as unknown as AIMService);
      const adapterCapableAim = {
        ...aggregatedAimWithoutHf().parsedAIMs[0]!,
        model: 'adapter-capable-model',
        aimId: 'adapter-capable-aim',
        imageVersion: '2.0.0',
        isLatest: true,
      };
      const unsupportedAim = {
        ...adapterCapableAim,
        model: 'unsupported-model',
        aimId: 'unsupported-aim',
        imageVersion: '1.0.0',
        isLatest: false,
      };
      const aggregatedAim = {
        ...aggregatedAimWithoutHf(),
        parsedAIMs: [adapterCapableAim, unsupportedAim],
        latestAim: adapterCapableAim,
      };
      vi.mocked(listAllAdapterArtifacts).mockResolvedValue([adapter]);
      getAimClusterProfilesSpy.mockImplementation(async (aimId: string) =>
        aimId === 'adapter-capable-aim'
          ? [
              {
                ...adaptersCapableProfile,
                spec: {
                  ...adaptersCapableProfile.spec,
                  aimId: 'adapter-capable-aim',
                  modelName: 'adapter-capable-model',
                },
              },
            ]
          : [
              {
                ...adaptersCapableProfile,
                spec: {
                  ...adaptersCapableProfile.spec,
                  aimId: 'unsupported-aim',
                  modelName: 'unsupported-model',
                  features: [],
                },
              },
            ],
      );

      render(
        <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
        { wrapper },
      );

      await advanceThroughPersonalizationToDeployStep({
        selectAdapterButtonName: 'Select Support LoRA',
      });
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.back.title' }),
      );
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.back.title' }),
      );
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.back.title' }),
      );
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.back.title' }),
      );
      fireEvent.click(await screen.findByRole('option', { name: '1.0.0' }));

      await waitFor(() => {
        expect(
          screen.queryByRole('switch', {
            name: 'deployAIM.personalization.enable',
          }),
        ).not.toBeInTheDocument();
      });
      await advanceToDeployStep();
      fireEvent.click(
        screen.getByRole('button', { name: 'actions.submit.title' }),
      );

      await waitFor(() => expect(deployAimSpy).toHaveBeenCalled());
      const [, payload] = deployAimSpy.mock.calls[0]!;
      expect(payload).not.toHaveProperty('adapterMode');
      expect(payload).not.toHaveProperty('adapters');
      expect(payload).not.toHaveProperty('maxLoraRank');

      deployAimSpy.mockRestore();
    });

    it('hides the personalization step and omits adapter fields from the payload when no profile supports adapters', async () => {
      const deployAimSpy = vi
        .spyOn(inferenceLib, 'deployInference')
        .mockResolvedValue(undefined as unknown as AIMService);
      getAimClusterProfilesSpy.mockResolvedValueOnce([
        {
          metadata: { name: 'profile-latency', labels: {} },
          spec: {
            aimId: 'test-model',
            modelName: 'test-model',
            metric: 'latency',
          },
          status: { status: 'Ready' },
        },
      ]);

      const aggregatedAim = aggregatedAimWithoutHf();
      render(
        <DeployAIMWizard onClose={vi.fn()} aggregatedAim={aggregatedAim} />,
        { wrapper },
      );

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'actions.next' }),
        ).not.toBeDisabled();
      });
      expect(
        screen.queryByRole('switch', {
          name: 'deployAIM.personalization.enable',
        }),
      ).not.toBeInTheDocument();

      clickWizardNext(); // model -> performance (no personalization step)
      await waitFor(() => {
        expect(
          screen.getByText('deployAIM.fields.metric.title'),
        ).toBeInTheDocument();
      });
      clickWizardNext(); // performance -> scaling
      await waitFor(() => {
        expect(screen.getByTestId('autoscaling-toggle')).toBeInTheDocument();
      });
      clickWizardNext(); // scaling -> review
      fireEvent.click(
        await screen.findByRole('button', { name: 'actions.submit.title' }),
      );

      await waitFor(() => {
        expect(deployAimSpy).toHaveBeenCalled();
      });
      const [, payload] = deployAimSpy.mock.calls[0]!;
      expect(payload).not.toHaveProperty('adapterMode');
      expect(payload).not.toHaveProperty('adapters');
      expect(payload.engineArgs).toBeUndefined();

      deployAimSpy.mockRestore();
    });
  });
});
