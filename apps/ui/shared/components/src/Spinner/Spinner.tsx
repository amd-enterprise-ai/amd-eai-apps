// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 narrowed the Spinner `color` scale to
// `success | warning | danger | accent | current` (dropping v2's
// `default`/`primary`/`secondary`) and dropped the `label` prop (v2 rendered a
// caption beside the spinner). This adapter maps the v2 colors and re-renders
// the label so call sites stay unchanged.
import { Spinner as SpinnerBase, cn } from '@heroui/react';
import type { ComponentProps, ReactElement, ReactNode } from 'react';

type V3Color = 'success' | 'warning' | 'danger' | 'accent' | 'current';

export interface SpinnerProps
  extends Omit<ComponentProps<typeof SpinnerBase>, 'color'> {
  color?: V3Color | 'default' | 'primary' | 'secondary';
  /** v2 caption rendered beside the spinner; also used as the accessible name. */
  label?: ReactNode;
}

const COLOR_MAP: Record<string, V3Color> = {
  default: 'current',
  primary: 'accent',
  secondary: 'current',
};

const Spinner = ({ color, label, ...props }: SpinnerProps): ReactElement => {
  const spinner = (
    <SpinnerBase
      color={color ? (COLOR_MAP[color] ?? (color as V3Color)) : undefined}
      aria-label={
        typeof label === 'string'
          ? label
          : (props['aria-label'] as string | undefined)
      }
      {...props}
    />
  );

  if (label == null || label === '') {
    return spinner;
  }

  return (
    <div className={cn('flex flex-col items-center gap-2')}>
      {spinner}
      <span>{label}</span>
    </div>
  );
};

export { Spinner };
