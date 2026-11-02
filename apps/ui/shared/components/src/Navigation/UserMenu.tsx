// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Switch as HeroUISwitch } from '@heroui/react';
import {
  DropdownRoot as Dropdown,
  DropdownItem,
  DropdownMenu,
  DropdownSection,
  DropdownTrigger,
} from '../Dropdown/DropdownPrimitive';
import {
  IconFlag,
  IconLogout,
  IconMoon,
  IconSun,
  IconUser,
} from '@tabler/icons-react';
import { CollectionElement } from '@react-types/shared';
import { useSession } from 'next-auth/react';
import React from 'react';

import { useTranslation } from 'next-i18next';
import { useTheme } from 'next-themes';

import { useSystemInfo } from '@amdenterpriseai/hooks';
import { createMailtoLink, logout } from '@amdenterpriseai/utils/app';

interface UserMenuProps {
  additionalMenuItems?: CollectionElement<object>;
}

export const UserMenu: React.FC<UserMenuProps> = ({ additionalMenuItems }) => {
  const { data: session } = useSession();
  const { theme, setTheme } = useTheme();
  const { t: tShared } = useTranslation('sharedComponents');
  const getSystemInfo = useSystemInfo();

  const handleLogout = async () => {
    await logout();
  };

  const reportIssueHref = createMailtoLink({
    subject: 'Issue report: [describe the problem shortly]',
    body: [
      'Issue:',
      '[Please describe the issue in detail, include steps to reproduce and what result was expected]',
      '',
      '--- System info ---',
      ...getSystemInfo(),
    ],
  });

  return (
    <div data-testid="user-menu">
      <Dropdown>
        <DropdownTrigger>
          <div className="flex items-center cursor-pointer gap-3 capitalize outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-lg">
            <div className="hidden md:flex flex-col justify-start text-right">
              <span className="font-semibold text-sm text-foreground">
                {session?.user?.name}
              </span>
              <span className="text-nowrap text-xs lowercase text-muted font-normal">
                {session?.user?.email}
              </span>
            </div>
            <div className="border border-default text-foreground rounded-full min-w-8 h-8 flex justify-center items-center">
              <IconUser stroke="2" size={14} />
            </div>
          </div>
        </DropdownTrigger>
        <DropdownMenu aria-label={tShared('list.actions.label')}>
          <DropdownSection
            aria-label={tShared('menu.actions.themeToggle')}
            showDivider
          >
            <DropdownItem
              key="menu-theme-toggle"
              shouldCloseOnSelect={false}
              onPress={() => setTheme(theme === 'light' ? 'dark' : 'light')}
              startContent={
                <HeroUISwitch
                  size="lg"
                  isSelected={theme === 'light'}
                  className="pointer-events-none shrink-0"
                >
                  <HeroUISwitch.Control>
                    <HeroUISwitch.Thumb>
                      <HeroUISwitch.Icon>
                        {theme === 'light' ? (
                          <IconSun className="size-3 text-inherit" />
                        ) : (
                          <IconMoon className="size-3 text-inherit" />
                        )}
                      </HeroUISwitch.Icon>
                    </HeroUISwitch.Thumb>
                  </HeroUISwitch.Control>
                </HeroUISwitch>
              }
            >
              {tShared('menu.actions.theme', {
                theme: tShared(
                  theme === 'light' ? 'theme.light' : 'theme.dark',
                ),
              })}
            </DropdownItem>
          </DropdownSection>
          {additionalMenuItems ?? null}
          <DropdownItem
            href={reportIssueHref}
            startContent={<IconFlag size={16} stroke={2} />}
            key="menu-report-issue"
          >
            {tShared('menu.actions.reportIssue')}
          </DropdownItem>
          <DropdownItem
            onPress={handleLogout}
            startContent={<IconLogout size={16} stroke={2} />}
            key="menu-logout"
          >
            {tShared('menu.actions.logout')}
          </DropdownItem>
        </DropdownMenu>
      </Dropdown>
    </div>
  );
};
