// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  DrawerPrimitive as Drawer,
  DrawerBody,
  DrawerContent,
  DrawerHeader,
} from './DrawerPrimitive';

import { PropsWithChildren } from 'react';

interface Props {
  isOpen?: boolean;
  title: string;
  onOpenChange?: () => void;
}

export const DrawerDisplay = ({
  isOpen,
  onOpenChange,
  title,
  children,
}: PropsWithChildren<Props>) => {
  return (
    <Drawer isOpen={isOpen} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>{title}</DrawerHeader>
        <DrawerBody>{children}</DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default DrawerDisplay;
