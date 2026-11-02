// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Button } from '../Buttons/Button';
import { ActionsDropdown } from './ActionsDropdown';
import { DropdownActionItem } from './types';
import { IconDotsVertical } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';

import { ActionItem } from '@amdenterpriseai/types';

interface ThreeDotActionsDropdownProps<T> {
  actions: ActionItem<T>[];
  item: T;
  isDisabled?: boolean;
}

// `ActionItem<T>` is `DropdownActionItem` with the row `item` threaded through
// its callbacks. Bind `item` once and let `ActionsDropdown` own the menu,
// disabled-state, and hint-tooltip rendering.
const toDropdownActions = <T,>(
  actions: ActionItem<T>[],
  item: T,
): DropdownActionItem[] =>
  actions.map((action) => ({
    key: action.key,
    className: action.className,
    label: action.label,
    color: action.color,
    startContent: action.startContent,
    description: action.description,
    showDivider: action.showDivider,
    onPress: () => action.onPress(item),
    isDisabled:
      typeof action.isDisabled === 'function'
        ? action.isDisabled(item)
        : action.isDisabled,
    hint: action.hint
      ?.filter((entry) => entry.showHint(item))
      .map(({ type, message }) => ({ type, message })),
  }));

export const ThreeDotActionsDropdown = <T,>({
  actions,
  item,
  isDisabled,
}: ThreeDotActionsDropdownProps<T>) => {
  const { t } = useTranslation('sharedComponents');
  if (actions.length === 0) {
    return null;
  }
  return (
    <div className="relative flex justify-center items-center gap-2">
      <ActionsDropdown
        actions={toDropdownActions(actions, item)}
        isDisabled={isDisabled}
      >
        <Button
          isIconOnly
          size="sm"
          variant="ghost"
          aria-label={t('list.actions.label')}
          className="h-auto w-6 min-w-6"
          isDisabled={isDisabled}
        >
          <IconDotsVertical className="text-muted" />
        </Button>
      </ActionsDropdown>
    </div>
  );
};

export default ThreeDotActionsDropdown;
