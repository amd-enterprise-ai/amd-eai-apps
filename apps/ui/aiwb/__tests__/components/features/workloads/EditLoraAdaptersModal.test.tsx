// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

import { EditLoraAdaptersModal } from '@/components/features/workloads/EditLoraAdaptersModal';
import { listAllAdapterArtifacts } from '@/lib/app/artifacts';
import { getProjectFineTunedModel } from '@/lib/app/aims';
import { getCustomModel } from '@/lib/app/custom-models';
import {
  getInferenceModel,
  invalidateAdapterQueries,
  updateInferenceAdapters,
} from '@/lib/app/inference';
import wrapper from '@/__tests__/ProviderWrapper';
import {
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
  type AIMProfileSpec,
  type AIMService,
} from '@/types/aims';
import type { LoraAdapter } from '@/types/artifacts';

const toast = { success: vi.fn(), error: vi.fn() };

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { names?: string }) =>
      options?.names ? `${key}: ${options.names}` : key,
  }),
}));

vi.mock('@amdenterpriseai/hooks', () => ({
  useSystemToast: () => ({ toast }),
}));

vi.mock('@/lib/app/artifacts', () => ({
  listAllAdapterArtifacts: vi.fn(),
}));

vi.mock('@/lib/app/inference', () => ({
  getInferenceModel: vi.fn(),
  invalidateAdapterQueries: vi.fn(),
  updateInferenceAdapters: vi.fn(),
}));

vi.mock('@/lib/app/aims', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/app/aims')>()),
  getProjectFineTunedModel: vi.fn(),
}));

vi.mock('@/lib/app/custom-models', () => ({
  getCustomModel: vi.fn(),
}));

vi.mock('@/components/features/loras/LoraAdapterSelectionTable', () => ({
  LoraAdapterSelectionTable: ({
    adapters,
    isLoading,
    selectedNames,
    onSelectionChange,
  }: {
    adapters: LoraAdapter[];
    isLoading: boolean;
    selectedNames: string[];
    onSelectionChange: (names: string[]) => void;
  }) => (
    <div>
      <span data-testid="adapter-table-loading">{String(isLoading)}</span>
      <span data-testid="eligible-adapters">
        {adapters.map((adapter) => adapter.name).join(',')}
      </span>
      <span data-testid="selected-adapters">{selectedNames.join(',')}</span>
      <button onClick={() => onSelectionChange([])}>Clear selection</button>
    </div>
  ),
}));

vi.mock('@amdenterpriseai/components', () => ({
  Modal: ({
    children,
    footer,
  }: React.PropsWithChildren<{ footer: React.ReactNode }>) => (
    <div>
      {children}
      {footer}
    </div>
  ),
  ActionButton: ({
    children,
    onPress,
    isDisabled,
  }: React.PropsWithChildren<{
    onPress?: () => void;
    isDisabled?: boolean;
  }>) => (
    <button onClick={onPress} disabled={isDisabled}>
      {children}
    </button>
  ),
}));

const deployment = {
  id: 'deployment-id',
  metadata: { name: 'deployment', labels: {}, annotations: {} },
  spec: {
    model: { name: 'base-model' },
    adapterMode: 'dynamic',
    adapters: [{ kind: 'AIMArtifact', name: 'eligible' }],
    adapterRuntime: { maxRank: 32 },
  },
} as unknown as AIMService;

const WORKLOAD_ID = '11111111-2222-3333-4444-555555555555';

// The id the artifacts endpoint resolves a deployment by, already lifted off
// the deployment's workload-id label by the list that opens this modal.
const deploymentWithWorkloadId = {
  ...deployment,
  id: WORKLOAD_ID,
} as unknown as AIMService;

// The deployment's model groups several quantised variants under one aimId,
// while the profile it resolved to loads one specific set of weights.
const MODEL_AIM_ID = 'example-org/base-model';
const RESOLVED_MODEL_ID = 'example-org/base-model-fp8';

const profileSpec = (overrides: Partial<AIMProfileSpec> = {}): AIMProfileSpec =>
  ({
    aimId: MODEL_AIM_ID,
    modelId: RESOLVED_MODEL_ID,
    features: ['adapters'],
    ...overrides,
  }) as AIMProfileSpec;

const resolvedProfileSpec = profileSpec();

