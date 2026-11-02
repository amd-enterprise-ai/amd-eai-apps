// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 renamed `Listbox` to `ListBox` and made its items/sections fully
// compound (`ListBox.Item` / `ListBox.Section`). The v3 items also dropped the
// v2 convenience props (`startContent`, `endContent`, `description`,
// `showDivider`, section `title`) and no longer render their own selection
// indicator. These thin adapters keep the v2 names and prop surface so existing
// consumers (Select, HuggingFaceTokenSelector, DataFilter, …) do not change.
import {
  Description,
  Header,
  Label,
  ListBox,
  ListBoxItem,
  ListBoxSection,
  Separator,
} from '@heroui/react';
import type {
  ListBoxItemProps as ListBoxItemRootProps,
  ListBoxProps,
  ListBoxSectionProps as ListBoxSectionRootProps,
} from '@heroui/react';
import type { ComponentProps, ReactElement, ReactNode } from 'react';

export type ListboxProps<T extends object = object> = ListBoxProps<T>;

export interface ListboxItemProps
  extends Omit<ListBoxItemRootProps, 'children'> {
  children?: ReactNode;
  /** Content rendered before the label (v2 compat). */
  startContent?: ReactNode;
  /** Content rendered after the label (v2 compat). */
  endContent?: ReactNode;
  /** Secondary description rendered under the label (v2 compat). */
  description?: ReactNode;
  /** Class name applied to the selection indicator. */
  indicatorClassName?: string;
  /** Whether to render the selected-state indicator. Defaults to `true`. */
  showIndicator?: boolean;
  /** Render a divider after the item (v2 compat). */
  showDivider?: boolean;
}

export interface ListboxSectionProps
  extends Omit<ListBoxSectionRootProps, 'children' | 'title'> {
  children?: ReactNode;
  /** Section heading (v2 compat). */
  title?: ReactNode;
  /** Render a divider after the section (v2 compat). */
  showDivider?: boolean;
}

const ListboxBase = (props: ComponentProps<typeof ListBox>): ReactElement => (
  <ListBox {...props} />
);

const ListboxItem = ({
  children,
  startContent,
  endContent,
  description,
  indicatorClassName,
  className,
  showIndicator = true,
  showDivider,
  textValue,
  ...props
}: ListboxItemProps) => (
  <>
    <ListBoxItem
      className={className || undefined}
      textValue={
        textValue ?? (description != null ? String(children) : undefined)
      }
      {...props}
    >
      {startContent}
      {description ? (
        <span className="flex flex-col">
          <Label>{children}</Label>
          <Description className="text-muted">{description}</Description>
        </span>
      ) : (
        children
      )}
      {endContent}
      {showIndicator ? (
        <ListBoxItem.Indicator className={indicatorClassName} />
      ) : null}
    </ListBoxItem>
    {showDivider ? <Separator /> : null}
  </>
);

const ListboxSection = ({
  children,
  title,
  showDivider,
  ...props
}: ListboxSectionProps) => (
  <>
    <ListBoxSection {...props}>
      {title ? <Header>{title}</Header> : null}
      {children}
    </ListBoxSection>
    {showDivider ? <Separator /> : null}
  </>
);

const Listbox = Object.assign(ListboxBase, {
  Item: ListboxItem,
  Section: ListboxSection,
});

export { Listbox, ListboxItem, ListboxSection };
