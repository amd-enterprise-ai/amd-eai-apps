// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormInput,
  FormSlider,
  FormSwitch,
  Wizard,
} from '@amdenterpriseai/components';
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'next-i18next';
import { z } from 'zod';

import ResourceAllocationInformer from '@/components/features/catalog/ResourceAllocationInformer';

import type { DeployWorkspaceFormValues } from '../types';

type RequiredResources = {
  gpus: number;
  memoryPerGpu: number;
  cpuPerGpu: number;
};

type AvailableResources = {
  gpus: number;
  memory: number;
  cpu: number;
};

export const createTargetStepSchema = (t: (key: string) => string) =>
  z.object({
    displayName: z
      .string()
      .trim()
      .min(1, {
        message: t('deployModal.settings.displayName.emptyNameError'),
      })
      .max(128),
    customizeResources: z.boolean(),
    gpus: z.number().int().optional(),
    memoryPerGpu: z.number().int().optional(),
    cpuPerGpu: z.number().int().optional(),
  });

type TargetStepFieldsProps = {
  form: UseFormReturn<DeployWorkspaceFormValues>;
  requiredResources: RequiredResources;
  availableResources: AvailableResources;
  enableResourceAllocation: boolean;
  isLoadingClusterResources: boolean;
  allocationCalculationNotReady: boolean;
};

export const TargetStepFields = ({
  form,
  requiredResources,
  availableResources,
  enableResourceAllocation,
  isLoadingClusterResources,
  allocationCalculationNotReady,
}: TargetStepFieldsProps) => {
  const { t } = useTranslation('catalog');
  const customizeResources = form.watch('customizeResources');
  const gpus = form.watch('gpus') ?? requiredResources.gpus;
  const memoryPerGpu =
    form.watch('memoryPerGpu') ?? requiredResources.memoryPerGpu;
  const cpuPerGpu = form.watch('cpuPerGpu') ?? requiredResources.cpuPerGpu;
  const currentResources = { gpus, memoryPerGpu, cpuPerGpu };
  const maxCpuPerGpu = Math.ceil(
    availableResources.cpu / Math.max(currentResources.gpus, 1),
  );

  return (
    <>
      <FormInput
        name="displayName"
        form={form}
        aria-label={t('deployModal.settings.displayName.label')}
        label={t('deployModal.settings.displayName.label')}
        placeholder={t('deployModal.settings.displayName.placeholder')}
        isRequired
        maxLength={128}
      />

      <FormSwitch
        form={form}
        name="customizeResources"
        data-testid="customize-resources-toggle"
        isDisabled={isLoadingClusterResources || !enableResourceAllocation}
      >
        {t('deployModal.settings.resourceAllocation.label')}
      </FormSwitch>
      {customizeResources ? (
        <div className="flex flex-col gap-4">
          <FormSlider
            form={form}
            name="gpus"
            key={`gpus-slider-${requiredResources.gpus}`}
            label={t('deployModal.settings.resourceAllocation.gpuCount')}
            isDisabled={allocationCalculationNotReady}
            maxValue={availableResources.gpus}
            minValue={0}
            step={1}
            getValue={(value) =>
              t('deployModal.settings.resourceAllocation.gpuCountValue', {
                value,
                maxValue: availableResources.gpus,
              })
            }
            marks={[
              {
                value: requiredResources.gpus,
                label: t('deployModal.settings.resourceAllocation.req'),
              },
            ]}
          />
          <FormSlider
            form={form}
            name="memoryPerGpu"
            key={`memoryPerGpu-slider-${requiredResources.memoryPerGpu}`}
            label={t('deployModal.settings.resourceAllocation.systemMemory')}
            isDisabled={allocationCalculationNotReady}
            maxValue={Math.ceil(availableResources.memory / Math.max(gpus, 1))}
            minValue={1}
            step={1}
            getValue={(item) =>
              t('deployModal.settings.resourceAllocation.systemMemoryValue', {
                value: item,
                maxValue: Math.ceil(
                  availableResources.memory /
                    Math.max(currentResources.gpus, 1),
                ),
              })
            }
            marks={[
              {
                value: requiredResources.memoryPerGpu,
                label: t('deployModal.settings.resourceAllocation.req'),
              },
            ]}
          />
          <FormSlider
            form={form}
            name="cpuPerGpu"
            key={`cpuPerGpu-slider-${requiredResources.cpuPerGpu}`}
            label={t('deployModal.settings.resourceAllocation.cpuCoreCount')}
            isDisabled={allocationCalculationNotReady}
            maxValue={maxCpuPerGpu}
            minValue={1}
            step={1}
            getValue={(item) =>
              t('deployModal.settings.resourceAllocation.cpuCoreCountValue', {
                value: item,
                maxValue: maxCpuPerGpu,
              })
            }
            marks={[
              {
                value: requiredResources.cpuPerGpu,
                label: t('deployModal.settings.resourceAllocation.req'),
              },
            ]}
          />
        </div>
      ) : null}
      <ResourceAllocationInformer
        isLoading={isLoadingClusterResources}
        currentResources={
          customizeResources ? currentResources : requiredResources
        }
        quota={undefined}
        requiredResources={requiredResources}
      />
    </>
  );
};

type TargetStepSummaryProps = {
  data: DeployWorkspaceFormValues;
  requiredResources: RequiredResources;
};

export const TargetStepSummary = ({
  data,
  requiredResources,
}: TargetStepSummaryProps) => {
  const { t } = useTranslation('catalog');

  const gpus = data.gpus ?? requiredResources.gpus;
  const memoryPerGpu = data.memoryPerGpu ?? requiredResources.memoryPerGpu;
  const cpuPerGpu = data.cpuPerGpu ?? requiredResources.cpuPerGpu;
  const resources = data.customizeResources
    ? { gpus, memoryPerGpu, cpuPerGpu }
    : requiredResources;
  const gpuMultiplier = Math.max(resources.gpus, 1);
  const allocationSummary = t('deployModal.summary.allocationSummary', {
    gpuCount: resources.gpus,
    cpuCount: gpuMultiplier * resources.cpuPerGpu,
    ramGb: gpuMultiplier * resources.memoryPerGpu,
  });

  return (
    <>
      <Wizard.SummaryRow
        label={t('deployModal.summary.displayName')}
        value={data.displayName}
      />
      <Wizard.SummaryRow
        label={t('deployModal.summary.resourceAllocation')}
        value={
          data.customizeResources
            ? t('deployModal.summary.customResources')
            : t('deployModal.summary.defaultResources')
        }
      />
      <Wizard.SummaryRow
        label={t('deployModal.summary.allocation')}
        value={allocationSummary}
      />
    </>
  );
};
