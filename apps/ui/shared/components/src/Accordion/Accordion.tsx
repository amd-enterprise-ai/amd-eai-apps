// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Accordion as HeroUIAccordion, cn, type Key } from '@heroui/react';
import React from 'react';

/**
 * v2→v3 Accordion compatibility wrapper.
 *
 * HeroUI v3 rebuilt Accordion on react-aria DisclosureGroup: `selectedKeys`→
 * `expandedKeys`, `onSelectionChange`→`onExpandedChange`, `selectionMode`→
 * `allowsMultipleExpanded`, and the item moved to a compound
 * `Item`>`Heading`>`Trigger`/`Panel`>`Body` tree (`title` is no longer a
 * prop). This wrapper keeps the v2 surface: it accepts the v2 selection prop
 * aliases, derives each item's `id` from its React `key` (v2 collections relied
 * on `key`), and maps per-item `classNames` slots to the compound
 * subcomponents.
 */
type Selection = 'all' | Iterable<Key>;

export interface AccordionItemClassNames {
  base?: string;
  heading?: string;
  trigger?: string;
  title?: string;
  panel?: string;
  content?: string;
  indicator?: string;
  startContent?: string;
}

const toKeySet = (keys?: Selection): Set<Key> | undefined =>
  keys == null || keys === 'all' ? undefined : new Set(keys);

export interface AccordionProps {
  children?: React.ReactNode;
  selectedKeys?: Selection;
  defaultSelectedKeys?: Selection;
  defaultExpandedKeys?: Selection;
  onSelectionChange?: (keys: Set<Key>) => void;
  selectionMode?: 'single' | 'multiple';
  className?: string;
}

const AccordionRoot: React.FC<AccordionProps> = ({
  children,
  selectedKeys,
  defaultSelectedKeys,
  defaultExpandedKeys,
  onSelectionChange,
  selectionMode,
  className,
}) => {
  // v2 collections keyed items by React `key`; v3 requires an explicit `id`.
  const items = React.Children.map(children, (child) => {
    if (!React.isValidElement(child)) return child;
    const element = child as React.ReactElement<{ id?: Key }>;
    if (element.props.id == null && element.key != null) {
      return React.cloneElement(element, { id: element.key });
    }
    return element;
  });

  return (
    <HeroUIAccordion
      expandedKeys={toKeySet(selectedKeys)}
      defaultExpandedKeys={toKeySet(defaultExpandedKeys ?? defaultSelectedKeys)}
      onExpandedChange={onSelectionChange}
      allowsMultipleExpanded={selectionMode === 'multiple'}
      className={className}
    >
      {items}
    </HeroUIAccordion>
  );
};

export interface AccordionItemProps {
  id?: Key;
  title?: React.ReactNode;
  children?: React.ReactNode;
  classNames?: AccordionItemClassNames;
  'aria-label'?: string;
}

export const AccordionItem: React.FC<AccordionItemProps> = ({
  id,
  title,
  children,
  classNames,
  'aria-label': ariaLabel,
}) => {
  const slot = (key: keyof AccordionItemClassNames) =>
    classNames?.[key] || undefined;

  return (
    <HeroUIAccordion.Item id={id} className={slot('base')}>
      <HeroUIAccordion.Heading className={slot('heading')}>
        <HeroUIAccordion.Trigger
          aria-label={ariaLabel}
          className={slot('trigger')}
        >
          <span className={slot('title')}>{title}</span>
          <HeroUIAccordion.Indicator className={slot('indicator')} />
        </HeroUIAccordion.Trigger>
      </HeroUIAccordion.Heading>
      <HeroUIAccordion.Panel
        className={cn('data-[expanded=true]:!overflow-visible', slot('panel'))}
      >
        <HeroUIAccordion.Body className={slot('content')}>
          {children}
        </HeroUIAccordion.Body>
      </HeroUIAccordion.Panel>
    </HeroUIAccordion.Item>
  );
};

export const Accordion = Object.assign(AccordionRoot, {
  Item: AccordionItem,
});
