// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconChevronDown, IconChevronRight } from '@tabler/icons-react';
import React, { useEffect, useState } from 'react';
import { cn } from '@heroui/react';

import { useTranslation } from 'next-i18next';
import { usePathname } from 'next/navigation';
import { useRouter } from 'next/router';

import { SidebarItem } from '@amdenterpriseai/types';
import { isMenuItemActive } from '@amdenterpriseai/utils/app';

import { stripProjectPrefix } from './project-utils';
import { SidebarButton } from './SidebarButton';
import { Tooltip } from '../Tooltip/Tooltip';

interface Props {
  item: SidebarItem;
  isCollapsed: boolean;
  idPrefix?: string;
  projectPrefix?: string;
  onNavigate?: () => void;
}

export const CollapsibleItem: React.FC<Props> = ({
  item,
  isCollapsed,
  idPrefix = 'sidebar',
  projectPrefix,
  onNavigate,
}) => {
  const { t } = useTranslation('common');
  const pathname = usePathname();
  const { locale, defaultLocale } = useRouter();
  const path = stripProjectPrefix(
    pathname,
    projectPrefix,
    locale,
    defaultLocale,
  );
  const hasActiveSubItem = !!item.subItems?.some((subItem) =>
    isMenuItemActive(subItem.href, path),
  );
  const submenuId = `${idPrefix}-submenu-${item.stringKey.replace(/[^a-z0-9]/gi, '-').toLowerCase()}`;
  const label = t(item.stringKey as any) as string;
  const subItems = isCollapsed ? undefined : item.subItems;
  const [isExpanded, setIsExpanded] = useState(hasActiveSubItem);

  useEffect(() => {
    if (hasActiveSubItem) setIsExpanded(true);
  }, [hasActiveSubItem]);

  return (
    <li>
      <Tooltip content={isCollapsed ? label : undefined} placement="right">
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className={cn(
            'menu-item flex h-11 items-center rounded-md py-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background',
            {
              'w-12': isCollapsed,
              'w-full': !isCollapsed,
              'bg-accent-soft text-accent-soft-foreground':
                isCollapsed && hasActiveSubItem,
              'bg-transparent hover:bg-default-hover dark:hover:bg-default':
                !isCollapsed || !hasActiveSubItem,
            },
          )}
          aria-current={isCollapsed && hasActiveSubItem ? 'true' : undefined}
          aria-expanded={subItems ? isExpanded : undefined}
          aria-controls={subItems ? submenuId : undefined}
        >
          <div className="flex w-full items-center tracking-tight">
            <span className="shrink-0 px-2" aria-hidden="true">
              {item.icon}
            </span>
            <span
              className={cn({
                'sr-only': isCollapsed,
                'text-nowrap': !isCollapsed,
              })}
            >
              {label}
            </span>
            <span
              className={cn('ml-auto mr-3 shrink-0', {
                hidden: isCollapsed,
              })}
              aria-hidden="true"
            >
              {isExpanded ? (
                <IconChevronDown size={14} />
              ) : (
                <IconChevronRight size={14} />
              )}
            </span>
          </div>
        </button>
      </Tooltip>

      {subItems && (
        // Stays mounted (never unmounted) so the grid-rows transition below can
        // animate the collapse; `inert` removes it from the tab order and a11y
        // tree instead, so it never traps keyboard/AT focus while collapsed.
        <div
          data-testid={submenuId}
          inert={!isExpanded}
          className={cn(
            'grid transition-[grid-template-rows,opacity] duration-300 ease-out',
            {
              'grid-rows-[1fr] opacity-100': isExpanded,
              'grid-rows-[0fr] opacity-0': !isExpanded,
            },
          )}
        >
          <div className="min-h-0">
            <ul id={submenuId} className="ml-4 mt-1">
              {subItems.map((subItem: SidebarItem) => (
                <li key={subItem.stringKey} className="gap-1 my-1">
                  <SidebarButton
                    href={subItem.href}
                    text={subItem.stringKey}
                    icon={subItem.icon}
                    isCollapsed={false}
                    projectPrefix={projectPrefix}
                    onNavigate={onNavigate}
                  />
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </li>
  );
};
