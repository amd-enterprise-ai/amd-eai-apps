// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

import { useRouter } from 'next/router';
import { useProject } from '@/contexts/ProjectContext';

import ApiKeyDetailsPage from '@/pages/[project]/api-keys/[id]/index';

vi.mock('next/router', () => ({
  useRouter: vi.fn(),
}));

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: vi.fn(),
}));

vi.mock('@/components/features/api-keys/ApiKeyMetricsDashboard', () => ({
  default: ({
    projectId,
    apiKeyId,
    apiKeyName,
  }: {
    projectId: string;
    apiKeyId: string;
    apiKeyName: string;
  }) => (
    <div
      data-testid="api-key-metrics-dashboard"
      data-project-id={projectId}
      data-key-id={apiKeyId}
      data-key-name={apiKeyName}
    />
  ),
}));

const mockUseProject = vi.mocked(useProject);
const mockUseRouter = vi.mocked(useRouter);

const defaultRouter = {
  query: { id: 'key-1', name: 'My Key' },
  pathname: '/[project]/api-keys/[id]',
  push: vi.fn(),
  replace: vi.fn(),
  asPath: '/project-1/api-keys/key-1',
};

const defaultProjectContext = {
  isStandaloneMode: false,
  apiKeysManagementEnabled: true,
  aiGatewayEnabled: true,
  airmAppUrl: undefined,
  activeProject: 'project-1',
  projects: [{ id: 'project-1', name: 'Project 1' }],
  isLoading: false,
  projectError: null,
  refetchProjects: vi.fn(),
  setActiveProject: vi.fn(),
  projectPath: (path: string) =>
    `/project-1${path.startsWith('/') ? path : `/${path}`}`,
  projectUrl: (path: string) =>
    `/project-1${path.startsWith('/') ? path : `/${path}`}`,
};

describe('ApiKeyDetailsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseRouter.mockReturnValue(defaultRouter as any);
    mockUseProject.mockReturnValue(defaultProjectContext);
  });

  it('renders the metrics dashboard when aiGatewayEnabled is true', () => {
    render(<ApiKeyDetailsPage />);

    const dashboard = screen.getByTestId('api-key-metrics-dashboard');
    expect(dashboard).toBeInTheDocument();
    expect(dashboard).toHaveAttribute('data-project-id', 'project-1');
    expect(dashboard).toHaveAttribute('data-key-id', 'key-1');
    expect(dashboard).toHaveAttribute('data-key-name', 'My Key');
  });

  it('renders nothing when aiGatewayEnabled is false', () => {
    mockUseProject.mockReturnValue({
      ...defaultProjectContext,
      aiGatewayEnabled: false,
    });

    const { container } = render(<ApiKeyDetailsPage />);

    expect(
      screen.queryByTestId('api-key-metrics-dashboard'),
    ).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when activeProject is null', () => {
    mockUseProject.mockReturnValue({
      ...defaultProjectContext,
      activeProject: null,
    });

    const { container } = render(<ApiKeyDetailsPage />);

    expect(
      screen.queryByTestId('api-key-metrics-dashboard'),
    ).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when apiKeyId is missing from query', () => {
    mockUseRouter.mockReturnValue({
      ...defaultRouter,
      query: {},
    } as any);

    const { container } = render(<ApiKeyDetailsPage />);

    expect(
      screen.queryByTestId('api-key-metrics-dashboard'),
    ).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });
});
