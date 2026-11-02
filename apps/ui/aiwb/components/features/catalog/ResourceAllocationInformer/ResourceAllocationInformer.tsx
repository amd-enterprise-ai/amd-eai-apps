// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { FC, useMemo } from 'react';

import { Alert, Card, CardBody, CardHeader } from '@amdenterpriseai/components';

import { useTranslation } from 'next-i18next';

import { ResourceType, type AllocationAlertColor } from './constants';

import TableLine from './TableLine';

type AllocationAlertContent = {
  color: AllocationAlertColor;
  description: string;
};

export type ResourceAllocationInformerProps = {
  isLoading: boolean;
  currentResources: {
    gpus: number;
    memoryPerGpu: number;
    cpuPerGpu: number;
  };
  quota?: {
    gpus: number;
    memory: number;
    cpu: number;
  };
  requiredResources: {
    gpus: number;
    memoryPerGpu: number;
    cpuPerGpu: number;
  };
};

const ResourceAllocationInformer: FC<ResourceAllocationInformerProps> = ({
  isLoading,
  currentResources,
  quota,
  requiredResources,
}) => {
  const { t } = useTranslation('catalog', {
    keyPrefix: 'deployModal.settings.resourceAllocation',
  });

  const { gpus, memoryPerGpu, cpuPerGpu } = currentResources;

  const { totalMemory, totalCpu } = useMemo(
    () => ({
      // For 0-GPU workloads, treat as 1 GPU to avoid multiplying by 0
      totalMemory: Math.max(gpus, 1) * memoryPerGpu,
      totalCpu: Math.max(gpus, 1) * cpuPerGpu,
    }),
    [gpus, memoryPerGpu, cpuPerGpu],
  );

  const { exceedsQuota, belowRequired } = useMemo(
    () => ({
      exceedsQuota: quota
        ? gpus > quota?.gpus ||
          totalMemory > quota?.memory ||
          totalCpu > quota?.cpu
        : false,
      belowRequired:
        gpus < requiredResources.gpus ||
        totalMemory <
          Math.max(requiredResources.gpus, 1) *
            requiredResources.memoryPerGpu ||
        totalCpu <
          Math.max(requiredResources.gpus, 1) * requiredResources.cpuPerGpu,
    }),
    [gpus, totalMemory, totalCpu, quota, requiredResources],
  );

  const alertContent = useMemo((): AllocationAlertContent | null => {
    if (belowRequired && exceedsQuota) {
      return {
        color: 'danger',
        description: t('belowRequiredExceedsQuotaWarning'),
      };
    }
    if (belowRequired) {
      return {
        color: 'danger',
        description: t('belowRequiredWarning'),
      };
    }
    if (exceedsQuota) {
      return {
        color: 'warning',
        description: t('exceedsQuotaWarning'),
      };
    }
    return null;
  }, [belowRequired, exceedsQuota, t]);

  return (
    <div className="flex flex-col gap-4 text-sm">
      <Card data-testid="resource-allocation-card" variant="secondary">
        <CardHeader>
          <h4>{t('totalResourceAllocation')}</h4>
        </CardHeader>
        <CardBody className="flex flex-col gap-2">
          <TableLine
            type={ResourceType.GPU}
            value={gpus}
            req={requiredResources.gpus}
            quota={quota?.gpus}
            isLoading={isLoading}
          />
          <TableLine
            type={ResourceType.RAM}
            value={memoryPerGpu}
            req={
              Math.max(requiredResources.gpus, 1) *
              requiredResources.memoryPerGpu
            }
            multiplier={Math.max(gpus, 1)}
            quota={quota?.memory}
            isLoading={isLoading}
          />
          <TableLine
            type={ResourceType.CPU}
            value={cpuPerGpu}
            req={
              Math.max(requiredResources.gpus, 1) * requiredResources.cpuPerGpu
            }
            multiplier={Math.max(gpus, 1)}
            quota={quota?.cpu}
            isLoading={isLoading}
          />
        </CardBody>
      </Card>

      {!isLoading && alertContent && (
        <Alert
          status={alertContent.color}
          description={alertContent.description}
        />
      )}
    </div>
  );
};

export default ResourceAllocationInformer;
