// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useCallback, useMemo, useState } from 'react';

import {
  IconArrowLeft,
  IconEdit,
  IconInfoCircle,
  IconTrash,
} from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import {
  AvailableChartColorsKeys,
  CustomComparatorConfig,
  TableColumns,
  TimeRangePeriod,
} from '@amdenterpriseai/types';
import type { TimeRange } from '@amdenterpriseai/types';
import {
  ActionButton,
  BarChart,
  Button,
  Card,
  CardBody,
  CardHeader,
  ChartTimeSelector,
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
  Select,
  SelectItem,
  StatisticsCard,
  StatusDisplay,
  Tab,
  Tabs,
  Tooltip,
} from '@amdenterpriseai/components';
import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';
import {
  APIRequestError,
  getCurrentTimeRange,
} from '@amdenterpriseai/utils/app';

import { useProject } from '@/contexts/ProjectContext';
import {
  deleteApiKey,
  fetchApiKeyDetails,
  fetchApiKeyMetrics,
} from '@/lib/app/api-keys';
import {
  aimParser,
  getAIMServiceStatusVariants,
  resolveAIMServiceDisplay,
} from '@/lib/app/aims';
import { useInferenceModelsByName } from '@/hooks/useInferenceModelsByName';
import { useProfileSpecsForServices } from '@/hooks/useProfileSpecsForServices';
import {
  ModelProfileSummary,
  toProfileSummaryFields,
} from '@/components/shared/ModelProfileSummary';
import { listAllInferenceDeployments } from '@/lib/app/inference';
import { listAllProjectFineTunedModels } from '@/lib/app/models';
import type { components } from '@/types/api';
import {
  AIM_MODEL_WORKLOAD_ID_LABEL,
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
} from '@/types/aims';
import type {
  AIMService,
  AIMServiceStatus,
  ModelProfileSummaryFields,
} from '@/types/aims';
import { SUBMITTER_ANNOTATION_KEY } from '@/components/features/secrets/constants';
import CreateApiKey from '@/components/features/api-keys/CreateApiKey';
import DeleteApiKeyModal from '@/components/features/api-keys/DeleteApiKeyModal';

const LinkedDeploymentsTableField = {
  NAME: 'name',
  STATUS: 'status',
  REPLICAS: 'replicas',
  CREATED_BY: 'createdBy',
  CREATED_AT: 'createdAt',
} as const;

type LinkedDeploymentsTableField =
  (typeof LinkedDeploymentsTableField)[keyof typeof LinkedDeploymentsTableField];

const INITIAL_TIME_PERIOD = TimeRangePeriod['24H'];

// Timeseries points come back as bare `{ [key]: number | string }` maps from
// the generated schema; each carries a `date` plus one entry per service id.
type MetricsResponse = components['schemas']['ApiKeyMetricsResponse'];
type AIMModelResource = components['schemas']['AIMModelResource'];
type MetricsDataPoint = MetricsResponse['requestsOverTime']['total'][number];

export function computeFilteredStats(
  metrics: MetricsResponse,
  selectedService: string,
): MetricsResponse['stats'] {
  if (selectedService === 'all') return metrics.stats;
  if (metrics.services.length === 1) return metrics.stats;

  const allSum = (data: MetricsDataPoint[]): number =>
    data.reduce(
      (acc, point) =>
        acc +
        metrics.services.reduce((s, svc) => {
          const v = point[svc];
          return s + (typeof v === 'number' ? v : 0);
        }, 0),
      0,
    );

  const svcSum = (data: MetricsDataPoint[]): number =>
    data.reduce((acc, point) => {
      const v = point[selectedService];
      return acc + (typeof v === 'number' ? v : 0);
    }, 0);

  const share = (data: MetricsDataPoint[]): number => {
    const total = allSum(data);
    return total > 0 ? svcSum(data) / total : 0;
  };

  const successful = Math.round(
    metrics.stats.successfulRequests *
      share(metrics.requestsOverTime.successful),
  );
  const failed = Math.round(
    metrics.stats.failedRequests * share(metrics.requestsOverTime.failed),
  );

  return {
    ...metrics.stats,
    totalRequests: successful + failed,
    successfulRequests: successful,
    failedRequests: failed,
    totalTokens: Math.round(
      metrics.stats.totalTokens * share(metrics.tokensOverTime.total),
    ),
  };
}