const adapter = (
  name: string,
  overrides: Partial<LoraAdapter> = {},
): LoraAdapter => ({
  id: name,
  name,
  displayName: name,
  compatibleWith: [RESOLVED_MODEL_ID],
  rank: 16,
  readiness: 'Ready',
  // Servability is the API's verdict now, not something the modal re-derives
  // from the lineage above, so it is stated on the row like any other field.
  servable: true,
  ...overrides,
});

const mockListAllAdapterArtifacts = vi.mocked(listAllAdapterArtifacts);
const mockGetInferenceModel = vi.mocked(getInferenceModel);
const mockGetProjectFineTunedModel = vi.mocked(getProjectFineTunedModel);
const mockGetCustomModel = vi.mocked(getCustomModel);
const mockUpdateInferenceAdapters = vi.mocked(updateInferenceAdapters);
const resolvedModel = {
  metadata: { name: 'base-model' },
  status: { aimId: MODEL_AIM_ID },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetInferenceModel.mockResolvedValue(
    resolvedModel as Awaited<ReturnType<typeof getInferenceModel>>,
  );
  mockGetProjectFineTunedModel.mockResolvedValue(
    resolvedModel as Awaited<ReturnType<typeof getProjectFineTunedModel>>,
  );
  mockGetCustomModel.mockResolvedValue(
    resolvedModel as Awaited<ReturnType<typeof getCustomModel>>,
  );
  mockListAllAdapterArtifacts.mockResolvedValue([
    adapter('eligible'),
    adapter('rank-too-high', { rank: 64 }),
    adapter('wrong-model', {
      compatibleWith: ['example-org/other-model'],
      servable: false,
    }),
    adapter('grouping-id-only', {
      compatibleWith: [MODEL_AIM_ID],
      servable: false,
    }),
    adapter('not-ready', { readiness: 'NotReady' }),
    adapter('unknown-rank', { rank: null }),
    // The API answers null when it was not asked, or could not tell. An
    // undetermined verdict is not a yes.
    adapter('undetermined', { servable: null }),
  ]);
  mockUpdateInferenceAdapters.mockResolvedValue(undefined);
});

it('lists only ready, compatible LoRAs within the deployment rank', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getByTestId('eligible-adapters')).toHaveTextContent(
      'eligible',
    ),
  );
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent('eligible');
  expect(screen.getByTestId('eligible-adapters')).not.toHaveTextContent(
    'rank-too-high',
  );
  expect(screen.getByTestId('eligible-adapters')).not.toHaveTextContent(
    'wrong-model',
  );
  expect(screen.getByTestId('eligible-adapters')).not.toHaveTextContent(
    'not-ready',
  );
  expect(screen.getByTestId('eligible-adapters')).not.toHaveTextContent(
    'unknown-rank',
  );
  // An adapter trained against a sibling variant names the model's grouping
  // id rather than the weights this deployment runs, so the API reports it as
  // unservable and the modal takes that verdict as given.
  expect(screen.getByTestId('eligible-adapters')).not.toHaveTextContent(
    'grouping-id-only',
  );
  expect(mockGetInferenceModel).toHaveBeenCalledWith('base-model');
});

it('asks the adapter list which rows the deployment itself can serve', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deploymentWithWorkloadId}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  // Naming the deployment is what makes the verdict specific to the profile it
  // resolved; without it every row comes back undetermined and nothing is
  // offered.
  await waitFor(() =>
    expect(mockListAllAdapterArtifacts).toHaveBeenCalledWith(
      'project',
      WORKLOAD_ID,
    ),
  );
});

it('does not offer an adapter the deployment was told it cannot serve', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getByTestId('eligible-adapters')).toHaveTextContent(
      'eligible',
    ),
  );
  expect(screen.getByTestId('eligible-adapters')).not.toHaveTextContent(
    'wrong-model',
  );
});

it('does not offer an adapter whose servability was never answered', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getByTestId('eligible-adapters')).toHaveTextContent(
      'eligible',
    ),
  );
  // Offering a row on an unanswered question is how a deploy is handed an
  // adapter its runtime then refuses to load.
  expect(screen.getByTestId('eligible-adapters')).not.toHaveTextContent(
    'undetermined',
  );
});

