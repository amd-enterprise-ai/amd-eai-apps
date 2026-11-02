// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionsToolbar,
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
  type Selection,
} from '@amdenterpriseai/components';
import {
  FilterComponentType,
  type FilterValueMap,
  SortDirection,
  type TableColumns,
} from '@amdenterpriseai/types';
import { useMemo, useState } from 'react';
import { useTranslation } from 'next-i18next';

import { MAX_LORA_ADAPTERS, type LoraAdapter } from '@/types/artifacts';

const AdapterTableField = {
  DISPLAY_NAME: 'displayName',
  RANK: 'rank',
  CREATED_BY: 'createdBy',
  CREATED_AT: 'createdAt',
} as const;

type AdapterTableField =
  (typeof AdapterTableField)[keyof typeof AdapterTableField];

const columns: TableColumns<AdapterTableField> = [
  { key: AdapterTableField.DISPLAY_NAME, sortable: true },
  { key: AdapterTableField.RANK, sortable: true },
  { key: AdapterTableField.CREATED_BY, sortable: true },
  { key: AdapterTableField.CREATED_AT, sortable: true },
];

type LoraAdapterSelectionTableProps = {
  adapters: LoraAdapter[];
  isLoading: boolean;
  selectedNames: string[];
  onSelectionChange: (names: string[]) => void;
  maxSelectionCount?: number;
};

export const LoraAdapterSelectionTable = ({
  adapters,
  isLoading,
  selectedNames,
  onSelectionChange,
  maxSelectionCount = MAX_LORA_ADAPTERS,
}: LoraAdapterSelectionTableProps) => {
  const { t } = useTranslation('loras');
  const [searchQuery, setSearchQuery] = useState('');
  // Derived from the selection rather than tracked, so a table mounted at the
  // cap (editing a deployment already serving the maximum) warns immediately
  // instead of waiting for the next toggle.
  const limitReached = selectedNames.length >= maxSelectionCount;
  const filteredAdapters = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query) return adapters;
    return adapters.filter((adapter) =>
      [adapter.displayName, adapter.name, adapter.description].some((value) =>
        value?.toLocaleLowerCase().includes(query),
      ),
    );
  }, [adapters, searchQuery]);
  const filterConfig = useMemo(
    () => ({
      search: {
        name: 'search',
        label: t('list.filters.search.placeholder'),
        placeholder: t('list.filters.search.placeholder'),
        type: FilterComponentType.TEXT,
        variant: 'secondary' as const,
      },
    }),
    [t],
  );
  const customRenderers = {
    [AdapterTableField.DISPLAY_NAME]: (adapter: LoraAdapter) => (
      <div className="flex flex-col gap-1">
        <span>{adapter.displayName}</span>
        {adapter.description ? (
          <span className="text-xs text-muted">{adapter.description}</span>
        ) : null}
        {adapter.servable === false ? (
          <span
            className="text-xs text-warning"
            data-testid={`lora-unservable-${adapter.name}`}
          >
            {t('selection.unservable')}
          </span>
        ) : adapter.readiness !== 'Ready' ? (
          <span
            className="text-xs text-warning"
            data-testid={`lora-not-ready-${adapter.name}`}
          >
            {/* Unknown means the weights could not be read at all, so telling
                the user to wait for an import that may not be running would
                send them to the wrong place. */}
            {t(
              adapter.readiness === 'Unknown'
                ? 'selection.readinessUnknown'
                : 'selection.notReady',
            )}
          </span>
        ) : null}
      </div>
    ),
    [AdapterTableField.RANK]: (adapter: LoraAdapter) =>
      adapter.rank ?? <NoDataDisplay />,
    [AdapterTableField.CREATED_BY]: (adapter: LoraAdapter) =>
      adapter.createdBy || <NoDataDisplay />,
    [AdapterTableField.CREATED_AT]: (adapter: LoraAdapter) =>
      adapter.createdAt ? (
        <DateDisplay date={adapter.createdAt} />
      ) : (
        <NoDataDisplay />
      ),
  };

  const handleSelectionChange = (selection: Selection) => {
    const names =
      selection === 'all'
        ? Array.from(
            new Set([
              ...selectedNames,
              ...filteredAdapters.map((adapter) => adapter.name),
            ]),
          )
        : Array.from(selection, String);
    onSelectionChange(names.slice(0, maxSelectionCount));
  };

  return (
    // The rendered rows are only meaningful once the adapters and the
    // eligibility inputs have landed; until then an empty table is a render
    // stage rather than a filtering result, which end-to-end callers otherwise
    // cannot tell apart.
    <div
      className="flex flex-col"
      data-testid="lora-adapters-selector"
      data-loading={String(isLoading)}
    >
      <ActionsToolbar
        canClear={false}
        filterConfig={filterConfig}
        onFilterChange={(filters: FilterValueMap) =>
          setSearchQuery(filters.search?.[0] ?? '')
        }
      />
      <ClientSideDataTable
        data={filteredAdapters}
        columns={columns}
        customRenderers={customRenderers}
        defaultSortByField={AdapterTableField.CREATED_AT}
        defaultSortDirection={SortDirection.DESC}
        idKey="name"
        isLoading={isLoading}
        isSelectable
        selectedKeys={new Set(selectedNames)}
        onSelectionChange={handleSelectionChange}
        translation={t}
      />
      <p
        className={`mt-2 text-xs ${limitReached ? 'text-danger' : 'text-muted'}`}
        data-testid="lora-selection-limit"
      >
        {limitReached
          ? t('selection.limitReached', { count: maxSelectionCount })
          : t('selection.count', {
              selected: selectedNames.length,
              count: maxSelectionCount,
            })}
      </p>
    </div>
  );
};
