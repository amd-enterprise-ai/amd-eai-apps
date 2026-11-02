// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionButton,
  Button,
  Card,
  CardBody,
  CardHeader,
  ChipDisplay,
  DateDisplay,
  CopySnippet,
  NoDataDisplay,
  Skeleton,
  StatusDisplay,
} from '@amdenterpriseai/components';
import {
  IconArrowLeft,
  IconExternalLink,
  IconMessage,
  IconFileText,
  IconTrash,
  IconInfoCircle,
  IconServer,
  IconCalendar,
  IconDatabase,
  IconWorld,
  IconLink,
} from '@tabler/icons-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/router';
import { useState, useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';
import { getPageTranslations } from '@/lib/server/i18n';

import {
  getWorkload,
  deleteWorkspace,
  getWorkloadMetrics,
} from '@/lib/app/workloads';
import { AIM_MODEL_WORKLOAD_ID_LABEL } from '@/types/aims';
import {
  getProjectFineTunedModel,
  resolveBaseModelSource,
} from '@/lib/app/aims';
import { cancelFineTuningJob } from '@/lib/app/models';
import { getDataset } from '@/lib/app/datasets';
import { getChart } from '@/lib/app/charts';

import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';
import { getWorkloadStatusVariants } from '@/utils/workloads';
import { getWorkloadTypeVariants } from '@amdenterpriseai/utils/app';
import type { components } from '@/types/api';
import {
  DOCS_WORKBENCH_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';

import { TimeRange, TimeRangePeriod } from '@amdenterpriseai/types';

import AIMConnectModal from '@/components/features/models/AIMConnectModal';
import DeleteWorkloadModal from '@/components/features/workloads/DeleteWorkloadModal';
import WorkloadLogsModal from '@/components/features/workloads/WorkloadLogsModal';
import { displayMegabytesInGigabytes } from '@amdenterpriseai/utils/app';

import InferenceMetrics from '@/components/features/workloads/InferenceMetrics';
import { aiWorkbenchMenuItems } from '@amdenterpriseai/utils/app';
import { get } from 'lodash';
import { useProject } from '@/contexts/ProjectContext';
import LoadingState from '@/components/shared/PageErrorHandler/LoadingState';
import ErrorMessage from '@/components/shared/PageErrorHandler/ErrorMessage';

const WorkloadDetailsPage: React.FC & WithDocumentationLink = () => {
  const { t } = useTranslation(['workloads', 'common', 'models']);
  const { toast } = useSystemToast();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { id } = router.query;
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const { activeProject, projectPath, aiGatewayEnabled, aiGatewayUrl } =
    useProject();

  const [timeRange, setTimeRange] = useState<TimeRange>(
    getCurrentTimeRange(TimeRangePeriod['15M']),
  );

  const {
    data: workload,
    isLoading: isWorkloadLoading,
    isError: isWorkloadError,
    refetch: refetchWorkload,
  } = useQuery({
    queryKey: ['workload', activeProject, id],
    queryFn: () => getWorkload(id as string, activeProject!),
    refetchInterval: 30000,
    enabled: !!id && !!activeProject,
  });

  const { data: gpuDeviceUtilization } = useQuery({
    queryKey: [
      'workload',
      activeProject,
      id,
      'metrics',
      'gpu_device_utilization',
      timeRange.start?.toISOString(),
      timeRange.end?.toISOString(),
    ],
    queryFn: () =>
      getWorkloadMetrics(
        id as string,
        activeProject!,
        timeRange.start,
        timeRange.end,
        'gpu_device_utilization',
      ),
    enabled: !!id && !!activeProject,
  });

  // GPU utilization is always a timeseries metric; narrow away the scalar
  // variants of the shared metric response union.
  const gpuDeviceValues =
    gpuDeviceUtilization && Array.isArray(gpuDeviceUtilization.data)
      ? gpuDeviceUtilization.data[0]?.values
      : undefined;
  const latestGpuDeviceUtilizationValue = gpuDeviceValues?.length
    ? gpuDeviceValues[gpuDeviceValues.length - 1]?.value
    : undefined;

  const { data: gpuMemoryUtilization } = useQuery({
    queryKey: [
      'workload',
      activeProject,
      id,
      'metrics',
      'gpu_memory_utilization',
      timeRange.start?.toISOString(),
      timeRange.end?.toISOString(),
    ],
    queryFn: () =>
      getWorkloadMetrics(
        id as string,
        activeProject!,
        timeRange.start,
        timeRange.end,
        'gpu_memory_utilization',
      ),
    enabled: !!id && !!activeProject,
  });

  const gpuMemoryValues =
    gpuMemoryUtilization && Array.isArray(gpuMemoryUtilization.data)
      ? gpuMemoryUtilization.data[0]?.values
      : undefined;
  const latestGpuMemoryUtilizationValue = gpuMemoryValues?.length
    ? gpuMemoryValues[gpuMemoryValues.length - 1]?.value
    : undefined;

  const modelId = workload?.type === 'FINE_TUNING' ? workload.id : undefined;

  const { data: model, isLoading: isLoadingModel } = useQuery({
    queryKey: ['model', activeProject, modelId],
    queryFn: () => getProjectFineTunedModel(modelId!, activeProject!),
    enabled:
      !!modelId &&
      !!activeProject &&
      // For finetuning, the AIMModel CR only exists once training completes.
      // For other workload types the model exists independently of workload status.
      (workload?.type !== 'FINE_TUNING' || workload?.status === 'Complete'),
  });

  const { data: dataset, isLoading: isLoadingDataset } = useQuery({
    queryKey: ['dataset', activeProject, workload?.datasetId],
    queryFn: () => getDataset(workload!.datasetId!, activeProject!),
    enabled: !!workload?.datasetId && !!activeProject,
    retry: false,
  });

  const { data: chart, isLoading: isLoadingChart } = useQuery({
    queryKey: ['chart', activeProject, workload?.chartId],
    queryFn: () => getChart(workload!.chartId!),
    enabled: !!workload?.chartId,
  });

  const canOpenWorkspace =
    workload?.type === 'WORKSPACE' &&
    workload?.status === 'Running' &&
    workload.endpoints?.external;

  const canOpenChat =
    workload?.type === 'INFERENCE' && workload.status === 'Running';

  // The workloads detail page only surfaces rows from the workloads table.
  // AIM-service-backed inference deployments link to /aims/[id], so an
  // INFERENCE row here is a raw workload that has no capability-specific
  // delete endpoint — the inference capability DELETE expects an AIM service
  // id and would 404 on a workload-table id. MODEL_DOWNLOAD and CUSTOM are
  // in the same boat. Only FINE_TUNING and WORKSPACE have 1:1 capability
  // deletes for workload-table rows.
  const deletableTypes: components['schemas']['WorkloadType'][] = [
    'FINE_TUNING',
    'WORKSPACE',
  ];
  const canDelete =
    workload?.status !== 'Deleted' &&
    !!workload?.type &&
    deletableTypes.includes(workload.type);

  // For inference workloads, append the API endpoint path
  const isInferenceWorkload = workload?.type === 'INFERENCE';

  // When the unified Envoy AI Gateway is enabled and configured, inference goes
  // through a single endpoint (the model is selected via the OpenAI `model`
  // field), shown in place of the per-service external host.
  const gatewayEndpointUrl =
    isInferenceWorkload && aiGatewayEnabled && aiGatewayUrl
      ? `${aiGatewayUrl.replace(/\/$/, '')}/v1/chat/completions`
      : '';
  const useGateway = !!gatewayEndpointUrl;

  const hasOutputData =
    useGateway ||
    (workload?.endpoints &&
      (workload.endpoints.external || workload.endpoints.internal));

  const { mutate: deleteWorkloadMutation } = useMutation({
    mutationFn: (id: string) => {
      if (workload?.type === 'FINE_TUNING') {
        return cancelFineTuningJob(id, activeProject!);
      }
      if (workload?.type === 'WORKSPACE') {
        return deleteWorkspace(activeProject!, id);
      }
      // Generic /workloads DELETE was removed — deletion is now
      // capability-specific. INFERENCE rows on this page are raw workloads
      // (AIM services route to /aims/[id] instead), so the inference
      // capability endpoint can't delete them. MODEL_DOWNLOAD and CUSTOM
      // have no capability surface either. Delete is hidden for all three
      // (see canDelete above); this throw stays as a defensive guard.
      throw new Error(
        `No delete capability for workload type ${workload?.type}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['workload', activeProject, id],
      });
      queryClient.invalidateQueries({
        queryKey: ['namespace', activeProject, 'workloads'],
      });
      toast.success(t('list.actions.delete.notification.success'));
      router.back();
    },
    onError: () => {
      toast.error(t('list.actions.delete.notification.error'));
    },
  });

  const statusVariants = useMemo(() => getWorkloadStatusVariants(t), [t]);
  const typeVariants = useMemo(() => getWorkloadTypeVariants(t), [t]);

  const launchWorkload = (status: components['schemas']['WorkloadStatus']) => {
    const isRunning = status === 'Running';

    if (!isRunning) {
      toast.error(t('list.errors.noRunningWorkload'));
      return;
    }

    const url = workload?.endpoints?.external || '';
    window.open(url, '_blank');
  };

  const handleBack = () => {
    router.back();
  };

  const handleOpenChat = () => {
    router.push(projectPath(`/chat?workload=${workload?.id}`));
  };

  const getEndpointUrl = (baseUrl: string) => {
    return isInferenceWorkload
      ? `${baseUrl}/v1/chat/completions`
      : baseUrl || '';
  };

  return isWorkloadLoading ? (
    <LoadingState />
  ) : isWorkloadError || !workload ? (
    <ErrorMessage onRefresh={refetchWorkload} />
  ) : (
    <div className="flex flex-col space-y-6 py-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <ActionButton
            secondary
            onPress={handleBack}
            size="sm"
            icon={<IconArrowLeft size={16} />}
          />
          <div className="flex items-center space-x-3 pr-2">
            <h2>{workload.displayName || workload.name}</h2>
            <StatusDisplay
              type={workload.status}
              variants={statusVariants}
              additionalProps={{ isShowBackground: true, isTextColored: true }}
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex space-x-2">
          {canOpenWorkspace && (
            <Button
              color="primary"
              variant="flat"
              onPress={() => launchWorkload(workload.status)}
              startContent={<IconExternalLink size={16} />}
            >
              {t('list.actions.openWorkspace.label')}
            </Button>
          )}

          {canOpenChat && (
            <Button
              color="default"
              variant="flat"
              onPress={handleOpenChat}
              startContent={<IconMessage size={16} />}
            >
              {t('list.actions.chat.label')}
            </Button>
          )}

          <Button
            color="default"
            variant="flat"
            onPress={() => setIsLogsModalOpen(true)}
            startContent={<IconFileText size={16} />}
          >
            {t('list.actions.logs.label')}
          </Button>

          {canDelete && (
            <Button
              color="danger"
              variant="flat"
              onPress={() => setIsDeleteModalOpen(true)}
              startContent={<IconTrash size={16} />}
            >
              {t('list.actions.delete.label')}
            </Button>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          {t('details.sections.workloadInformation')}
        </h3>
      </div>

      <div className="columns-1 md:columns-2 xl:columns-3 gap-6 space-y-6">
        {/* Basic Information */}
        <Card className="break-inside-avoid mb-6">
          <CardHeader>
            <h4 className="flex items-center gap-2 font-semibold">
              <IconInfoCircle size={16} className="text-muted" />
              {t('details.sections.basicInformation')}
            </h4>
          </CardHeader>
          <CardBody className="space-y-4">
            <div className="flex flex-col space-y-4">
              <div className="flex items-center space-x-3">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.displayName.title')}
                  </h5>
                  <p className="text-sm">
                    {workload.displayName || workload.name}
                  </p>
                </div>
              </div>

              {workload.description && (
                <div className="flex items-center space-x-3">
                  <div>
                    <h5 className="text-sm text-foreground">
                      {t('list.headers.description.title')}
                    </h5>
                    <p className="text-sm whitespace-pre-wrap break-words">
                      {workload.description}
                    </p>
                  </div>
                </div>
              )}

              <div className="flex items-center">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.id.title')}
                  </h5>
                  <p className="font-mono text-sm">{workload.id}</p>
                </div>
              </div>

              <div className="flex items-center">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.type.title')}
                  </h5>
                  <ChipDisplay type={workload.type} variants={typeVariants} />
                </div>
              </div>

              <div className="flex items-center">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.status.title')}
                  </h5>
                  <StatusDisplay
                    type={workload.status}
                    variants={statusVariants}
                  />
                </div>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Resource Information */}
        <Card className="break-inside-avoid mb-6">
          <CardHeader>
            <h4 className="flex items-center gap-2 font-semibold">
              <IconServer size={16} className="text-muted" />
              {t('details.sections.resources')}
            </h4>
          </CardHeader>
          <CardBody className="space-y-4">
            <div className="flex flex-col space-y-4">
              <div className="flex items-center space-x-3">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.gpu.title')}
                  </h5>
                  {latestGpuDeviceUtilizationValue &&
                  latestGpuDeviceUtilizationValue > 0 ? (
                    <p className="text-sm">
                      {t('list.valueTemplates.gpu', {
                        value: latestGpuDeviceUtilizationValue,
                      })}
                    </p>
                  ) : (
                    <NoDataDisplay />
                  )}
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.vram.title')}
                  </h5>
                  {latestGpuMemoryUtilizationValue &&
                  latestGpuMemoryUtilizationValue > 0 ? (
                    <p className="text-sm">
                      {t('list.valueTemplates.vram', {
                        value: displayMegabytesInGigabytes(
                          latestGpuMemoryUtilizationValue,
                        ),
                      })}
                    </p>
                  ) : (
                    <NoDataDisplay />
                  )}
                </div>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Timeline */}
        <Card className="break-inside-avoid mb-6">
          <CardHeader>
            <h4 className="flex items-center gap-2 font-semibold">
              <IconCalendar size={16} className="text-muted" />
              {t('details.sections.timeline')}
            </h4>
          </CardHeader>
          <CardBody className="space-y-4">
            <div className="flex flex-col space-y-4">
              <div className="flex items-center space-x-3">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.createdBy.title')}
                  </h5>
                  <p className="text-sm">{workload.createdBy}</p>
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('list.headers.createdAt.title')}
                  </h5>
                  <DateDisplay date={workload.createdAt} />
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <div>
                  <h5 className="text-sm text-foreground">
                    {t('details.fields.updatedAt')}
                  </h5>
                  <DateDisplay date={workload.updatedAt} />
                </div>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Model Information */}
        {(model || (isLoadingModel && workload?.type === 'FINE_TUNING')) && (
          <Card className="break-inside-avoid mb-6">
            <CardHeader>
              <h4 className="flex items-center gap-2 font-semibold">
                <IconDatabase size={16} className="text-muted" />
                {t('list.headers.model.title')}
              </h4>
            </CardHeader>
            <CardBody className="space-y-4">
              {isLoadingModel ? (
                <div className="flex flex-col space-y-4">
                  <Skeleton className="w-full h-6 rounded-lg" />
                  <Skeleton className="w-3/4 h-6 rounded-lg" />
                  <Skeleton className="w-1/2 h-6 rounded-lg" />
                </div>
              ) : (
                <div className="flex flex-col space-y-4">
                  <div className="flex items-center space-x-3">
                    <div>
                      <h5 className="text-sm text-foreground">
                        {t('list.headers.model.name')}
                      </h5>
                      <p className="text-sm">{model!.metadata.name}</p>
                    </div>
                  </div>

                  {resolveBaseModelSource(model!)?.modelId && (
                    <div className="flex items-center space-x-3">
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('list.headers.model.canonicalName')}
                        </h5>
                        <p className="font-mono text-sm">
                          {resolveBaseModelSource(model!)?.modelId}
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center space-x-3">
                    <div>
                      <h5 className="text-sm text-foreground">
                        {t('list.headers.model.id')}
                      </h5>
                      <p className="font-mono text-sm">
                        {model!.metadata.labels?.[AIM_MODEL_WORKLOAD_ID_LABEL]}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        )}

        {/* Dataset Information */}
        {(dataset || (isLoadingDataset && workload?.datasetId)) && (
          <Card className="break-inside-avoid mb-6">
            <CardHeader>
              <h4 className="flex items-center gap-2 font-semibold">
                <IconDatabase size={16} className="text-muted" />
                {t('list.headers.dataset.title')}
              </h4>
            </CardHeader>
            <CardBody className="space-y-4">
              {isLoadingDataset ? (
                <div className="flex flex-col space-y-4">
                  <Skeleton className="w-full h-6 rounded-lg" />
                  <Skeleton className="w-3/4 h-6 rounded-lg" />
                  <Skeleton className="w-1/2 h-6 rounded-lg" />
                </div>
              ) : (
                <div className="flex flex-col space-y-4">
                  <div className="flex items-center space-x-3">
                    <div>
                      <h5 className="text-sm text-foreground">
                        {t('list.headers.dataset.name')}
                      </h5>
                      <p className="text-sm">{dataset!.name}</p>
                    </div>
                  </div>

                  {dataset!.description && (
                    <div className="flex items-center space-x-3">
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('list.headers.dataset.description')}
                        </h5>
                        <p className="text-sm">{dataset!.description}</p>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center space-x-3">
                    <div>
                      <h5 className="text-sm text-foreground">
                        {t('list.headers.dataset.id')}
                      </h5>
                      <p className="font-mono text-sm">{dataset!.id}</p>
                    </div>
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        )}

        {/* Chart Information */}
        {(chart || (isLoadingChart && workload?.chartId)) && (
          <Card className="break-inside-avoid mb-6">
            <CardHeader>
              <h4 className="flex items-center gap-2 font-semibold">
                <IconDatabase size={16} className="text-muted" />
                {t('list.headers.chart.title')}
              </h4>
            </CardHeader>
            <CardBody className="space-y-4">
              {isLoadingChart ? (
                <div className="flex flex-col space-y-4">
                  <Skeleton className="w-full h-6 rounded-lg" />
                  <Skeleton className="w-3/4 h-6 rounded-lg" />
                  <Skeleton className="w-1/2 h-6 rounded-lg" />
                </div>
              ) : (
                <div className="flex flex-col space-y-4">
                  <div className="flex items-center space-x-3">
                    <div>
                      <h5 className="text-sm text-foreground">
                        {t('list.headers.chart.name')}
                      </h5>
                      <p className="text-sm">{chart!.name}</p>
                    </div>
                  </div>

                  {chart!.description && (
                    <div className="flex items-center space-x-3">
                      <div>
                        <h5 className="text-sm text-foreground">
                          {t('list.headers.chart.description')}
                        </h5>
                        <p className="text-sm">{chart!.description}</p>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center space-x-3">
                    <div>
                      <h5 className="text-sm text-foreground">
                        {t('list.headers.chart.id')}
                      </h5>
                      <p className="font-mono text-sm">{chart!.id}</p>
                    </div>
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        )}

        {/* Output Information */}
        {hasOutputData && (
          <Card className="break-inside-avoid mb-6">
            <CardHeader>
              <div className="flex w-full items-center justify-between gap-2">
                <h4 className="flex items-center gap-2 font-semibold">
                  <IconWorld size={16} className="text-muted" />
                  {t('details.sections.output')}
                </h4>
                {isInferenceWorkload && (
                  <Button
                    data-testid="connect-to-model-button"
                    size="sm"
                    variant="light"
                    startContent={<IconLink size={14} />}
                    onPress={() => setIsConnectModalOpen(true)}
                  >
                    {t('models:aimCatalog.actions.connect.label')}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardBody className="space-y-4">
              {useGateway ? (
                <CopySnippet
                  label={t(
                    'models:aimCatalog.actions.connect.modal.inferenceUrl',
                  )}
                  value={gatewayEndpointUrl}
                  className="w-full"
                />
              ) : (
                workload.endpoints?.external && (
                  <CopySnippet
                    label={t('details.fields.externalHost')}
                    value={getEndpointUrl(workload.endpoints.external)}
                    className="w-full"
                  />
                )
              )}

              {workload.endpoints?.internal && (
                <CopySnippet
                  label={t('details.fields.internalHost')}
                  value={getEndpointUrl(workload.endpoints.internal)}
                  className="w-full"
                />
              )}
            </CardBody>
          </Card>
        )}
      </div>

      {/* Modals */}
      <DeleteWorkloadModal
        isOpen={isDeleteModalOpen}
        onOpenChange={setIsDeleteModalOpen}
        workload={workload}
        onConfirmAction={deleteWorkloadMutation}
      />

      {isLogsModalOpen && (
        <WorkloadLogsModal
          isOpen={isLogsModalOpen}
          onOpenChange={setIsLogsModalOpen}
          workload={workload}
          namespace={activeProject!}
        />
      )}

      {isConnectModalOpen && (
        <AIMConnectModal
          isOpen={isConnectModalOpen}
          onOpenChange={setIsConnectModalOpen}
          endpoints={workload?.endpoints}
          serviceId={workload?.id ?? undefined}
          // AIM catalog deployments (the only capability-tagged inference
          // surface) route to /aims/[id]; INFERENCE rows here are raw workloads
          // with no catalog tags, so chat is the only applicable capability.
          capability="chat"
          onChatRequested={(serviceId) => {
            router.push({
              pathname: projectPath('/chat'),
              query: { workload: serviceId },
            });
          }}
        />
      )}
    </div>
  );
};

export async function getServerSideProps(context: {
  locale: any;
  params: any;
  query: any;
}) {
  const { locale, params, query } = context;
  const project = params?.project as string;

  const translations = await getPageTranslations(locale, [
    'workloads',
    'models',
  ]);

  let breadcrumb: { title: string; href?: string }[] = [
    {
      title:
        translations._nextI18Next?.initialI18nStore[locale]?.workloads?.details
          ?.breadcrumb || 'Workload details',
    },
  ];

  // Determine previous route from referer query param for correct parent breadcrumb
  const refererRoutePath = query?.ref || '/';
  const prevNavItem = aiWorkbenchMenuItems.find(
    (item) => item.href === refererRoutePath,
  );

  if (prevNavItem) {
    const title = get(
      translations._nextI18Next?.initialI18nStore[locale]?.common,
      prevNavItem.stringKey,
      prevNavItem.stringKey,
    );

    breadcrumb = [
      {
        title,
        href: `/${project}${prevNavItem.href}`,
      },
      ...breadcrumb,
    ];
  }

  return {
    props: {
      ...translations,
      pageBreadcrumb: breadcrumb,
    },
  };
}

export default WorkloadDetailsPage;

WorkloadDetailsPage.documentationLink = `${DOCS_WORKBENCH_BASE}/workloads.html`;