it('names the profile as unable to load adapters instead of showing an empty table', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={profileSpec({ features: [] })}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await screen.findByTestId('profile-no-adapters');
  // An empty selection table would read as "no adapter matches", which invites
  // an Apply that detaches the ones already attached.
  expect(screen.queryByTestId('eligible-adapters')).not.toBeInTheDocument();
  expect(
    screen.queryByText('details.loraAdapters.edit.modelUnavailable'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText('details.loraAdapters.edit.modelUnreadable'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByTestId('profile-weights-unknown'),
  ).not.toBeInTheDocument();
});

it('keeps Apply disabled when the resolved profile cannot serve adapters', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={profileSpec({ features: [] })}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await screen.findByTestId('profile-no-adapters');
  // Every adapter is ineligible here, so the submitted set is empty while the
  // deployment has one attached — an enabled Apply would detach it on a click.
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();
  expect(mockUpdateInferenceAdapters).not.toHaveBeenCalled();
});

it('keeps Apply disabled when the resolved profile names no weights at all', async () => {
  // Neither modelId nor aimId — the API cannot tell which adapters to serve.
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={profileSpec({
        modelId: undefined,
        aimId: undefined,
      })}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await screen.findByTestId('profile-weights-unknown');
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();
  expect(screen.queryByTestId('eligible-adapters')).not.toBeInTheDocument();
  expect(screen.queryByTestId('profile-no-adapters')).not.toBeInTheDocument();
  expect(mockUpdateInferenceAdapters).not.toHaveBeenCalled();
});

it('shows the adapter table and enables Apply when the profile has only an aimId', async () => {
  // The API already decided servability per row; the modal defers to that verdict
  // rather than re-checking lineage locally. A profile with aimId but no modelId
  // is accepted by the backend two-arm rule, so the modal must not refuse it.
  mockListAllAdapterArtifacts.mockResolvedValue([
    adapter('aim-match', { compatibleWith: [MODEL_AIM_ID], servable: true }),
  ]);

  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={profileSpec({ modelId: undefined })}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getByTestId('eligible-adapters')).toHaveTextContent(
      'aim-match',
    ),
  );
  expect(
    screen.queryByTestId('profile-weights-unknown'),
  ).not.toBeInTheDocument();
  // The selection differs from the attached set, so Apply must be enabled.
  expect(
    screen.getByText('details.loraAdapters.edit.apply'),
  ).not.toBeDisabled();
});

it('does not warn about detaching adapters it has disabled Apply over', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={profileSpec({ features: [] })}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await screen.findByTestId('profile-no-adapters');
  // "will be detached if you apply" is untrue while Apply cannot be pressed.
  expect(
    screen.queryByText(/details\.loraAdapters\.edit\.willDetach/),
  ).not.toBeInTheDocument();
});

it('separates a profile that cannot serve adapters from a still-loading one', async () => {
  const { rerender } = render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={undefined}
      isResolvedProfileLoading
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  expect(screen.queryByTestId('profile-no-adapters')).not.toBeInTheDocument();
  expect(
    screen.queryByTestId('profile-weights-unknown'),
  ).not.toBeInTheDocument();
  expect(screen.getByTestId('adapter-table-loading')).toHaveTextContent('true');

  rerender(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={profileSpec({ features: [] })}
      isOpen
      onOpenChange={vi.fn()}
    />,
  );

  await screen.findByTestId('profile-no-adapters');
});

it('still lists adapters when the resolved profile can serve them', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getByTestId('eligible-adapters')).toHaveTextContent(
      'eligible',
    ),
  );
  expect(screen.queryByTestId('profile-no-adapters')).not.toBeInTheDocument();
  expect(
    screen.queryByTestId('profile-weights-unknown'),
  ).not.toBeInTheDocument();
});

it('does not claim the model is unresolvable while its profile is still loading', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={undefined}
      isResolvedProfileLoading
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(
      screen.getByText('details.loraAdapters.edit.description'),
    ).toBeInTheDocument(),
  );
  expect(
    screen.queryByText('details.loraAdapters.edit.modelUnavailable'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText('details.loraAdapters.edit.modelUnreadable'),
  ).not.toBeInTheDocument();
});

it('cannot detach the attached adapters while its profile is still loading', async () => {
  const onOpenChange = vi.fn();
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={undefined}
      isResolvedProfileLoading
      isOpen
      onOpenChange={onOpenChange}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
      'eligible',
    ),
  );
  // Nothing is eligible yet, so an untouched selection looks like a request to
  // detach everything; the user must not be able to submit it.
  expect(screen.getByTestId('adapter-table-loading')).toHaveTextContent('true');
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();

  fireEvent.click(screen.getByText('details.loraAdapters.edit.apply'));

  expect(mockUpdateInferenceAdapters).not.toHaveBeenCalled();
  expect(onOpenChange).not.toHaveBeenCalled();
});

