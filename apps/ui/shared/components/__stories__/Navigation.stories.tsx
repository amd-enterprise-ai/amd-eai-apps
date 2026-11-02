// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { IconChartBar, IconFolder, IconUsers } from '@tabler/icons-react';

import { SidebarItem } from '@amdenterpriseai/types';

import { Navigation } from '../src/Navigation/Navigation';

export default { title: 'Navigation/Navigation' } satisfies StoryDefault;

const menuItems: SidebarItem[] = [
  {
    href: '/dashboard',
    stringKey: 'Dashboard',
    icon: <IconChartBar size={16} stroke={2} />,
  },
  {
    href: '/projects',
    stringKey: 'Projects',
    icon: <IconFolder size={16} stroke={2} />,
  },
  {
    href: '/users',
    stringKey: 'Users',
    icon: <IconUsers size={16} stroke={2} />,
    subItems: [
      { href: '/users/active', stringKey: 'Active Users' },
      { href: '/users/inactive', stringKey: 'Inactive Users' },
    ],
  },
];

export const Desktop: Story = () => (
  <div className="flex h-screen">
    <Navigation
      appTitle="AI Workbench"
      menuItems={menuItems}
      isMobileOpen={false}
      onMobileClose={() => undefined}
    />
    <main className="flex-1 p-8">
      Collapse the sidebar, then hover over it.
    </main>
  </div>
);

export const MobileOpen: Story = () => (
  <div className="h-screen">
    <Navigation
      appTitle="AI Workbench"
      menuItems={menuItems}
      isMobileOpen
      onMobileClose={() => undefined}
    />
  </div>
);
