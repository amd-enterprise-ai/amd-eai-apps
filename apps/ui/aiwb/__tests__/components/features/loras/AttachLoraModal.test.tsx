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
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import wrapper from '@/__tests__/ProviderWrapper';
import {
  invalidateQueriesSpy,
  wrapQueryClientWithInvalidateSpy,
} from '@/__tests__/testUtils/queryClientSpy';
import { AttachLoraModal } from '@/components/features/loras/AttachLoraModal';
import { useProfileSpecsForServices } from '@/hooks/useProfileSpecsForServices';
import { profileKey } from '@/lib/app/aims/profileKey';
import { resolveDeploymentAimId } from '@/lib/app/deployment-model';
import {
  attachAdapterToDeployment,
  invalidateAdapterQueries,
  listInferenceDeployments,
} from '@/lib/app/inference';
import {
  FINE_TUNED_LABEL,
  type AIMProfileSpec,
  type AIMService,
} from '@/types/aims';
import type { LoraAdapter } from '@/types/artifacts';

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return {
    ...actual,
    useQueryClient: () =>
      wrapQueryClientWithInvalidateSpy(actual.useQueryClient()),
  };
});

const mockToast = { success: vi.fn(), error: vi.fn() };

vi.mock('@amdenterpriseai/hooks', () => ({
  useSystemToast: () => ({ toast: mockToast }),
}));

// The real Select/SelectItem are React Aria components too heavy to exercise
// here. This mock preserves the bits the tests need: SelectItem's React
// `key` (mirroring how the real component derives its item ids) drives which
// deployment `onChange` reports when an option is clicked.
vi.mock('@amdenterpriseai/components', async () => {
  const { Children, cloneElement, isValidElement } = await import('react');

  const wireOptions = (
    nodes: ReactNode,
    onSelect: (value: string) => void,
  ): ReactNode =>
    Children.map(nodes, (child) => {
      if (!isValidElement(child)) return child;
      if (child.key == null) {
        // A ListboxSection: recurse into its own items.
        const { children } = child.props as { children?: ReactNode };
        return cloneElement(child, {
          children: wireOptions(children, onSelect),
        } as never);
      }
      return cloneElement(child, {
        onSelect: () => onSelect(String(child.key)),
      } as never);
    });

  return {
    ActionButton: ({
      children,
      isDisabled,
      isLoading,
      onPress,
    }: {
      children: ReactNode;
      isDisabled?: boolean;
      isLoading?: boolean;
      onPress?: () => void;
    }) => (
      <button
        disabled={isDisabled || isLoading}
        onClick={onPress}
        type="button"
      >
        {children}
      </button>
    ),
    Alert: ({
      children,
      description,
      title,
      ...props
    }: {
      children?: ReactNode;
      description?: ReactNode;
      title: ReactNode;
    }) => (
      <div role="alert" {...props}>
        {title}
        {description}
        {children}
      </div>
    ),
    ListboxSection: ({
      children,
      title,
    }: {
      children: ReactNode;
      title: ReactNode;
    }) => (
      <section aria-label={String(title)}>
        <h2>{title}</h2>
        {children}
      </section>
    ),
    Modal: ({
      children,
      footer,
      title,
    }: {
      children: ReactNode;
      footer: ReactNode;
      title: ReactNode;
    }) => (
      <div role="dialog">
        <h1>{title}</h1>
        {children}
        {footer}
      </div>
    ),
    Select: ({
      children,
      onChange,
    }: {
      children: ReactNode;
      onChange?: (event: { target: { value: string } }) => void;
    }) => (
      <div>
        {wireOptions(children, (value) => onChange?.({ target: { value } }))}
      </div>
    ),
    SelectItem: ({
      children,
      description,
      isDisabled,
      startContent,
      onSelect,
    }: {
      children: ReactNode;
      description?: ReactNode;
      isDisabled?: boolean;
      startContent?: ReactNode;
      onSelect?: () => void;
    }) => (
      <div
        aria-disabled={isDisabled}
        onClick={isDisabled ? undefined : onSelect}
        role="option"
        tabIndex={-1}
      >
        {startContent}
        {children}
        {description}
      </div>
    ),
  };
});