it('reports a failed profile fetch as unloadable rather than as an unresolvable identity', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={undefined}
      isResolvedProfileError
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(
      screen.getByText('details.loraAdapters.edit.modelUnreadable'),
    ).toBeInTheDocument(),
  );
  expect(
    screen.queryByText('details.loraAdapters.edit.modelUnavailable'),
  ).not.toBeInTheDocument();
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();
});

it('disables Apply and keeps the attached selection when the serving profile is unknown', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={null}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(
      screen.getByText('details.loraAdapters.edit.modelUnavailable'),
    ).toBeInTheDocument(),
  );
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();
  // Rows may still be listed -- servability is the API's answer and does not
  // depend on this spec -- but the attached selection must survive untouched,
  // because a disabled Apply is the only thing standing between an unresolved
  // model and a submission that detaches everything.
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent('eligible');
  expect(mockUpdateInferenceAdapters).not.toHaveBeenCalled();
});

it('warns when an attached adapter is no longer eligible', async () => {
  const deploymentWithIneligibleAdapter = {
    ...deployment,
    spec: {
      ...deployment.spec,
      adapters: [{ kind: 'AIMArtifact', name: 'rank-too-high' }],
    },
  } as AIMService;

  render(
    <EditLoraAdaptersModal
      deployment={deploymentWithIneligibleAdapter}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  expect(
    await screen.findByText(/details\.loraAdapters\.edit\.willDetach/),
  ).toHaveTextContent('rank-too-high');
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
    'rank-too-high',
  );
});

it('drops a no-longer-eligible adapter from the submitted set on Apply, even if never toggled', async () => {
  const deploymentWithIneligibleAdapter = {
    ...deployment,
    spec: {
      ...deployment.spec,
      adapters: [
        { kind: 'AIMArtifact', name: 'eligible' },
        { kind: 'AIMArtifact', name: 'rank-too-high' },
      ],
    },
  } as AIMService;

  render(
    <EditLoraAdaptersModal
      deployment={deploymentWithIneligibleAdapter}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await screen.findByText(/details\.loraAdapters\.edit\.willDetach/);
  // The user applies without touching the selection table at all — the
  // table only renders eligible adapters, so "rank-too-high" was never an
  // option to toggle off, yet it must still not reach the PATCH.
  fireEvent.click(screen.getByText('details.loraAdapters.edit.apply'));

  await waitFor(() =>
    expect(mockUpdateInferenceAdapters).toHaveBeenCalledWith(
      'project',
      'deployment-id',
      ['eligible'],
    ),
  );
});

it.each([
  ['fine-tuned', { [FINE_TUNED_LABEL]: 'true' }, mockGetProjectFineTunedModel],
  ['custom', { [NAMESPACE_AIM_MODEL_LABEL]: 'true' }, mockGetCustomModel],
])('resolves the canonical ID for a %s model', async (_, labels, getter) => {
  const labeledDeployment = {
    ...deployment,
    metadata: { ...deployment.metadata, labels },
  } as AIMService;
  render(
    <EditLoraAdaptersModal
      deployment={labeledDeployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() => expect(getter).toHaveBeenCalled());
});

// A model carrying no aimId yet is one the controller has not finished
// reconciling, which reaches the modal as a lookup that yielded nothing rather
// than as a distinguishable state: retrying is the right advice for it.
it('disables Apply and keeps the attached selection when the model lookup yields no id', async () => {
  mockGetInferenceModel.mockResolvedValue({
    metadata: { name: 'base-model' },
    status: {},
  } as Awaited<ReturnType<typeof getInferenceModel>>);

  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(
      screen.getByText('details.loraAdapters.edit.modelUnreadable'),
    ).toBeInTheDocument(),
  );
  expect(
    screen.queryByText('details.loraAdapters.edit.modelUnavailable'),
  ).not.toBeInTheDocument();
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent('eligible');
});

it('reports a deployment naming no model as an unresolvable identity, not as a failed load', async () => {
  const deploymentWithoutModel = {
    ...deployment,
    spec: { ...deployment.spec, model: undefined },
  } as unknown as AIMService;

  render(
    <EditLoraAdaptersModal
      deployment={deploymentWithoutModel}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(
      screen.getByText('details.loraAdapters.edit.modelUnavailable'),
    ).toBeInTheDocument(),
  );
  expect(
    screen.queryByText('details.loraAdapters.edit.modelUnreadable'),
  ).not.toBeInTheDocument();
  expect(mockGetInferenceModel).not.toHaveBeenCalled();
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();
});

it('reports a failed model lookup as unreadable rather than as an unresolvable identity', async () => {
  mockGetInferenceModel.mockRejectedValue(new Error('network unavailable'));

  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(
      screen.getByText('details.loraAdapters.edit.modelUnreadable'),
    ).toBeInTheDocument(),
  );
  expect(
    screen.queryByText('details.loraAdapters.edit.modelUnavailable'),
  ).not.toBeInTheDocument();
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent('eligible');
});

