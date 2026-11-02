// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';
import { Select, SelectItem } from '@amdenterpriseai/components';

import { IconCpu } from '@tabler/icons-react';

import type { Workload } from '@/types/workloads';

interface Props {
  selectedModelId?: string;
  workloads: Workload[];
  onModelDeploymentChange: (modelId: string) => void;
  label?: string;
  isDisabled?: boolean;
  allowEmptySelection?: boolean;
  showOnlyRunningWorkloads?: boolean;
  workloadDescriptions?: Record<string, string>;
}

export function ModelDeploymentSelect({
  selectedModelId,
  onModelDeploymentChange,
  workloads,
  label,
  isDisabled,
  allowEmptySelection,
  showOnlyRunningWorkloads = true,
  workloadDescriptions,
}: Props) {
  const filteredWorkloads = useMemo(
    () =>
      workloads.filter(
        (workload) =>
          (!showOnlyRunningWorkloads || workload.status === 'Running') &&
          workload.type === 'INFERENCE',
      ),
    [workloads, showOnlyRunningWorkloads],
  );

  return (
    <Select
      className="select-wrapper w-full lg:min-w-72"
      variant="primary"
      data-testid="model-deployment-select"
      aria-label={label}
      placeholder={label}
      showDescriptionInTrigger
      disallowEmptySelection={!allowEmptySelection}
      selectedKeys={selectedModelId ? [selectedModelId] : []}
      onChange={(e) => onModelDeploymentChange(e.target.value)}
      isDisabled={workloads.length === 0 || isDisabled}
      startContent={<IconCpu size={16} />}
    >
      {filteredWorkloads.map((workload) => (
        <SelectItem
          aria-roledescription="option"
          key={workload.id}
          aria-label={workload.id}
          description={workloadDescriptions?.[workload.id]}
        >
          {workload.displayName ?? workload.name}
        </SelectItem>
      ))}
    </Select>
  );
}

export default ModelDeploymentSelect;
