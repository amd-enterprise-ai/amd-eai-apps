// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';

import {
  installPackageTestJsdom,
  resetActiveProjectLocalStorage,
} from '@/../shared/utils/__tests__/vitestJsdomSetup';
import { withMockAmdenterpriseaiButtonStubs } from '@/../shared/utils/__tests__/mockAmdenterpriseaiButtonStubs';

// jsdom returns 0 for percent-based width/height, causing recharts to render
// nothing. This shim resolves percent-sized ResponsiveContainer to fixed pixel
// dimensions so charts render and can be asserted on in tests.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  const React = await vi.importActual<typeof import('react')>('react');

  return {
    ...actual,
    ResponsiveContainer: ({
      children,
      width = '100%',
      height = '100%',
    }: {
      children?: ReactNode;
      width?: number | string;
      height?: number | string;
    }) => {
      const resolvedWidth = typeof width === 'number' ? width : 800;
      const resolvedHeight = typeof height === 'number' ? height : 240;
      const chartChild = React.isValidElement(children)
        ? React.cloneElement(
            children as ReactElement<Record<string, unknown>>,
            {
              width: resolvedWidth,
              height: resolvedHeight,
            },
          )
        : children;

      return React.createElement(
        'div',
        {
          'data-testid': 'recharts-responsive-container',
          style: { width: resolvedWidth, height: resolvedHeight },
        },
        chartChild,
      );
    },
  };
});

installPackageTestJsdom();

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return withMockAmdenterpriseaiButtonStubs(actual);
});

configure({ asyncUtilTimeout: 15_000 });

Object.defineProperty(window, 'scrollTo', {
  value: vi.fn(),
  writable: true,
});

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en',
      changeLanguage: vi.fn(),
    },
  }),
  Trans: ({
    children,
    i18nKey,
  }: {
    children?: React.ReactNode;
    i18nKey?: string;
  }) => children ?? i18nKey ?? null,
  I18nextProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en',
      changeLanguage: vi.fn(),
    },
  }),
  Trans: ({
    children,
    i18nKey,
  }: {
    children?: React.ReactNode;
    i18nKey?: string;
  }) => children ?? i18nKey ?? null,
  appWithTranslation: (Component: React.ComponentType) => Component,
}));

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({
    isStandaloneMode: false,
    apiKeysManagementEnabled: true,
    aiGatewayEnabled: true,
    airmAppUrl: undefined,
    activeProject: 'project1',
    projects: [{ id: 'project1', name: 'Project 1' }],
    isLoading: false,
    projectError: null,
    refetchProjects: vi.fn(),
    setActiveProject: vi.fn(),
    projectPath: (path: string) =>
      `/project1${path.startsWith('/') ? path : `/${path}`}`,
    projectUrl: (path: string) =>
      `/project1${path.startsWith('/') ? path : `/${path}`}`,
  }),
  ProjectProvider: ({ children }: { children: React.ReactNode }) => children,
}));

beforeEach(() => {
  resetActiveProjectLocalStorage();
});

afterEach(() => {
  cleanup();
});

vi.mock('next/router', () => ({
  useRouter: () => ({
    locale: 'en',
    pathname: '/',
    query: {},
    asPath: '/',
    push: vi.fn(),
    replace: vi.fn(),
    reload: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
    beforePopState: vi.fn(),
    events: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
    isFallback: false,
    isLocaleDomain: false,
    isReady: true,
  }),
}));
