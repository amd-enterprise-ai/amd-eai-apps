// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, waitFor } from '@testing-library/react';
import { AppProps } from 'next/app';
import { Session } from 'next-auth';
import App from '@/pages/_app';
import { PageBreadcrumbs } from '@amdenterpriseai/types';
import '@testing-library/jest-dom';
import { CollectionElement } from '@react-types/shared';

// Mock next-i18next
vi.mock('next-i18next', () => ({
  appWithTranslation: (component: any) => component,
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock TanStack Query
vi.mock('@tanstack/react-query', () => ({
  QueryClient: vi.fn().mockImplementation(() => ({
    setQueryData: vi.fn(),
    getQueryData: vi.fn(),
    invalidateQueries: vi.fn(),
    clear: vi.fn(),
  })),
  QueryClientProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="query-client-provider">{children}</div>
  ),
}));

// Mock next-auth
vi.mock('next-auth/react', () => ({
  SessionProvider: ({
    children,
    session,
    refetchInterval,
  }: {
    children: React.ReactNode;
    session: Session | null;
    refetchInterval?: number;
  }) => (
    <div
      data-testid="session-provider"
      data-session={session ? 'authenticated' : 'unauthenticated'}
      data-refetch-interval={refetchInterval}
    >
      {children}
    </div>
  ),
}));

// Mock next-themes
vi.mock('next-themes', () => ({
  ThemeProvider: ({
    children,
    attribute,
    defaultTheme,
    disableTransitionOnChange,
  }: {
    children: React.ReactNode;
    attribute?: string;
    defaultTheme?: string;
    disableTransitionOnChange?: boolean;
  }) => (
    <div
      data-testid="theme-provider"
      data-attribute={attribute}
      data-default-theme={defaultTheme}
      data-disable-transition={disableTransitionOnChange}
    >
      {children}
    </div>
  ),
}));

// Mock layouts
vi.mock('@amdenterpriseai/layouts', () => ({
  AppLayout: ({
    children,
    pageBreadcrumb,
    toolbarEndContent,
    additionalMenuItems,
  }: {
    children: React.ReactNode;
    pageBreadcrumb?: PageBreadcrumbs;
    toolbarEndContent?: React.ReactNode;
    additionalMenuItems?: CollectionElement<object>;
  }) => {
    return (
      <div
        data-testid="app-layout"
        data-breadcrumb-count={pageBreadcrumb?.length || 0}
        data-has-toolbar-content={!!toolbarEndContent}
        data-has-additional-menu-items={!!additionalMenuItems}
      >
        {additionalMenuItems}
        {children}
      </div>
    );
  },
}));

vi.mock('@/components/shared/PageErrorHandler/PageErrorHandler', () => ({
  PageErrorHandler: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="page-error-handler">{children}</div>
  ),
}));

vi.mock('@/hooks/useAirmLinkMenuItem', () => ({
  useAirmLinkMenuItem: () => <div data-testid="airm-link-menu-item" />,
}));

vi.mock('@amdenterpriseai/components', () => ({
  SystemToastContainer: () => <div data-testid="system-toast-container" />,
}));

const defaultUseProjectReturn = {
  isStandaloneMode: false,
  airmAppUrl: undefined as string | undefined,
  activeProject: 'project1',
  projects: [{ id: 'project1', name: 'Project 1' }],
  isLoading: false,
  isInitialized: true,
  projectError: null,
  refetchProjects: vi.fn(),
  setActiveProject: vi.fn(),
};

const mockUseProject = vi.fn(() => defaultUseProjectReturn);

vi.mock('@/contexts/ProjectContext', () => ({
  ProjectProvider: ({
    children,
    standaloneNamespace,
  }: {
    children: React.ReactNode;
    standaloneNamespace?: string | null;
  }) => (
    <div
      data-testid="project-provider"
      data-standalone-namespace={standaloneNamespace ?? undefined}
    >
      {children}
    </div>
  ),
  useProject: () => mockUseProject(),
}));

const { appConfigMock } = vi.hoisted(() => ({
  appConfigMock: {
    getAppConfig: (opts?: {
      appConfig?: {
        isStandaloneMode: boolean;
        defaultNamespace: string | null;
      };
    }) =>
      opts?.appConfig ?? {
        isStandaloneMode: false,
        defaultNamespace: null,
      },
  },
}));
vi.mock('@/lib/app/app-config', () => appConfigMock);

// Test component that accepts props
const TestComponent = ({
  testProp,
  customProp,
}: {
  testProp?: string;
  customProp?: string;
}) => (
  <div data-testid="test-component">
    <span data-testid="test-prop">{testProp}</span>
    <span data-testid="custom-prop">{customProp}</span>
  </div>
);

describe('App Component', () => {
  const baseAppProps: AppProps = {
    Component: TestComponent,
    pageProps: {
      session: null,
    },
    router: {
      route: '/',
      pathname: '/',
      query: {},
      asPath: '/',
      push: vi.fn(),
      replace: vi.fn(),
      reload: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      beforePopState: vi.fn(),
      events: {
        on: vi.fn(),
        off: vi.fn(),
        emit: vi.fn(),
      },
      isFallback: false,
      isReady: true,
      isPreview: false,
      isLocaleDomain: false,
    } as any,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseProject.mockImplementation(() => defaultUseProjectReturn);
  });

  describe('Provider Setup', () => {
    it('should render all providers in the correct hierarchy', () => {
      render(<App {...baseAppProps} />);

      // Check that all providers are rendered
      expect(screen.getByTestId('session-provider')).toBeInTheDocument();
      expect(screen.getByTestId('query-client-provider')).toBeInTheDocument();
      expect(screen.getByTestId('project-provider')).toBeInTheDocument();
      expect(screen.getByTestId('theme-provider')).toBeInTheDocument();
      expect(screen.getByTestId('app-layout')).toBeInTheDocument();
      expect(screen.getByTestId('page-error-handler')).toBeInTheDocument();
      expect(screen.getByTestId('system-toast-container')).toBeInTheDocument();
      expect(screen.getByTestId('test-component')).toBeInTheDocument();
    });

    it('should configure SessionProvider with correct props', () => {
      const mockSession: Session = {
        user: {
          id: 'user-123',
          name: 'Test User',
          email: 'test@example.com',
          roles: ['Platform Administrator'],
        },
        expires: '2025-12-31',
        error: 'RefreshAccessTokenError',
      };

      const propsWithSession = {
        ...baseAppProps,
        pageProps: { session: mockSession },
      };

      render(<App {...propsWithSession} />);

      const sessionProvider = screen.getByTestId('session-provider');
      expect(sessionProvider).toHaveAttribute('data-session', 'authenticated');
      expect(sessionProvider).toHaveAttribute('data-refetch-interval', '600'); // 10 * 60
    });

    it('should configure SessionProvider for unauthenticated state', () => {
      render(<App {...baseAppProps} />);

      const sessionProvider = screen.getByTestId('session-provider');
      expect(sessionProvider).toHaveAttribute(
        'data-session',
        'unauthenticated',
      );
    });

    it('should configure ThemeProvider with correct props', () => {
      render(<App {...baseAppProps} />);

      const themeProvider = screen.getByTestId('theme-provider');
      expect(themeProvider).toHaveAttribute('data-attribute', 'class');
      expect(themeProvider).toHaveAttribute('data-default-theme', 'dark');
      expect(themeProvider).toHaveAttribute('data-disable-transition', 'true');
    });
  });

  describe('Session Handling', () => {
    it('should handle undefined session', () => {
      const propsWithUndefinedSession = {
        ...baseAppProps,
        pageProps: { session: undefined },
      };

      render(<App {...propsWithUndefinedSession} />);

      expect(screen.getByTestId('session-provider')).toHaveAttribute(
        'data-session',
        'unauthenticated',
      );
      expect(screen.getByTestId('test-component')).toBeInTheDocument();
    });

    it('should handle valid session object', () => {
      const mockSession: Session = {
        user: {
          id: 'user-456',
          name: 'John Doe',
          email: 'john@example.com',
          roles: ['Team Member'],
        },
        expires: '2025-12-31T23:59:59.999Z',
        accessToken: 'mock-access-token',
        error: 'RefreshAccessTokenError',
      };

      const propsWithSession = {
        ...baseAppProps,
        pageProps: { session: mockSession },
      };

      render(<App {...propsWithSession} />);

      expect(screen.getByTestId('session-provider')).toHaveAttribute(
        'data-session',
        'authenticated',
      );
    });
  });

  describe('Additional menu items', () => {
    it('should render AirmLinkMenuItem component', () => {
      render(<App {...baseAppProps} />);

      expect(screen.getByTestId('airm-link-menu-item')).toBeInTheDocument();
    });

    it('should pass AirmLinkMenuItem to AppLayout additionalMenuItems', () => {
      render(<App {...baseAppProps} />);

      const appLayout = screen.getByTestId('app-layout');
      expect(appLayout).toHaveAttribute(
        'data-has-additional-menu-items',
        'true',
      );
    });
  });

  describe('Breadcrumb Handling', () => {
    it('should pass breadcrumbs to AppLayout', () => {
      const mockBreadcrumbs: PageBreadcrumbs = [
        { title: 'Home', href: '/' },
        { title: 'Users', href: '/users' },
        { title: 'Profile' },
      ];

      const propsWithBreadcrumbs = {
        ...baseAppProps,
        pageProps: {
          session: null,
          pageBreadcrumb: mockBreadcrumbs,
        },
      };

      render(<App {...propsWithBreadcrumbs} />);

      const appLayout = screen.getByTestId('app-layout');
      expect(appLayout).toHaveAttribute('data-breadcrumb-count', '3');
    });
  });

  describe('Props Forwarding', () => {
    it('should forward all pageProps to Component except session and pageBreadcrumb', () => {
      const propsWithCustomData = {
        ...baseAppProps,
        pageProps: {
          session: {
            user: {
              id: 'user-789',
              name: 'Test User',
              roles: ['Platform Administrator'],
            },
            expires: '2025-12-31',
            error: 'RefreshAccessTokenError',
          } as Session,
          pageBreadcrumb: [{ title: 'Home' }],
          testProp: 'test-value',
          customProp: 'custom-value',
          anotherProp: 123,
        },
      };

      render(<App {...propsWithCustomData} />);

      expect(screen.getByTestId('test-prop')).toHaveTextContent('test-value');
      expect(screen.getByTestId('custom-prop')).toHaveTextContent(
        'custom-value',
      );
    });

    it('should not pass session or pageBreadcrumb as props to Component', () => {
      const propsWithSessionAndBreadcrumb = {
        ...baseAppProps,
        pageProps: {
          session: {
            user: {
              id: 'user-abc',
              name: 'Test User',
              roles: ['user'],
            },
            expires: '2025-12-31',
            error: 'RefreshAccessTokenError',
          } as Session,
          pageBreadcrumb: [{ title: 'Home' }],
          testProp: 'only-this-should-pass',
        },
      };

      render(<App {...propsWithSessionAndBreadcrumb} />);

      // Only testProp should be passed to the component
      expect(screen.getByTestId('test-prop')).toHaveTextContent(
        'only-this-should-pass',
      );
    });

    it('should handle pageProps with only session', () => {
      const propsWithOnlySession = {
        ...baseAppProps,
        pageProps: {
          session: {
            user: {
              id: 'user-def',
              name: 'Test User',
              roles: ['Team Member'],
            },
            expires: '2025-12-31',
            error: 'RefreshAccessTokenError',
          } as Session,
        },
      };

      render(<App {...propsWithOnlySession} />);

      // Component should render with no props
      expect(screen.getByTestId('test-component')).toBeInTheDocument();
      expect(screen.getByTestId('test-prop')).toHaveTextContent('');
      expect(screen.getByTestId('custom-prop')).toHaveTextContent('');
    });
  });

  describe('Integration', () => {
    it('should handle complex pageProps correctly', async () => {
      const complexProps = {
        ...baseAppProps,
        pageProps: {
          session: {
            user: {
              id: 'user-complex',
              name: 'Complex User',
              email: 'complex@example.com',
              roles: ['Platform Administrator'],
            },
            expires: '2025-12-31',
            error: 'RefreshAccessTokenError',
          } as Session,
          pageBreadcrumb: [
            { title: 'Dashboard', href: '/dashboard' },
            { title: 'Settings' },
          ],
          testProp: 'complex-test',
          customProp: 'complex-custom',
          metadata: { version: '1.0.0' },
          isLoading: false,
        },
      };

      render(<App {...complexProps} />);

      // Wait for all providers to render
      await waitFor(() => {
        expect(screen.getByTestId('session-provider')).toHaveAttribute(
          'data-session',
          'authenticated',
        );
        expect(screen.getByTestId('app-layout')).toHaveAttribute(
          'data-breadcrumb-count',
          '2',
        );
        expect(screen.getByTestId('test-prop')).toHaveTextContent(
          'complex-test',
        );
        expect(screen.getByTestId('custom-prop')).toHaveTextContent(
          'complex-custom',
        );
      });
    });

    it('should maintain provider order for proper context inheritance', () => {
      render(<App {...baseAppProps} />);

      const sessionProvider = screen.getByTestId('session-provider');
      const queryProvider = screen.getByTestId('query-client-provider');
      const projectProvider = screen.getByTestId('project-provider');
      const themeProvider = screen.getByTestId('theme-provider');

      // Check if providers are nested correctly by DOM structure
      expect(sessionProvider).toContainElement(queryProvider);
      expect(queryProvider).toContainElement(projectProvider);
      expect(projectProvider).toContainElement(themeProvider);
    });
  });

  describe('Error Boundaries and Edge Cases', () => {
    it('should handle invalid session gracefully', () => {
      const propsWithInvalidSession = {
        ...baseAppProps,
        pageProps: {
          session: null,
          testProp: 'should-still-work',
        },
      };

      expect(() => {
        render(<App {...propsWithInvalidSession} />);
      }).not.toThrow();

      expect(screen.getByTestId('session-provider')).toHaveAttribute(
        'data-session',
        'unauthenticated',
      );
      expect(screen.getByTestId('test-prop')).toHaveTextContent(
        'should-still-work',
      );
    });

    it('should handle missing pageProps', () => {
      const propsWithMissingPageProps = {
        ...baseAppProps,
        pageProps: {} as any,
      };

      expect(() => {
        render(<App {...propsWithMissingPageProps} />);
      }).not.toThrow();

      expect(screen.getByTestId('session-provider')).toBeInTheDocument();
      expect(screen.getByTestId('test-component')).toBeInTheDocument();
    });

    it('should include PageErrorHandler in the component tree', () => {
      render(<App {...baseAppProps} />);

      // PageErrorHandler should be in the component tree
      expect(screen.getByTestId('page-error-handler')).toBeInTheDocument();

      // And it should wrap the actual component
      const errorHandler = screen.getByTestId('page-error-handler');
      const component = screen.getByTestId('test-component');
      expect(errorHandler).toContainElement(component);
    });
  });
});
