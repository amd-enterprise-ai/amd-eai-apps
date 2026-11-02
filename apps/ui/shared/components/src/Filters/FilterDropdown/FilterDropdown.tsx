// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Selection } from '../../Select/Select';
import { Listbox, ListboxItem } from '../../Listbox/Listbox';
import { CloseButton, cn, Popover } from '@heroui/react';
import { injectCollectionIds } from '../../internal/collectionIds';
import { useTranslation } from 'next-i18next';
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import FilterButtonTrigger from './FilterButtonTrigger';
import { FILTER_CONSTANTS } from './constants';
import { useFilterState } from '@amdenterpriseai/hooks';
import type { FilterItem } from '@amdenterpriseai/types';

export type { FilterItem };

/**
 * Ref interface for FilterDropdown component
 */
export interface FilterDropdownRef {
  clear: () => void;
}

/**
 * Props for the FilterDropdown component
 */
export interface FilterDropdownProps {
  label: string;
  items: FilterItem[];
  icon?: ReactNode;
  className?: string;
  defaultSelectedKeys?: string[];
  selectedKeys?: string[];
  showDescription?: boolean;
  onSelectionChange?: (keys: Set<string>) => void;
  tooltipText?: string;
}

/**
 * FilterDropdown Component
 *
 * A multi-select dropdown with advanced features including:
 * - External state synchronization with debouncing
 * - First-selection behavior (clear all, select one)
 * - Reset functionality
 * - Accessible keyboard navigation
 *
 * @example
 * ```tsx
 * <FilterDropdown
 *   label="Status"
 *   items={statusItems}
 *   selectedKeys={selectedStatuses}
 *   onSelectionChange={setSelectedStatuses}
 *   defaultSelectedKeys={['active']}
 * />
 * ```
 */
const FilterDropdown = forwardRef<FilterDropdownRef, FilterDropdownProps>(
  (
    {
      label,
      items,
      icon,
      className,
      showDescription = true,
      tooltipText,
      selectedKeys,
      defaultSelectedKeys,
      onSelectionChange,
    },
    ref,
  ) => {
    const {
      currentSelectedSet,
      hasUserInteracted,
      handleSelectionChange,
      handleReset,
    } = useFilterState({
      selectedKeys,
      defaultSelectedKeys,
      items,
      onSelectionChange,
    });

    useImperativeHandle(ref, () => ({ clear: handleReset }), [handleReset]);

    const { t } = useTranslation('sharedComponents');
    const [isOpen, setIsOpen] = useState(false);

    const tooltip = useMemo(() => {
      if (tooltipText) return tooltipText;
      return items
        .filter((item) => currentSelectedSet.has(item.key))
        .map((item) => item.label)
        .join(', ');
    }, [items, currentSelectedSet, tooltipText]);

    const handleListboxSelectionChange = useCallback(
      (keys: Selection) => {
        handleSelectionChange(new Set(Array.from(keys).map(String)));
      },
      [handleSelectionChange],
    );

    const selectedIconClassName = !hasUserInteracted ? 'opacity-30' : '';

    const listboxItems = useMemo(
      () =>
        items.map(
          ({
            key,
            label: itemLabel,
            description = '',
            showDivider = false,
          }) => (
            <ListboxItem
              key={key}
              className="capitalize"
              aria-label={itemLabel}
              description={showDescription ? description : undefined}
              showDivider={showDivider}
              indicatorClassName={selectedIconClassName}
            >
              {itemLabel}
            </ListboxItem>
          ),
        ),
      [items, showDescription, selectedIconClassName],
    );

    return (
      <div className={cn('relative w-full', className)}>
        <Popover isOpen={isOpen} onOpenChange={setIsOpen}>
          <Popover.Trigger
            className="flex w-full cursor-pointer appearance-none border-0 bg-transparent p-0 text-start"
            aria-label={label}
          >
            <FilterButtonTrigger
              label={label}
              startContent={icon}
              tooltipText={tooltip}
              numberOfSelectedKeys={currentSelectedSet.size}
              isActive={hasUserInteracted}
              showClearButton={hasUserInteracted}
            />
          </Popover.Trigger>
          <Popover.Content
            className={FILTER_CONSTANTS.MIN_DROPDOWN_WIDTH}
            placement="bottom start"
          >
            <Listbox
              aria-label={label}
              selectionMode="multiple"
              selectedKeys={currentSelectedSet}
              onSelectionChange={handleListboxSelectionChange}
              // Let Escape close the popover instead of RAC's default
              // clearSelection, which swallows the first Escape when a selection
              // exists and leaves the dropdown open.
              escapeKeyBehavior="none"
              autoFocus
            >
              {injectCollectionIds(listboxItems)}
            </Listbox>
          </Popover.Content>
        </Popover>
        {hasUserInteracted && (
          <CloseButton
            onPress={handleReset}
            aria-label={t('actions.clear.title')}
            className="search-field__clear-button absolute right-0 top-1/2 -translate-y-1/2 z-10"
          />
        )}
      </div>
    );
  },
);

FilterDropdown.displayName = 'FilterDropdown';

export default FilterDropdown;
