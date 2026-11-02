// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { IconFile, IconLink, IconPencil, IconTrash } from '@tabler/icons-react';
import { ActionButton } from '../../../src/Buttons';
import {
  DropdownRoot,
  DropdownItem,
  DropdownMenu,
  DropdownSection,
  DropdownSubmenuIndicator,
  DropdownSubmenuTrigger,
  DropdownTrigger,
} from '../../../src/Dropdown/DropdownPrimitive';

export default {
  title: 'Components/Dropdown',
} satisfies StoryDefault;

// ============================================================================
// Basic dropdown
// ============================================================================

export const Basic: Story = () => (
  <DropdownRoot>
    <DropdownTrigger>
      <ActionButton primary>Open Dropdown</ActionButton>
    </DropdownTrigger>
    <DropdownMenu aria-label="Actions">
      <DropdownItem
        key="new"
        startContent={<IconFile size={16} />}
        description="Create a blank document"
      >
        New file
      </DropdownItem>
      <DropdownItem key="copy" startContent={<IconLink size={16} />}>
        Copy link
      </DropdownItem>
      <DropdownItem
        key="edit"
        startContent={<IconPencil size={16} />}
        description="Open in editor"
      >
        Edit file
      </DropdownItem>
      <DropdownItem
        key="delete"
        variant="danger"
        startContent={<IconTrash size={16} />}
      >
        Delete file
      </DropdownItem>
    </DropdownMenu>
  </DropdownRoot>
);

// ============================================================================
// Compound form
// ============================================================================

export const CompoundForm: Story = () => (
  <DropdownRoot>
    <DropdownRoot.Trigger>
      <ActionButton primary>Compound Dropdown</ActionButton>
    </DropdownRoot.Trigger>
    <DropdownRoot.Menu aria-label="Actions">
      <DropdownRoot.Item key="new">New file</DropdownRoot.Item>
      <DropdownRoot.Item key="copy">Copy link</DropdownRoot.Item>
      <DropdownRoot.Item key="delete" variant="danger">
        Delete
      </DropdownRoot.Item>
    </DropdownRoot.Menu>
  </DropdownRoot>
);

// ============================================================================
// With sections
// ============================================================================

export const WithSections: Story = () => (
  <DropdownRoot>
    <DropdownTrigger>
      <ActionButton primary>With Sections</ActionButton>
    </DropdownTrigger>
    <DropdownMenu aria-label="Actions with sections">
      <DropdownSection title="Actions">
        <DropdownItem key="new">New file</DropdownItem>
        <DropdownItem key="copy">Copy link</DropdownItem>
      </DropdownSection>
      <DropdownSection title="Danger Zone">
        <DropdownItem key="delete" variant="danger">
          Delete file
        </DropdownItem>
      </DropdownSection>
    </DropdownMenu>
  </DropdownRoot>
);

// ============================================================================
// Disabled keys
// ============================================================================

export const DisabledKeys: Story = () => (
  <DropdownRoot>
    <DropdownTrigger>
      <ActionButton primary>With Disabled Keys</ActionButton>
    </DropdownTrigger>
    <DropdownMenu aria-label="Actions" disabledKeys={['edit', 'delete']}>
      <DropdownItem key="new">New file</DropdownItem>
      <DropdownItem key="copy">Copy link</DropdownItem>
      <DropdownItem key="edit">Edit file (disabled)</DropdownItem>
      <DropdownItem key="delete">Delete file (disabled)</DropdownItem>
    </DropdownMenu>
  </DropdownRoot>
);

// ============================================================================
// With submenus
// ============================================================================

export const WithSubmenus: Story = () => (
  <DropdownRoot>
    <DropdownTrigger>
      <ActionButton primary>With Submenus</ActionButton>
    </DropdownTrigger>
    <DropdownMenu aria-label="Actions with submenus">
      <DropdownItem key="new" startContent={<IconFile size={16} />}>
        New file
      </DropdownItem>
      <DropdownItem key="copy" startContent={<IconLink size={16} />}>
        Copy link
      </DropdownItem>
      <DropdownSubmenuTrigger>
        <DropdownItem key="share" endContent={<DropdownSubmenuIndicator />}>
          Share
        </DropdownItem>
        <DropdownMenu aria-label="Share targets">
          <DropdownItem key="email">Email</DropdownItem>
          <DropdownItem key="link">Copy share link</DropdownItem>
        </DropdownMenu>
      </DropdownSubmenuTrigger>
      <DropdownItem key="delete" variant="danger">
        Delete file
      </DropdownItem>
    </DropdownMenu>
  </DropdownRoot>
);
