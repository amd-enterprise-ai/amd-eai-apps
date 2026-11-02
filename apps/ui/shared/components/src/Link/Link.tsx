// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Link as HeroUILink, cn } from '@heroui/react';
import { IconExternalLink } from '@tabler/icons-react';
import React from 'react';

/**
 * v2→v3 Link compatibility wrapper.
 *
 * HeroUI v3's Link dropped the `color`/`size`/`underline`/`isExternal`/
 * `showAnchorIcon` variant props and the polymorphic `as` prop (it is a plain
 * react-aria-components Link). This wrapper keeps the v2 surface: it maps
 * `color` to a token class, expands `isExternal` to `target`/`rel`, optionally
 * renders an anchor icon, and renders a custom `as` element (e.g. Next.js Link)
 * with link styling when requested.
 */
type LinkColor =
  | 'foreground'
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'danger';

export interface LinkProps
  extends Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'color'> {
  as?: React.ElementType;
  href?: string;
  color?: LinkColor;
  /** Accepted for v2 compatibility; v3 has no link size scale. */
  size?: 'sm' | 'md' | 'lg';
  /** Accepted for v2 compatibility; v3 links underline on hover by default. */
  underline?: 'none' | 'hover' | 'always' | 'active' | 'focus';
  isExternal?: boolean;
  showAnchorIcon?: boolean;
  className?: string;
  children?: React.ReactNode;
}

const COLOR_CLASS: Record<LinkColor, string> = {
  foreground: 'text-foreground',
  primary: 'text-accent',
  secondary: 'text-accent',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
};

export const Link: React.FC<LinkProps> = ({
  as: As,
  href,
  color,
  size: _size,
  underline: _underline,
  isExternal,
  showAnchorIcon,
  className,
  children,
  target,
  rel,
  ...rest
}) => {
  const colorClass = color ? COLOR_CLASS[color] : undefined;
  const externalTarget = isExternal ? '_blank' : target;
  const externalRel = isExternal ? (rel ?? 'noopener noreferrer') : rel;
  const anchorIcon =
    showAnchorIcon && isExternal ? (
      <IconExternalLink size={16} className="ml-0.5 inline-block" />
    ) : null;

  if (As) {
    return (
      <As
        href={href}
        className={cn('link', colorClass, className)}
        target={externalTarget}
        rel={externalRel}
        {...rest}
      >
        {children}
        {anchorIcon}
      </As>
    );
  }

  return (
    <HeroUILink
      href={href}
      className={cn(colorClass, className)}
      target={externalTarget}
      rel={externalRel}
      {...(rest as React.ComponentProps<typeof HeroUILink>)}
    >
      {children}
      {anchorIcon}
    </HeroUILink>
  );
};

export default Link;
