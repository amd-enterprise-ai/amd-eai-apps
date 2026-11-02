// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Skeleton } from '@amdenterpriseai/components';
import type { SortDescriptor } from '@heroui/react';
import {
  Checkbox as HeroUICheckbox,
  Table as HeroUITable,
  cn,
} from '@heroui/react';
import { useCallback, useMemo, useState } from 'react';
import type { Key, ReactNode } from 'react';

import type { Selection } from '../Select/Select';

import {
  ACTIONS_COLUMN,
  ACTIONS_COLUMN_KEY,
  getActionsColumnRenderer,
} from '../Dropdown/table-actions';

import {
  ActionItem,
  TableColumns,
  PageFrameSize,
  SortDirection,
} from '@amdenterpriseai/types';

import TablePagination from './TablePagination';
import TableEmptyState from './TableEmptyState';

export type TableVariant = 'default' | 'transparent';

interface Props<T extends object, C> {
  data: T[];
  total: number;
  pageSize?: PageFrameSize;
  page?: number;
  columns: TableColumns<C>;
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
  customRenderers?: Record<string, (item: T) => ReactNode | string>;
  onRowPressed?: (id: string) => void;
  rowActions?: ActionItem<T>[] | ((item: T) => ActionItem<T>[]);
  isRowDisabled?: (item: T) => boolean;
  onSortChange: (sortDescriptor: SortDescriptor) => void;
  onFrameSizeChange: (frameSize: PageFrameSize) => void;
  onPageChange: (page: number) => void;
  tableVariant?: TableVariant;
}

