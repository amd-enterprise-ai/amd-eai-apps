// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';

import {
  personalizationStepDefaults,
  PersonalizationStepFields,
} from '@/components/features/models/DeployAIMWizard/steps/PersonalizationStep';
import type { DeployAIMFormValues } from '@/components/features/models/DeployAIMWizard/types';
import type { LoraAdapter } from '@/types/artifacts';

import { formValues } from './fixtures';

// Scoped to PersonalizationStepFields' own wiring (toggle visibility, rank
// recompute, pruning). Search/rank-rendering behavior of the real table lives
// in LoraAdapterSelectionTable.test.tsx and isn't duplicated here.
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
    <div data-testid="lora-adapters-selector-stub">
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

const adapter = (
  name: string,
  rank: number,
  overrides: Partial<LoraAdapter> = {},
): LoraAdapter => ({
  id: name,
  name,
  displayName: name,
  compatibleWith: [],
  readiness: 'Ready',
  rank,
  ...overrides,
});

const PersonalizationStepHarness = ({
  adapters,
  maxLoraRank,
  selectedAdapters,
}: {
  adapters: LoraAdapter[];
  maxLoraRank?: string;
  selectedAdapters?: string[];
}) => {
  const form = useForm<DeployAIMFormValues>({
    defaultValues: {
      ...formValues,
      ...personalizationStepDefaults,
      ...(maxLoraRank ? { maxLoraRank } : {}),
      ...(selectedAdapters ? { adapters: selectedAdapters } : {}),
    },
  });
  return (
    <>
      <PersonalizationStepFields
        form={form}
        adapters={adapters}
        isLoading={false}
      />
      <output data-testid="selected-adapters">
        {(form.watch('adapters') ?? []).join(',')}
      </output>
      <output data-testid="max-lora-rank">{form.watch('maxLoraRank')}</output>
    </>
  );
};

const enablePersonalization = () =>
  fireEvent.click(
    screen.getByRole('switch', { name: 'deployAIM.personalization.enable' }),
  );