vi.mock('@/hooks/useProfileSpecsForServices', () => ({
  useProfileSpecsForServices: vi.fn(),
}));

// invalidateAdapterQueries keeps its real implementation so the query keys it
// invalidates are asserted through `invalidateQueriesSpy` instead of against a
// stub that can drift from the keys the pages actually read.
vi.mock('@/lib/app/inference', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/app/inference')>();
  return {
    attachAdapterToDeployment: vi.fn(),
    invalidateAdapterQueries: vi.fn(actual.invalidateAdapterQueries),
    listInferenceDeployments: vi.fn(),
  };
});

vi.mock('@/lib/app/deployment-model', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/app/deployment-model')>();
  return {
    ...actual,
    resolveDeploymentAimId: vi.fn(),
  };
});

// A model's aimId groups its quantised variants; each profile names the one
// set of weights it loads, and that is what an adapter is trained against.
const MODEL_AIM_ID = 'example-org/base-model';
const SERVED_MODEL_ID = 'example-org/base-model-fp8';
const SIBLING_MODEL_ID = 'example-org/base-model-bf16';

const adapter: LoraAdapter = {
  id: 'adapter-1',
  name: 'adapter-1',
  displayName: 'Support LoRA',
  compatibleWith: [SERVED_MODEL_ID],
  rank: 16,
  readiness: 'Ready',
};

const profileSpec = (
  modelId: string,
  features = ['adapters'],
): AIMProfileSpec =>
  ({ aimId: MODEL_AIM_ID, modelId, features }) as AIMProfileSpec;

const profileNameOf = (deploymentName: string) => `${deploymentName}-profile`;

/** Resolves every rendered deployment's profile to the served weights. */
const specsServing = (deployments: AIMService[], modelId = SERVED_MODEL_ID) =>
  new Map(
    deployments.map((deployment) => [
      profileKey(
        deployment.status?.resolvedProfile?.scope,
        profileNameOf(deployment.metadata.name),
      ),
      profileSpec(modelId),
    ]),
  );

const pageOfDeployments = (data: AIMService[]) => ({
  data,
  pagination: { total: data.length, page: 1, pageSize: 100 },
});

const deployment = ({
  adapterMode = 'dynamic',
  attached = false,
  name,
  maxRank = 64,
  labels = {},
}: {
  adapterMode?: NonNullable<AIMService['spec']>['adapterMode'];
  attached?: boolean;
  name: string;
  maxRank?: number | null;
  labels?: Record<string, string>;
}): AIMService =>
  ({
    id: name,
    metadata: { annotations: {}, labels, name },
    spec: {
      adapterMode,
      adapterRuntime: maxRank == null ? undefined : { maxRank },
      adapters: attached ? [{ kind: 'AIMArtifact', name: adapter.name }] : [],
      model: { name: `${name}-model` },
    },
    status: {
      status: 'Running',
      resolvedProfile: { name: profileNameOf(name), scope: 'Cluster' },
    },
    statusValue: 'Running',
  }) as AIMService;

const renderModal = async (
  deployments: AIMService[],
  overrides: {
    adapter?: LoraAdapter;
    onOpenChange?: (isOpen: boolean) => void;
    specByName?: Map<string, AIMProfileSpec>;
  } = {},
) => {
  vi.mocked(listInferenceDeployments).mockResolvedValue(
    pageOfDeployments(deployments),
  );
  vi.mocked(resolveDeploymentAimId).mockResolvedValue(MODEL_AIM_ID);
  vi.mocked(useProfileSpecsForServices).mockReturnValue({
    isError: false,
    refetch: vi.fn(),
    isLoading: false,
    specByName: overrides.specByName ?? specsServing(deployments),
  });

  render(
    <AttachLoraModal
      adapter={overrides.adapter ?? adapter}
      isOpen
      onOpenChange={overrides.onOpenChange ?? vi.fn()}
    />,
    { wrapper },
  );

  await screen.findByText(deployments[0].metadata.name);
};

