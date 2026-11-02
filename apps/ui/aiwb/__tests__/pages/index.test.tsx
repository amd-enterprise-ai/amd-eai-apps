// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import {
  fetchProjectCpuUsage,
  fetchProjectQuota,
  fetchProjectSystemMemory,
  fetchProjectWorkloadMetrics,
  fetchProjectWorkloadStats,
  fetchProjectGPUDeviceUtilization,
  fetchProjectGPUMemoryUtilization,
} from '@/lib/app/projects';
import {
  resolveAIMServiceDisplay,
  type AIMServiceDisplayInfo,
} from '@/lib/app/aims';
import {
  getInferenceModel,
  listAllInferenceDeployments,
} from '@/lib/app/inference';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import type { GetServerSidePropsContext } from 'next';
import { serverSideTranslations } from 'next-i18next/serverSideTranslations';

import wrapper from '@/__tests__/ProviderWrapper';
import '@testing-library/jest-dom';
import type { ComponentProps } from 'react';
import { Mock, vi } from 'vitest';
import ProjectDashboardPage, { getServerSideProps } from '@/pages/[project]';

const mockServerSideTranslations = vi.mocked(serverSideTranslations);

const mockInvalidateQueries = vi.fn();
const mockResetQueries = vi.fn();

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: () => ({
      invalidateQueries: mockInvalidateQueries,
      resetQueries: mockResetQueries,
      getQueryCache: () => ({
        findAll: () => [],
        subscribe: (_onStoreChange: () => void) => () => {},
      }),
    }),
  };
});

vi.mock('next-i18next/serverSideTranslations', () => ({
  serverSideTranslations: vi.fn().mockResolvedValue({}),
}));

vi.mock('@/lib/app/projects', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    fetchProjectWorkloadMetrics: vi.fn(),
    fetchProjectWorkloadStats: vi.fn(),
    fetchProjectGPUDeviceUtilization: vi.fn(),
    fetchProjectGPUMemoryUtilization: vi.fn(),
    fetchProjectCpuUsage: vi.fn(),
    fetchProjectSystemMemory: vi.fn(),
    fetchProjectQuota: vi.fn(),
  };
});

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: 'test-project-123',
    setActiveProject: vi.fn(),
  }),
}));

vi.mock('@/lib/app/aims', async (importOriginal) => ({
  ...(await importOriginal()),
  resolveAIMServiceDisplay: vi.fn(),
}));

vi.mock('@/lib/app/inference', () => ({
  getInferenceModel: vi.fn(),
  listAllInferenceDeployments: vi.fn(),
  deleteInferenceDeployment: vi.fn(),
}));

const mockPush = vi.fn();

