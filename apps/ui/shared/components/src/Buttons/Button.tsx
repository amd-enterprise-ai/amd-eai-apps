// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Button as ButtonBase,
  type ButtonProps as ButtonBaseProps,
} from '@heroui/react';
import React from 'react';

export { ButtonGroup } from '@heroui/react';

type V3Variant = NonNullable<ButtonBaseProps['variant']>;
type V2Color =
  | 'default'
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'danger';
type V2Variant =
  | 'solid'
  | 'bordered'
  | 'light'
  | 'flat'
  | 'faded'
  | 'shadow'
  | 'ghost';
type V2Radius = 'none' | 'sm' | 'md' | 'lg' | 'full';

/**
 * HeroUI v3 collapsed the v2 `color` × `variant` matrix into a single `variant`
 * scale and dropped `radius`, `isLoading`, `spinner`, `startContent`,
 * `endContent`. This adapter preserves the v2 Button prop surface so the ~150
 * app/shared call sites do not change, mapping the legacy props onto the v3 API.
 *
 * The color×variant → variant mapping is necessarily lossy (v3 has no
 * soft-primary fill, etc.); pairings flagged for visual QA are noted in the
 * migration report.
 */
export interface ButtonProps
  extends Omit<ButtonBaseProps, 'variant' | 'children'> {
  children?: React.ReactNode;
  variant?: V3Variant | V2Variant;
  color?: V2Color;
  /** Accepted for v2 compatibility; v3 derives radius from size, so ignored. */
  radius?: V2Radius;
  isLoading?: boolean;
  spinner?: React.ReactNode;
  startContent?: React.ReactNode;
  endContent?: React.ReactNode;
  /** v2 alias for `isDisabled`; mapped onto the v3 disabled state. */
  disabled?: boolean;
  /** When set, the button renders as a link via HeroUI v3's `render` prop. */
  href?: string;
  /** Opens the link in a new tab when `href` is set. */
  isExternal?: boolean;
  // HTML passthroughs that react-aria-components' Button type does not surface
  // but v2 call sites still rely on.
  tabIndex?: number;
  role?: React.AriaRole;
  title?: string;
  'data-testid'?: string;
  [dataAttr: `data-${string}`]: unknown;
}

const V3_VARIANTS: readonly string[] = [
  'primary',
  'secondary',
  'tertiary',
  'danger',
  'danger-soft',
  'ghost',
  'outline',
];

const mapVariant = (
  color: V2Color | undefined,
  variant: V3Variant | V2Variant | undefined,
): V3Variant => {
  if (variant && V3_VARIANTS.includes(variant)) {
    return variant as V3Variant;
  }
  if (color === 'danger') {
    return variant === 'flat' || variant === 'light' || variant === 'faded'
      ? 'danger-soft'
      : 'danger';
  }
  if (color === 'primary') {
    return 'primary';
  }
  switch (variant) {
    case 'bordered':
      return 'outline';
    case 'light':
      return 'tertiary';
    case 'ghost':
    case 'faded':
      return 'ghost';
    default:
      return 'secondary';
  }
};

export const Button = React.forwardRef<
  HTMLButtonElement | HTMLAnchorElement,
  ButtonProps
>(
  (
    {
      children,
      color,
      variant,
      radius: _radius,
      isLoading = false,
      spinner,
      startContent,
      endContent,
      isDisabled,
      disabled,
      href,
      isExternal,
      render,
      className,
      fullWidth,
      isIconOnly,
      size,
      ...rest
    },
    ref,
  ) => {
    const mappedVariant = mapVariant(color, variant);
    const resolvedDisabled = isDisabled ?? disabled;

    const renderAsLink: NonNullable<ButtonBaseProps['render']> = (props) => (
      <a
        {...(props as unknown as React.AnchorHTMLAttributes<HTMLAnchorElement>)}
        href={href}
        {...(isExternal
          ? { target: '_blank', rel: 'noopener noreferrer' }
          : {})}
      />
    );

    return (
      <ButtonBase
        ref={ref as React.Ref<HTMLButtonElement>}
        variant={mappedVariant}
        isDisabled={resolvedDisabled || isLoading}
        className={className}
        fullWidth={fullWidth}
        isIconOnly={isIconOnly}
        size={size}
        render={render ?? (href ? renderAsLink : undefined)}
        {...rest}
      >
        {isLoading && spinner ? spinner : startContent}
        {children}
        {endContent}
      </ButtonBase>
    );
  },
);

Button.displayName = 'Button';
