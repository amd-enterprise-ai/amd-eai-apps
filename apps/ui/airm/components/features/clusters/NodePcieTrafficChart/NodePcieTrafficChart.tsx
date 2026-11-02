// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Card,
  CardBody,
  CardHeader,
  DynamicValueLegend,
  LineChart,
  Tab,
  Tabs,
} from '@amdenterpriseai/components';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';

import type { AvailableChartColorsKeys } from '@amdenterpriseai/types';
import type { TimeRange } from '@amdenterpriseai/types';

import {
  fetchNodePcieBandwidth,
  fetchNodePcieEfficiency,
} from '@/services/app';
import { mergeGpuDeviceTimeseriesToChartData } from '@/utils/node-gpu-utilization';
import { PcieTrafficTabId } from '@/types/enums/clusters';
import { PCIE_TRAFFIC_TAB_IDS } from '@/constants/clusters/nodeDetail';
import {
  getClusterNodeTimeRangeQueryKeyPrefix,
  filterGpuDevicesBySelection,
  getGpuChartCategories,
  getGpuChartColors,
} from '@/utils/cluster-nodes';
import { displayHumanReadableBytes } from '@amdenterpriseai/utils/app';

interface Props {
  clusterId: string;
  nodeId: string;
  timeRange: TimeRange;
  selectedGpuDevices: Set<string>;
  gpuColorMap: Map<string, number>;
  isDevicesLoading: boolean;
}

const translationKeySet = ['clusters', 'common'] as const;

export const NodePcieTrafficChart: React.FC<Props> = ({
  clusterId,
  nodeId,
  timeRange,
  selectedGpuDevices,
  gpuColorMap,
  isDevicesLoading,
}) => {
  const { t } = useTranslation(translationKeySet);
  const [pcieTrafficTab, setPcieTrafficTab] = useState<PcieTrafficTabId>(
    PcieTrafficTabId.Bandwidth,
  );
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

  const pcieBandwidthQuery = useQuery({
    queryKey: [...queryKeyBase, 'pcie-bandwidth'],
    queryFn: () =>
      fetchNodePcieBandwidth(clusterId, nodeId, timeRange.start, timeRange.end),
    enabled: pcieTrafficTab === PcieTrafficTabId.Bandwidth,
  });

  const pcieEfficiencyQuery = useQuery({
    queryKey: [...queryKeyBase, 'pcie-efficiency'],
    queryFn: () =>
      fetchNodePcieEfficiency(
        clusterId,
        nodeId,
        timeRange.start,
        timeRange.end,
      ),
    enabled: pcieTrafficTab === PcieTrafficTabId.Performance,
  });

  const activeQuery =
    pcieTrafficTab === PcieTrafficTabId.Bandwidth
      ? pcieBandwidthQuery
      : pcieEfficiencyQuery;

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

  const chartUnit = pcieTrafficTab === PcieTrafficTabId.Performance ? '%' : '';

  const chartValueFormatter = useMemo(
    () =>
      pcieTrafficTab === PcieTrafficTabId.Performance
        ? (v: number) => `${Number(v).toFixed(0)}%`
        : (v: number) => `${displayHumanReadableBytes(v)}/s`,
    [pcieTrafficTab],
  );

  const chartMaxValue =
    pcieTrafficTab === PcieTrafficTabId.Performance ? 100 : undefined;

  // Bandwidth labels (e.g. "1.2 GB/s") are wider and wrap to two lines at the
  // default yAxisWidth, clipping the topmost tick. Extra top margin prevents that.
  const chartMarginTop =
    pcieTrafficTab === PcieTrafficTabId.Bandwidth ? 20 : undefined;

  const isLoading =
    isDevicesLoading ||
    (pcieTrafficTab === PcieTrafficTabId.Bandwidth
      ? pcieBandwidthQuery.isLoading
      : pcieEfficiencyQuery.isLoading);

  const showNoData =
    pcieTrafficTab === PcieTrafficTabId.Bandwidth
      ? !pcieBandwidthQuery.isLoading && devicesToShow.length === 0
      : !pcieEfficiencyQuery.isLoading && devicesToShow.length === 0;

  const tabItems = useMemo(
    () =>
      PCIE_TRAFFIC_TAB_IDS.map((tabId) => ({
        id: tabId,
        title:
          tabId === PcieTrafficTabId.Bandwidth
            ? t('clusters:nodes.detail.deviceMetrics.pcieTraffic.tabBandwidth')
            : t(
                'clusters:nodes.detail.deviceMetrics.pcieTraffic.tabPerformance',
              ),
      })),
    [t],
  );

  return (
    <Card className="min-h-[120px]">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2 w-full">
          <span className="text-sm font-semibold text-foreground">
            {t('clusters:nodes.detail.deviceMetrics.pcieTraffic.title')}
          </span>
          <Tabs
            variant="primary"
            aria-label={t(
              'clusters:nodes.detail.deviceMetrics.pcieTraffic.title',
            )}
            selectedKey={pcieTrafficTab}
            onSelectionChange={(key) =>
              setPcieTrafficTab(key as PcieTrafficTabId)
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
            {t('clusters:nodes.detail.deviceMetrics.noData')}
          </p>
        ) : (
          <>
            <LineChart
              data={chartData}
              index="date"
              categories={chartCategories}
              colors={chartColors as AvailableChartColorsKeys[]}
              valueFormatter={chartValueFormatter}
              minValue={0}
              maxValue={chartMaxValue}
              marginTop={chartMarginTop}
              showLegend={false}
              showYAxis={true}
              connectNulls={true}
              className="h-72"
              yAxisWidth={64}
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
                unit={chartUnit}
                isLoading={isLoading}
                valueFormatter={chartValueFormatter}
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
