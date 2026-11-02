// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useSession } from 'next-auth/react';
import { useTranslation } from 'next-i18next';
import Link from 'next/link';
import React, { useState } from 'react';
import { FocusScope } from 'react-aria';
import { cn } from '@heroui/react';

import { AMDLogoSymbol } from '@amdenterpriseai/assets/svg/logo';
import { useDebouncedCallback } from '@amdenterpriseai/hooks';
import { SidebarItem } from '@amdenterpriseai/types';
import { filterMenuItemsByRole } from '@amdenterpriseai/utils/app';

import { Tooltip } from '../Tooltip/Tooltip';
import { CollapsibleItem } from './CollapsibleItem';
import { SidebarButton } from './SidebarButton';
import { SidebarToggleButton } from './SidebarToggleButton';

const COLLAPSE_DELAY_MS = 300;

type NavigationProps = {
  appTitle: string;
  menuItems: SidebarItem[];
  projectPrefix?: string;
  isMobileOpen: boolean;
  onMobileClose: () => void;
};

export const Navigation: React.FC<NavigationProps> = ({
  appTitle,
  menuItems,
  projectPrefix,
  isMobileOpen,
  onMobileClose,
}) => {
  const { data: session } = useSession({ required: true });
  const { t } = useTranslation('common');
  const { t: tShared } = useTranslation('sharedComponents');
  const [isPinned, setPinned] = useState(true);
  const [isHovered, setHovered] = useState(false);
  const isExpanded = isPinned || isHovered;
  const filteredItems = filterMenuItemsByRole(
    menuItems,
    session?.user?.roles ?? [],
  );
  const setHoveredLater = useDebouncedCallback(
    (hovered: boolean) => setHovered(hovered),
    COLLAPSE_DELAY_MS,
  );

  const renderItems = (
    isCollapsed: boolean,
    idPrefix: string,
    onNavigate?: () => void,
  ) =>
    filteredItems.map((item) =>
      item.subItems?.length ? (
        <CollapsibleItem
          key={item.stringKey}
          item={item}
          isCollapsed={isCollapsed}
          idPrefix={idPrefix}
          projectPrefix={projectPrefix}
          onNavigate={onNavigate}
        />
      ) : (
        <li key={item.stringKey}>
          <SidebarButton
            href={item.href}
            text={item.stringKey}
            icon={item.icon}
            isCollapsed={isCollapsed}
            projectPrefix={projectPrefix}
            onNavigate={onNavigate}
          />
        </li>
      ),
    );

  const reveal = () => {
    setHovered(true);
    setHoveredLater(true);
  };

  const onBlur = (event: React.FocusEvent<HTMLElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setHoveredLater(false);
    }
  };

  return (
    <>
      {!isPinned && isExpanded && (
        <div
          data-testid="navigation-dim-layer"
          aria-hidden="true"
          className="fixed inset-0 z-30 bg-black/40 pointer-events-none"
        />
      )}

      <div
        data-testid="desktop-navigation-spacer"
        className={cn(
          'relative hidden h-screen shrink-0 transition-[width] duration-100 md:block',
          {
            'w-80': isPinned,
            'w-16': !isPinned,
          },
        )}
      >
        <aside
          id="sidebar-nav-panel"
          onMouseEnter={reveal}
          onMouseLeave={() => setHoveredLater(false)}
          onFocus={reveal}
          onBlur={onBlur}
          style={{
            clipPath: isExpanded ? 'inset(0)' : 'inset(0 16rem 0 0)',
          }}
          className={cn(
            'absolute inset-y-0 left-0 z-40 flex w-80 flex-col justify-between overflow-x-hidden border-r border-default bg-background px-2 py-4 transition-[clip-path] duration-100 ease-in-out will-change-[clip-path]',
            { 'shadow-overlay': !isPinned && isExpanded },
          )}
        >
          <div>
            <div className="mb-6 px-4 flex justify-between items-center">
              <Link
                href={projectPrefix ? `/${projectPrefix}/` : '/'}
                aria-label={tShared('menu.sidebar.goToHome')}
                className="flex gap-2"
              >
                <AMDLogoSymbol
                  aria-hidden="true"
                  className="text-foreground h-4"
                />
                {!isExpanded ? null : (
                  <span className="text-foreground font-bold text-nowrap">
                    {t(appTitle as any) as string}
                  </span>
                )}
              </Link>

              <Tooltip
                content={tShared(
                  isPinned ? 'menu.sidebar.collapse' : 'menu.sidebar.expand',
                )}
                placement="right"
              >
                <SidebarToggleButton
                  isExpanded={isPinned}
                  onExpandedChange={setPinned}
                  controlsId="sidebar-nav-panel"
                  ariaLabel={tShared(
                    isPinned ? 'menu.sidebar.collapse' : 'menu.sidebar.expand',
                  )}
                  className={cn({
                    'opacity-0 focus-visible:opacity-100': !isExpanded,
                  })}
                />
              </Tooltip>
            </div>

            {session && (
              <nav aria-label={tShared('menu.navigation')}>
                <ul className="flex flex-col gap-1">
                  {renderItems(!isExpanded, 'desktop')}
                </ul>
              </nav>
            )}
          </div>

          {isExpanded && process.env.NEXT_PUBLIC_BUILD_VERSION && (
            <div className="w-full px-4 flex justify-between items-center text-sm mb-2">
              <span className="flex whitespace-nowrap text-foreground dark:text-muted">
                {`v${process.env.NEXT_PUBLIC_BUILD_VERSION}`}
              </span>
            </div>
          )}
        </aside>
        {!isExpanded && (
          <div
            data-testid="collapsed-navigation-border"
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 right-0 z-50 border-r border-default"
          />
        )}
      </div>

      {isMobileOpen && (
        <FocusScope contain restoreFocus autoFocus>
          <nav
            id="mobile-nav-overlay"
            role="dialog"
            aria-modal="true"
            aria-label={tShared('menu.navigation')}
            onKeyDown={(event) => {
              if (event.key === 'Escape') onMobileClose();
            }}
            className="fixed inset-x-0 bottom-0 top-16 z-30 overflow-y-auto bg-background/70 px-6 pt-2 backdrop-blur-xl backdrop-saturate-150 md:hidden"
          >
            <ul className="flex flex-col gap-1">
              {renderItems(false, 'mobile', onMobileClose)}
            </ul>
          </nav>
        </FocusScope>
      )}
    </>
  );
};
