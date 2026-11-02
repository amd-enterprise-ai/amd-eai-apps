// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  IconAppWindow,
  IconChartBar,
  IconCheckupList,
  IconCpu,
  IconDatabase,
  IconHammer,
  IconMessage,
  IconServer,
  IconShieldLock,
  IconUsers,
} from '@tabler/icons-react';

import {
  aiWorkbenchMenuItems,
  airmMenuItems,
  isMenuItemActive,
} from '@amdenterpriseai/utils/app';

describe('Menu Utils', () => {
  describe('airmMenuItems', () => {
    it('should contain the correct number of menu items', () => {
      expect(airmMenuItems).toHaveLength(6);
    });

    it('should contain dashboard menu item', () => {
      const dashboardItem = airmMenuItems.find((item) => item.href === '/');
      expect(dashboardItem).toBeDefined();
      expect(dashboardItem?.stringKey).toBe('pages.dashboard.title');
      expect(dashboardItem?.icon).toBeDefined();
    });

    it('should contain clusters menu item', () => {
      const clustersItem = airmMenuItems.find(
        (item) => item.href === '/clusters',
      );
      expect(clustersItem).toBeDefined();
      expect(clustersItem?.stringKey).toBe('pages.clusters.title');
      expect(clustersItem?.icon).toBeDefined();
    });

    it('should contain projects menu item', () => {
      const projectsItem = airmMenuItems.find(
        (item) => item.href === '/projects',
      );
      expect(projectsItem).toBeDefined();
      expect(projectsItem?.stringKey).toBe('pages.projects.title');
      expect(projectsItem?.icon).toBeDefined();
    });

    it('should contain secrets menu item', () => {
      const secretsItem = airmMenuItems.find(
        (item) => item.href === '/secrets',
      );
      expect(secretsItem).toBeDefined();
      expect(secretsItem?.stringKey).toBe('pages.secrets.title');
      expect(secretsItem?.icon).toBeDefined();
    });

    it('should contain users menu item', () => {
      const usersItem = airmMenuItems.find((item) => item.href === '/users');
      expect(usersItem).toBeDefined();
      expect(usersItem?.stringKey).toBe('pages.users.title');
      expect(usersItem?.icon).toBeDefined();
    });

    it('should have correct icon properties for all items', () => {
      airmMenuItems.forEach((item) => {
        expect(item.icon).toBeDefined();
        expect((item.icon?.props as any)?.size).toBe(16);
        expect((item.icon?.props as any)?.stroke).toBe(2);
      });
    });
  });

  describe('aiWorkbenchMenuItems', () => {
    it('should contain the correct number of menu items', () => {
      expect(aiWorkbenchMenuItems).toHaveLength(7);
    });

    it('should contain chat menu item', () => {
      const chatItem = aiWorkbenchMenuItems.find(
        (item) => item.href === '/chat',
      );
      expect(chatItem).toBeDefined();
      expect(chatItem?.stringKey).toBe('pages.chat.title');
      expect(chatItem?.icon).toBeDefined();
    });

    it('should group fine-tuning pages', () => {
      const fineTuningItem = aiWorkbenchMenuItems.find(
        (item) => item.href === '/fine-tuning',
      );
      expect(fineTuningItem?.stringKey).toBe('pages.fineTuning.title');
      expect(fineTuningItem?.icon).toBeDefined();
      expect(fineTuningItem?.subItems).toEqual([
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
      ]);
    });

    it('should contain models menu item', () => {
      const modelsItem = aiWorkbenchMenuItems.find(
        (item) => item.href === '/models',
      );
      expect(modelsItem).toBeDefined();
      expect(modelsItem?.stringKey).toBe('pages.models.title');
      expect(modelsItem?.icon).toBeDefined();
      expect(modelsItem?.subItems).not.toContainEqual({
        href: '/models/fine-tune-models',
        stringKey: 'pages.fineTuneModels.title',
      });
    });

    it('should contain secrets menu item', () => {
      const secretsItem = aiWorkbenchMenuItems.find(
        (item) => item.href === '/secrets',
      );
      expect(secretsItem).toBeDefined();
      expect(secretsItem?.stringKey).toBe('pages.workbenchSecrets.title');
      expect(secretsItem?.icon).toBeDefined();
    });

    it('should contain workspaces menu item', () => {
      const workspacesItem = aiWorkbenchMenuItems.find(
        (item) => item.href === '/workspaces',
      );
      expect(workspacesItem).toBeDefined();
      expect(workspacesItem?.stringKey).toBe('pages.workspaces.title');
      expect(workspacesItem?.icon).toBeDefined();
    });

    it('should have correct icon properties for all items', () => {
      aiWorkbenchMenuItems.forEach((item) => {
        expect(item.icon).toBeDefined();
        expect((item.icon?.props as any)?.size).toBe(16);
        expect((item.icon?.props as any)?.stroke).toBe(2);
      });
    });
  });

  describe('isMenuItemActive', () => {
    describe('when path is null', () => {
      it('should return false', () => {
        expect(isMenuItemActive('/any-path', null)).toBe(false);
      });
    });

    describe('for root path (/)', () => {
      it('should return true when current path is exactly "/"', () => {
        expect(isMenuItemActive('/', '/')).toBe(true);
      });

      it('should return false when current path starts with "/" but is not exactly "/"', () => {
        expect(isMenuItemActive('/', '/dashboard')).toBe(false);
        expect(isMenuItemActive('/', '/some-other-path')).toBe(false);
      });
    });

    describe('for non-root paths', () => {
      it('should return true when current path matches exactly', () => {
        expect(isMenuItemActive('/projects', '/projects')).toBe(true);
        expect(isMenuItemActive('/users', '/users')).toBe(true);
        expect(isMenuItemActive('/clusters', '/clusters')).toBe(true);
      });

      it('should return true when current path starts with href followed by "/"', () => {
        expect(isMenuItemActive('/projects', '/projects/123')).toBe(true);
        expect(
          isMenuItemActive('/clusters', '/clusters/my-cluster/details'),
        ).toBe(true);
        expect(isMenuItemActive('/models', '/models/create/new')).toBe(true);
      });

      it('should return false when current path does not match or start with href', () => {
        expect(isMenuItemActive('/projects', '/secrets')).toBe(false);
        expect(isMenuItemActive('/models', '/workloads')).toBe(false);
      });

      it('should return false when current path contains href but does not start with it', () => {
        expect(isMenuItemActive('/projects', '/admin/projects')).toBe(false);
      });

      it('should handle partial matches correctly', () => {
        // Should not match when href is a substring but not a path segment
        expect(isMenuItemActive('/project', '/projects')).toBe(false);
      });
    });

    describe('edge cases', () => {
      it('should handle empty path', () => {
        expect(isMenuItemActive('/projects', '')).toBe(false);
      });

      it('should handle paths with query parameters', () => {
        expect(isMenuItemActive('/projects', '/projects?tab=active')).toBe(
          false,
        );
      });

      it('should handle paths with fragments', () => {
        expect(isMenuItemActive('/projects', '/projects#section1')).toBe(false);
      });
    });
  });
});