interface Props {
  projectId: string;
  apiKeyId: string;
  apiKeyName: string;
}

// ─────────────────────────────────────────────────────────────────────────────

const CHART_COLORS: AvailableChartColorsKeys[] = [
  'blue',
  'emerald',
  'violet',
  'amber',
  'cyan',
  'pink',
  'lime',
  'fuchsia',
];

// ── Helpers ────────────────────────────────────────────────────────────────

const formatCount = (val: number): string => {
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}k`;
  return val.toString();
};

// The gateway attributes token metrics by the model's workload-id (the x-ai-eg-backend
// UUID captured as the aim_service_id metric label) — the same id used for GPU/vLLM
// metrics and the /inference/{id} API. So join the metric series to a deployment by that
// same workload-id label, not a derived <ns>-<isname> string. The displayed name still
// comes from resolveAIMServiceDisplay; this only sets the lookup key.
const getAimServiceId = (d: AIMService): string =>
  d.metadata.labels?.[AIM_MODEL_WORKLOAD_ID_LABEL] ?? d.metadata.name;

type LinkedDeploymentRow = {
  id: string;
  name: string;
  status: AIMServiceStatus | undefined;
  replicas: number;
  createdBy: string;
  createdAt?: string;
  profile: ModelProfileSummaryFields | null;
};

const linkedDeploymentColumns: TableColumns<LinkedDeploymentsTableField> = [
  { key: LinkedDeploymentsTableField.NAME, sortable: true },
  { key: LinkedDeploymentsTableField.STATUS, sortable: true },
  { key: LinkedDeploymentsTableField.REPLICAS, sortable: true },
  { key: LinkedDeploymentsTableField.CREATED_BY, sortable: true },
  { key: LinkedDeploymentsTableField.CREATED_AT, sortable: true },
];

const aimServiceStatusRank: Record<AIMServiceStatus, number> = {
  Pending: 0,
  Starting: 1,
  Running: 2,
  Degraded: 3,
  Failed: 4,
  Deleted: 5,
};

const rankAimServiceStatus = (status: AIMServiceStatus | undefined): number =>
  status ? aimServiceStatusRank[status] : Number.MAX_SAFE_INTEGER;

const linkedDeploymentComparators: CustomComparatorConfig<
  LinkedDeploymentRow,
  LinkedDeploymentsTableField
> = {
  [LinkedDeploymentsTableField.STATUS]: (a, b) =>
    rankAimServiceStatus(a.status) - rankAimServiceStatus(b.status),
  [LinkedDeploymentsTableField.CREATED_AT]: (a, b) =>
    new Date(a.createdAt ?? 0).getTime() - new Date(b.createdAt ?? 0).getTime(),
};

const getDeploymentLabel = (
  d: AIMService,
  parsedAIMs: ReturnType<typeof aimParser>[],
): string => {
  const displayInfo = resolveAIMServiceDisplay(d, parsedAIMs);
  const isFineTuned = d.metadata.labels?.[FINE_TUNED_LABEL] === 'true';
  const label = isFineTuned
    ? displayInfo.title
    : `${displayInfo.canonicalName}${displayInfo.imageVersion ? ` (${displayInfo.imageVersion})` : ''}`.trim();
  return label || getAimServiceId(d);
};

type RequestsFilter = 'total' | 'successful' | 'failed';
type TokensFilter = 'total' | 'input' | 'output';

// ── Component ──────────────────────────────────────────────────────────────

export const ApiKeyMetricsDashboard: React.FC<Props> = ({
  projectId,
  apiKeyId,
  apiKeyName,
}) => {
  const { t } = useTranslation('api-keys');
  const { t: tModels } = useTranslation('models');
  const router = useRouter();
  const { projectPath } = useProject();
  const queryClient = useQueryClient();
  const { toast } = useSystemToast();

  const [requestsFilter, setRequestsFilter] = useState<RequestsFilter>('total');
  const [tokensFilter, setTokensFilter] = useState<TokensFilter>('total');
  const [selectedService, setSelectedService] = useState<string>('all');
  const [timePeriod, setTimePeriod] =
    useState<TimeRangePeriod>(INITIAL_TIME_PERIOD);
  const [timeRange, setTimeRange] = useState<TimeRange>(() =>
    getCurrentTimeRange(INITIAL_TIME_PERIOD),
  );

  const {
    isOpen: isEditOpen,
    onOpen: onEditOpen,
    onClose: onEditClose,
  } = useOverlayState();

  const {
    isOpen: isDeleteOpen,
    onOpen: onDeleteOpen,
    onOpenChange: onDeleteOpenChange,
  } = useOverlayState();

  const { data: apiKeyDetails } = useQuery({
    queryKey: ['project', projectId, 'api-key', apiKeyId],
    queryFn: () => fetchApiKeyDetails(projectId, apiKeyId),
    enabled: !!projectId && !!apiKeyId,
  });

  const { data: metrics, isLoading: isLoadingMetrics } = useQuery({
    queryKey: [
      'api-key-metrics',
      projectId,
      apiKeyId,
      timePeriod,
      timeRange.start.toISOString(),
      timeRange.end.toISOString(),
    ],
    queryFn: () =>
      fetchApiKeyMetrics(projectId, apiKeyId, {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      }),
    enabled: !!projectId && !!apiKeyId,
  });

  const { mutate: deleteApiKeyMutation } = useMutation({
    mutationFn: () => deleteApiKey(projectId, apiKeyId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['project-api-keys', projectId],
      });
      toast.success(t('list.actions.delete.notification.success'));
      router.push(projectPath('/api-keys'));
    },
    onError: (error) => {
      toast.error(
        t('list.actions.delete.notification.error'),
        error as APIRequestError,
      );
    },
  });

  const displayName = apiKeyDetails?.displayName ?? apiKeyName;

  const services = metrics?.services ?? [];

  const { data: allDeployments = [], isLoading: isLoadingDeployments } =
    useQuery({
      queryKey: ['inferenceDeployments', projectId],
      queryFn: () => listAllInferenceDeployments(projectId),
      enabled: !!projectId,
    });

  const linkedDeployments = useMemo(() => {
    const workloadIdSet = new Set(apiKeyDetails?.groups ?? []);
    return allDeployments.filter((d) => {
      const workloadId = d.metadata.labels?.[AIM_MODEL_WORKLOAD_ID_LABEL];
      return workloadId != null && workloadIdSet.has(workloadId);
    });
  }, [allDeployments, apiKeyDetails?.groups]);

  const clusterAimNames = useMemo(
    () =>
      linkedDeployments
        .filter(
          (d) =>
            d.metadata.labels?.[FINE_TUNED_LABEL] !== 'true' &&
            d.metadata.labels?.[NAMESPACE_AIM_MODEL_LABEL] !== 'true',
        )
        .map((d) => d.spec?.model?.name)
        .filter((name): name is string => !!name),
    [linkedDeployments],
  );

  const { byName: clusterAimsByName, isLoading: isClusterAimsLoading } =
    useInferenceModelsByName(clusterAimNames);

  const parsedAIMs = useMemo(
    () => Array.from(clusterAimsByName.values()).map((m) => aimParser(m)),
    [clusterAimsByName],
  );

  const { data: fineTunedModelCrs = [], isLoading: isFineTunedModelsLoading } =
    useQuery<AIMModelResource[]>({
      queryKey: ['project', projectId, 'fine-tuned-models'],
      queryFn: () => listAllProjectFineTunedModels(projectId),
      enabled: !!projectId,
      staleTime: Infinity,
    });

  const aimIds = useMemo(
    () =>
      isClusterAimsLoading || isFineTunedModelsLoading
        ? []
        : [
            ...Array.from(clusterAimsByName.values()).map(
              (m) => m.status?.aimId,
            ),
            ...fineTunedModelCrs.map((m) => m.status?.aimId),
          ].filter((id): id is string => !!id),
    [
      clusterAimsByName,
      isClusterAimsLoading,
      fineTunedModelCrs,
      isFineTunedModelsLoading,
    ],
  );
  const resolvedProfiles = useMemo(
    () => linkedDeployments.map(({ status }) => status?.resolvedProfile),
    [linkedDeployments],
  );

  const { specByName: profileSpecByName } = useProfileSpecsForServices({
    aimIds,
    project: projectId,
    resolvedProfiles,
  });

  const linkedDeploymentRows = useMemo((): LinkedDeploymentRow[] => {
    return linkedDeployments.map((d) => ({
      id: d.metadata.name,
      name: getDeploymentLabel(d, parsedAIMs),
      status: d.status?.status,
      replicas: d.status?.runtime?.currentReplicas ?? d.spec?.replicas ?? 0,
      createdBy: d.metadata.annotations?.[SUBMITTER_ANNOTATION_KEY] ?? '—',
      createdAt: d.metadata.creationTimestamp ?? undefined,
      profile: toProfileSummaryFields(d, profileSpecByName),
    }));
  }, [linkedDeployments, parsedAIMs, profileSpecByName]);

  const linkedDeploymentRenderers = useMemo(
    (): Partial<
      Record<
        LinkedDeploymentsTableField,
        (item: LinkedDeploymentRow) => React.ReactNode | string
      >
    > => ({
      [LinkedDeploymentsTableField.NAME]: (item) => (
        <div className="flex flex-col gap-1">
          <span>{item.name}</span>
          <ModelProfileSummary profile={item.profile} t={tModels} />
        </div>
      ),
      [LinkedDeploymentsTableField.STATUS]: (item) => {
        if (!item.status) {
          return <NoDataDisplay />;
        }
        return (
          <StatusDisplay
            type={item.status}
            variants={getAIMServiceStatusVariants(tModels)}
          />
        );
      },
      [LinkedDeploymentsTableField.CREATED_AT]: (item) => {
        if (item.createdAt) {
          return <DateDisplay date={item.createdAt} />;
        }
        return <NoDataDisplay />;
      },
    }),
    [tModels],
  );

  const serviceIdToLabel = useMemo(() => {
    const map = new Map<string, string>();
    const labelCounts = new Map<string, number>();
    for (const d of linkedDeployments) {
      const serviceId = getAimServiceId(d);
      const displayInfo = resolveAIMServiceDisplay(d, parsedAIMs);
      const isFineTuned = d.metadata.labels?.[FINE_TUNED_LABEL] === 'true';
      const baseLabel =
        (isFineTuned
          ? displayInfo.title
          : `${displayInfo.canonicalName}${displayInfo.imageVersion ? ` (${displayInfo.imageVersion})` : ''}`.trim()) ||
        serviceId;
      const count = labelCounts.get(baseLabel) ?? 0;
      labelCounts.set(baseLabel, count + 1);
      map.set(
        serviceId,
        count === 0 ? baseLabel : `${baseLabel} (${count + 1})`,
      );
    }
    return map;
  }, [linkedDeployments, parsedAIMs]);

  // Union of services seen in metrics + bound deployments with no traffic yet.
  const allServiceIds = useMemo(() => {
    const metricsSet = new Set(services);
    const extra = linkedDeployments
      .map(getAimServiceId)
      .filter((id) => !metricsSet.has(id));
    return [...services, ...extra];
  }, [services, linkedDeployments]);

  const filteredCategories = useMemo(() => {
    if (selectedService === 'all')
      return allServiceIds.map((id) => serviceIdToLabel.get(id) ?? id);
    return [serviceIdToLabel.get(selectedService) ?? selectedService];
  }, [selectedService, allServiceIds, serviceIdToLabel]);

  const activeChartColors = useMemo(() => {
    if (selectedService === 'all')
      return allServiceIds.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);
    const idx = allServiceIds.indexOf(selectedService);
    return [CHART_COLORS[Math.max(0, idx) % CHART_COLORS.length]];
  }, [selectedService, allServiceIds]);

  const filterChartData = useCallback(
    (base: MetricsDataPoint[]): MetricsDataPoint[] => {
      if (selectedService === 'all') return base;
      return base.map(({ date, ...rest }) => ({
        date,
        [selectedService]: rest[selectedService] ?? 0,
      }));
    },
    [selectedService],
  );

  const remapKeys = useCallback(
    (data: MetricsDataPoint[]): MetricsDataPoint[] =>
      data.map(({ date, ...rest }) => {
        const result: MetricsDataPoint = { date };
        for (const [key, val] of Object.entries(rest)) {
          result[serviceIdToLabel.get(key) ?? key] = val;
        }
        return result;
      }),
    [serviceIdToLabel],
  );

  const requestsData = useMemo(() => {
    const over = metrics?.requestsOverTime;
    const base =
      requestsFilter === 'successful'
        ? (over?.successful ?? [])
        : requestsFilter === 'failed'
          ? (over?.failed ?? [])
          : (over?.total ?? []);
    return remapKeys(filterChartData(base));
  }, [requestsFilter, filterChartData, metrics, remapKeys]);

  const tokensData = useMemo(() => {
    const over = metrics?.tokensOverTime;
    const base =
      tokensFilter === 'input'
        ? (over?.input ?? [])
        : tokensFilter === 'output'
          ? (over?.output ?? [])
          : (over?.total ?? []);
    return remapKeys(filterChartData(base));
  }, [tokensFilter, filterChartData, metrics, remapKeys]);

  const filteredStats = useMemo(
    () => (metrics ? computeFilteredStats(metrics, selectedService) : null),
    [metrics, selectedService],
  );

  return (
    <div className="flex flex-col gap-4 w-full pt-4 pb-12">
      {/* Header */}
      <div className="flex items-center gap-2">
        <ActionButton
          secondary
          size="sm"
          onPress={() => router.push(projectPath('/api-keys'))}
          icon={<IconArrowLeft size={16} />}
          aria-label={t('details.back')}
        />
        <span
          data-testid="metrics-header-key-name"
          className="font-semibold text-foreground"
        >
          {displayName}
        </span>
        <div className="ml-auto flex gap-2">
          <Button
            size="sm"
            variant="bordered"
            startContent={<IconEdit size={14} />}
            onPress={onEditOpen}
          >
            {t('list.actions.edit.title')}
          </Button>
          <Button
            size="sm"
            color="danger"
            variant="bordered"
            startContent={<IconTrash size={14} />}
            onPress={onDeleteOpen}
          >
            {t('list.actions.delete.title')}
          </Button>
        </div>
      </div>

      {/* Usage metrics controls */}
      <div className="flex items-center gap-3">
        <span className="font-medium text-foreground">
          {t('details.usageMetrics')}
        </span>
        <div className="ml-auto flex items-center gap-3">
          <Select
            className="w-52"
            aria-label={t('details.filters.inferenceService')}
            placeholder={t('details.filters.inferenceService')}
            selectedKeys={[selectedService]}
            items={[
              { key: 'all', label: t('details.filters.allServices') },
              ...allServiceIds.map((s) => ({
                key: s,
                label: serviceIdToLabel.get(s) ?? s,
              })),
            ]}
            onSelectionChange={(keys) => {
              const key =
                keys === 'all' ? 'all' : (Array.from(keys)[0] as string);
              if (key) setSelectedService(key);
            }}
          >
            {(item: { key: string; label: string }) => (
              <SelectItem key={item.key}>{item.label}</SelectItem>
            )}
          </Select>
          <ChartTimeSelector
            initialTimePeriod={INITIAL_TIME_PERIOD}
            onTimeRangeChange={(period: TimeRangePeriod, range: TimeRange) => {
              setTimePeriod(period);
              setTimeRange(range);
            }}
            onChartsRefresh={() =>
              setTimeRange(getCurrentTimeRange(timePeriod))
            }
          />
        </div>
      </div>

      {/* Stat tiles */}
      <div
        data-testid="metrics-stat-cards"
        className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4"
      >
        <StatisticsCard
          title={t('details.stats.totalRequests')}
          tooltip={t('details.stats.totalRequestsTooltip')}
          statistic={filteredStats?.totalRequests ?? 0}
          statisticFormatter={formatCount}
          isLoading={isLoadingMetrics}
        />
        <StatisticsCard
          title={t('details.stats.successfulRequests')}
          tooltip={t('details.stats.successfulRequestsTooltip')}
          statistic={filteredStats?.successfulRequests ?? 0}
          statisticFormatter={formatCount}
          isLoading={isLoadingMetrics}
        />
        <StatisticsCard
          title={t('details.stats.failedRequests')}
          tooltip={t('details.stats.failedRequestsTooltip')}
          statistic={filteredStats?.failedRequests ?? 0}
          statisticFormatter={formatCount}
          isLoading={isLoadingMetrics}
        />
        <StatisticsCard
          title={t('details.stats.totalTokens')}
          tooltip={t('details.stats.totalTokensTooltip')}
          statistic={filteredStats?.totalTokens ?? 0}
          statisticFormatter={formatCount}
          isLoading={isLoadingMetrics}
        />
        <StatisticsCard
          title={t('details.stats.linkedDeployments')}
          tooltip={t('details.stats.linkedDeploymentsTooltip')}
          statistic={linkedDeployments.length}
          isLoading={isLoadingDeployments}
        />
      </div>

      {/* Inference requests chart */}
      <Card className="overflow-visible">
        <CardHeader>
          <div className="flex items-center flex-grow gap-2">
            <span>{t('details.charts.inferenceRequests.title')}</span>
            <Tooltip
              content={t('details.charts.inferenceRequests.tooltip')}
              className="max-w-[300px]"
            >
              <IconInfoCircle className="text-muted cursor-pointer" size={16} />
            </Tooltip>
            <div className="ml-auto">
              <Tabs
                selectedKey={requestsFilter}
                onSelectionChange={(key) =>
                  setRequestsFilter(key as RequestsFilter)
                }
              >
                <Tab key="total" title={t('details.charts.filter.total')} />
                <Tab
                  key="successful"
                  title={t('details.charts.filter.successful')}
                />
                <Tab key="failed" title={t('details.charts.filter.failed')} />
              </Tabs>
            </div>
          </div>
        </CardHeader>
        <CardBody className="overflow-visible pt-2">
          <BarChart
            type="stacked"
            data={requestsData}
            categories={filteredCategories}
            colors={activeChartColors}
            index="date"
            maxBarSize={49}
          />
        </CardBody>
      </Card>

      {/* Token consumption chart */}
      <Card className="overflow-visible">
        <CardHeader>
          <div className="flex items-center flex-grow gap-2">
            <span>{t('details.charts.tokenConsumption.title')}</span>
            <Tooltip
              content={t('details.charts.tokenConsumption.tooltip')}
              className="max-w-[300px]"
            >
              <IconInfoCircle className="text-muted cursor-pointer" size={16} />
            </Tooltip>
            <div className="ml-auto">
              <Tabs
                selectedKey={tokensFilter}
                onSelectionChange={(key) =>
                  setTokensFilter(key as TokensFilter)
                }
              >
                <Tab key="total" title={t('details.charts.filter.total')} />
                <Tab
                  key="input"
                  title={t('details.charts.filter.inputTokens')}
                />
                <Tab
                  key="output"
                  title={t('details.charts.filter.outputTokens')}
                />
              </Tabs>
            </div>
          </div>
        </CardHeader>
        <CardBody className="overflow-visible pt-2">
          <BarChart
            type="stacked"
            data={tokensData}
            categories={filteredCategories}
            colors={activeChartColors}
            index="date"
            maxBarSize={49}
          />
        </CardBody>
      </Card>

      {/* Linked Deployments */}
      <Card>
        <CardHeader className="px-0">
          <span className="text-base leading-6 font-medium text-foreground">
            {t('details.linkedDeployments.title')}
          </span>
        </CardHeader>
        <CardBody className="p-0">
          <ClientSideDataTable
            data={linkedDeploymentRows}
            columns={linkedDeploymentColumns}
            customRenderers={linkedDeploymentRenderers}
            customComparator={linkedDeploymentComparators}
            defaultSortByField={LinkedDeploymentsTableField.NAME}
            translation={t}
            translationKeyPrefix="linkedDeployments"
            idKey="id"
            isLoading={isLoadingDeployments}
          />
        </CardBody>
      </Card>

      {/* Modals */}
      <CreateApiKey
        isOpen={isEditOpen}
        projectId={projectId}
        apiKey={apiKeyDetails}
        onClose={onEditClose}
      />
      <DeleteApiKeyModal
        isOpen={isDeleteOpen}
        onOpenChange={onDeleteOpenChange}
        apiKey={apiKeyDetails}
        onConfirmAction={() => deleteApiKeyMutation()}
      />
    </div>
  );
};

export default ApiKeyMetricsDashboard;
