// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { LoraAdapterSelectionTable } from '@/components/features/loras/LoraAdapterSelectionTable';
import type { LoraAdapter } from '@/types/artifacts';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (
      key: string,
      values?: { selected?: number; count?: number },
    ): string => {
      if (key === 'selection.count') {
        return `${values?.selected} of ${values?.count} LoRAs selected`;
      }
      if (key === 'selection.limitReached') {
        return `You can select up to ${values?.count} LoRAs.`;
      }
      return key;
    },
  }),
}));

vi.mock('@amdenterpriseai/components', () => ({
  // Wired to onFilterChange the same way the real search filter drives it, so
  // tests can exercise LoraAdapterSelectionTable's own search behavior without
  // pulling in the real ActionsToolbar/filter-panel implementation.
  ActionsToolbar: ({
    onFilterChange,
  }: {
    onFilterChange: (filters: { search?: string[] }) => void;
  }) => (
    <input
      aria-label="search"
      onChange={(event) => onFilterChange({ search: [event.target.value] })}
    />
  ),
  // Renders each row through the real customRenderers so column-specific
  // rendering (e.g. the rank fallback) is actually exercised, not just the
  // column list passed down.
  ClientSideDataTable: ({
    data,
    columns,
    customRenderers,
    onSelectionChange,
  }: {
    data: LoraAdapter[];
    columns: Array<{ key: string }>;
    customRenderers: Record<string, (adapter: LoraAdapter) => React.ReactNode>;
    onSelectionChange: (selection: Set<string> | 'all') => void;
  }) => (
    <div>
      <span data-testid="column-order">
        {columns.map((column) => column.key).join(',')}
      </span>
      <table>
        <tbody>
          {data.map((adapter) => (
            <tr key={adapter.name} data-testid={`row-${adapter.name}`}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  data-testid={`cell-${adapter.name}-${column.key}`}
                >
                  {customRenderers[column.key]?.(adapter)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={() => onSelectionChange(new Set())}>Clear</button>
      <button onClick={() => onSelectionChange('all')}>Select all</button>
      <button
        onClick={() =>
          onSelectionChange(new Set(data.map((adapter) => adapter.name)))
        }
      >
        Select rows
      </button>
    </div>
  ),
  DateDisplay: () => null,
  NoDataDisplay: () => <span>No data</span>,
}));

const adapters: LoraAdapter[] = ['one', 'two', 'three'].map((name) => ({
  id: name,
  name,
  displayName: name,
  compatibleWith: [],
  readiness: 'Ready',
}));

it('tells a row the deployment cannot load apart from one still importing', () => {
  render(
    <LoraAdapterSelectionTable
      adapters={[
        { ...adapters[0]!, name: 'servable' },
        { ...adapters[0]!, name: 'wrong-weights', servable: false },
        { ...adapters[0]!, name: 'importing', readiness: 'NotReady' },
      ]}
      isLoading={false}
      selectedNames={[]}
      onSelectionChange={vi.fn()}
    />,
  );

  // One resolves by waiting and the other only by changing the selection, so a
  // single shared message would send half the users nowhere.
  expect(screen.getByTestId('lora-unservable-wrong-weights')).toHaveTextContent(
    'selection.unservable',
  );
  expect(screen.getByTestId('lora-not-ready-importing')).toHaveTextContent(
    'selection.notReady',
  );
  expect(
    screen.queryByTestId('lora-not-ready-wrong-weights'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByTestId('lora-unservable-servable'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByTestId('lora-not-ready-servable'),
  ).not.toBeInTheDocument();
});

it('says nothing about servability on a row that was never judged', () => {
  render(
    <LoraAdapterSelectionTable
      adapters={[{ ...adapters[0]!, name: 'undetermined', servable: null }]}
      isLoading={false}
      selectedNames={[]}
      onSelectionChange={vi.fn()}
    />,
  );

  // Null is "not asked", and warning on it would accuse a perfectly loadable
  // adapter of a lineage mismatch nobody checked for.
  expect(
    screen.queryByTestId('lora-unservable-undetermined'),
  ).not.toBeInTheDocument();
});

it('orders columns with rank directly after the adapter name', () => {
  render(
    <LoraAdapterSelectionTable
      adapters={adapters}
      isLoading={false}
      selectedNames={[]}
      onSelectionChange={vi.fn()}
    />,
  );

  expect(screen.getByTestId('column-order')).toHaveTextContent(
    'displayName,rank,createdBy,createdAt',
  );
});

it('renders the adapter rank, falling back to a no-data indicator when rank is unknown', () => {
  const adaptersWithRanks: LoraAdapter[] = [
    {
      id: 'ranked',
      name: 'ranked',
      displayName: 'Ranked Adapter',
      compatibleWith: [],
      readiness: 'Ready',
      rank: 42,
    },
    {
      id: 'unranked',
      name: 'unranked',
      displayName: 'Unranked Adapter',
      compatibleWith: [],
      readiness: 'Ready',
    },
  ];
  render(
    <LoraAdapterSelectionTable
      adapters={adaptersWithRanks}
      isLoading={false}
      selectedNames={[]}
      onSelectionChange={vi.fn()}
    />,
  );

  expect(screen.getByTestId('cell-ranked-rank')).toHaveTextContent('42');
  expect(screen.getByTestId('cell-unranked-rank')).toHaveTextContent('No data');
});

it('filters adapters by name, display name, or description as the search query changes', () => {
  const adaptersToFilter: LoraAdapter[] = [
    {
      id: 'one',
      name: 'one',
      displayName: 'Alpha',
      description: 'first adapter',
      compatibleWith: [],
      readiness: 'Ready',
    },
    {
      id: 'two',
      name: 'two',
      displayName: 'Beta',
      description: 'second adapter',
      compatibleWith: [],
      readiness: 'Ready',
    },
  ];
  render(
    <LoraAdapterSelectionTable
      adapters={adaptersToFilter}
      isLoading={false}
      selectedNames={[]}
      onSelectionChange={vi.fn()}
    />,
  );

  expect(screen.getByTestId('row-one')).toBeInTheDocument();
  expect(screen.getByTestId('row-two')).toBeInTheDocument();

  fireEvent.change(screen.getByRole('textbox', { name: 'search' }), {
    target: { value: 'beta' },
  });

  expect(screen.queryByTestId('row-one')).not.toBeInTheDocument();
  expect(screen.getByTestId('row-two')).toBeInTheDocument();

  fireEvent.change(screen.getByRole('textbox', { name: 'search' }), {
    target: { value: '' },
  });

  expect(screen.getByTestId('row-one')).toBeInTheDocument();
  expect(screen.getByTestId('row-two')).toBeInTheDocument();
});

it('allows clearing every selected LoRA', () => {
  const onSelectionChange = vi.fn();
  render(
    <LoraAdapterSelectionTable
      adapters={adapters}
      isLoading={false}
      selectedNames={['one']}
      onSelectionChange={onSelectionChange}
    />,
  );

  fireEvent.click(screen.getByText('Clear'));

  expect(onSelectionChange).toHaveBeenCalledWith([]);
});

it('caps selection at the API limit', () => {
  const onSelectionChange = vi.fn();
  render(
    <LoraAdapterSelectionTable
      adapters={adapters}
      isLoading={false}
      selectedNames={[]}
      onSelectionChange={onSelectionChange}
      maxSelectionCount={2}
    />,
  );

  fireEvent.click(screen.getByText('Select all'));

  expect(onSelectionChange).toHaveBeenCalledWith(['one', 'two']);
});

it('signals the limit for a selection that already sits at it', () => {
  render(
    <LoraAdapterSelectionTable
      adapters={adapters}
      isLoading={false}
      selectedNames={['one', 'two']}
      onSelectionChange={vi.fn()}
      maxSelectionCount={2}
    />,
  );

  expect(screen.getByText('You can select up to 2 LoRAs.')).toBeInTheDocument();
});

it('reports the count while the selection is below the limit', () => {
  render(
    <LoraAdapterSelectionTable
      adapters={adapters}
      isLoading={false}
      selectedNames={['one']}
      onSelectionChange={vi.fn()}
      maxSelectionCount={2}
    />,
  );

  expect(screen.getByText('1 of 2 LoRAs selected')).toBeInTheDocument();
});

it('caps individual row selections at the API limit', () => {
  const onSelectionChange = vi.fn();
  render(
    <LoraAdapterSelectionTable
      adapters={adapters}
      isLoading={false}
      selectedNames={[]}
      onSelectionChange={onSelectionChange}
      maxSelectionCount={2}
    />,
  );

  fireEvent.click(screen.getByText('Select rows'));

  expect(onSelectionChange).toHaveBeenCalledWith(['one', 'two']);
});
