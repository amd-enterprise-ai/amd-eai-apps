// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  createContext,
  useContext,
  useMemo,
  ReactNode,
  useCallback,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/router';
import { useLocalStorage } from '@amdenterpriseai/hooks';

import { getAppConfig, AppConfig } from '@/lib/app/app-config';
import { fetchProjects } from '@/lib/app/projects';
import type { ProjectsResponse } from '@/types/projects';

interface ProjectContextType {
  isStandaloneMode: boolean;
  apiKeysManagementEnabled: boolean;
  aiGatewayEnabled: boolean;
  aiGatewayUrl?: string;
  airmAppUrl?: string;
  activeProject: string | null;
  projects: ProjectsResponse['data'];
  isLoading: boolean;
  projectError: unknown | null;
  refetchProjects: () => void;
  setActiveProject: (projectId: string) => void;
  /** Returns project-prefixed path for use with router.push/replace (no locale prefix). */
  projectPath: (path: string) => string;
  /** Returns full URL with locale prefix for use with window.open or direct links. */
  projectUrl: (path: string) => string;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

interface ProjectProviderProps {
  children: ReactNode;
}

export const ProjectProvider = ({ children }: ProjectProviderProps) => {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [, setLastProject] = useLocalStorage<string | null>(
    'lastProject',
    null,
  );

  const projectFromUrl = router.query.project as string | undefined;

  const { data: appConfig } = useQuery<AppConfig>({
    queryKey: ['appConfig'],
    queryFn: getAppConfig,
    initialData: {
      isStandaloneMode: false,
      defaultNamespace: null,
      apiKeysManagementEnabled: true,
      aiGatewayEnabled: true,
    },
  });

  const {
    isStandaloneMode,
    defaultNamespace,
    apiKeysManagementEnabled = true,
    aiGatewayEnabled = true,
    aiGatewayUrl,
  } = appConfig;

  const { data, isLoading, error, refetch } = useQuery<ProjectsResponse>({
    queryKey: ['user-projects'],
    queryFn: fetchProjects,
    refetchInterval: 10000,
    enabled: !isStandaloneMode,
  });

  const projects: ProjectsResponse['data'] = useMemo(() => {
    if (isStandaloneMode && defaultNamespace) {
      return [{ id: defaultNamespace, name: defaultNamespace }];
    }
    return data?.data || [];
  }, [isStandaloneMode, defaultNamespace, data?.data]);

  const activeProject = useMemo((): string | null => {
    if (isStandaloneMode) {
      return defaultNamespace;
    }
    if (!projectFromUrl) {
      return null;
    }
    const isValid = projects.some((p) => p.id === projectFromUrl);
    return isValid ? projectFromUrl : null;
  }, [isStandaloneMode, defaultNamespace, projectFromUrl, projects]);

  const localePrefix = useMemo(() => {
    if (router.locale && router.locale !== router.defaultLocale) {
      return `/${router.locale}`;
    }
    return '';
  }, [router.locale, router.defaultLocale]);

  const projectPath = useCallback(
    (path: string): string => {
      const normalizedPath = path.startsWith('/') ? path : `/${path}`;
      if (!activeProject) {
        return normalizedPath;
      }
      return `/${activeProject}${normalizedPath}`;
    },
    [activeProject],
  );

  const projectUrl = useCallback(
    (path: string): string => {
      return `${localePrefix}${projectPath(path)}`;
    },
    [localePrefix, projectPath],
  );

  const invalidateProjectQueries = useCallback((): void => {
    queryClient.invalidateQueries({ queryKey: ['project'] });
  }, [queryClient]);

  const setActiveProject = useCallback(
    (projectId: string): void => {
      if (projectId === activeProject) return;
      setLastProject(projectId);
      invalidateProjectQueries();
      const isProjectListPage =
        router.pathname.includes('[project]') &&
        !router.pathname.includes('[id]');
      if (isProjectListPage) {
        void router.push({
          pathname: router.pathname,
          query: { ...router.query, project: projectId },
        });
      } else {
        void router.push(`/${projectId}/`);
      }
    },
    [activeProject, router, setLastProject, invalidateProjectQueries],
  );

  const refetchProjects = useCallback((): void => {
    void refetch();
  }, [refetch]);

  const value: ProjectContextType = useMemo(
    () => ({
      isStandaloneMode,
      apiKeysManagementEnabled,
      aiGatewayEnabled,
      aiGatewayUrl,
      airmAppUrl: appConfig.airmAppUrl,
      activeProject,
      projects,
      isLoading,
      projectError: error ?? null,
      refetchProjects,
      setActiveProject,
      projectPath,
      projectUrl,
    }),
    [
      isStandaloneMode,
      apiKeysManagementEnabled,
      aiGatewayEnabled,
      aiGatewayUrl,
      appConfig.airmAppUrl,
      activeProject,
      projects,
      isLoading,
      error,
      refetchProjects,
      setActiveProject,
      projectPath,
      projectUrl,
    ],
  );

  return (
    <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
  );
};

export const useProject = () => {
  const context = useContext(ProjectContext);
  if (context === undefined) {
    throw new Error('useProject must be used within a ProjectProvider');
  }
  return context;
};