vi.mock('next/router', () => ({
  useRouter: () => ({
    query: { id: '1' },
    push: mockPush,
  }),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: {
      user: {
        email: 'test@example.com',
        id: 'test-user-id',
      },
    },
    update: vi.fn(),
  }),
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('projects page', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    (fetchProjectWorkloadMetrics as Mock).mockResolvedValue({
      data: [],
      pagination: { page: 1, pageSize: 20, total: 0 },
    });
    (fetchProjectWorkloadStats as Mock).mockResolvedValue({
      namespace: 'workbench',
      total: 0,
      statusCounts: [],
    });
    (fetchProjectGPUMemoryUtilization as Mock).mockResolvedValue({
      data: [],
    });
    (fetchProjectGPUDeviceUtilization as Mock).mockResolvedValue({
      data: [],
    });
    (fetchProjectCpuUsage as Mock).mockResolvedValue({
      data: [],
    });
    (fetchProjectSystemMemory as Mock).mockResolvedValue({
      data: [],
    });
    (fetchProjectQuota as Mock).mockResolvedValue({
      isQuotaManaged: false,
      quotas: {},
    });
    (listAllInferenceDeployments as Mock).mockResolvedValue([]);
    (getInferenceModel as Mock).mockRejectedValue(
      new APIRequestError('not found', 404),
    );
    (resolveAIMServiceDisplay as Mock).mockReturnValue({
      title: '',
      canonicalName: '',
      imageVersion: '',
      name: '',
      metric: 'default',
    } satisfies AIMServiceDisplayInfo);

    mockInvalidateQueries.mockClear();
    mockResetQueries.mockClear();
  });

  const renderProjectPage = (
    props?: Partial<ComponentProps<typeof ProjectDashboardPage>>,
  ) => {
    return render(<ProjectDashboardPage {...props} />, { wrapper });
  };

  it('shows loading state initially', async () => {
    act(() => {
      renderProjectPage();
    });

    await waitFor(() => {
      expect(screen.getByText('dashboard.overview.title')).toBeInTheDocument();
    });
  });

  it('should not crash the page', async () => {
    act(() => {
      renderProjectPage();
    });

    await waitFor(() => {
      expect(screen.getByText('dashboard.overview.title')).toBeInTheDocument();
    });
  });

  it('should call fetchProjectGPUDeviceUtilization on page load', () => {
    act(() => {
      renderProjectPage();
    });

    expect(fetchProjectGPUDeviceUtilization as Mock).toHaveBeenCalled();
  });

  it('should call fetchProjectWorkloadMetrics on page load', async () => {
    act(() => {
      renderProjectPage();
    });

    await waitFor(() => {
      expect(fetchProjectWorkloadMetrics as Mock).toHaveBeenCalled();
    });
  });

  it('should call fetchProjectWorkloadStats on page load', () => {
    act(() => {
      renderProjectPage();
    });

    expect(fetchProjectWorkloadStats as Mock).toHaveBeenCalled();
  });

  it('should call fetchProjectGPUMemoryUtilization on page load', () => {
    act(() => {
      renderProjectPage();
    });

    expect(fetchProjectGPUMemoryUtilization as Mock).toHaveBeenCalled();
  });

  it('refresh button trigger refetch', async () => {
    await act(() => {
      renderProjectPage();
    });

    expect(fetchProjectGPUMemoryUtilization as Mock).toBeCalledTimes(1);
    expect(fetchProjectGPUDeviceUtilization as Mock).toBeCalledTimes(1);

    await waitFor(() => {
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument();
    });

    await act(() => {
      fireEvent.click(screen.getByText('actions.refresh.title'));
    });

    expect(fetchProjectGPUMemoryUtilization as Mock).toBeCalledTimes(2);
    expect(fetchProjectGPUDeviceUtilization as Mock).toBeCalledTimes(2);
    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      queryKey: ['project', 'test-project-123', 'workloads'],
    });
    expect(mockResetQueries).toHaveBeenCalledWith({
      queryKey: ['project', 'test-project-123', 'stats'],
    });
  });

  it('should handle time range change correctly', async () => {
    await act(() => {
      renderProjectPage();
    });

    // Verify the time selector component is rendered
    await waitFor(() => {
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument();
    });
  });

  it('should render all dashboard sections', async () => {
    act(() => {
      renderProjectPage();
    });

    // Check for overview sections
    await waitFor(() => {
      expect(screen.getByText('dashboard.overview.title')).toBeInTheDocument();
      expect(screen.getByText('dashboard.workloads.title')).toBeInTheDocument();
    });
  });
});

describe('ProjectDashboardPage getServerSideProps', () => {
  const baseContext = {
    locale: 'en',
    params: { project: 'bench-ns' },
    query: {},
    resolvedUrl: '/bench-ns',
    req: {},
    res: {},
  } as unknown as GetServerSidePropsContext;

  beforeEach(() => {
    vi.clearAllMocks();
    mockServerSideTranslations.mockResolvedValue({} as never);
  });

  it('returns props with breadcrumb when translations succeed', async () => {
    const result = await getServerSideProps(baseContext);

    expect(result).toEqual({
      props: {
        pageBreadcrumb: [
          {
            title: undefined,
            href: '/bench-ns/',
          },
        ],
      },
    });
  });

  it('redirects home when translations fail', async () => {
    mockServerSideTranslations.mockRejectedValue(new Error('i18n failed'));

    const result = await getServerSideProps(baseContext);

    expect(result).toEqual({
      redirect: { destination: '/', permanent: false },
    });
  });
});
