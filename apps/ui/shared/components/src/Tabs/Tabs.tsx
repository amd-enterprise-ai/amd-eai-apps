// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Tabs as HeroUITabs, cn, type Key } from '@heroui/react';
import React from 'react';

/**
 * HeroUI v3 Tabs compatibility wrapper.
 *
 * v3 uses compound components (`Tabs` > `Tabs.ListContainer` > `Tabs.List` >
 * `Tabs.Tab` + `Tabs.Panel`) and dropped the v2 `Tab` `title` prop and
 * collection/`items` render-prop API. This wrapper preserves the v2 caller
 * surface: `Tab` children (or `items` + render-prop) with React `key`, `title`,
 * and panel `children`. We derive v3 `id` from the React `key` and emit matching
 * `Tabs.Panel` nodes for tabs that carry panel content.
 */
export interface TabProps {
  id?: Key;
  title?: React.ReactNode;
  children?: React.ReactNode;
  isDisabled?: boolean;
  className?: string;
  'aria-label'?: string;
}

/**
 * Marker component. `Tabs` reads its props directly; it is never mounted on its
 * own, so it renders nothing if used outside of `Tabs`.
 */
export const Tab: React.FC<TabProps> = () => null;

interface TabsClassNames {
  base?: string | false;
  tabList?: string | false;
  tab?: string | false;
  panel?: string | false;
  tabWrapper?: string | false;
}

export interface TabsProps<T extends { id: Key } = { id: Key }> {
  children?: React.ReactNode | ((item: T) => React.ReactNode);
  items?: Iterable<T>;
  selectedKey?: Key;
  defaultSelectedKey?: Key;
  onSelectionChange?: (key: Key) => void;
  isDisabled?: boolean;
  variant?: 'primary' | 'secondary';
  /** When true, tab list spans full width with equal-width tabs. Default false — strip fits content. */
  fullWidth?: boolean;
  className?: string;
  classNames?: TabsClassNames;
  'aria-label'?: string;
}

interface NormalizedTab {
  id: string;
  label: React.ReactNode;
  panel: React.ReactNode;
  isDisabled?: boolean;
  className?: string;
  ariaLabel?: string;
}

const TabsRoot = <T extends { id: Key } = { id: Key }>({
  children,
  items,
  selectedKey,
  defaultSelectedKey,
  onSelectionChange,
  isDisabled,
  variant,
  fullWidth = false,
  className,
  classNames,
  'aria-label': ariaLabel,
}: TabsProps<T>) => {
  const tabNodes: React.ReactNode =
    typeof children === 'function' && items
      ? Array.from(items).map((item) =>
          (children as (item: T) => React.ReactNode)(item),
        )
      : (children as React.ReactNode);

  const normalized: NormalizedTab[] = [];
  React.Children.forEach(tabNodes, (child) => {
    if (!React.isValidElement<TabProps>(child)) return;
    const { id, title, children: panel, isDisabled: tabDisabled } = child.props;
    const resolvedId = id ?? child.key ?? undefined;
    if (resolvedId == null) return;
    normalized.push({
      id: String(resolvedId),
      label: title ?? panel,
      // Only tabs that pass a `title` (the label) can also own panel content;
      // a child without a title is label-only navigation.
      panel: title != null ? panel : undefined,
      isDisabled: tabDisabled,
      className: child.props.className,
      ariaLabel: child.props['aria-label'],
    });
  });

  const tabWidth = fullWidth ? 'w-full' : 'w-fit';
  const stripWidth = fullWidth || variant === 'secondary' ? 'w-full' : 'w-fit';

  return (
    <HeroUITabs
      selectedKey={selectedKey == null ? undefined : String(selectedKey)}
      defaultSelectedKey={
        defaultSelectedKey == null ? undefined : String(defaultSelectedKey)
      }
      onSelectionChange={onSelectionChange}
      isDisabled={isDisabled}
      variant={variant}
      className={cn(classNames?.base, className) || undefined}
    >
      <HeroUITabs.ListContainer
        className={cn(stripWidth, classNames?.tabWrapper) || undefined}
      >
        <HeroUITabs.List
          aria-label={ariaLabel}
          className={cn(stripWidth, classNames?.tabList) || undefined}
        >
          {normalized.map((tab) => (
            <HeroUITabs.Tab
              key={tab.id}
              id={tab.id}
              isDisabled={tab.isDisabled}
              aria-label={tab.ariaLabel}
              className={
                cn(classNames?.tab, tab.className, tabWidth) || undefined
              }
            >
              {tab.label}
              <HeroUITabs.Indicator />
            </HeroUITabs.Tab>
          ))}
        </HeroUITabs.List>
      </HeroUITabs.ListContainer>
      {normalized
        .filter((tab) => tab.panel != null && tab.panel !== false)
        .map((tab) => (
          <HeroUITabs.Panel
            key={tab.id}
            id={tab.id}
            className={cn(classNames?.panel) || undefined}
          >
            {tab.panel}
          </HeroUITabs.Panel>
        ))}
    </HeroUITabs>
  );
};

export const Tabs = Object.assign(TabsRoot, { Tab });
