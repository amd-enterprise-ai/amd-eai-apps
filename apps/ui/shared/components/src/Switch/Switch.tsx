// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Description, Switch as HeroUISwitch, cn } from '@heroui/react';
import React from 'react';

/**
 * v2→v3 Switch compatibility wrapper.
 *
 * HeroUI v3 made Switch fully compound (`Switch` > `Switch.Content` >
 * `Switch.Control` > `Switch.Thumb` + label), renamed `onValueChange`→`onChange`,
 * and dropped `color`/`startContent`/`endContent`/`classNames`. This wrapper
 * keeps the v2 surface so call sites (FormSwitch, UserMenu, …) stay unchanged.
 */
type RootProps = React.ComponentProps<typeof HeroUISwitch>;

export interface SwitchChangeEvent {
  target: { checked: boolean };
}

export interface SwitchProps extends Omit<RootProps, 'children' | 'onChange'> {
  children?: React.ReactNode;
  description?: React.ReactNode;
  /** Accepted for v2 compatibility; v3 switches have no color prop. */
  color?: string;
  startContent?: React.ReactNode;
  endContent?: React.ReactNode;
  /** v2 native-like change handler; receives `{ target: { checked } }`. */
  onChange?: (event: SwitchChangeEvent) => void;
  onValueChange?: (isSelected: boolean) => void;
  classNames?: {
    base?: string;
    wrapper?: string;
    thumb?: string;
    label?: string;
    description?: string;
  };
}

export const Switch: React.FC<SwitchProps> = ({
  children,
  description,
  color: _color,
  startContent,
  endContent,
  onChange,
  onValueChange,
  className,
  classNames,
  ...rest
}) => {
  const handleChange = (isSelected: boolean) => {
    onChange?.({ target: { checked: isSelected } });
    onValueChange?.(isSelected);
  };

  const hasDescription = description != null && description !== '';

  const labelContent = (
    <>
      {startContent}
      {children}
      {endContent}
    </>
  );

  return (
    <HeroUISwitch
      onChange={handleChange}
      className={cn(
        hasDescription &&
          'grid grid-cols-[auto_1fr] grid-rows-[auto_auto] items-start gap-x-3 gap-y-1',
        classNames?.base,
        className,
      )}
      {...rest}
    >
      <HeroUISwitch.Content
        className={cn(classNames?.label, hasDescription && 'contents')}
      >
        <HeroUISwitch.Control
          className={cn(
            classNames?.wrapper,
            hasDescription && 'col-start-1 row-span-2 self-start',
          )}
        >
          <HeroUISwitch.Thumb className={classNames?.thumb} />
        </HeroUISwitch.Control>
        {hasDescription ? (
          <span className="col-start-2 row-start-1 inline-flex items-center gap-1">
            {labelContent}
          </span>
        ) : (
          labelContent
        )}
      </HeroUISwitch.Content>
      {hasDescription ? (
        <Description
          className={cn(
            'col-start-2 row-start-2 ps-0! text-muted',
            classNames?.description,
          )}
        >
          {description}
        </Description>
      ) : null}
    </HeroUISwitch>
  );
};

export default Switch;
