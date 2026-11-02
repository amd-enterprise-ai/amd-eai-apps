// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 rebuilt Dropdown on React Aria Components and changed its anatomy:
// the menu now lives inside `Dropdown.Popover`, items/sections are fully
// compound (`Label` / `Description` / `Dropdown.ItemIndicator` / `Header`) and
// the v2 convenience props (`startContent`, `endContent`, `description`,
// `showDivider`, `isReadOnly`) were removed. These adapters keep the v2
// names/structure (`<Dropdown>` → `<DropdownTrigger>` + `<DropdownMenu>` with
// `<DropdownItem>` / `<DropdownSection>`) so consumers do not have to change,
// mapping the old prop surface onto v3 and recomposing the popover/menu tree
// internally. Selection lists belong on `Listbox`, not this action-menu adapter.
import {
  Description,
  Dropdown as HeroDropdown,
  Header,
  Label,
  Separator,
  cn,
} from '@heroui/react';
import type {
  DropdownItemProps as DropdownItemRootProps,
  DropdownMenuProps as DropdownMenuRootProps,
  DropdownProps,
  DropdownSectionProps as DropdownSectionRootProps,
} from '@heroui/react';
import {
  Children,
  cloneElement,
  type ComponentProps,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from 'react';

import { injectCollectionIds } from '../internal/collectionIds';
import { isInteractiveTriggerChild } from '../internal/triggerChild';

export interface DropdownItemProps
  extends Omit<DropdownItemRootProps, 'children'> {
  children?: ReactNode;
  /** Content rendered before the label (v2 compat). */
  startContent?: ReactNode;
  /** Content rendered after the label (v2 compat). */
  endContent?: ReactNode;
  /** Secondary text rendered under the label (v2 compat). */
  description?: ReactNode;
  /** Render a divider after the item (v2 compat). */
  showDivider?: boolean;
  /** No-op in v3; retained so existing call sites compile. */
  isReadOnly?: boolean;
}

export interface DropdownSectionProps
  extends Omit<DropdownSectionRootProps, 'children' | 'title'> {
  children?: ReactNode;
  /** Section heading (v2 compat). */
  title?: ReactNode;
  /** Render a divider after the section (v2 compat). */
  showDivider?: boolean;
}

export type DropdownMenuProps<T extends object = object> =
  DropdownMenuRootProps<T>;

export interface DropdownTriggerProps {
  children?: ReactNode;
  className?: string;
}

// v3 `Dropdown.Trigger` renders its own `<Button>` and nests `children` inside
// it. v2 call sites pass an already-interactive trigger (our `Button`/
// `ActionButton`), which would produce a button-in-button. react-aria's
// `MenuTrigger` wires the trigger through `PressResponder` context, so an
// interactive child can be the trigger directly; we merge the wrapper's
// `className` onto it. Non-interactive content keeps the v3 `Button` wrapper.
const DropdownTrigger = ({
  children,
  className,
  ...props
}: DropdownTriggerProps): ReactElement => {
  if (
    Children.count(children) === 1 &&
    isInteractiveTriggerChild(children) &&
    isValidElement<{ className?: string }>(children)
  ) {
    return className
      ? cloneElement(children, {
          className: cn(children.props.className, className),
        })
      : children;
  }
  return (
    <HeroDropdown.Trigger className={className} {...props}>
      {children}
    </HeroDropdown.Trigger>
  );
};

const DropdownItem = ({
  children,
  startContent,
  endContent,
  description,
  showDivider,
  variant,
  isReadOnly: _isReadOnly,
  ...props
}: DropdownItemProps) => {
  const dangerClass = variant === 'danger' ? 'text-danger' : undefined;
  const item = (
    <HeroDropdown.Item
      variant={variant}
      className="flex flex-row gap-2"
      {...props}
    >
      {startContent ? (
        <div
          className={cn(
            'flex flex-row h-8 items-center justify-center',
            dangerClass,
          )}
        >
          {startContent}
        </div>
      ) : null}
      <div className="flex flex-col w-full">
        <Label>{children}</Label>

        {description ? (
          <Description className="text-muted">{description}</Description>
        ) : null}
      </div>
      {endContent ? (
        <div
          className={cn(
            'flex flex-row h-8 items-center justify-center',
            dangerClass,
          )}
        >
          {endContent}
        </div>
      ) : null}
    </HeroDropdown.Item>
  );
  // Avoid wrapping in a fragment unless a divider is needed so the bare
  // `Dropdown.Item` can be used directly as a `Dropdown.SubmenuTrigger` child.
  if (!showDivider) {
    return item;
  }
  return (
    <>
      {item}
      <Separator />
    </>
  );
};

const DropdownSection = ({
  children,
  title,
  showDivider,
  ...props
}: DropdownSectionProps) => (
  <>
    <HeroDropdown.Section {...props}>
      {title ? <Header>{title}</Header> : null}
      {children}
    </HeroDropdown.Section>
    {showDivider ? <Separator /> : null}
  </>
);

const DropdownMenu = <T extends object = object>({
  children,
  ...props
}: DropdownMenuProps<T>) => (
  <HeroDropdown.Popover>
    <HeroDropdown.Menu {...props}>
      {typeof children === 'function'
        ? children
        : injectCollectionIds(children as ReactNode)}
    </HeroDropdown.Menu>
  </HeroDropdown.Popover>
);

export type DropdownSubmenuTriggerProps = ComponentProps<
  typeof HeroDropdown.SubmenuTrigger
>;

// `Dropdown.SubmenuTrigger` is a React Aria collection *branch* node: the menu's
// collection builder identifies it by a static marker on the component itself,
// so it cannot be wrapped in our own function component (a wrapper renders as a
// plain item and the submenu is silently dropped). Re-export the primitive
// directly. Its children are the trigger `Dropdown.Item` (carrying a
// `Dropdown.SubmenuIndicator`) followed by the submenu's `Dropdown.Menu`.
const DropdownSubmenuTrigger = HeroDropdown.SubmenuTrigger;

export interface DropdownSubmenuIndicatorProps {
  children?: ReactNode;
  className?: string;
}

// Chevron rendered inside a submenu-parent `Dropdown.Item`. Defaults to v3's
// built-in indicator; accepts `children` to override it.
const DropdownSubmenuIndicator = ({
  children,
  className,
}: DropdownSubmenuIndicatorProps) => (
  <HeroDropdown.SubmenuIndicator className={className}>
    {children}
  </HeroDropdown.SubmenuIndicator>
);

// v2 Dropdown accepted `isDisabled` on the root to disable the whole menu; v3's
// root is a DialogTrigger that has no such prop (the trigger button owns its own
// disabled state). Absorb it here so call sites stay unchanged.
export interface DropdownRootProps extends DropdownProps {
  isDisabled?: boolean;
}

type DropdownRootType = ((props: DropdownRootProps) => ReactElement) & {
  Item: typeof DropdownItem;
  Menu: typeof DropdownMenu;
  Section: typeof DropdownSection;
  Trigger: typeof DropdownTrigger;
  SubmenuTrigger: typeof DropdownSubmenuTrigger;
  SubmenuIndicator: typeof DropdownSubmenuIndicator;
};

const DropdownRootBase = ({
  isDisabled: _isDisabled,
  ...props
}: DropdownRootProps): ReactElement => <HeroDropdown {...props} />;

const DropdownRoot = DropdownRootBase as DropdownRootType;
DropdownRoot.Item = DropdownItem;
DropdownRoot.Menu = DropdownMenu;
DropdownRoot.Section = DropdownSection;
DropdownRoot.Trigger = DropdownTrigger;
DropdownRoot.SubmenuTrigger = DropdownSubmenuTrigger;
DropdownRoot.SubmenuIndicator = DropdownSubmenuIndicator;

export {
  DropdownRoot,
  DropdownItem,
  DropdownMenu,
  DropdownSection,
  DropdownTrigger,
  DropdownSubmenuTrigger,
  DropdownSubmenuIndicator,
};
export type { DropdownProps };
