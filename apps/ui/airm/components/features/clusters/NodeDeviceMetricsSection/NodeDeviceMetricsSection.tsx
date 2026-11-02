// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ChartTimeSelector } from '@amdenterpriseai/components';
import { useCallback, useMemo, useRef, useState } from 'react';
import { useIsFetching, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';

import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';
import { TimeRangePeriod } from '@amdenterpriseai/types';
import type { TimeRange } from '@amdenterpriseai/types';

import { fetchNodeGpuDevices } from '@/services/app';
import { ALL_DEVICES_KEY } from '@/constants/clusters/nodeDetail';
import { getClusterNodeQueryKeyPrefix } from '@/utils/cluster-nodes';

import { GpuDeviceSelect } from './GpuDeviceSelect';
import { NodeGpuUtilizationChart } from '../NodeGpuUtilizationChart/NodeGpuUtilizationChart';
import { NodeGpuTemperatureChart } from '../NodeGpuTemperatureChart/NodeGpuTemperatureChart';
import { NodeGpuPowerUsageChart } from '../NodeGpuPowerUsageChart/NodeGpuPowerUsageChart';
import { NodePcieTrafficChart } from '../NodePcieTrafficChart/NodePcieTrafficChart';
import { useLastQueryUpdated } from '@amdenterpriseai/hooks';

interface Props {
  clusterId: string;
  nodeId: string;
}

export const NodeDeviceMetricsSection: React.FC<Props> = ({
  clusterId,
  nodeId,
}) => {
  const { t } = useTranslation('clusters');

  const currentTimePeriod = useRef<TimeRangePeriod>(TimeRangePeriod['1H']);
  const [timeRange, setTimeRange] = useState<TimeRange>(() =>
    getCurrentTimeRange(TimeRangePeriod['1H']),
  );
  const [selectedGpuDevices, setSelectedGpuDevices] = useState<Set<string>>(
    () => new Set([ALL_DEVICES_KEY]),
  );
  const queryKeyBase = getClusterNodeQueryKeyPrefix(clusterId, nodeId);

  const isFetchingMetrics =
    useIsFetching({
      queryKey: queryKeyBase,
    }) > 0;

  const lastUpdated = useLastQueryUpdated(queryKeyBase);

  const gpuDevicesQuery = useQuery({
    queryKey: [...queryKeyBase, 'gpu-devices'],
    queryFn: () => fetchNodeGpuDevices(clusterId, nodeId),
  });

  const gpuColorMap = useMemo(
    () =>
      (gpuDevicesQuery.data?.gpuDevices ?? []).reduce(
        (map, d, i) => map.set(d.gpuUuid, i),
        new Map<string, number>(),
      ),
    [gpuDevicesQuery.data?.gpuDevices],
  );

  const gpuDeviceOptions = useMemo(() => {
    const options: { key: string; label: string; uuid?: string }[] = [
      {
        key: ALL_DEVICES_KEY,
        label: t('clusters:nodes.detail.deviceMetrics.gpuDevice.allDevices'),
      },
    ];
    const devices = gpuDevicesQuery.data?.gpuDevices ?? [];
    [...devices]
      .sort((a, b) => parseInt(a.gpuId, 10) - parseInt(b.gpuId, 10))
      .forEach((d) => {
        const label = `gpu-${parseInt(d.gpuId, 10) + 1}`;
        options.push({ key: label, label, uuid: d.gpuUuid });
      });
    return options;
  }, [gpuDevicesQuery.data?.gpuDevices, t]);

  const handleTimeRangeChange = useCallback(
    (period: TimeRangePeriod, newTimeRange: TimeRange) => {
      currentTimePeriod.current = period;
      setTimeRange(newTimeRange);
    },
    [],
  );

  const handleChartsRefresh = useCallback(() => {
    setTimeRange(getCurrentTimeRange(currentTimePeriod.current));
  }, []);

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-row items-center justify-between gap-4 flex-wrap">
        <h3 className="text-base font-medium">
          {t('clusters:nodes.detail.deviceMetrics.title')}
        </h3>
        <div className="flex items-center gap-3 flex-nowrap">
          <GpuDeviceSelect
            selectedGpuDevices={selectedGpuDevices}
            gpuDeviceOptions={gpuDeviceOptions}
            gpuColorMap={gpuColorMap}
            onChange={setSelectedGpuDevices}
          />
          <ChartTimeSelector
            onTimeRangeChange={handleTimeRangeChange}
            onChartsRefresh={handleChartsRefresh}
            isFetching={isFetchingMetrics}
            lastFetchedTimestamp={lastUpdated}
            initialTimePeriod={TimeRangePeriod['1H']}
          />
        </div>
      </div>

      <NodeGpuUtilizationChart
        clusterId={clusterId}
        nodeId={nodeId}
        timeRange={timeRange}
        selectedGpuDevices={selectedGpuDevices}
        gpuColorMap={gpuColorMap}
        isDevicesLoading={gpuDevicesQuery.isLoading}
      />
      <NodeGpuTemperatureChart
        clusterId={clusterId}
        nodeId={nodeId}
        timeRange={timeRange}
        selectedGpuDevices={selectedGpuDevices}
        gpuColorMap={gpuColorMap}
        isDevicesLoading={gpuDevicesQuery.isLoading}
      />
      <NodeGpuPowerUsageChart
        clusterId={clusterId}
        nodeId={nodeId}
        timeRange={timeRange}
        selectedGpuDevices={selectedGpuDevices}
        gpuColorMap={gpuColorMap}
        isDevicesLoading={gpuDevicesQuery.isLoading}
      />
      <NodePcieTrafficChart
        clusterId={clusterId}
        nodeId={nodeId}
        timeRange={timeRange}
        selectedGpuDevices={selectedGpuDevices}
        gpuColorMap={gpuColorMap}
        isDevicesLoading={gpuDevicesQuery.isLoading}
      />
    </section>
  );
};
