// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Selection } from '../Select/Select';
import type { SortDescriptor } from '@heroui/react';
import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { defaultComparator } from '@amdenterpriseai/utils/app';

import { ActionItem, TableColumns } from '@amdenterpriseai/types';
import { CustomComparatorConfig } from '@amdenterpriseai/types';
import { PageFrameSize } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';

import BaseDataTable, { type TableVariant } from './BaseDataTable';

interface Props<T, K extends keyof T, C> {
  data: T[];
  columns: TableColumns<C>;
  customComparator?: CustomComparatorConfig<T, K>;
  className?: string;
  defaultSortByField: C;
  defaultSortDirection?: SortDirection;
  translation: (key: string, options?: Record<string, unknown>) => string;
  translationKeyPrefix?: string;
  idKey: keyof T;
  isLoading?: boolean;
  isFetching?: boolean;
  selectedKeys?: Selection;
  isSelectable?: boolean;
  onSelectionChange?: (keys: Selection) => void;
  customRenderers?: Record<string, (item: T) => React.ReactNode | string>;
  onRowPressed?: (id: string) => void;
  rowActions?: ActionItem<T>[] | ((item: T) => ActionItem<T>[]);
  isRowDisabled?: (item: T) => boolean;
  tableVariant?: TableVariant;
}

/**
 * Client-side data table for datasets that are already loaded in memory.
 * Handles sorting, pagination, optional row selection, row actions, and
 * row-level navigation through `onRowPressed`.
 *
 * ## When to use ClientSideDataTable
 *
 * - The full dataset is already available in the UI and can be sorted/paginated locally.
 * - Use `ServerSideDataTable` when data is large, must be fetched page-by-page,
 *   or filtering/sorting needs backend support.
 *
 * ## Row navigation
 *
 * Use `onRowPressed` for primary navigation; clicking any part of the row navigates.
 * Do not use inline links in cells. For secondary navigation to a different
 * destination (e.g. project dashboard from a workloads table), add a row action
 * in the (...) overflow menu (e.g. "View project") that performs the navigation.
 *
 * ```tsx
 * // Good — row click is the primary navigation
 * <ClientSideDataTable onRowPressed={(id) => router.push(`/items/${id}`)} />
 *
 * // Good — secondary navigation via overflow menu
 * rowActions={(item) => [
 *   ...(item.projectId ? [{
 *     key: 'view-project',
 *     label: 'View project',
 *     onPress: () => router.push(`/projects/${item.projectId}`),
 *   }] : []),
 *   { key: 'delete', label: 'Delete', color: 'danger', onPress: () => onDelete(item) },
 * ]}
 * ```
 *
 * ## Row actions — overflow menu items
 *
 * Actions appear in the "..." overflow menu at the end of each row. They accept a
 * static array or a function `(item) => ActionItem[]` for conditional actions.
 *
 * Memoize `rowActions` so BaseDataTable does not re-render on every parent render:
 *
 * ```tsx
 * // Good — stable reference
 * const rowActions = useMemo(() => [
 *   { key: 'delete', label: 'Delete', color: 'danger', onPress: (item) => onDelete(item) },
 * ], [onDelete]);
 *
 * // Bad — new array on every render
 * rowActions={[{ key: 'delete', label: 'Delete', onPress: ... }]}
 * ```
 *
 * Avoid duplicating `onRowPressed` as a row action (e.g. an "Open" action that navigates
 * to the same page as clicking the row).
 *
 * ## Custom renderers — display formatting
 *
 * Map of column key to render function. Renderers control **what the user sees** in
 * each cell. They are purely a presentation concern and have no effect on sorting.
 *
 * Only provide a renderer when the column needs formatting, badges, icons, or composite
 * content. If the renderer just returns the raw field value, omit it — the table already
 * does that by default.
 *
 * ```tsx
 * // Good — formatting, components, unit conversion
 * [Field.STATUS]: (row) => <StatusBadge status={row.status} />,
 * [Field.CREATED_AT]: (row) => <DateDisplay date={row.createdAt} />,
 * [Field.MEMORY]: (row) => displayBytesInGigabytes(row.memoryBytes),
 * [Field.GPU_TYPE]: (row) => row.gpuInfo ? row.gpuInfo.name : '-',
 *
 * // Bad — redundant, the table already renders raw values
 * [Field.NAME]: (row) => row.name,
 * [Field.NAME]: (row) => <span>{row.name}</span>,
 * [Field.CREATED_BY]: (row) => <span>{row.createdBy}</span>,
 * ```
 *
 * Memoize `customRenderers` with `useMemo` when they depend on translation `t` or
 * other reactive values; define them outside the component when they are static.
 *
 * ## Custom comparators — sorting
 *
 * Map of column key to comparator function. Comparators control **how rows are
 * ordered** when the user clicks a column header. They are purely a sorting concern
 * and have no effect on display.
 *
 * The default comparator sorts by raw field value using `localeCompare` (strings) or
 * `>/<` (numbers). That works for simple fields like `name` or `email`, but breaks
 * down in several common scenarios. Provide a custom comparator when:
 *
 * **Derived/computed values** — the displayed value is calculated from multiple fields
 * or transformed from the raw value:
 *
 * ```tsx
 * // CPU cores displayed as cpuMilliCores / 1000
 * [Field.CPU_CORES]: (a, b) => a.cpuMilliCores - b.cpuMilliCores,
 *
 * // GPU memory computed from count * per-device bytes
 * [Field.GPU_MEMORY]: (a, b) =>
 *   a.gpuCount * (a.gpuInfo?.memoryBytesPerDevice ?? 0)
 *   - b.gpuCount * (b.gpuInfo?.memoryBytesPerDevice ?? 0),
 * ```
 *
 * **Business/lifecycle ordering** — the raw value is a string enum but should sort
 * by domain-specific rank, not alphabetically:
 *
 * ```tsx
 * const statusRank = { Pending: 0, Running: 1, Complete: 2, Failed: 3 };
 * [Field.STATUS]: (a, b) => statusRank[a.status] - statusRank[b.status],
 * ```
 *
 * **Dates** — formatted date strings (e.g. `Jan 2, 2026`) sort alphabetically by
 * month name, not chronologically. Compare on the raw ISO string or timestamp:
 *
 * ```tsx
 * [Field.CREATED_AT]: (a, b) =>
 *   new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
 * ```
 *
 * **Nested fields** — the sortable value lives inside a nested object:
 *
 * ```tsx
 * [Field.NAME]: (a, b) => a.storage.name.localeCompare(b.storage.name),
 * ```
 *
 * **Composite name fields** — the displayed name is assembled from multiple fields:
 *
 * ```tsx
 * [Field.NAME]: (a, b) =>
 *   `${a.firstName} ${a.lastName}`.localeCompare(`${b.firstName} ${b.lastName}`),
 * ```
 *
 * ## Default sort field and columns
 *
 * Use the table field enum for `defaultSortByField` instead of a string literal so
 * the compiler catches renames:
 *
 * ```tsx
 * // Good
 * defaultSortByField={ProjectTableField.NAME}
 *
 * // Bad — no type safety
 * defaultSortByField={'name'}
 * ```
 *
 * ## Anti-patterns to avoid
 *
 * - **Inline rowActions arrays** — passing a literal array creates a new reference on
 *   every render. Hoist to a constant or memoize with `useMemo`.
 *
 * - **Redundant custom renderers** — a renderer that just returns the raw field value
 *   (e.g. `(item) => item.name`) adds code with no benefit. Omit it.
 *
 * - **Missing comparators for sortable derived columns** — if a sortable column has a
 *   raw value that differs from what the user sees (computed values, translated labels,
 *   formatted dates), add a custom comparator. Renderers and comparators are independent;
 *   a renderer does not change sort order.
 *
 * - **Redundant custom comparators** — if the raw field value already sorts correctly
 *   (e.g. a plain string `name`, a numeric `gpuCount`), omit the comparator and let
 *   the default handle it.
 *
 * - **Inline links in cells** — do not use `<Link>` or clickable links inside
 *   cell renderers. For secondary navigation (e.g. to a related resource), add a
 *   row action in the overflow menu instead.
 *
 * - **String literal defaultSortByField** — use the column field enum so refactors
 *   and renames are caught by the compiler.
 *
 * - **Unstable idKey** — array indices or transient values break selection, disabled
 *   rows, and action targeting. Use a stable unique identifier from the data model.
 *
 * - **Wrong enum in customComparator** — make sure comparator keys use the same
 *   table field enum as `columns`. Mixing enums from a different table can compile
 *   but silently breaks sorting.
 */
