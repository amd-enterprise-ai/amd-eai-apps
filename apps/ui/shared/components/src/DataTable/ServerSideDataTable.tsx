// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Selection } from '../Select/Select';
import type { SortDescriptor } from '@heroui/react';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  CollectionRequestParams,
  CustomSortFieldMapperConfig,
  FilterParams,
} from '@amdenterpriseai/types';
import { ActionItem, TableColumns } from '@amdenterpriseai/types';
import { PageFrameSize } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';

import BaseDataTable from './BaseDataTable';

import { isEqual } from 'lodash';

interface Props<T, K extends keyof T, C, S> {
  filters?: FilterParams<S>[];
  data: T[];
  total: number;
  handleDataRequest: (requestParams: CollectionRequestParams<S>) => void;
  columns: TableColumns<C>;
  customSortFieldMapper?: CustomSortFieldMapperConfig<S, K>;
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
}

export const ServerSideDataTable = <T extends object, K extends keyof T, C, S>({
  data,
  filters,
  total,
  handleDataRequest,
  className,
  columns,
  customRenderers,
  customSortFieldMapper,
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
}: Props<T, K, C, S>) => {
  const [sortedBy, setSortedBy] = useState<SortDescriptor>({
    column: defaultSortByField as string,
    direction: defaultSortDirection ? defaultSortDirection : SortDirection.ASC,
  });

  const [currentPage, setCurrentPage] = useState<number>(1);
  const [frameSize, setFrameSize] = useState<PageFrameSize>(
    PageFrameSize.SMALL,
  );
  const prevFiltersRef = useRef<FilterParams<S>[] | undefined>(filters);

  const handleTableChange = useCallback(
    (
      newSort: SortDescriptor,
      newPage: number,
      newFrameSize: number,
      newFilter?: FilterParams<S>[],
    ) => {
      const sortCondition = customSortFieldMapper?.[newSort.column as K]
        ? customSortFieldMapper[newSort.column as K]?.fields.map(
            (field: keyof S) => ({
              field,
              direction: newSort.direction as SortDirection,
            }),
          )
        : [
            {
              field: newSort.column as keyof S,
              direction: newSort.direction as SortDirection,
            },
          ];

      setSortedBy({ ...newSort });
      setCurrentPage(newPage);
      setFrameSize(newFrameSize);

      handleDataRequest({
        page: newPage,
        pageSize: newFrameSize,
        filter: newFilter,
        sort: sortCondition,
      });
    },
    [customSortFieldMapper, handleDataRequest],
  );

  const handleSortChange = useCallback(
    (sortDescriptor: SortDescriptor) => {
      handleTableChange(sortDescriptor, currentPage, frameSize, filters);
    },
    [currentPage, frameSize, handleTableChange, filters],
  );

  const handleFrameSizeChange = useCallback(
    (frameSize: PageFrameSize) => {
      handleTableChange(sortedBy, 1, frameSize, filters);
    },
    [handleTableChange, sortedBy, filters],
  );

  const handlePageChange = useCallback(
    (page: number) => {
      handleTableChange(sortedBy, page, frameSize, filters);
    },
    [handleTableChange, sortedBy, frameSize, filters],
  );

  useEffect(() => {
    if (!isEqual(prevFiltersRef.current, filters)) {
      setCurrentPage(1);
      handleTableChange(sortedBy, 1, frameSize, filters);
      prevFiltersRef.current = filters;
    }
  }, [filters, handleTableChange, sortedBy, frameSize]);

  return (
    <BaseDataTable
      page={currentPage}
      pageSize={frameSize}
      data={data}
      total={total}
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
    />
  );
};

export default ServerSideDataTable;
