// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';

import { ActionsDropdown } from '../../../src/Dropdown/ActionsDropdown';
import type { DropdownActionItem } from '../../../src/Dropdown/types';

export default {
  title: 'Components/ActionsDropdown',
} satisfies StoryDefault;

const flatActions: DropdownActionItem[] = [
  { key: 'settings', label: 'Settings', onPress: () => {} },
  { key: 'delete', label: 'Delete', color: 'danger', onPress: () => {} },
];

export const Default: Story = () => <ActionsDropdown actions={flatActions} />;

const disabledActions: DropdownActionItem[] = [
  { key: 'edit', label: 'Edit', onPress: () => {} },
  {
    key: 'archive',
    label: 'Archive (disabled)',
    isDisabled: true,
    onPress: () => {},
  },
];

export const WithDisabledItem: Story = () => (
  <ActionsDropdown actions={disabledActions} />
);

const nestedActions: DropdownActionItem[] = [
  {
    key: 'deployments',
    label: '2 deployments',
    isSection: true,
    onPress: () => {},
    actions: [
      {
        key: 'deployment-a',
        label: 'deployment-a',
        description: 'v2.0.1 • Latency',
        onPress: () => {},
        actions: [
          { key: 'details-a', label: 'Workload details', onPress: () => {} },
          { key: 'chat-a', label: 'Chat with model', onPress: () => {} },
          {
            key: 'undeploy-a',
            label: 'Undeploy',
            color: 'danger',
            onPress: () => {},
          },
        ],
      },
    ],
  },
];

export const WithSectionsAndSubmenus: Story = () => (
  <ActionsDropdown actions={nestedActions} />
);