describe('AttachLoraModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    invalidateQueriesSpy.mockClear();
    vi.mocked(useProfileSpecsForServices).mockReturnValue({
      isError: false,
      refetch: vi.fn(),
      isLoading: false,
      specByName: new Map(),
    });
    vi.mocked(attachAdapterToDeployment).mockResolvedValue(undefined as never);
  });

  it('shows only the compatible section when every deployment is compatible', async () => {
    await renderModal([deployment({ name: 'compatible-deployment' })]);

    expect(
      screen.getByRole('region', {
        name: 'attachLora.sections.compatible',
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('region', {
        name: 'attachLora.sections.incompatible',
      }),
    ).not.toBeInTheDocument();
  });

  it('shows only the incompatible section when no deployment is compatible', async () => {
    await renderModal([
      deployment({ adapterMode: 'static', name: 'incompatible-deployment' }),
    ]);

    expect(
      screen.getByRole('region', {
        name: 'attachLora.sections.incompatible',
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('region', {
        name: 'attachLora.sections.compatible',
      }),
    ).not.toBeInTheDocument();
  });

  it('keeps an attached deployment in its section but disables it', async () => {
    await renderModal([
      deployment({ attached: true, name: 'attached-deployment' }),
    ]);

    const compatibleSection = screen.getByRole('region', {
      name: 'attachLora.sections.compatible',
    });
    const option = within(compatibleSection).getByRole('option');
    expect(option).toHaveAttribute('aria-disabled', 'true');
    expect(
      within(option).getByRole('img', {
        name: 'attachLora.status.attached',
      }),
    ).toContainElement(option.querySelector('.text-success'));
  });

  it('treats an adapter with an unknown rank as incompatible', async () => {
    await renderModal([deployment({ name: 'unknown-rank-deployment' })], {
      adapter: { ...adapter, rank: null },
    });

    const incompatibleSection = screen.getByRole('region', {
      name: 'attachLora.sections.incompatible',
    });
    expect(
      within(incompatibleSection).getByText(
        'attachLora.incompatibility.adapterRankUnavailable',
      ),
    ).toBeInTheDocument();
  });

  it('treats a deployment with an unknown maximum rank as incompatible', async () => {
    await renderModal([
      deployment({ name: 'unknown-maximum-rank-deployment', maxRank: null }),
    ]);

    const incompatibleSection = screen.getByRole('region', {
      name: 'attachLora.sections.incompatible',
    });
    expect(
      within(incompatibleSection).getByText(
        'attachLora.incompatibility.maxRankUnavailable',
      ),
    ).toBeInTheDocument();
  });

  it('treats a deployment below the adapter rank as incompatible', async () => {
    await renderModal([
      deployment({ name: 'rank-too-low-deployment', maxRank: 8 }),
    ]);

    const incompatibleSection = screen.getByRole('region', {
      name: 'attachLora.sections.incompatible',
    });
    expect(
      within(incompatibleSection).getByText(
        'attachLora.incompatibility.maxRank',
      ),
    ).toBeInTheDocument();
  });

  it('includes a fine-tuned deployment not present in the cluster catalog', async () => {
    await renderModal([
      deployment({
        labels: { [FINE_TUNED_LABEL]: 'true' },
        name: 'fine-tuned-deployment',
      }),
    ]);

    expect(
      screen.getByRole('option', { name: /fine-tuned-deployment/ }),
    ).toBeInTheDocument();
  });

  it('looks up profiles for every running deployment', async () => {
    const deployments = [
      deployment({ name: 'compatible-deployment' }),
      deployment({ name: 'other-model-deployment' }),
    ];
    vi.mocked(listInferenceDeployments).mockResolvedValue(
      pageOfDeployments(deployments),
    );
    vi.mocked(resolveDeploymentAimId).mockImplementation(
      async (_namespace, service) =>
        service.id === 'compatible-deployment'
          ? MODEL_AIM_ID
          : 'example-org/other-model',
    );
    vi.mocked(useProfileSpecsForServices).mockReturnValue({
      isError: false,
      refetch: vi.fn(),
      isLoading: false,
      specByName: specsServing(deployments),
    });
    render(
      <AttachLoraModal adapter={adapter} isOpen onOpenChange={vi.fn()} />,
      { wrapper },
    );

    await screen.findByRole('option', { name: /compatible-deployment/ });

    // The profiles are what decide compatibility, so narrowing the lookup to
    // already-compatible deployments would leave the filter without inputs.
    await waitFor(() => {
      expect(useProfileSpecsForServices).toHaveBeenLastCalledWith(
        expect.objectContaining({
          aimIds: [MODEL_AIM_ID, 'example-org/other-model'],
        }),
      );
    });
  });

  it('offers only the deployments whose serving profile can load the adapter', async () => {
    const serving = deployment({ name: 'serving-deployment' });
    const siblingVariant = deployment({ name: 'sibling-variant-deployment' });
    await renderModal([serving, siblingVariant], {
      specByName: new Map([
        [
          profileKey('Cluster', profileNameOf(serving.metadata.name)),
          profileSpec(SERVED_MODEL_ID),
        ],
        [
          profileKey('Cluster', profileNameOf(siblingVariant.metadata.name)),
          profileSpec(SIBLING_MODEL_ID),
        ],
      ]),
    });

    expect(
      screen.getByRole('option', { name: /serving-deployment/ }),
    ).toBeInTheDocument();
    // Both deployments run the same catalog model, so keying on that model
    // would have offered a deployment whose weights the adapter never saw.
    expect(
      screen.queryByRole('option', { name: /sibling-variant-deployment/ }),
    ).not.toBeInTheDocument();
  });

  it('offers the deployment when the adapter only names the model grouping id', async () => {
    const deployments = [deployment({ name: 'compatible-deployment' })];
    vi.mocked(listInferenceDeployments).mockResolvedValue(
      pageOfDeployments(deployments),
    );
    vi.mocked(resolveDeploymentAimId).mockResolvedValue(MODEL_AIM_ID);
    vi.mocked(useProfileSpecsForServices).mockReturnValue({
      isError: false,
      refetch: vi.fn(),
      isLoading: false,
      specByName: specsServing(deployments),
    });
    render(
      <AttachLoraModal
        adapter={{ ...adapter, compatibleWith: [MODEL_AIM_ID] }}
        isOpen
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );

    // The grouping id is coarser than the weights the profile serves, but every
    // producer still writes it and the attach endpoint accepts it — refusing it
    // here would hide a deployment the API would have taken. Flip this with the
    // aimId arm of `canProfilesServeAdapter`.
    expect(
      await screen.findByRole('option', { name: /compatible-deployment/ }),
    ).toBeInTheDocument();
  });

  it('waits for profiles before declaring that nothing can serve the adapter', async () => {
    vi.mocked(listInferenceDeployments).mockResolvedValue(
      pageOfDeployments([deployment({ name: 'compatible-deployment' })]),
    );
    vi.mocked(resolveDeploymentAimId).mockResolvedValue(MODEL_AIM_ID);
    vi.mocked(useProfileSpecsForServices).mockReturnValue({
      isError: false,
      refetch: vi.fn(),
      isLoading: true,
      specByName: new Map(),
    });
    render(
      <AttachLoraModal adapter={adapter} isOpen onOpenChange={vi.fn()} />,
      { wrapper },
    );

    await waitFor(() => {
      expect(resolveDeploymentAimId).toHaveBeenCalled();
    });
    expect(
      screen.queryByTestId('attach-lora-empty-state'),
    ).not.toBeInTheDocument();
  });

  it('offers to retry instead of claiming nothing can serve the adapter when the profile lookup fails', async () => {
    const refetch = vi.fn().mockResolvedValue(undefined);
    vi.mocked(listInferenceDeployments).mockResolvedValue(
      pageOfDeployments([deployment({ name: 'compatible-deployment' })]),
    );
    vi.mocked(resolveDeploymentAimId).mockResolvedValue(MODEL_AIM_ID);
    vi.mocked(useProfileSpecsForServices).mockReturnValue({
      isLoading: false,
      isError: true,
      refetch,
      specByName: new Map(),
    });
    render(
      <AttachLoraModal adapter={adapter} isOpen onOpenChange={vi.fn()} />,
      { wrapper },
    );

    // Eligibility was never established, so an empty result is an unanswered
    // question rather than the answer "no deployment can serve this".
    expect(
      await screen.findByTestId('attach-lora-error-state'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('attach-lora-empty-state'),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'attachLora.actions.retry' }),
    );

    await waitFor(() => {
      expect(refetch).toHaveBeenCalled();
    });
  });

  it('attaches the adapter to the selected compatible deployment', async () => {
    const onOpenChange = vi.fn();
    await renderModal([deployment({ name: 'compatible-deployment' })], {
      onOpenChange,
    });

    fireEvent.click(
      screen.getByRole('option', { name: /compatible-deployment/ }),
    );

    const attachButton = screen.getByRole('button', {
      name: 'attachLora.actions.attach',
    });
    expect(attachButton).toBeEnabled();
    fireEvent.click(attachButton);

    await waitFor(() => {
      expect(attachAdapterToDeployment).toHaveBeenCalledWith(
        'project1',
        expect.objectContaining({ id: 'compatible-deployment' }),
        adapter.name,
      );
    });
    expect(mockToast.success).toHaveBeenCalled();
    expect(invalidateAdapterQueries).toHaveBeenCalledWith(
      expect.anything(),
      'project1',
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('refreshes both the deployment list and the deployment details after attaching', async () => {
    await renderModal([deployment({ name: 'compatible-deployment' })]);

    fireEvent.click(
      screen.getByRole('option', { name: /compatible-deployment/ }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'attachLora.actions.attach' }),
    );

    await waitFor(() => {
      expect(invalidateQueriesSpy).toHaveBeenCalledWith({
        queryKey: ['project', 'project1', 'inference'],
      });
    });
    // The AIM details page reads its deployment from this key with
    // refetchOnMount disabled, so it only shows the new adapter if the attach
    // invalidates it too.
    expect(invalidateQueriesSpy).toHaveBeenCalledWith({
      queryKey: ['aimService', 'project1'],
    });
  });

  it('shows an error and keeps the modal open when the attach mutation fails', async () => {
    vi.mocked(attachAdapterToDeployment).mockRejectedValue(
      new Error('attach failed'),
    );
    const onOpenChange = vi.fn();
    await renderModal([deployment({ name: 'compatible-deployment' })], {
      onOpenChange,
    });

    fireEvent.click(
      screen.getByRole('option', { name: /compatible-deployment/ }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'attachLora.actions.attach' }),
    );

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'attachLora.notifications.error',
      );
    });
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('shows an error and retries when deployment loading fails', async () => {
    vi.mocked(listInferenceDeployments)
      .mockRejectedValueOnce(new Error('load failed'))
      .mockResolvedValueOnce(pageOfDeployments([]));
    vi.mocked(resolveDeploymentAimId).mockResolvedValue(
      'example-org/base-model',
    );
    render(
      <AttachLoraModal adapter={adapter} isOpen onOpenChange={vi.fn()} />,
      { wrapper },
    );

    expect(
      await screen.findByTestId('attach-lora-error-state'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('attach-lora-empty-state'),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'attachLora.actions.retry' }),
    );

    await waitFor(() => {
      expect(listInferenceDeployments).toHaveBeenCalledTimes(2);
    });
  });

  it('shows an error when a deployment model cannot be resolved', async () => {
    vi.mocked(listInferenceDeployments).mockResolvedValue(
      pageOfDeployments([deployment({ name: 'unresolved-deployment' })]),
    );
    vi.mocked(resolveDeploymentAimId).mockRejectedValue(
      new Error('model resolution failed'),
    );
    render(
      <AttachLoraModal adapter={adapter} isOpen onOpenChange={vi.fn()} />,
      { wrapper },
    );

    expect(
      await screen.findByTestId('attach-lora-error-state'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('attach-lora-empty-state'),
    ).not.toBeInTheDocument();
  });
});
