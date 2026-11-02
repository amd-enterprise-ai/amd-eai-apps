// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React, { useMemo } from 'react';
import { Button } from './Button';
import type { ButtonProps } from './Button';
import { VARIANT_CONFIGS, SPINNER_ELEMENT } from './constants';

type ExclusiveButtonProps =
  | { primary: true; secondary?: never; tertiary?: never }
  | { secondary: true; primary?: never; tertiary?: never }
  | { tertiary: true; primary?: never; secondary?: never }
  | { primary?: never; secondary?: never; tertiary?: never }; // empty object defaults to secondary

export type ActionButtonProps = Omit<
  ButtonProps,
  'variant' | 'radius' | 'spinner' | 'isIconOnly'
> &
  ExclusiveButtonProps & {
    icon?: React.ReactNode;
  };

/**
 * Utility function to detect if children content is empty or contains only whitespace
 * Handles various React node types including strings, arrays, fragments, and elements
 * @param children - React node to check for emptiness
 * @returns True if children is empty or contains only whitespace, false otherwise
 */
const isChildrenEmpty = (children: React.ReactNode): boolean => {
  if (children === undefined || children === null) return true;

  if (typeof children === 'string') return children.trim() === '';

  if (Array.isArray(children))
    return children.every((child) => isChildrenEmpty(child));

  if (React.isValidElement(children)) {
    if (children.type === React.Fragment)
      return isChildrenEmpty(
        (children.props as { children?: React.ReactNode }).children,
      );

    return false;
  }

  return false;
};

/**
 * Memoized icon wrapper component to prevent unnecessary re-renders
 * Only renders the icon when it exists and the button is not in loading state
 * @param icon - React node representing the icon to display
 * @param isLoading - Whether the button is in loading state
 * @returns Icon wrapped in a div with appropriate styling, or null if no icon or loading
 */
const IconWrapper = React.memo<{ icon?: React.ReactNode; isLoading?: boolean }>(
  ({ icon, isLoading }) =>
    !icon || isLoading ? null : (
      <div className="select-none outline-none">{icon}</div>
    ),
);

IconWrapper.displayName = 'IconWrapper';

/**
 * ActionButton - A customizable button component with predefined styling variants
 *
 * This component wraps HeroUI's Button with enforced styling constraints and additional features:
 * - Enforces solid/flat/light variants based on primary/secondary/tertiary props
 * - Sets radius to match button size for consistent styling
 * - Automatically detects icon-only buttons when children is empty
 * - Provides a consistent spinner element for loading states
 * - Supports optional icon display with proper loading state handling
 *
 * @example
 * ```tsx
 * // Primary button with text
 * <ActionButton primary onPress={handleSave}>Save</ActionButton>
 *
 * // Secondary button with icon
 * <ActionButton secondary icon={<IconPlus />}>Add Item</ActionButton>
 *
 * // Icon-only tertiary button
 * <ActionButton tertiary icon={<IconEdit />} />
 *
 * // Loading state
 * <ActionButton primary isLoading>Processing...</ActionButton>
 * ```
 *
 * @param props - ActionButton props extending HeroUI ButtonProps with variant constraints
 * @param ref - Forwarded ref to the underlying button element
 * @returns Styled button component with enforced design system constraints
 */
export const ActionButton = React.memo(
  React.forwardRef<HTMLButtonElement, ActionButtonProps>((props, ref) => {
    const {
      children,
      color,
      size = 'md',
      icon,
      isLoading,
      startContent,
      primary = false,
      tertiary = false,
      // react-toastify / overlay code sometimes forwards toast helpers onto buttons
      closeToast: _closeToast,
      ...buttonProps
    } = props as ActionButtonProps & { closeToast?: unknown };

    const variantConfig = useMemo(() => {
      if (color === 'danger') return VARIANT_CONFIGS.danger;
      if (primary) return VARIANT_CONFIGS.primary;
      if (tertiary) return VARIANT_CONFIGS.tertiary;
      return VARIANT_CONFIGS.secondary;
    }, [primary, tertiary, color]);

    const isIconOnly = useMemo(() => isChildrenEmpty(children), [children]);

    return (
      <Button
        {...buttonProps}
        ref={ref}
        color={color}
        radius={size}
        size={size}
        variant={variantConfig.variant}
        spinner={SPINNER_ELEMENT}
        isLoading={isLoading}
        isIconOnly={isIconOnly}
        startContent={
          startContent !== undefined ? (
            startContent
          ) : (
            <IconWrapper icon={icon} isLoading={isLoading} />
          )
        }
      >
        {children}
      </Button>
    );
  }),
);

ActionButton.displayName = 'ActionButton';