it('keeps in-progress selection changes when deployment data refetches', async () => {
  const { rerender } = render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await screen.findByText('Clear selection');
  fireEvent.click(screen.getByText('Clear selection'));
  expect(screen.getByTestId('selected-adapters')).toBeEmptyDOMElement();

  rerender(
    <EditLoraAdaptersModal
      deployment={
        {
          ...deployment,
          spec: {
            ...deployment.spec,
            adapters: [
              { kind: 'AIMArtifact', name: 'eligible' },
              { kind: 'AIMArtifact', name: 'another-adapter' },
            ],
          },
        } as AIMService
      }
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
  );

  expect(screen.getByTestId('selected-adapters')).toBeEmptyDOMElement();
});

it('disables Apply and keeps the attached selection when loading adapters fails', async () => {
  mockListAllAdapterArtifacts.mockRejectedValue(
    new Error('network unavailable'),
  );

  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled(),
  );
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent('eligible');
});

it('cannot detach an attachment whose servability the API could not answer', async () => {
  const onOpenChange = vi.fn();
  // A healthy cached profile, a Ready attachment inside the rank budget, and
  // an artifacts response that could not resolve the deployment's serving
  // profile: null is "not answered", and must never be spent as a removal.
  mockListAllAdapterArtifacts.mockResolvedValue([
    adapter('eligible', { servable: null }),
    adapter('other'),
  ]);

  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={onOpenChange}
    />,
    { wrapper },
  );

  await screen.findByTestId('servability-unknown');
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent('eligible');
  expect(screen.getByTestId('eligible-adapters')).toHaveTextContent('eligible');
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();
  // Nothing was claimed as detachable, so nothing may be silently detached.
  expect(
    screen.queryByText(/details\.loraAdapters\.edit\.willDetach/),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByText('details.loraAdapters.edit.apply'));

  await waitFor(() =>
    expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
      'eligible',
    ),
  );
  expect(mockUpdateInferenceAdapters).not.toHaveBeenCalled();
  expect(onOpenChange).not.toHaveBeenCalled();
});

// The servability guard above closed one route to a silent detachment. The
// readiness filter is another way to the same loss: such an attachment never
// reached the candidate list, so it was absent from the eligible set, left the
// servability guard false, and was stripped from what Apply submitted.
it.each([['NotReady'], ['Unknown']])(
  'cannot detach an attachment whose readiness is %s on an untouched Apply',
  async (readiness) => {
    const onOpenChange = vi.fn();
    // Rank is null as well: an adapter still importing has not had its rank
    // read yet, so a guard that consulted rank would condemn it anyway.
    mockListAllAdapterArtifacts.mockResolvedValue([
      adapter('eligible'),
      adapter('still-importing', {
        readiness: readiness as LoraAdapter['readiness'],
        rank: null,
      }),
    ]);
    const deploymentWithUnreadyAttachment = {
      ...deployment,
      spec: {
        ...deployment.spec,
        adapters: [
          { kind: 'AIMArtifact', name: 'eligible' },
          { kind: 'AIMArtifact', name: 'still-importing' },
        ],
      },
    } as AIMService;

    render(
      <EditLoraAdaptersModal
        deployment={deploymentWithUnreadyAttachment}
        namespace="project"
        resolvedProfileSpec={resolvedProfileSpec}
        isOpen
        onOpenChange={onOpenChange}
      />,
      { wrapper },
    );

    // Visible and still checked: hiding it would read as "already detached".
    await screen.findByTestId('attachments-not-ready');
    expect(screen.getByTestId('eligible-adapters')).toHaveTextContent(
      'still-importing',
    );
    expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
      'still-importing',
    );
    // Not yet judged, so no detachment may be promised for it either.
    expect(
      screen.queryByText(/details\.loraAdapters\.edit\.willDetach/),
    ).not.toBeInTheDocument();
    expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();

    fireEvent.click(screen.getByText('details.loraAdapters.edit.apply'));

    await waitFor(() =>
      expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
        'still-importing',
      ),
    );
    // The absence of the call is the assertion: a reduced argument would still
    // be the detachment, merely announced.
    expect(mockUpdateInferenceAdapters).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  },
);

