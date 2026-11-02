// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Select, SelectItem } from '@amdenterpriseai/components';

import { IconCpu } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';

import {
  ALL_DEVICES_KEY,
  GPU_LINE_CHART_COLORS,
} from '@/constants/clusters/nodeDetail';
import { getChartColorBg, getColorForGpuUuid } from '@/utils/cluster-nodes';

interface GpuDeviceOption {
  key: string;
  label: string;
  uuid?: string;
}

interface Props {
  selectedGpuDevices: Set<string>;
  gpuDeviceOptions: GpuDeviceOption[];
  gpuColorMap: Map<string, number>;
  onChange: (next: Set<string>) => void;
}

const translationKeySet = ['clusters', 'common'] as const;

export const GpuDeviceSelect: React.FC<Props> = ({
  selectedGpuDevices,
  gpuDeviceOptions,
  gpuColorMap,
  onChange,
}) => {
  const { t } = useTranslation(translationKeySet);

  const handleSelectionChange = (keys: Iterable<React.Key>) => {
    const newSet = new Set(keys as Iterable<string>);
    const hadAllDevices = selectedGpuDevices.has(ALL_DEVICES_KEY);

    if (newSet.size === 0) {
      onChange(new Set([ALL_DEVICES_KEY]));
      return;
    }
    if (newSet.has(ALL_DEVICES_KEY) && !hadAllDevices) {
      onChange(new Set([ALL_DEVICES_KEY]));
      return;
    }
    if (newSet.has(ALL_DEVICES_KEY) && hadAllDevices && newSet.size > 1) {
      onChange(
        new Set(Array.from(newSet).filter((k) => k !== ALL_DEVICES_KEY)),
      );
      return;
    }
    onChange(newSet);
  };

  const renderValue = () => {
    const sel = selectedGpuDevices;
    if (sel.size === 0 || sel.has(ALL_DEVICES_KEY)) {
      return t('clusters:nodes.detail.deviceMetrics.gpuDevice.allDevices');
    }
    if (sel.size === 1) return Array.from(sel)[0];
    return t('clusters:nodes.detail.deviceMetrics.gpuDevice.selectedCount', {
      count: sel.size,
    });
  };

  return (
    <Select
      aria-label={t('clusters:nodes.detail.deviceMetrics.gpuDevice.label')}
      className="min-w-64"
      variant="primary"
      selectionMode="multiple"
      selectedKeys={selectedGpuDevices}
      onSelectionChange={handleSelectionChange}
      disallowEmptySelection
      startContent={<IconCpu size={16} className="text-muted shrink-0" />}
      renderValue={renderValue}
    >
      {gpuDeviceOptions.map((opt) => (
        <SelectItem
          key={opt.key}
          textValue={opt.label}
          startContent={
            opt.key === ALL_DEVICES_KEY ? (
              <IconCpu size={16} className="text-muted shrink-0" />
            ) : (
              <span
                className={`size-2 rounded-sm shrink-0 ${getChartColorBg(
                  opt.uuid
                    ? getColorForGpuUuid(
                        opt.uuid,
                        gpuColorMap,
                        GPU_LINE_CHART_COLORS,
                      )
                    : 'gray',
                )}`}
              />
            )
          }
        >
          {opt.label}
        </SelectItem>
      ))}
    </Select>
  );
};
