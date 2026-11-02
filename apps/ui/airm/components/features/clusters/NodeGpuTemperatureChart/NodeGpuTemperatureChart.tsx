// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  BarChart,
  Card,
  CardBody,
  CardHeader,
  DynamicValueLegend,
  Tab,
  Tabs,
} from '@amdenterpriseai/components';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';

import type { AvailableChartColorsKeys } from '@amdenterpriseai/types';
import type { TimeRange } from '@amdenterpriseai/types';

import {
  fetchNodeGpuJunctionTemperature,
  fetchNodeGpuMemoryTemperature,
} from '@/services/app';
import { mergeGpuDeviceTimeseriesToChartData } from '@/utils/node-gpu-utilization';
import { GpuTemperatureTabId } from '@/types/enums/clusters';
import { GPU_TEMPERATURE_TAB_IDS } from '@/constants/clusters/nodeDetail';
import {
  getClusterNodeTimeRangeQueryKeyPrefix,
  filterGpuDevicesBySelection,
  getGpuChartCategories,
  getGpuChartColors,
} from '@/utils/cluster-nodes';

interface Props {
  clusterId: string;
  nodeId: string;
  timeRange: TimeRange;
  selectedGpuDevices: Set<string>;
  gpuColorMap: Map<string, number>;
  isDevicesLoading: boolean;
}

const temperatureFormatter = (v: number) =>
  `${Number.isInteger(v) ? v : Number(v).toFixed(1)}\u00B0C`;

const translationKeySet = ['clusters', 'common'] as const;

export const NodeGpuTemperatureChart: React.FC<Props> = ({
  clusterId,
  nodeId,
  timeRange,
  selectedGpuDevices,
  gpuColorMap,
  isDevicesLoading,
}) => {
  const { t } = useTranslation(translationKeySet);
  const [gpuTemperatureTab, setGpuTemperatureTab] =
    useState<GpuTemperatureTabId>(GpuTemperatureTabId.Junction);
  const [hoveredChartPoint, setHoveredChartPoint] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [activeLegendGpu, setActiveLegendGpu] = useState<string | undefined>(
    undefined,
  );

  const queryKeyBase = getClusterNodeTimeRangeQueryKeyPrefix(
    clusterId,
    nodeId,
    timeRange,
  );

  const junctionTemperatureQuery = useQuery({
    queryKey: [...queryKeyBase, 'junction-temperature'],
    queryFn: () =>
      fetchNodeGpuJunctionTemperature(
        clusterId,
        nodeId,
        timeRange.start,
        timeRange.end,
      ),
    enabled: gpuTemperatureTab === GpuTemperatureTabId.Junction,
  });

  const memoryTemperatureQuery = useQuery({
    queryKey: [...queryKeyBase, 'memory-temperature'],
    queryFn: () =>
      fetchNodeGpuMemoryTemperature(
        clusterId,
        nodeId,
        timeRange.start,
        timeRange.end,
      ),
    enabled: gpuTemperatureTab === GpuTemperatureTabId.Memory,
  });

  const activeQuery =
    gpuTemperatureTab === GpuTemperatureTabId.Memory
      ? memoryTemperatureQuery
      : junctionTemperatureQuery;

  const devicesToShow = useMemo(
    () =>
      filterGpuDevicesBySelection(
        activeQuery.data?.gpuDevices ?? [],
        selectedGpuDevices,
      ),
    [activeQuery.data?.gpuDevices, selectedGpuDevices],
  );

  const chartData = useMemo(
    () => mergeGpuDeviceTimeseriesToChartData(devicesToShow),
    [devicesToShow],
  );

  const chartCategories = useMemo(
    () => getGpuChartCategories(devicesToShow),
    [devicesToShow],
  );

  const chartColors = useMemo(
    () => getGpuChartColors(devicesToShow, gpuColorMap),
    [devicesToShow, gpuColorMap],
  );

  const isLoading = activeQuery.isLoading || isDevicesLoading;
  const showNoData = !activeQuery.isLoading && devicesToShow.length === 0;

  const tabItems = useMemo(
    () =>
      GPU_TEMPERATURE_TAB_IDS.map((tabId) => ({
        id: tabId,
        title:
          tabId === GpuTemperatureTabId.Memory
            ? t(
                'clusters:nodes.detail.deviceMetrics.gpuTemperature.tabMemoryTemperature',
              )
            : t(
                'clusters:nodes.detail.deviceMetrics.gpuTemperature.tabJunctionTemperature',
              ),
      })),
    [t],
  );

  return (
    <Card className="min-h-[120px]">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2 w-full">
          <span className="text-sm font-semibold text-foreground">
            {t('clusters:nodes.detail.deviceMetrics.gpuTemperature.title')}
          </span>
          <Tabs
            variant="primary"
            aria-label={t(
              'clusters:nodes.detail.deviceMetrics.gpuTemperature.title',
            )}
            selectedKey={gpuTemperatureTab}
            onSelectionChange={(key) =>
              setGpuTemperatureTab(key as GpuTemperatureTabId)
            }
            classNames={{
              base: 'w-fit',
              panel: 'hidden',
              tabList: 'dark:bg-default-hover',
            }}
            items={tabItems}
          >
            {(item) => <Tab key={item.id} title={item.title} />}
          </Tabs>
        </div>
      </CardHeader>
      <CardBody className="pt-0 mt-4">
        {showNoData ? (
          <p className="text-muted text-sm">
            {t('clusters:nodes.detail.deviceMetrics.noTemperatureData')}
          </p>
        ) : (
          <>
            <BarChart
              data={chartData}
              index="date"
              categories={chartCategories}
              colors={chartColors as AvailableChartColorsKeys[]}
              valueFormatter={temperatureFormatter}
              minValue={0}
              maxValue={100}
              allowDecimals={false}
              showLegend={false}
              showYAxis={true}
              className="h-72"
              activeLegendProp={activeLegendGpu}
              tooltipCallback={({ active, payload }) => {
                setHoveredChartPoint(
                  active && payload?.length
                    ? (payload[0].payload as Record<string, unknown>)
                    : null,
                );
              }}
              isLoading={isLoading}
            />
            {(isLoading || chartCategories.length > 0) && (
              <DynamicValueLegend
                categories={chartCategories}
                colors={chartColors as AvailableChartColorsKeys[]}
                data={chartData as Record<string, unknown>[]}
                unit={'\u00B0C'}
                isLoading={isLoading}
                valueFormatter={temperatureFormatter}
                displayPoint={hoveredChartPoint}
                activeCategory={activeLegendGpu}
                onCategoryClick={(category) =>
                  setActiveLegendGpu((prev) =>
                    prev === category ? undefined : category,
                  )
                }
              />
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
};
