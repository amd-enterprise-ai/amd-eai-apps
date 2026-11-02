// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 renamed `BreadcrumbItem` to `BreadcrumbsItem` and exposes it as the
// compound `Breadcrumbs.Item`. It also dropped the `size` prop. Keep the v2
// `BreadcrumbItem` name as an alias and absorb `size` so existing consumers do
// not need to change.
import {
  Breadcrumbs as BreadcrumbsBase,
  BreadcrumbsItem,
  type BreadcrumbsProps as BreadcrumbsBaseProps,
} from '@heroui/react';
import type { ReactElement } from 'react';

export type { BreadcrumbsItemProps as BreadcrumbItemProps } from '@heroui/react';

export interface BreadcrumbsProps extends BreadcrumbsBaseProps {
  /** Accepted for v2 compatibility; v3 has no Breadcrumbs size scale. */
  size?: string;
}

const BreadcrumbItem = BreadcrumbsItem;

// v3/react-aria renders Breadcrumbs as an `<ol>` (role `list`) and applies the
// `aria-label` there. v2 rendered a `<nav aria-label>` landmark, so wrap the v3
// tree in a `<nav>` to preserve the `navigation` role and accessible name that
// consumers (and their tests) rely on.
const BreadcrumbsBaseWrapper = ({
  size: _size,
  'aria-label': ariaLabel,
  ...props
}: BreadcrumbsProps): ReactElement => (
  <nav aria-label={ariaLabel}>
    <BreadcrumbsBase aria-label={ariaLabel} {...props} />
  </nav>
);

const Breadcrumbs = Object.assign(BreadcrumbsBaseWrapper, {
  Item: BreadcrumbItem,
});

export { Breadcrumbs, BreadcrumbItem };
