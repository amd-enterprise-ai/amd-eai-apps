// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Key } from '@heroui/react';
import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from 'react';

const isSubmenuTriggerNode = (element: ReactElement): boolean => {
  const type = element.type as { displayName?: string; name?: string };
  const name = type.displayName ?? type.name ?? '';
  return /SubmenuTrigger/i.test(name);
};

/**
 * HeroUI v3 builds its collections (ListBox, Menu, …) on React Aria Components,
 * whose collection builder ignores the React `key` prop and instead reads an
 * explicit `id` (falling back to an auto-generated key). v2 consumers identify
 * collection items via `key`, so this helper copies each element's `key` into
 * an `id` prop when no `id` is present, recursing through sections/fragments so
 * existing `<Item key=…>` usage keeps driving selection and actions.
 */
export const injectCollectionIds = (nodes: ReactNode): ReactNode =>
  Children.map(nodes, (child) => {
    if (!isValidElement(child)) return child;
    const element = child as ReactElement<{
      id?: Key;
      children?: ReactNode;
    }>;
    // `Dropdown.SubmenuTrigger` is a React Aria collection branch node whose
    // identity the collection builder detects by element type. Assigning it an
    // `id` makes the builder treat it as a leaf item and silently drops the
    // submenu, so never patch the trigger itself — only recurse into its
    // children (the trigger item + submenu menu) to keep their `key`→`id`.
    const isSubmenuTrigger = isSubmenuTriggerNode(element);
    const patched: { id?: Key; children?: ReactNode } = {};
    if (!isSubmenuTrigger && element.props.id == null && element.key != null) {
      patched.id = element.key;
    }
    if (element.props.children != null) {
      const nextChildren = injectCollectionIds(element.props.children);
      if (nextChildren !== element.props.children) {
        patched.children = nextChildren;
      }
    }
    return Object.keys(patched).length > 0
      ? cloneElement(element, patched)
      : child;
  });
