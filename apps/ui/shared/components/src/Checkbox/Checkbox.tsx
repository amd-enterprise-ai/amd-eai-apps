// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 rebuilt Checkbox as a compound component (`Checkbox.Control` >
// `Checkbox.Indicator`, plus an optional `Checkbox.Content` > `Label`) and
// replaced the v2 `onValueChange(isSelected)` / native `onChange(event)` props
// with a single `onChange(isSelected)` handler. This adapter keeps the v2 prop
// surface — flat `<Checkbox>label</Checkbox>` with `onValueChange` and/or the
// event-style `onChange` — by composing the v3 subcomponents internally and
// fanning the change handler out to both callbacks.
import { Checkbox as HeroUICheckbox, Label } from '@heroui/react';
import type { CheckboxRootProps } from '@heroui/react';
import type { ReactNode } from 'react';

export interface CheckboxChangeEvent {
  target: { checked: boolean };
}

export interface CheckboxProps
  extends Omit<CheckboxRootProps, 'onChange' | 'children'> {
  children?: ReactNode;
  /** v2 value-change handler. */
  onValueChange?: (isSelected: boolean) => void;
  /** v2 native-like change handler; receives `{ target: { checked } }`. */
  onChange?: (event: CheckboxChangeEvent) => void;
}

export const Checkbox = ({
  children,
  onValueChange,
  onChange,
  'aria-label': ariaLabel,
  ...props
}: CheckboxProps) => (
  <HeroUICheckbox
    onChange={(isSelected: boolean) => {
      onValueChange?.(isSelected);
      onChange?.({ target: { checked: isSelected } });
    }}
    {...(children == null && ariaLabel ? { 'aria-label': ariaLabel } : {})}
    {...props}
  >
    {children != null ? (
      <HeroUICheckbox.Content>
        <HeroUICheckbox.Control>
          <HeroUICheckbox.Indicator />
        </HeroUICheckbox.Control>
        <Label>{children}</Label>
      </HeroUICheckbox.Content>
    ) : (
      <HeroUICheckbox.Control>
        <HeroUICheckbox.Indicator />
      </HeroUICheckbox.Control>
    )}
  </HeroUICheckbox>
);

export default Checkbox;
