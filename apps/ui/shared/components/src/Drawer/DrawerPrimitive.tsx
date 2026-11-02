// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Drawer as HeroUIDrawer } from '@heroui/react';
import React from 'react';

/**
 * v2→v3 Drawer compatibility shim — mirrors the Modal shim.
 *
 * HeroUI v3 uses a compound tree (`Drawer` > `Backdrop` > `Content` > `Dialog` >
 * `Header`/`Body`/`Footer`/`CloseTrigger`). This shim keeps the v2 JSX shape
 * (`DrawerPrimitive` > `DrawerContent` > Header/Body/Footer) while locking
 * placement to the right edge, a blur backdrop, and baked header/body/close
 * styling so consumers cannot drift visually.
 */

interface DrawerPrimitiveProps {
  children: React.ReactNode;
  isOpen?: boolean;
  onOpenChange?: (isOpen: boolean) => void;
  onClose?: () => void;
  isDismissable?: boolean;
  /** v2 compat: accepted but ignored; width is controlled by DRAWER_DIALOG_PANEL_CLASS */
  size?: string;
  /** v2 compat: accepted but ignored */
  radius?: string;
  [key: `data-${string}`]: unknown;
}

const DrawerRoot: React.FC<DrawerPrimitiveProps> = ({
  children,
  isOpen,
  onOpenChange,
  onClose,
  isDismissable = true,
  size: _size,
  radius: _radius,
  ...rest
}) => {
  const handleOpenChange = (open: boolean) => {
    onOpenChange?.(open);
    if (!open) {
      onClose?.();
    }
  };

  return (
    <HeroUIDrawer isOpen={isOpen} onOpenChange={handleOpenChange}>
      <HeroUIDrawer.Backdrop isDismissable={isDismissable} variant="blur">
        <HeroUIDrawer.Content placement="right" {...rest}>
          {children}
        </HeroUIDrawer.Content>
      </HeroUIDrawer.Backdrop>
    </HeroUIDrawer>
  );
};

interface SlotProps {
  children: React.ReactNode;
  className?: string;
}

interface ContentProps extends SlotProps {
  hideCloseButton?: boolean;
}

/** Fixed panel width (wider than HeroUI default); `max-w-[85vw]` keeps narrow viewports usable. */
const DRAWER_DIALOG_PANEL_CLASS = 'w-[30rem] max-w-[85vw]';

export const DrawerContent: React.FC<ContentProps> = ({
  children,
  hideCloseButton = false,
}) => (
  <HeroUIDrawer.Dialog className={DRAWER_DIALOG_PANEL_CLASS}>
    {!hideCloseButton ? <HeroUIDrawer.CloseTrigger /> : null}
    {children}
  </HeroUIDrawer.Dialog>
);

export const DrawerHeader: React.FC<SlotProps> = ({ children }) => (
  <HeroUIDrawer.Header>
    <HeroUIDrawer.Heading>{children}</HeroUIDrawer.Heading>
  </HeroUIDrawer.Header>
);

export const DrawerBody: React.FC<SlotProps> = ({ children, className }) => (
  <HeroUIDrawer.Body className={className}>{children}</HeroUIDrawer.Body>
);

export const DrawerFooter: React.FC<SlotProps> = ({ children }) => (
  <HeroUIDrawer.Footer>{children}</HeroUIDrawer.Footer>
);

export const DrawerPrimitive = Object.assign(DrawerRoot, {
  Content: DrawerContent,
  Header: DrawerHeader,
  Body: DrawerBody,
  Footer: DrawerFooter,
});
