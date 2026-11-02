// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useTranslation } from 'next-i18next';

import { TimeRangePeriod, TimeRange } from '@amdenterpriseai/types';
import { useMemo } from 'react';
import {
  getTickGap,
  transformTimeSeriesDataToChartData,
} from '@amdenterpriseai/utils/app';
import {
  BarChart,
  Card,
  CardBody,
  CardHeader,
  Tooltip,
} from '@amdenterpriseai/components';
import { IconInfoCircle } from '@tabler/icons-react';
import { getInferenceRequests } from '@/lib/app/metrics';
import { useQuery } from '@tanstack/react-query';
import { useProject } from '@/contexts/ProjectContext';
import { InferenceMetricsColors } from '@/types/metrics';

interface Props {
  namespace: string;
  workloadId: string;
  timeRange: TimeRange;
  timePeriod: TimeRangePeriod;
  podName?: string;
}

const WAITING_REQUESTS_COLOR = InferenceMetricsColors.WAITING_REQUESTS;
const RUNNING_REQUESTS_COLOR = InferenceMetricsColors.RUNNING_REQUESTS;

export const InferenceRequestsCard: React.FC<Props> = ({
  namespace,
  workloadId,
  timeRange,
  timePeriod,
  podName,
}) => {
  const { t } = useTranslation('workloads');
  const { activeProject } = useProject();

  const { data: inferenceRequestsData, isLoading: isInferenceRequestsLoading } =
    useQuery({
      queryKey: [
        'project',
        activeProject,
        'workload',
        workloadId,
        'metrics',
        'inferenceRequests',
        podName,
        {
          start: timeRange.start.toISOString(),
          end: timeRange.end.toISOString(),
        },
      ],
      queryFn: () =>
        getInferenceRequests({
          workloadId,
          namespace,
          start: timeRange.start,
          end: timeRange.end,
          podName,
        }),
    });

  const inferenceRequestsChartData = useMemo(() => {
    if (!inferenceRequestsData?.data) return null;

    const mappedData = inferenceRequestsData.data.map((item) => ({
      metadata: {
        ...item.metadata,
        metric: item.metadata.label,
      },
      values: (item.values ?? []).map((point) => ({
        timestamp: point.timestamp,
        value: point.value ?? null,
      })),
    }));

    return transformTimeSeriesDataToChartData(
      mappedData,
      inferenceRequestsData.range.timestamps,
      'metric',
    );
  }, [inferenceRequestsData]);

  return (
    <Card className="max-w-full w-full h-full overflow-visible flex flex-col">
      <CardHeader>
        <div className="flex items-center flex-grow">
          <div>{t('details.metrics.inferenceRequests.title')}</div>
          <div className="ml-auto">
            <Tooltip
              content={t('details.metrics.inferenceRequests.description')}
              className="max-w-[300px]"
            >
              <IconInfoCircle className="text-muted cursor-pointer" size={16} />
            </Tooltip>
          </div>
        </div>
      </CardHeader>
      <CardBody className="overflow-visible pt-2 flex-1 flex flex-col">
        <BarChart
          className="h-full"
          type="stacked"
          data={
            inferenceRequestsChartData ? inferenceRequestsChartData.data : []
          }
          categories={
            inferenceRequestsChartData
              ? inferenceRequestsChartData.categories
              : []
          }
          colors={[RUNNING_REQUESTS_COLOR, WAITING_REQUESTS_COLOR]}
          isLoading={isInferenceRequestsLoading}
          index="date"
          tickGap={getTickGap(timePeriod)}
        />
      </CardBody>
    </Card>
  );
};

export default InferenceRequestsCard;
