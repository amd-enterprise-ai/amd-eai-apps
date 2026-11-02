// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';

import Head from 'next/head';
import { CollectionElement } from '@react-types/shared';

import { PageBreadcrumbs, SidebarItem } from '@amdenterpriseai/types';
import { useOverlayState } from '@amdenterpriseai/hooks';

import { AppBar, Navigation } from '@amdenterpriseai/components';

interface Props {
  children: React.ReactNode;
  pageBreadcrumb?: PageBreadcrumbs;
  appTitle: string;
  menuItems: SidebarItem[];
  toolbarEndContent?: React.ReactNode;
  additionalMenuItems?: CollectionElement<object>;
  documentationHref?: string;
  projectPrefix?: string;
}

export const AppLayout = ({
  pageBreadcrumb,
  children,
  appTitle,
  menuItems,
  toolbarEndContent,
  additionalMenuItems,
  documentationHref,
  projectPrefix,
}: Props) => {
  const { isOpen, onClose, onOpenChange } = useOverlayState();

  return (
    <>
      <Head>
        <title>AMD Enterprise AI</title>
        <meta name="description" content="AMD Enterprise AI" />
        <meta
          name="viewport"
          content="height=device-height, width=device-width, initial-scale=1, user-scalable=no"
        />
        <link rel="icon" type="image/vnd.microsoft.icon" href="/favicon.ico" />
      </Head>
      <div className="flex overflow-hidden bg-background">
        <Navigation
          appTitle={appTitle}
          menuItems={menuItems}
          projectPrefix={projectPrefix}
          isMobileOpen={isOpen}
          onMobileClose={onClose}
        />
        <main className="flex flex-col w-full overflow-x-hidden h-screen">
          <AppBar
            pageBreadcrumb={pageBreadcrumb}
            endContent={toolbarEndContent}
            additionalMenuItems={additionalMenuItems}
            documentationHref={documentationHref}
            isMobileMenuOpen={isOpen}
            onMobileMenuOpenChange={onOpenChange}
          />
          <div className="flex-1 md:mb-0 lg:pb-0 max-h-screen overflow-y-auto h-full px-4 md:px-6 lg:px-8">
            {children}
          </div>
        </main>
      </div>
    </>
  );
};

export default AppLayout;
