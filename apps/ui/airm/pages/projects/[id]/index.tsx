// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  ActionButton,
  Alert,
  ChartTimeSelector,
  ConfirmationModal,
  DropdownItem,
  DropdownMenu,
  Dropdown,
  DropdownTrigger,
} from '@amdenterpriseai/components';
import {
  useLastQueryUpdated,
  useOverlayState,
  useSystemToast,
} from '@amdenterpriseai/hooks';
import {
  IconChevronDown,
  IconExternalLink,
  IconSettings,
  IconTrash,
} from '@tabler/icons-react';
import {
  useIsFetching,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';

import { getServerSession } from 'next-auth';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import { useAccessControl } from '@/hooks/useAccessControl';
import { getPageTranslations } from '@/utils/i18n';
import {
  deleteProject as deleteProjectAPI,
  fetchProjectAverageGPUIdleTime,
  fetchProjectAverageWaitTime,
  fetchProjectGPUDeviceUtilization,
  fetchProjectGPUMemoryUtilization,
  fetchProjectWorkloadsStatuses,
} from '@/services/app';
import { getProject } from '@/services/server';

import { getProjectEditUrl } from '@/utils/projects';
import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';
import {
  DOCS_RESOURCE_MANAGER_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { isHttpUrl, stripTrailingSlashes } from '@amdenterpriseai/utils/app';
import { authOptions } from '@amdenterpriseai/utils/server';

import { TimeRangePeriod } from '@amdenterpriseai/types';
import {
  MetricScalarResponse,
  TimeRange,
  TimeSeriesAllocationData,
  TimeSeriesResponse,
} from '@amdenterpriseai/types';
import { WorkloadStatusStatsResponse } from '@/types/metrics';
import { ProjectWithMembers } from '@/types/projects';

import {
  AverageGPUIdleTimeCard,
  AverageWaitTimeCard,
  GPUDeviceUsageCard,
  GPUMemoryUsageCard,
  ProjectWorkloadsStatsCard,
  ProjectWorkloadsTable,
  QuotaUtilizationCard,
} from '@/components/features/projects';

const PROJECT_DASHBOARD_METRICS_QUERY_PREFIX = ['project', 'metrics'] as const;

const GPU_MEMORY_UTILIZATION_NUMERATOR_LABEL = 'utilizedGpuVram';
const GPU_MEMORY_UTILIZATION_DENOMINATOR_LABEL = 'allocatedGpuVram';
const GPU_DEVICE_UTILIZATION_NUMERATOR_LABEL = 'utilizedGpus';
const GPU_DEVICE_UTILIZATION_DENOMINATOR_LABEL = 'allocatedGpus';

interface Props {
  project: ProjectWithMembers;
}

const ProjectDashboardPage: React.FC<Props> & WithDocumentationLink = ({
  project,
}) => {
  const { t } = useTranslation('projects');
  const router = useRouter();
  const { id } = router.query;
  const { toast } = useSystemToast();
  const { isAdministrator } = useAccessControl();
  const queryClient = useQueryClient();
  const [timeRange, setTimeRange] = useState<TimeRange>(
    getCurrentTimeRange(TimeRangePeriod['1H']),
  );
  const currentTimePeriod = useRef<TimeRangePeriod>(TimeRangePeriod['1H']);
  const {
    isOpen: isDeleteModalOpen,
    onOpen: onDeleteModalOpen,
    onOpenChange: onDeleteModalOpenChange,
  } = useOverlayState();
  const { mutate: deleteProject, isPending: isDeletePending } = useMutation({
    mutationFn: deleteProjectAPI,
    onSuccess: () => {
      onDeleteModalOpenChange();
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      toast.success(t('settings.delete.notification.success'));
      router.push('/projects');
    },
    onError: (error) => {
      onDeleteModalOpenChange();
      toast.error(
        t('settings.delete.notification.error'),
        error as APIRequestError,
      );
    },
  });

  const {
    data: projectWorkloadsStatuses,
    isLoading: isProjectWorkloadsStatusesLoading,
  } = useQuery<WorkloadStatusStatsResponse>({
    queryKey: [...PROJECT_DASHBOARD_METRICS_QUERY_PREFIX, 'statuses', id],
    queryFn: () => fetchProjectWorkloadsStatuses(id as string),
  });

  const {
    data: projectGPUMemoryUtilization,
    isLoading: isProjectGPUMemoryUtilizationLoading,
  } = useQuery<TimeSeriesResponse>({
    queryKey: [
      ...PROJECT_DASHBOARD_METRICS_QUERY_PREFIX,
      'gpu-memory-utilization',
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () => {
      return fetchProjectGPUMemoryUtilization(
        id as string,
        timeRange.start,
        timeRange.end,
      );
    },
  });

  const {
    data: projectGPUDeviceUtilization,
    isLoading: isProjectGPUDeviceUtilizationLoading,
  } = useQuery<TimeSeriesResponse>({
    queryKey: [
      ...PROJECT_DASHBOARD_METRICS_QUERY_PREFIX,
      'gpu-device-utilization',
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () => {
      return fetchProjectGPUDeviceUtilization(
        id as string,
        timeRange.start,
        timeRange.end,
      );
    },
  });

  const {
    data: projectAverageWaitTime,
    isLoading: isProjectAverageWaitTimeLoading,
  } = useQuery<MetricScalarResponse>({
    queryKey: [
      ...PROJECT_DASHBOARD_METRICS_QUERY_PREFIX,
      'average-wait-time',
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () => {
      return fetchProjectAverageWaitTime(
        id as string,
        timeRange.start,
        timeRange.end,
      );
    },
  });

  const {
    data: projectAverageGPUIdleTime,
    isLoading: isProjectAverageGPUIdleTimeLoading,
  } = useQuery<MetricScalarResponse>({
    queryKey: [
      ...PROJECT_DASHBOARD_METRICS_QUERY_PREFIX,
      'gpu-idle-time',
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () => {
      return fetchProjectAverageGPUIdleTime(
        id as string,
        timeRange.start,
        timeRange.end,
      );
    },
  });

  const projectGPUMemoryUtilizationChartData: TimeSeriesAllocationData =
    useMemo(() => {
      if (!projectGPUMemoryUtilization?.data)
        return { numerator: [], denominator: [] };
      const utilized = projectGPUMemoryUtilization.data.find(
        (s) => s.metadata?.label === GPU_MEMORY_UTILIZATION_NUMERATOR_LABEL,
      );
      const allocated = projectGPUMemoryUtilization.data.find(
        (s) => s.metadata?.label === GPU_MEMORY_UTILIZATION_DENOMINATOR_LABEL,
      );
      return {
        numerator: utilized?.values ?? [],
        denominator: allocated?.values ?? [],
      };
    }, [projectGPUMemoryUtilization]);

  const projectGPUDeviceUtilizationChartData: TimeSeriesAllocationData =
    useMemo(() => {
      if (!projectGPUDeviceUtilization?.data)
        return { numerator: [], denominator: [] };
      const utilized = projectGPUDeviceUtilization.data.find(
        (s) => s.metadata?.label === GPU_DEVICE_UTILIZATION_NUMERATOR_LABEL,
      );
      const allocated = projectGPUDeviceUtilization.data.find(
        (s) => s.metadata?.label === GPU_DEVICE_UTILIZATION_DENOMINATOR_LABEL,
      );
      return {
        numerator: utilized?.values ?? [],
        denominator: allocated?.values ?? [],
      };
    }, [projectGPUDeviceUtilization]);

  const handleTimeBoundChange = useCallback(
    (timePeriod: TimeRangePeriod, timeRange: TimeRange) => {
      currentTimePeriod.current = timePeriod as TimeRangePeriod;
      setTimeRange(timeRange);
    },
    [setTimeRange, currentTimePeriod],
  );

  const handleChartsRefresh = useCallback(() => {
    setTimeRange(getCurrentTimeRange(currentTimePeriod.current));
  }, []);

  const isFetchingMetrics =
    useIsFetching({
      queryKey: PROJECT_DASHBOARD_METRICS_QUERY_PREFIX,
    }) > 0;

  const lastUpdated = useLastQueryUpdated(
    PROJECT_DASHBOARD_METRICS_QUERY_PREFIX,
  );

  return (
    <div className="flex flex-col gap-8 mt-8">
      <div className="flex flex-col justify-center">
        <div className="mb-8 flex items-center justify-between">
          <h3>{t('dashboard.overview.title')}</h3>
          <div className="flex items-center gap-3">
            <ChartTimeSelector
              onTimeRangeChange={handleTimeBoundChange}
              initialTimePeriod={TimeRangePeriod['1H']}
              translationPrefix="timeRange"
              onChartsRefresh={handleChartsRefresh}
              isFetching={isFetchingMetrics}
              lastFetchedTimestamp={lastUpdated}
            />
            <Dropdown>
              <DropdownTrigger>
                <ActionButton
                  aria-label={t('dashboard.action.label') || ''}
                  endContent={<IconChevronDown size={16} />}
                >
                  {t('dashboard.action.label')}
                </ActionButton>
              </DropdownTrigger>
              <DropdownMenu
                aria-label={t('dashboard.action.label') || ''}
                disabledKeys={[
                  ...(!project.cluster?.workbenchBaseUrl ||
                  !isHttpUrl(project.cluster.workbenchBaseUrl)
                    ? ['viewInAiwb']
                    : []),
                  ...(!isAdministrator ? ['delete'] : []),
                ]}
              >
                {!isAdministrator ? (
                  <DropdownItem
                    key="teamMemberAlert"
                    className="pointer-events-none"
                  >
                    <Alert
                      status="warning"
                      isTight
                      title={t('dashboard.action.teamMemberAlert.title')}
                      hideIcon
                      className="w-[240px]"
                      description={t(
                        'dashboard.action.teamMemberAlert.description',
                      )}
                    />
                  </DropdownItem>
                ) : null}
                <DropdownItem
                  key="editSettings"
                  onPress={() => router.push(getProjectEditUrl(id as string))}
                  startContent={<IconSettings />}
                >
                  {t('dashboard.action.editSettings')}
                </DropdownItem>
                <DropdownItem
                  key="viewInAiwb"
                  onPress={() => {
                    window.open(
                      `${stripTrailingSlashes(project.cluster!.workbenchBaseUrl!)}/${project.name}`,
                      '_blank',
                      'noopener,noreferrer',
                    );
                  }}
                  showDivider
                  startContent={<IconExternalLink />}
                >
                  {t('dashboard.action.viewInAiwb')}
                </DropdownItem>
                <DropdownItem
                  key="delete"
                  variant="danger"
                  onPress={onDeleteModalOpen}
                  startContent={<IconTrash />}
                >
                  {t('dashboard.action.delete')}
                </DropdownItem>
              </DropdownMenu>
            </Dropdown>
          </div>
        </div>
        <div className="flex justify-center grow">
          <div className="grid w-full max-w-[1800px] gap-4 grid-cols-1 md:grid-cols-3">
            <div className="md:row-span-2 flex justify-end">
              <ProjectWorkloadsStatsCard
                isLoading={isProjectWorkloadsStatusesLoading}
                projectName={project.name}
                totalWorkloads={projectWorkloadsStatuses?.totalWorkloads ?? 0}
                data={projectWorkloadsStatuses?.statusCounts ?? []}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:col-span-2">
              <AverageWaitTimeCard
                data={projectAverageWaitTime}
                isLoading={isProjectAverageWaitTimeLoading}
              />
              <QuotaUtilizationCard
                data={projectGPUDeviceUtilizationChartData}
                isLoading={isProjectGPUDeviceUtilizationLoading}
              />
              <AverageGPUIdleTimeCard
                data={projectAverageGPUIdleTime}
                isLoading={isProjectAverageGPUIdleTimeLoading}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:col-span-2">
              <GPUDeviceUsageCard
                data={projectGPUDeviceUtilizationChartData}
                isLoading={isProjectGPUDeviceUtilizationLoading}
              />
              <GPUMemoryUsageCard
                data={projectGPUMemoryUtilizationChartData}
                isLoading={isProjectGPUMemoryUtilizationLoading}
              />
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-8">
        <h3>{t('dashboard.workloads.title')}</h3>
        <ProjectWorkloadsTable projectId={id as string} />
      </div>
      <ConfirmationModal
        confirmationButtonColor="danger"
        description={t('settings.delete.confirmation.description', {
          project: project.name,
        })}
        title={t('settings.delete.confirmation.title')}
        isOpen={isDeleteModalOpen}
        loading={isDeletePending}
        onConfirm={() => deleteProject(project.id)}
        onClose={onDeleteModalOpenChange}
      />
    </div>
  );
};

ProjectDashboardPage.documentationLink = `${DOCS_RESOURCE_MANAGER_BASE}/projects/project-dashboard.html`;

export default ProjectDashboardPage;

export async function getServerSideProps(context: any) {
  const { locale } = context;

  const session = await getServerSession(context.req, context.res, authOptions);

  try {
    const project = await getProject(
      context.params.id,
      session?.accessToken as string,
    );

    const translations = await getPageTranslations(locale, [
      'projects',
      'users',
      'workloads',
    ]);

    const breadcrumb = [
      {
        title:
          translations._nextI18Next?.initialI18nStore[locale]?.projects?.title,
        href: '/projects',
      },
      {
        title: `${project.name}`,
        href: `/projects/${project.id}`,
      },
    ];

    return {
      props: {
        ...translations,
        project,
        pageBreadcrumb: breadcrumb,
      },
    };
  } catch (error) {
    console.error('Project not found: ' + error);
    return {
      redirect: {
        destination: '/',
        permanent: false,
      },
    };
  }
}
