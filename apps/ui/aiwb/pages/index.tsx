// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useEffect, useMemo } from 'react';

import type { GetServerSidePropsContext } from 'next/types';
import { useRouter } from 'next/router';

import { useLocalStorage } from '@amdenterpriseai/hooks';

import { useProject } from '@/contexts/ProjectContext';
import { getPageTranslations } from '@/lib/server/i18n';
import { ProjectSelectPrompt } from '@/components/shared/ProjectSelect';
import LoadingState from '@/components/shared/PageErrorHandler/LoadingState';

const RootPage: React.FC = () => {
  const router = useRouter();
  const { projects, isLoading, isStandaloneMode, activeProject } = useProject();
  const [lastProject] = useLocalStorage<string | null>('lastProject', null);

  const validLastProject = useMemo(
    () => lastProject && projects.some((p) => p.id === lastProject),
    [lastProject, projects],
  );

  const shouldRedirect =
    (isStandaloneMode && activeProject) || validLastProject;

  useEffect(() => {
    if (isLoading) return;
    if (isStandaloneMode && activeProject) {
      void router.replace(`/${activeProject}/`);
      return;
    }
    if (validLastProject) {
      void router.replace(`/${lastProject}/`);
    }
  }, [
    isLoading,
    isStandaloneMode,
    activeProject,
    validLastProject,
    lastProject,
    router,
  ]);

  if (isLoading || shouldRedirect) {
    return <LoadingState />;
  }
  return <ProjectSelectPrompt />;
};

export default RootPage;

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const { locale = 'en' } = context;

  const translations = await getPageTranslations(locale);

  return {
    props: {
      ...translations,
    },
  };
}
