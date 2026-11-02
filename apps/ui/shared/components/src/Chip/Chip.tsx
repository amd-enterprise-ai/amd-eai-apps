// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Chip as HeroUIChip, cn } from '@heroui/react';
import { IconX } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import React from 'react';

/**
 * v2→v3 Chip compatibility wrapper.
 *
 * HeroUI v3 reworked the v2 `color` × `variant` matrix (color: drops
 * primary/secondary, adds accent; variant: primary/secondary/soft/tertiary),
 * and dropped `startContent`/`endContent`/`onClose`/`radius`/`classNames`. This
 * wrapper keeps the v2 surface so call sites (Status, InlineBadge,
 * TextAreaWrapper) stay unchanged.
 *
 * HeroUI v3 also removed the implicit whitespace-nowrap that v2 applied inside
 * Chip, causing chip labels to wrap across two lines in narrow columns.
 * Re-applied centrally here so all consumers are fixed without call-site changes.
 */
type V3Color = 'default' | 'accent' | 'success' | 'warning' | 'danger';
type V3Variant = 'primary' | 'secondary' | 'soft' | 'tertiary';

export interface ChipProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'color'> {
  children?: React.ReactNode;
  color?:
    | 'default'
    | 'primary'
    | 'secondary'
    | 'success'
    | 'warning'
    | 'danger'
    | 'accent';
  variant?:
    | 'solid'
    | 'bordered'
    | 'light'
    | 'flat'
    | 'faded'
    | 'shadow'
    | 'dot'
    | V3Variant;
  size?: 'sm' | 'md' | 'lg';
  startContent?: React.ReactNode;
  endContent?: React.ReactNode;
  onClose?: () => void;
  /** Accepted for v2 compatibility; v3 chips are not individually disabled. */
  isDisabled?: boolean;
  /** Accepted for v2 compatibility; v3 derives radius from size. */
  radius?: 'none' | 'sm' | 'md' | 'lg' | 'full';
  className?: string;
  classNames?: { base?: string; content?: string; closeButton?: string };
}

const mapColor = (color: ChipProps['color']): V3Color => {
  switch (color) {
    case 'primary':
    case 'accent':
      return 'accent';
    case 'success':
      return 'success';
    case 'warning':
      return 'warning';
    case 'danger':
      return 'danger';
    default:
      return 'default';
  }
};

const V3_VARIANTS: readonly string[] = [
  'primary',
  'secondary',
  'soft',
  'tertiary',
];

const mapVariant = (variant: ChipProps['variant']): V3Variant => {
  if (variant && V3_VARIANTS.includes(variant)) {
    return variant as V3Variant;
  }
  switch (variant) {
    case 'solid':
    case 'shadow':
      return 'primary';
    case 'bordered':
      return 'tertiary';
    case 'dot':
      return 'secondary';
    default:
      return 'soft';
  }
};

export const Chip: React.FC<ChipProps> = ({
  children,
  color,
  variant,
  size,
  startContent,
  endContent,
  onClose,
  isDisabled: _isDisabled,
  radius: _radius,
  className,
  classNames,
  ...rest
}) => {
  const { t } = useTranslation('sharedComponents');

  return (
    <HeroUIChip
      color={mapColor(color)}
      variant={mapVariant(variant)}
      size={size}
      className={cn('whitespace-nowrap', classNames?.base, className)}
      {...rest}
    >
      {startContent}
      {children != null && children !== '' ? (
        <HeroUIChip.Label className={classNames?.content}>
          {children}
        </HeroUIChip.Label>
      ) : null}
      {endContent}
      {onClose ? (
        <button
          type="button"
          aria-label={t('actions.close.title')}
          onClick={onClose}
          className={cn('ml-1 inline-flex', classNames?.closeButton)}
        >
          <IconX size={14} />
        </button>
      ) : null}
    </HeroUIChip>
  );
};

export default Chip;
