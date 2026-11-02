// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ReactNode } from 'react';
import { FilterFieldMapping, FilterValueMap } from '@amdenterpriseai/types';
import { DataFilter } from '../Filters';
import { Toolbar } from '@amdenterpriseai/layouts';
import RefreshButton from '../Filters/RefreshButton';

interface Props {
  filterConfig: FilterFieldMapping;
  onFilterChange: (filters: FilterValueMap) => void;
  canClear?: boolean;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  updatedTimestamp?: number;
  extraContent?: ReactNode;
  endContent?: ReactNode;
}

export const ActionsToolbar = ({
  filterConfig,
  canClear = true,
  isRefreshing,
  onFilterChange,
  onRefresh,
  extraContent,
  endContent,
  updatedTimestamp,
}: Props) => {
  return (
    <Toolbar>
      <div
        className={`flex w-full lg:w-[fit-content] gap-3 items-center flex-wrap order-2 lg:order-1 ${endContent == undefined ? 'flex-1' : ''}`}
      >
        {onRefresh ? (
          <RefreshButton
            compact
            isLoading={isRefreshing}
            onPress={onRefresh}
            lastFetchedTimestamp={updatedTimestamp}
          />
        ) : null}
        <DataFilter
          filters={filterConfig}
          onFilterChange={onFilterChange}
          canClear={canClear}
        />
        {extraContent}
      </div>
      {endContent != undefined ? (
        <>
          <div className="flex items-center gap-3 sm:justify-start justify-end ml-auto lg:ml-0 order-1 lg:order-2">
            {endContent}
          </div>
          <div className="w-full border-b border-default dark:border-default lg:hidden order-1 lg:order-2"></div>
        </>
      ) : null}
    </Toolbar>
  );
};

export default ActionsToolbar;