export const ClientSideDataTable = <T extends object, K extends keyof T, C>({
  data,
  className,
  columns,
  customRenderers,
  customComparator,
  onSelectionChange,
  selectedKeys,
  idKey,
  defaultSortByField,
  defaultSortDirection,
  isFetching,
  isLoading,
  isSelectable,
  translation,
  translationKeyPrefix,
  onRowPressed,
  rowActions,
  isRowDisabled,
  tableVariant,
}: Props<T, K, C>) => {
  const [sortedBy, setSortedBy] = useState<SortDescriptor>({
    column: defaultSortByField as string,
    direction: defaultSortDirection ? defaultSortDirection : SortDirection.ASC,
  });

  const [currentPage, setCurrentPage] = useState<number>(1);
  const [frameSize, setFrameSize] = useState<PageFrameSize>(
    PageFrameSize.SMALL,
  );

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(data.length / frameSize));
    setCurrentPage((prevPage) => Math.min(prevPage, totalPages));
  }, [data.length, frameSize]);

  const sortedData = useMemo(() => {
    const column = sortedBy.column as C;
    const sorted = [...data].sort(
      customComparator?.[column] || defaultComparator(column as string),
    );
    if (sortedBy.direction === SortDirection.DESC) {
      sorted.reverse();
    }
    return sorted;
  }, [data, customComparator, sortedBy.direction, sortedBy.column]);

  const dataFrame = useMemo(() => {
    const currentIdx = (currentPage - 1) * frameSize;
    return sortedData.slice(currentIdx, currentIdx + frameSize);
  }, [currentPage, sortedData, frameSize]);

  const handleSortChange = useCallback((sortDescriptor: SortDescriptor) => {
    setSortedBy({ ...sortDescriptor });
  }, []);

  const handleFrameSizeChange = (frameSize: PageFrameSize) => {
    setFrameSize(frameSize);
    setCurrentPage(1);
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  return (
    <BaseDataTable
      data={dataFrame}
      total={data.length}
      page={currentPage}
      pageSize={frameSize}
      className={className}
      columns={columns}
      customRenderers={customRenderers}
      onSelectionChange={onSelectionChange}
      selectedKeys={selectedKeys}
      idKey={idKey}
      defaultSortByField={defaultSortByField}
      defaultSortDirection={defaultSortDirection}
      isFetching={isFetching}
      isLoading={isLoading}
      isSelectable={isSelectable}
      translation={translation}
      translationKeyPrefix={translationKeyPrefix}
      onRowPressed={onRowPressed}
      rowActions={rowActions}
      isRowDisabled={isRowDisabled}
      onSortChange={handleSortChange}
      onFrameSizeChange={handleFrameSizeChange}
      onPageChange={handlePageChange}
      tableVariant={tableVariant}
    />
  );
};

export default ClientSideDataTable;
