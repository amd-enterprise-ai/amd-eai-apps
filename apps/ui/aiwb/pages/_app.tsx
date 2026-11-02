// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SessionProvider } from 'next-auth/react';

import { appWithTranslation } from 'next-i18next';
import { ThemeProvider as NextThemesProvider } from 'next-themes';
import { AppProps } from 'next/app';
import { useRouter } from 'next/router';

import nextI18NextConfig from '../next-i18next.config.js';

import { useMemo } from 'react';

import { AppLayout } from '@amdenterpriseai/layouts';
import { SystemToastContainer } from '@amdenterpriseai/components';
import { useAirmLinkMenuItem } from '@/hooks/useAirmLinkMenuItem';
import { PageErrorHandler } from '@/components/shared/PageErrorHandler/PageErrorHandler';
import { ProjectProvider, useProject } from '@/contexts/ProjectContext';

import '@/styles/globals.css';
import { aiWorkbenchMenuItems } from '@amdenterpriseai/utils/app';
import { WithDocumentationLink } from '@amdenterpriseai/utils/app';
import {
  ProjectSelect,
  ProjectSelectPrompt,
} from '@/components/shared/ProjectSelect';

function AppContent({
  Component,
  pageProps,
}: {
  Component: AppProps['Component'] & WithDocumentationLink;
  pageProps: Record<string, unknown>;
}) {
  const router = useRouter();
  const additionalMenuItems = useAirmLinkMenuItem();
  const { apiKeysManagementEnabled } = useProject();
  const project = router.query.project as string | undefined;
  const isRootPage = !project;

  const menuItems = useMemo(
    () =>
      apiKeysManagementEnabled
        ? aiWorkbenchMenuItems
        : aiWorkbenchMenuItems.filter((item) => item.href !== '/api-keys'),
    [apiKeysManagementEnabled],
  );

  return (
    <NextThemesProvider
      disableTransitionOnChange
      attribute="class"
      defaultTheme="dark"
    >
      <SystemToastContainer />
      <AppLayout
        pageBreadcrumb={
          pageProps?.pageBreadcrumb as AppProps['pageProps']['pageBreadcrumb']
        }
        menuItems={menuItems}
        toolbarEndContent={<ProjectSelect />}
        appTitle="sections.aiWorkbench.title"
        documentationHref={Component.documentationLink}
        additionalMenuItems={additionalMenuItems}
        projectPrefix={project}
      >
        <PageErrorHandler
          projectRequired={!isRootPage}
          noActiveProjectComponent={<ProjectSelectPrompt />}
        >
          <Component {...pageProps} />
        </PageErrorHandler>
      </AppLayout>
    </NextThemesProvider>
  );
}

function App({ Component, pageProps: { session, ...pageProps } }: AppProps) {
  const queryClient = new QueryClient();

  return (
    <SessionProvider session={session} refetchInterval={10 * 60}>
      <QueryClientProvider client={queryClient}>
        <ProjectProvider>
          <AppContent Component={Component} pageProps={pageProps} />
        </ProjectProvider>
      </QueryClientProvider>
    </SessionProvider>
  );
}

export default appWithTranslation(App, nextI18NextConfig);