describe('PersonalizationStepFields', () => {
  it('reveals the rank select and adapter picker only once personalization is enabled', () => {
    render(<PersonalizationStepHarness adapters={[adapter('one', 8)]} />);

    expect(
      screen.queryByRole('button', { name: /maxRank\.label/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('lora-adapters-selector-stub'),
    ).not.toBeInTheDocument();

    enablePersonalization();

    expect(
      screen.getByRole('button', { name: /maxRank\.label/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('lora-adapters-selector-stub'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('max-lora-rank')).toHaveTextContent('32');
  });

  it('raises maxLoraRank to the next supported ceiling when a known-rank adapter is selected', () => {
    render(<PersonalizationStepHarness adapters={[adapter('big', 20)]} />);
    enablePersonalization();

    fireEvent.click(screen.getByRole('button', { name: 'Select big' }));

    expect(screen.getByTestId('selected-adapters')).toHaveTextContent('big');
    // rank 20 has no exact tier; the next supported ceiling above it is 32.
    expect(screen.getByTestId('max-lora-rank')).toHaveTextContent('32');
  });

  it('prunes selections without lowering the configured maximum rank', () => {
    const { rerender } = render(
      <PersonalizationStepHarness
        adapters={[adapter('small', 8), adapter('big', 100)]}
      />,
    );
    enablePersonalization();
    fireEvent.click(screen.getByRole('button', { name: 'Select small' }));
    fireEvent.click(screen.getByRole('button', { name: 'Select big' }));

    expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
      'small,big',
    );
    expect(screen.getByTestId('max-lora-rank')).toHaveTextContent('128');

    // Simulate the AIM/profile changing so 'big' is no longer compatible.
    rerender(<PersonalizationStepHarness adapters={[adapter('small', 8)]} />);

    expect(screen.getByTestId('selected-adapters')).toHaveTextContent('small');
    expect(screen.getByTestId('max-lora-rank')).toHaveTextContent('128');
  });

  it('preserves a user-selected rank above the selected adapter requirement', () => {
    render(
      <PersonalizationStepHarness
        adapters={[adapter('small', 8)]}
        maxLoraRank="128"
      />,
    );
    enablePersonalization();

    fireEvent.click(screen.getByRole('button', { name: 'Select small' }));

    expect(screen.getByTestId('max-lora-rank')).toHaveTextContent('128');
  });

  it('disables maximum rank options below the selected adapter requirement', () => {
    render(<PersonalizationStepHarness adapters={[adapter('big', 100)]} />);
    enablePersonalization();
    fireEvent.click(screen.getByRole('button', { name: 'Select big' }));
    fireEvent.click(
      screen.getByRole('button', {
        name: /deployAIM\.personalization\.maxRank\.label/,
      }),
    );

    expect(screen.getByRole('option', { name: '64' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByRole('option', { name: '128' })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('leaves every maximum rank option selectable while no adapter is selected', () => {
    render(<PersonalizationStepHarness adapters={[adapter('small', 8)]} />);
    enablePersonalization();
    fireEvent.click(
      screen.getByRole('button', {
        name: /deployAIM\.personalization\.maxRank\.label/,
      }),
    );

    // Nothing is selected, so no adapter constrains the ceiling: the tiers
    // below the form default (32) must stay reachable.
    for (const rank of ['1', '8', '16']) {
      expect(screen.getByRole('option', { name: rank })).not.toHaveAttribute(
        'aria-disabled',
        'true',
      );
    }
  });

  it('does not offer adapters above the maximum supported rank', () => {
    render(
      <PersonalizationStepHarness adapters={[adapter('too-big', 1024)]} />,
    );
    enablePersonalization();

    expect(
      screen.queryByRole('button', { name: 'Select too-big' }),
    ).not.toBeInTheDocument();
  });
});

it('names a selected adapter the narrowed profiles can no longer serve', () => {
  render(
    <PersonalizationStepHarness
      adapters={[
        adapter('fp8-adapter', 8),
        adapter('fp16-adapter', 8, { servable: false }),
      ]}
      selectedAdapters={['fp16-adapter']}
    />,
  );

  enablePersonalization();

  expect(screen.getByTestId('unservable-adapters-warning')).toBeInTheDocument();
  // Dropping it silently is how a deploy ends up missing an adapter the user
  // believes they asked for, so the selection is kept for them to act on.
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
    'fp16-adapter',
  );
});

it('names a selected adapter whose weights have not finished importing', () => {
  render(
    <PersonalizationStepHarness
      adapters={[
        adapter('fp8-adapter', 8),
        adapter('importing', 8, { readiness: 'NotReady' }),
      ]}
      selectedAdapters={['importing']}
    />,
  );

  enablePersonalization();

  // Weights still arriving is a different problem from a lineage that will
  // never match: one resolves by waiting, the other only by changing the
  // selection, so telling the user the wrong one sends them nowhere.
  expect(screen.getByTestId('not-ready-adapters-warning')).toBeInTheDocument();
  expect(
    screen.queryByTestId('unservable-adapters-warning'),
  ).not.toBeInTheDocument();
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
    'importing',
  );
});

it('says nothing when every selected adapter is still servable', () => {
  render(
    <PersonalizationStepHarness
      adapters={[adapter('fp8-adapter', 8)]}
      selectedAdapters={['fp8-adapter']}
    />,
  );

  enablePersonalization();

  expect(
    screen.queryByTestId('unservable-adapters-warning'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByTestId('not-ready-adapters-warning'),
  ).not.toBeInTheDocument();
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
    'fp8-adapter',
  );
});

it('lets the user clear a retained unservable selection without leaving the step', () => {
  render(
    <PersonalizationStepHarness
      adapters={[
        adapter('fp8-adapter', 8),
        adapter('fp16-adapter', 8, { servable: false }),
      ]}
      selectedAdapters={['fp16-adapter']}
    />,
  );

  enablePersonalization();

  // Warning about a name with no row of its own is a dead end: the deploy
  // stays blocked and the step offers nothing to act on.
  expect(screen.getByTestId('unservable-adapters-warning')).toBeInTheDocument();
  const retainedRow = screen.getByRole('button', {
    name: 'Select fp16-adapter',
  });
  expect(retainedRow).toHaveAttribute('data-unservable', 'true');

  fireEvent.click(retainedRow);

  // The warning is answered by the wizard withdrawing the row on the next
  // render; what the step owes is a clearable selection.
  expect(screen.getByTestId('selected-adapters').textContent).toBe('');
});

it('lets the user clear a retained still-importing selection without leaving the step', () => {
  render(
    <PersonalizationStepHarness
      adapters={[
        adapter('fp8-adapter', 8),
        adapter('importing', 8, { readiness: 'NotReady' }),
      ]}
      selectedAdapters={['importing']}
    />,
  );

  enablePersonalization();

  const retainedRow = screen.getByRole('button', { name: 'Select importing' });
  expect(retainedRow).toHaveAttribute('data-not-ready', 'true');

  fireEvent.click(retainedRow);

  expect(screen.getByTestId('selected-adapters').textContent).toBe('');
});

it('keeps offering the servable adapters alongside a retained one', () => {
  render(
    <PersonalizationStepHarness
      adapters={[
        adapter('fp8-adapter', 8),
        adapter('fp16-adapter', 8, { servable: false }),
      ]}
      selectedAdapters={['fp16-adapter']}
    />,
  );

  enablePersonalization();

  expect(
    screen.getByRole('button', { name: 'Select fp8-adapter' }),
  ).toHaveAttribute('data-unservable', 'false');
});

it('does not raise the rank ceiling for a retained unservable adapter', () => {
  render(
    <PersonalizationStepHarness
      adapters={[
        adapter('fp8-adapter', 8),
        adapter('big-unservable', 256, { servable: false }),
      ]}
      selectedAdapters={['big-unservable']}
    />,
  );

  enablePersonalization();

  // An adapter that cannot be deployed must not drag the deployment's rank
  // ceiling up: the cost is paid in memory by a runtime that will never load
  // it.
  expect(screen.getByTestId('max-lora-rank')).toHaveTextContent('32');
});

it('does not raise the rank ceiling for a retained still-importing adapter', () => {
  render(
    <PersonalizationStepHarness
      adapters={[
        adapter('fp8-adapter', 8),
        adapter('big-importing', 256, { readiness: 'NotReady' }),
      ]}
      selectedAdapters={['big-importing']}
    />,
  );

  enablePersonalization();

  expect(screen.getByTestId('max-lora-rank')).toHaveTextContent('32');
});

it('offers a retained unservable adapter even when its rank is out of range', () => {
  render(
    <PersonalizationStepHarness
      adapters={[adapter('off-scale', 1024, { servable: false })]}
      selectedAdapters={['off-scale']}
    />,
  );

  enablePersonalization();

  // Without a row the selection can never be cleared, and the rank filter
  // would otherwise take the row away before the user can act on it.
  expect(
    screen.getByRole('button', { name: 'Select off-scale' }),
  ).toBeInTheDocument();
  expect(screen.getByTestId('selected-adapters')).toHaveTextContent(
    'off-scale',
  );
});
