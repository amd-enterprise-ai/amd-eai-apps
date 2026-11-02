// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  IconAlertTriangle,
  IconDotsVertical,
  IconInfoCircle,
} from '@tabler/icons-react';
import { Key, ReactNode } from 'react';
import { useTranslation } from 'next-i18next';

import { ActionFieldHintType } from '@amdenterpriseai/types';

import { ActionButton } from '../Buttons/ActionButton';
import { Tooltip } from '../Tooltip';
import {
  DropdownRoot as Dropdown,
  DropdownItem,
  DropdownMenu,
  DropdownSection,
  DropdownSubmenuIndicator,
  DropdownSubmenuTrigger,
  DropdownTrigger,
} from './DropdownPrimitive';
import { DropdownActionItem, DropdownItemHint } from './types';

interface ActionsDropdownProps {
  actions: DropdownActionItem[];
  isDisabled?: boolean;
  children?: ReactNode;
}

const hasSubmenu = (action: DropdownActionItem): boolean =>
  !action.isSection && !!action.actions && action.actions.length > 0;

// Only leaf items (no submenu, not a section) own an executable `onPress`.
// Section containers and submenu parents merely group or open child menus, so
// they are excluded from the action registry and activating them never fires an
// `onPress`.
const collectActionables = (
  actions: DropdownActionItem[],
  registry: Map<string, () => void>,
  disabledKeys: string[],
): void => {
  for (const action of actions) {
    if (action.isSection || hasSubmenu(action)) {
      collectActionables(action.actions ?? [], registry, disabledKeys);
      continue;
    }
    registry.set(action.key, action.onPress);
    if (action.isDisabled) {
      disabledKeys.push(action.key);
    }
  }
};

const HintList = ({ hints }: { hints: DropdownItemHint[] }) => (
  <div className="flex flex-col gap-1 mt-1 text-xs">
    {hints.map((hint) => (
      <div className="flex items-center gap-1" key={hint.message}>
        {hint.type === ActionFieldHintType.INFO && (
          <IconInfoCircle className="text-info" />
        )}
        {hint.type === ActionFieldHintType.WARNING && (
          <IconAlertTriangle className="text-warning" />
        )}
        {hint.type === ActionFieldHintType.ERROR && (
          <IconAlertTriangle className="text-danger" />
        )}
        <span>{hint.message}</span>
      </div>
    ))}
  </div>
);

interface MenuContext {
  onAction: (key: Key) => void;
  disabledKeys: string[];
}

const renderItem =
  (ctx: MenuContext) =>
  (action: DropdownActionItem): ReactNode => {
    if (action.isSection) {
      return (
        <DropdownSection
          key={action.key}
          title={action.label}
          data-testid={`section-${action.key}`}
        >
          {(action.actions ?? []).map(renderItem(ctx))}
        </DropdownSection>
      );
    }
    const variant = action.color === 'danger' ? 'danger' : undefined;
    const itemProps = {
      id: action.key,
      className: action.className,
      'data-testid': action.key,
      'aria-label': action.label,
      startContent: action.startContent,
      description: action.description,
      variant,
    } as const;
    if (hasSubmenu(action)) {
      return (
        <DropdownSubmenuTrigger key={action.key}>
          <DropdownItem
            {...itemProps}
            endContent={<DropdownSubmenuIndicator />}
          >
            {action.label}
          </DropdownItem>
          <DropdownMenu onAction={ctx.onAction} disabledKeys={ctx.disabledKeys}>
            {action.actions!.map(renderItem(ctx))}
          </DropdownMenu>
        </DropdownSubmenuTrigger>
      );
    }
    return (
      <DropdownItem
        key={action.key}
        {...itemProps}
        showDivider={action.showDivider}
      >
        {action.label}
      </DropdownItem>
    );
  };

/**
 * Data-driven action menu built on the HeroUI v3 Dropdown adapter. Accepts a
 * tree of {@link DropdownActionItem}s and renders flat items, sections, and
 * native submenus, dispatching each leaf's `onPress`. Optional per-action
 * `hint`s surface in a tooltip wrapping the menu.
 */
export const ActionsDropdown = ({
  actions,
  isDisabled,
  children,
}: ActionsDropdownProps) => {
  const { t } = useTranslation('sharedComponents');

  if (actions.length === 0) {
    return null;
  }
  const registry = new Map<string, () => void>();
  const disabledKeys: string[] = [];
  collectActionables(actions, registry, disabledKeys);
  const handleAction = (key: Key) => registry.get(String(key))?.();
  // The same handler/disabledKeys are bound to every menu level because HeroUI
  // dispatches `onAction` per menu, and submenu items live in their own menu
  // collection.
  const ctx: MenuContext = { onAction: handleAction, disabledKeys };
  const hints = actions.flatMap((action) => action.hint ?? []);
  const menu = (
    <DropdownMenu onAction={handleAction} disabledKeys={disabledKeys}>
      {actions.map(renderItem(ctx))}
    </DropdownMenu>
  );
  const defaultTrigger = (
    <ActionButton
      tertiary
      size="sm"
      aria-label={t('list.actions.menu')}
      className="h-auto w-6 min-w-6"
      isDisabled={isDisabled}
      icon={<IconDotsVertical className="text-muted" />}
    />
  );
  return (
    <Dropdown isDisabled={isDisabled}>
      <DropdownTrigger>{children ?? defaultTrigger}</DropdownTrigger>
      {hints.length > 0 ? (
        <Tooltip content={<HintList hints={hints} />}>{menu}</Tooltip>
      ) : (
        menu
      )}
    </Dropdown>
  );
};

export default ActionsDropdown;
