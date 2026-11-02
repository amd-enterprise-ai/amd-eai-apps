// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React, { FC, useMemo } from 'react';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useRouter } from 'next/router';
import { useTranslation } from 'next-i18next';
import { cn } from '@heroui/react';

import { Tooltip } from '../Tooltip/Tooltip';

import { isMenuItemActive } from '@amdenterpriseai/utils/app';

import { buildProjectHref, stripProjectPrefix } from './project-utils';

interface Props {
  text: string;
  href: string;
  isCollapsed: boolean;
  icon?: React.ReactNode;
  projectPrefix?: string;
  onNavigate?: () => void;
}

export const SidebarButton: FC<Props> = ({
  href,
  text,
  icon,
  isCollapsed,
  projectPrefix,
  onNavigate,
}) => {
  const { t } = useTranslation('common');
  const pathname = usePathname();
  const router = useRouter();

  const fullHref = useMemo(
    () => buildProjectHref(href, projectPrefix),
    [projectPrefix, href],
  );

  const pathWithoutProject = useMemo(
    () =>
      stripProjectPrefix(
        pathname,
        projectPrefix,
        router.locale,
        router.defaultLocale,
      ),
    [projectPrefix, pathname, router.locale, router.defaultLocale],
  );

  const label = t(text as any) as string;
  const content = (
    <div className="flex w-full items-center tracking-tight">
      <span className="shrink-0 px-2" aria-hidden="true">
        {icon}
      </span>
      <span
        className={cn({
          'sr-only': isCollapsed,
          'text-nowrap': !isCollapsed,
        })}
      >
        {label}
      </span>
    </div>
  );

  const isActive = isMenuItemActive(href, pathWithoutProject);
  const classNames = cn({
    'bg-accent-soft text-accent-soft-foreground': isActive,
    'bg-transparent hover:bg-default-hover dark:hover:bg-default': !isActive,
  });

  return (
    <Tooltip content={isCollapsed ? label : undefined} placement="right">
      <Link
        className={cn(
          'menu-item flex h-11 items-center rounded-md py-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          {
            'w-12': isCollapsed,
            'w-full': !isCollapsed,
          },
          classNames,
        )}
        href={fullHref}
        aria-current={isActive ? 'page' : undefined}
        onClick={onNavigate}
      >
        {content}
      </Link>
    </Tooltip>
  );
};
