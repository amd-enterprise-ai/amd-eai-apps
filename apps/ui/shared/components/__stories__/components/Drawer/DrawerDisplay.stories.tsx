// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';

import { DrawerDisplay } from '../../../src/Drawer';
import { ActionButton } from '../../../src/Buttons';

export default {
  title: 'Components/Drawer/DrawerDisplay',
} satisfies StoryDefault;

export const Basic: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open display drawer
      </ActionButton>
      <DrawerDisplay
        isOpen={isOpen}
        onOpenChange={() => setIsOpen(false)}
        title="Connection details"
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">
            DrawerDisplay wraps DrawerPrimitive for read-only content with a
            fixed right-edge layout and blur backdrop.
          </p>
          <dl className="flex flex-col gap-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted">Endpoint</dt>
              <dd className="font-mono">https://api.example.com/v1</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Region</dt>
              <dd className="font-mono">us-east-1</dd>
            </div>
          </dl>
        </div>
      </DrawerDisplay>
    </div>
  );
};

export const LongContent: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open display drawer
      </ActionButton>
      <DrawerDisplay
        isOpen={isOpen}
        onOpenChange={() => setIsOpen(false)}
        title="Release notes"
      >
        <div className="flex flex-col gap-4">
          {Array.from({ length: 12 }).map((_, index) => (
            <p key={index} className="text-sm text-foreground">
              Section {index + 1}: the drawer body scrolls independently while
              the header stays pinned, so long content stays readable.
            </p>
          ))}
        </div>
      </DrawerDisplay>
    </div>
  );
};
