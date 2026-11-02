// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ActionItem, TableColumn } from '@amdenterpriseai/types';

import { ThreeDotActionsDropdown } from './ThreeDotActionsDropdown';

export const ACTIONS_COLUMN_KEY = 'actions';

export const ACTIONS_COLUMN = {
  key: ACTIONS_COLUMN_KEY,
  width: 1,
  className: 'text-right vertical-align-middle w-4',
  sortable: false,
} as TableColumn<typeof ACTIONS_COLUMN_KEY>;

/**
 * Creates a renderer for an actions column in a data table that resolves actions from function or direct array
 * @param rowActions The actions to display for each row, or a function to generate them
 * @param item The data item for the current row
 * @param isDisabled Whether the actions should be disabled
 */
export const getActionsColumnRenderer = <T,>(
  rowActions: ActionItem<T>[] | ((item: T) => ActionItem<T>[]),
  item: T,
  isDisabled?: boolean,
) => {
  const actions =
    typeof rowActions === 'function' ? rowActions(item) : rowActions;

  return (
    <ThreeDotActionsDropdown
      actions={actions}
      item={item}
      isDisabled={isDisabled}
    />
  );
};