const BaseDataTable = <T extends object, C>({
  data,
  total,
  pageSize,
  page,
  className,
  columns: columnsProp,
  customRenderers,
  onSelectionChange,
  onSortChange,
  onFrameSizeChange,
  onPageChange,
  selectedKeys,
  idKey,
  defaultSortByField,
  defaultSortDirection,
  isFetching: _isFetching,
  isLoading,
  isSelectable,
  translation,
  translationKeyPrefix,
  onRowPressed,
  rowActions,
  isRowDisabled,
  tableVariant = 'default',
}: Props<T, C>) => {
  const t = translation;
  const heroVariant = tableVariant === 'transparent' ? 'secondary' : 'primary';

  const [sortedBy, setSortedBy] = useState<SortDescriptor>({
    column: defaultSortByField as string,
    direction: defaultSortDirection ? defaultSortDirection : SortDirection.ASC,
  });

  const [currentPage, setCurrentPage] = useState<number>(1);
  const [frameSize, setFrameSize] = useState<PageFrameSize>(
    PageFrameSize.SMALL,
  );

  const handleSortChange = useCallback(
    (sortDescriptor: SortDescriptor) => {
      setSortedBy({ ...sortDescriptor });
      onSortChange(sortDescriptor);
    },
    [onSortChange],
  );

  const handleFrameSizeChange = useCallback(
    (frameSize: PageFrameSize) => {
      setFrameSize(frameSize);
      setCurrentPage(1);
      onFrameSizeChange(frameSize);
    },
    [onFrameSizeChange],
  );

  const handlePageChange = useCallback(
    (page: number) => {
      setCurrentPage(page);
      onPageChange(page);
    },
    [onPageChange, setCurrentPage],
  );

  // Compute disabledKeys from isRowDisabled if provided
  const computedDisabledKeys = useMemo(() => {
    if (isRowDisabled) {
      const disabled = data
        .filter((item) => isRowDisabled(item))
        .map((item) => item[idKey] as string | number);
      return disabled.length > 0 ? new Set(disabled) : undefined;
    }
    return undefined;
  }, [isRowDisabled, data, idKey]);

  const columns: TableColumns<typeof ACTIONS_COLUMN_KEY | C> = [...columnsProp];

  if (rowActions) {
    columns.push(ACTIONS_COLUMN);
  }

  // v3 collections (React Aria Components) require an explicit `id`; the v2 code
  // identified columns via `key`, so derive `id` from it. Exactly one column
  // must be the row header for accessibility.
  const columnsWithId = columns.map((column, index) => ({
    ...column,
    id: column.key as string,
    isRowHeader: index === 0,
  }));

  const renderHeaderContent = (
    column: (typeof columnsWithId)[number],
  ): ReactNode =>
    column.key ? (
      <div className="inline-flex flex-col text-sm gap-0 h-full">
        {t(
          `list.${translationKeyPrefix ? `${translationKeyPrefix}.` : ''}headers.${column.key as string}.title`,
        )}

        {!!column.hasDescription && (
          <div className="text-muted font-light text-xs">
            {t(
              `list.${translationKeyPrefix ? `${translationKeyPrefix}.` : ''}headers.${column.key as string}.description`,
            )}
          </div>
        )}
      </div>
    ) : null;

  const cellRenderer = (
    item: T,
    columnKey: Key,
    rowDisabled: boolean,
  ): ReactNode | string => {
    if (customRenderers?.[columnKey as string]) {
      return customRenderers[columnKey as string](item);
    } else if ((columnKey as string) === ACTIONS_COLUMN_KEY && rowActions) {
      return getActionsColumnRenderer(rowActions, item, rowDisabled);
    }
    return (item as Record<string, unknown>)[columnKey as string] as ReactNode;
  };

  const placeholderRowCount = pageSize ?? frameSize;
  const items = isLoading
    ? (Array.from(
        { length: placeholderRowCount },
        (_, row) =>
          ({
            [idKey as string]: `row-${row}`,
          }) as T,
      ) as T[])
    : data;

  const emptyStateText = t(
    `list.${translationKeyPrefix ? `${translationKeyPrefix}.` : ''}empty.description`,
  );

  const renderSelectionCheckbox = (
    ariaLabel: string,
    variant?: 'secondary',
  ) => (
    <HeroUICheckbox aria-label={ariaLabel} slot="selection" variant={variant}>
      <HeroUICheckbox.Content>
        <HeroUICheckbox.Control>
          <HeroUICheckbox.Indicator />
        </HeroUICheckbox.Control>
      </HeroUICheckbox.Content>
    </HeroUICheckbox>
  );

  const paginationFooter =
    total > PageFrameSize.SMALL && !isLoading ? (
      <TablePagination
        onFrameSizeChange={handleFrameSizeChange}
        onPageChange={handlePageChange}
        currentPage={page ?? currentPage}
        frameSize={pageSize ?? frameSize}
        translationKeyPrefix={translationKeyPrefix}
        totalItems={total}
        translation={translation}
      />
    ) : null;

  return (
    <div className={className}>
      <HeroUITable.Root variant={heroVariant}>
        <HeroUITable.ScrollContainer>
          <HeroUITable.Content
            aria-label={
              t(
                `list.${translationKeyPrefix ? `${translationKeyPrefix}.` : ''}table.ariaLabel`,
              ) || ''
            }
            disabledKeys={computedDisabledKeys}
            onRowAction={
              onRowPressed && ((id: Key) => onRowPressed(id as string))
            }
            onSelectionChange={onSelectionChange}
            onSortChange={handleSortChange}
            selectedKeys={selectedKeys}
            selectionMode={isSelectable ? 'multiple' : 'none'}
            sortDescriptor={sortedBy}
          >
            <HeroUITable.Header>
              {isSelectable && (
                <HeroUITable.Column className="pr-0" id="selection" width={40}>
                  {renderSelectionCheckbox('Select all')}
                </HeroUITable.Column>
              )}
              <HeroUITable.Collection items={columnsWithId}>
                {(column: (typeof columnsWithId)[number]) => (
                  <HeroUITable.Column
                    allowsSorting={column.sortable}
                    className={column.className}
                    id={column.id}
                    isRowHeader={column.isRowHeader}
                    maxWidth={column.maxWidth}
                    minWidth={column.minWidth}
                    width={column.width}
                  >
                    {column.sortable
                      ? ({
                          sortDirection,
                        }: {
                          sortDirection?: 'ascending' | 'descending';
                        }) => (
                          <HeroUITable.SortableColumnHeader
                            sortDirection={sortDirection}
                          >
                            {renderHeaderContent(column)}
                          </HeroUITable.SortableColumnHeader>
                        )
                      : renderHeaderContent(column)}
                  </HeroUITable.Column>
                )}
              </HeroUITable.Collection>
            </HeroUITable.Header>
            <HeroUITable.Body
              items={items}
              dependencies={[computedDisabledKeys]}
              renderEmptyState={() => <TableEmptyState text={emptyStateText} />}
            >
              {(item: T) => {
                const rowDisabled =
                  computedDisabledKeys?.has(item[idKey] as string | number) ??
                  false;
                return (
                  <HeroUITable.Row
                    id={`${item[idKey]}`}
                    className={cn({
                      'cursor-pointer': onRowPressed && !isLoading,
                    })}
                  >
                    {isSelectable && (
                      <HeroUITable.Cell className="pr-0">
                        {renderSelectionCheckbox(
                          `Select row ${item[idKey]}`,
                          'secondary',
                        )}
                      </HeroUITable.Cell>
                    )}
                    <HeroUITable.Collection items={columnsWithId}>
                      {(column: (typeof columnsWithId)[number]) => (
                        <HeroUITable.Cell className={column.className}>
                          {isLoading ? (
                            <Skeleton className="h-4 w-3/5 rounded-lg" />
                          ) : (
                            cellRenderer(item, column.id, rowDisabled)
                          )}
                        </HeroUITable.Cell>
                      )}
                    </HeroUITable.Collection>
                  </HeroUITable.Row>
                );
              }}
            </HeroUITable.Body>
          </HeroUITable.Content>
        </HeroUITable.ScrollContainer>
        {paginationFooter && (
          <HeroUITable.Footer>{paginationFooter}</HeroUITable.Footer>
        )}
      </HeroUITable.Root>
    </div>
  );
};

export default BaseDataTable;
