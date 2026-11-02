// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';
import {
  DrawerPrimitive,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
} from '../../../src/Drawer';
import { ActionButton } from '../../../src/Buttons';

export default {
  title: 'Components/Drawer/DrawerPrimitive',
} satisfies StoryDefault;

export const CompoundAPI: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <>
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open Drawer
      </ActionButton>
      <DrawerPrimitive isOpen={isOpen} onOpenChange={() => setIsOpen(false)}>
        <DrawerPrimitive.Content>
          <DrawerPrimitive.Header>Compound API</DrawerPrimitive.Header>
          <DrawerPrimitive.Body>
            <p>This drawer uses the compound component pattern.</p>
          </DrawerPrimitive.Body>
          <DrawerPrimitive.Footer>
            <ActionButton secondary onPress={() => setIsOpen(false)}>
              Close
            </ActionButton>
          </DrawerPrimitive.Footer>
        </DrawerPrimitive.Content>
      </DrawerPrimitive>
    </>
  );
};

export const FlatAliases: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <>
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open Drawer
      </ActionButton>
      <DrawerPrimitive isOpen={isOpen} onOpenChange={() => setIsOpen(false)}>
        <DrawerContent>
          <DrawerHeader>Flat Aliases</DrawerHeader>
          <DrawerBody>
            <p>This drawer uses the flat alias exports.</p>
          </DrawerBody>
          <DrawerFooter>
            <ActionButton secondary onPress={() => setIsOpen(false)}>
              Close
            </ActionButton>
          </DrawerFooter>
        </DrawerContent>
      </DrawerPrimitive>
    </>
  );
};
