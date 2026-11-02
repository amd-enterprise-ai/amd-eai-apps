// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  IconAppWindow,
  IconChartBar,
  IconCheckupList,
  IconCpu,
  IconFolderRoot,
  IconKey,
  IconLayoutDashboard,
  IconMessage,
  IconServer,
  IconWheel,
  IconShieldLock,
  IconUsers,
} from '@tabler/icons-react';
import React from 'react';

import { SidebarItem, UserRole } from '@amdenterpriseai/types';

export const airmMenuItems: SidebarItem[] = [
  {
    href: '/',
    stringKey: 'pages.dashboard.title',
    icon: React.createElement(IconChartBar, { size: 16, stroke: 2 }),
    visibilityByRole: new Set([UserRole.PLATFORM_ADMIN]),
  },
  {
    href: '/clusters',
    stringKey: 'pages.clusters.title',
    icon: React.createElement(IconServer, { size: 16, stroke: 2 }),
  },
  {
    href: '/projects',
    stringKey: 'pages.projects.title',
    icon: React.createElement(IconCheckupList, { size: 16, stroke: 2 }),
  },
  {
    href: '/secrets',
    stringKey: 'pages.secrets.title',
    icon: React.createElement(IconShieldLock, { size: 16, stroke: 2 }),
    visibilityByRole: new Set([UserRole.PLATFORM_ADMIN]),
  },
  {
    href: '/storages',
    stringKey: 'pages.storages.title',
    icon: React.createElement(IconFolderRoot, { size: 16, stroke: 2 }),
    visibilityByRole: new Set([UserRole.PLATFORM_ADMIN]),
  },
  {
    href: '/users',
    stringKey: 'pages.users.title',
    icon: React.createElement(IconUsers, { size: 16, stroke: 2 }),
    visibilityByRole: new Set([UserRole.PLATFORM_ADMIN]),
  },
];

export const aiWorkbenchMenuItems: SidebarItem[] = [
  {
    href: '/',
    stringKey: 'pages.dashboard.title',
    icon: React.createElement(IconLayoutDashboard, { size: 16, stroke: 2 }),
  },
  {
    href: '/api-keys',
    stringKey: 'pages.apiKeys.title',
    icon: React.createElement(IconKey, { size: 16, stroke: 2 }),
  },
  {
    href: '/chat',
    stringKey: 'pages.chat.title',
    icon: React.createElement(IconMessage, { size: 16, stroke: 2 }),
  },
  {
    href: '/models',
    stringKey: 'pages.models.title',
    icon: React.createElement(IconCpu, { size: 16, stroke: 2 }),
    subItems: [
      {
        href: '/models/aim-catalog',
        stringKey: 'pages.aimCatalog.title',
      },
      {
        href: '/models/custom-models',
        stringKey: 'pages.customModels.title',
      },
      {
        href: '/models/deployed-models',
        stringKey: 'pages.deployedModels.title',
      },
    ],
  },
  {
    href: '/fine-tuning',
    stringKey: 'pages.fineTuning.title',
    icon: React.createElement(IconWheel, { size: 16, stroke: 2 }),
    subItems: [
      {
        href: '/fine-tuning/datasets',
        stringKey: 'pages.datasets.title',
      },
      {
        href: '/fine-tuning/models',
        stringKey: 'pages.fineTuneModels.title',
      },
      {
        href: '/fine-tuning/loras',
        stringKey: 'pages.loras.title',
      },
    ],
  },
  {
    href: '/secrets',
    stringKey: 'pages.workbenchSecrets.title',
    icon: React.createElement(IconShieldLock, { size: 16, stroke: 2 }),
  },
  {
    href: '/workspaces',
    stringKey: 'pages.workspaces.title',
    icon: React.createElement(IconAppWindow, { size: 16, stroke: 2 }),
  },
];

export const isMenuItemActive = (
  href: string,
  path: string | null,
): boolean => {
  if (!path) return false;

  // Special case for root path to avoid matching all paths
  if (href === '/') {
    return path === '/';
  }

  // Check if current path matches exactly or starts with the href
  return path === href || path.startsWith(href + '/');
};

/**
 * Filters menu items based on user roles.
 * - If visibilityByRole is undefined, the item is visible to all users.
 * - If visibilityByRole has entries, the item is visible only if the user has at least one matching role.
 */
export const filterMenuItemsByRole = (
  items: SidebarItem[],
  userRoles: string[],
): SidebarItem[] => {
  return items
    .filter((item) => {
      if (!item.visibilityByRole) return true;
      return userRoles.some((role) =>
        item.visibilityByRole?.has(role as UserRole),
      );
    })
    .map((item) => ({
      ...item,
      subItems: item.subItems
        ? filterMenuItemsByRole(item.subItems, userRoles)
        : undefined,
    }));
};

/**
 * Returns the href of the first menu item accessible by the user.
 * - If visibilityByRole is undefined, the item is accessible to all.
 * - If visibilityByRole is defined, accessible only if user has a matching role.
 * Returns undefined if no accessible route is found.
 */
export const getFirstAccessibleRoute = (
  items: SidebarItem[],
  userRoles: string[],
): string | undefined => {
  const accessibleItem = items.find((item) => {
    if (!item.visibilityByRole) return true;
    return userRoles.some((role) =>
      item.visibilityByRole?.has(role as UserRole),
    );
  });
  return accessibleItem?.href;
};