// Guarding the attachment must not take the deliberate detachment with it:
// clearing the row is the user saying the removal is meant.
it('detaches an unready attachment once the user clears it', async () => {
  mockListAllAdapterArtifacts.mockResolvedValue([
    adapter('eligible'),
    adapter('still-importing', { readiness: 'NotReady', rank: null }),
  ]);
  const deploymentWithUnreadyAttachment = {
    ...deployment,
    spec: {
      ...deployment.spec,
      adapters: [
        { kind: 'AIMArtifact', name: 'eligible' },
        { kind: 'AIMArtifact', name: 'still-importing' },
      ],
    },
  } as AIMService;

  render(
    <EditLoraAdaptersModal
      deployment={deploymentWithUnreadyAttachment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await screen.findByTestId('attachments-not-ready');
  fireEvent.click(screen.getByText('Clear selection'));

  await waitFor(() =>
    expect(screen.getByText('details.loraAdapters.edit.apply')).toBeEnabled(),
  );
  fireEvent.click(screen.getByText('details.loraAdapters.edit.apply'));

  await waitFor(() =>
    expect(mockUpdateInferenceAdapters).toHaveBeenCalledWith(
      'project',
      'deployment-id',
      [],
    ),
  );
});

it('applies an empty selection and reports success', async () => {
  const onOpenChange = vi.fn();
  const onSuccess = vi.fn();
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={onOpenChange}
      onSuccess={onSuccess}
    />,
    { wrapper },
  );

  await screen.findByText('Clear selection');
  fireEvent.click(screen.getByText('Clear selection'));
  fireEvent.click(screen.getByText('details.loraAdapters.edit.apply'));

  await waitFor(() =>
    expect(mockUpdateInferenceAdapters).toHaveBeenCalledWith(
      'project',
      'deployment-id',
      [],
    ),
  );
  expect(invalidateAdapterQueries).toHaveBeenCalledWith(
    expect.anything(),
    'project',
  );
  expect(onSuccess).toHaveBeenCalledOnce();
  expect(toast.success).toHaveBeenCalledWith(
    'details.loraAdapters.edit.success',
  );
  expect(onOpenChange).toHaveBeenCalledWith(false);
});

it('disables Apply while the selection still matches the attached adapters', async () => {
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={vi.fn()}
    />,
    { wrapper },
  );

  await waitFor(() =>
    expect(screen.getByTestId('eligible-adapters')).toHaveTextContent(
      'eligible',
    ),
  );
  // Applying the attached set back unchanged would PATCH, toast and
  // invalidate for nothing.
  expect(screen.getByText('details.loraAdapters.edit.apply')).toBeDisabled();

  fireEvent.click(screen.getByText('Clear selection'));

  expect(
    screen.getByText('details.loraAdapters.edit.apply'),
  ).not.toBeDisabled();
  expect(mockUpdateInferenceAdapters).not.toHaveBeenCalled();
});

it('keeps the modal open and reports an update failure', async () => {
  const onOpenChange = vi.fn();
  mockUpdateInferenceAdapters.mockRejectedValue(new Error('failed'));
  render(
    <EditLoraAdaptersModal
      deployment={deployment}
      namespace="project"
      resolvedProfileSpec={resolvedProfileSpec}
      isOpen
      onOpenChange={onOpenChange}
    />,
    { wrapper },
  );

  await screen.findByText('Clear selection');
  fireEvent.click(screen.getByText('Clear selection'));
  await waitFor(() =>
    expect(
      screen.getByText('details.loraAdapters.edit.apply'),
    ).not.toBeDisabled(),
  );
  fireEvent.click(screen.getByText('details.loraAdapters.edit.apply'));

  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith('details.loraAdapters.edit.error'),
  );
  expect(onOpenChange).not.toHaveBeenCalled();
});
