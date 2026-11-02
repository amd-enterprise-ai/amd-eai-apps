// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Tooltip as HeroUITooltip, cn } from '@heroui/react';
import React, {
  cloneElement,
  isValidElement,
  type HTMLAttributes,
} from 'react';
import { Focusable, type FocusableProps } from 'react-aria';

import { isInteractiveTriggerChild } from '../internal/triggerChild';

/**
 * v2→v3 Tooltip compatibility wrapper.
 *
 * HeroUI v3 made Tooltip fully compound (`Tooltip` > `Tooltip.Trigger` +
 * `Tooltip.Content`) and dropped the flat `content` prop. This wrapper keeps the
 * v2 `<Tooltip content={...}>{trigger}</Tooltip>` surface so the ~12 call sites
 * stay unchanged, splitting trigger/content props onto the right subcomponents.
 */
type ContentProps = React.ComponentProps<typeof HeroUITooltip.Content>;
type RootProps = React.ComponentProps<typeof HeroUITooltip>;

// v2 used dash-separated placements (`top-start`); v3/react-aria use a
// space-separated grammar (`top start`, and `left top`/`left bottom` for the
// cross-axis on the sides).
const PLACEMENT_MAP: Record<string, string> = {
  'top-start': 'top start',
  'top-end': 'top end',
  'bottom-start': 'bottom start',
  'bottom-end': 'bottom end',
  'left-start': 'left top',
  'left-end': 'left bottom',
  'right-start': 'right top',
  'right-end': 'right bottom',
};

const mapPlacement = (
  placement?: string,
): ContentProps['placement'] | undefined =>
  placement === undefined
    ? undefined
    : ((PLACEMENT_MAP[placement] ?? placement) as ContentProps['placement']);

export interface TooltipProps {
  children: React.ReactNode;
  content?: React.ReactNode;
  /** Accepts v2 dash placements (`top-start`) and v3 space placements. */
  placement?: ContentProps['placement'] | (string & {});
  offset?: ContentProps['offset'];
  crossOffset?: ContentProps['crossOffset'];
  containerPadding?: ContentProps['containerPadding'];
  /** Accepted for v2 compatibility; v3 tooltips have no size variant. */
  size?: 'sm' | 'md' | 'lg';
  showArrow?: boolean;
  delay?: RootProps['delay'];
  closeDelay?: RootProps['closeDelay'];
  isDisabled?: RootProps['isDisabled'];
  isOpen?: RootProps['isOpen'];
  defaultOpen?: RootProps['defaultOpen'];
  onOpenChange?: RootProps['onOpenChange'];
  className?: string;
  classNames?: { base?: string; content?: string };
}

export const Tooltip: React.FC<TooltipProps> = ({
  children,
  content,
  placement,
  offset,
  crossOffset,
  containerPadding,
  size: _size,
  showArrow,
  delay = 250,
  closeDelay,
  isDisabled,
  isOpen,
  defaultOpen,
  onOpenChange,
  className,
  classNames,
}) => {
  if (content === undefined || content === null || content === '') {
    return <>{children}</>;
  }
  // An already-interactive child (Button/Link/native button) is itself the
  // focusable trigger; react-aria's TooltipTrigger wires it via context. Other
  // content needs a Focusable wrapper to pick up those trigger props — wrapping
  // a button there would nest two button-role elements.
  //
  // HeroUITooltip.Trigger cannot play that role: it consumes a FocusableContext
  // from a react-aria copy vendored inside @heroui/react, a different module
  // instance from the one TooltipTrigger publishes the trigger ref through. The
  // ref never arrives, and the overlay, left without an anchor, positions itself
  // at the viewport origin.
  const isInteractive = isInteractiveTriggerChild(children);
  // Focusable clones its props and ref onto the child, so only a plain DOM
  // element is guaranteed to accept both; a component that drops the ref again
  // costs the tooltip its anchor. Everything else — components, bare strings,
  // fragments — gets a span we control.
  //
  // A DOM element keeps the markup the call site wrote, including its role or
  // lack of one. Giving it an interactive role would let screen readers announce
  // the tooltip, but the same element is also used to wrap disabled controls,
  // where the role would mask the control it contains.
  const domChild =
    isValidElement<HTMLAttributes<HTMLElement>>(children) &&
    typeof children.type === 'string'
      ? children
      : null;
  const focusableChild = domChild ? (
    cloneElement(domChild, {
      // A disabled button swallows pointer events, so hover has to reach the
      // element wrapping it instead.
      className: cn(
        domChild.props.className,
        '[&_button:disabled]:pointer-events-none',
      ),
    })
  ) : (
    // The role keeps react-aria announcing the tooltip as a description.
    // biome-ignore lint/a11y/useSemanticElements: a <button> would imply an action and could wrap interactive children.
    <span className="cursor-help" role="button" tabIndex={0}>
      {children}
    </span>
  );
  const trigger = isInteractive ? (
    children
  ) : (
    <Focusable>{focusableChild as FocusableProps['children']}</Focusable>
  );
  return (
    <HeroUITooltip
      delay={delay}
      closeDelay={closeDelay}
      isDisabled={isDisabled}
      isOpen={isOpen}
      defaultOpen={defaultOpen}
      onOpenChange={onOpenChange}
    >
      {trigger}
      <HeroUITooltip.Content
        placement={mapPlacement(placement)}
        offset={offset}
        crossOffset={crossOffset}
        containerPadding={containerPadding}
        showArrow={showArrow}
        className={cn(
          'break-normal wrap-break-word',
          classNames?.base,
          classNames?.content,
          className,
        )}
      >
        {content}
      </HeroUITooltip.Content>
    </HeroUITooltip>
  );
};

export default Tooltip;
