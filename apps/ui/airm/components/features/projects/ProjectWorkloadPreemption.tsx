// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  SelectItem,
  FormNumberInput,
  FormSelect,
  FormSwitch,
  Tooltip,
} from '@amdenterpriseai/components';
import { IconInfoCircle } from '@tabler/icons-react';
import type { TFunction } from 'i18next';
import { useLayoutEffect, useRef } from 'react';
import type { UseFormReturn } from 'react-hook-form';

import { CREATE_PROJECT_GPU_PREEMPTION_DEFAULTS } from '@/components/features/projects/constants';

import { GpuPreemptionPolicy } from '@/types/enums/gpu-preemption-policy';
import { ProjectGpuPreemptionFormFields } from '@/types/enums/project-form-fields';
import { CreateProjectFormData } from '@/types/projects';

export interface ProjectWorkloadPreemptionProps {
  form: UseFormReturn<CreateProjectFormData>;
  t: TFunction;
}

export function ProjectWorkloadPreemption({
  form,
  t,
}: ProjectWorkloadPreemptionProps) {
  const enabled = form.watch(ProjectGpuPreemptionFormFields.ENABLED);
  const prevEnabledRef = useRef(enabled);
  useLayoutEffect(() => {
    const justTurnedOn = !prevEnabledRef.current && enabled;
    prevEnabledRef.current = enabled;
    if (!enabled || !justTurnedOn) return;
    const defaults = CREATE_PROJECT_GPU_PREEMPTION_DEFAULTS;
    const policy = form.getValues(ProjectGpuPreemptionFormFields.POLICY);
    if (
      policy == null ||
      !Object.values(GpuPreemptionPolicy).includes(
        policy as GpuPreemptionPolicy,
      )
    ) {
      form.setValue(ProjectGpuPreemptionFormFields.POLICY, defaults.policy, {
        shouldValidate: true,
        shouldDirty: false,
      });
    }
    const th = form.getValues(ProjectGpuPreemptionFormFields.THRESHOLD);
    if (th === undefined || !Number.isFinite(th)) {
      form.setValue(
        ProjectGpuPreemptionFormFields.THRESHOLD,
        defaults.threshold,
        { shouldValidate: true, shouldDirty: false },
      );
    }
    const gr = form.getValues(ProjectGpuPreemptionFormFields.GRACE_PERIOD);
    if (gr === undefined || !Number.isFinite(gr)) {
      form.setValue(
        ProjectGpuPreemptionFormFields.GRACE_PERIOD,
        defaults.gracePeriod,
        { shouldValidate: true, shouldDirty: false },
      );
    }
  }, [enabled, form]);

  return (
    <div className="flex flex-col gap-4 border-t border-default pt-4">
      <div className="flex items-center gap-1">
        <h3 className="text-sm font-semibold text-foreground">
          {t('modal.create.form.preemption.sectionTitle')}
        </h3>
        <Tooltip
          classNames={{
            content: 'max-w-md',
          }}
          content={t('modal.create.form.preemption.tooltip')}
          placement="top"
        >
          <button
            type="button"
            className="inline-flex cursor-pointer rounded-sm border-0 bg-transparent p-0 text-muted outline-offset-2 hover:opacity-80"
            aria-label={t('modal.create.form.preemption.tooltipTriggerAria')}
          >
            <IconInfoCircle size={16} aria-hidden />
          </button>
        </Tooltip>
      </div>
      <FormSwitch
        form={form}
        name={ProjectGpuPreemptionFormFields.ENABLED}
        aria-label={t('modal.create.form.preemption.toggle')}
      >
        {t('modal.create.form.preemption.toggle')}
      </FormSwitch>
      {/* Unmount when off so fields unregister (shouldUnregister). Re-seed defaults when toggled on so validation and FormSelect stay aligned. */}
      {enabled ? (
        <div className="flex flex-col gap-4">
          {/*
           * TODO: Policy select briefly shows the wrong value after save
           * (project settings). Underlying form/ManagedForm + RHF reset/refetch timing;
           * not the API payload. See ticket for repro steps.
           */}
          <FormSelect
            form={form}
            name={ProjectGpuPreemptionFormFields.POLICY}
            label={t('modal.create.form.preemption.policy.label')}
            placeholder={t('modal.create.form.preemption.policy.placeholder')}
            isRequired
            disallowEmptySelection
          >
            <SelectItem
              key={GpuPreemptionPolicy.OnPressure}
              textValue={t('modal.create.form.preemption.policy.onPressure')}
            >
              {t('modal.create.form.preemption.policy.onPressure')}
            </SelectItem>
            <SelectItem
              key={GpuPreemptionPolicy.Always}
              textValue={t('modal.create.form.preemption.policy.always')}
            >
              {t('modal.create.form.preemption.policy.always')}
            </SelectItem>
          </FormSelect>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-4">
            <div className="min-w-0">
              <FormNumberInput
                form={form}
                name={ProjectGpuPreemptionFormFields.THRESHOLD}
                label={t('modal.create.form.preemption.threshold.label')}
                minValue={0}
                maxValue={100}
                isRequired
                endContent={<span className="text-sm text-muted">%</span>}
              />
            </div>
            <div className="min-w-0">
              <FormNumberInput
                form={form}
                name={ProjectGpuPreemptionFormFields.GRACE_PERIOD}
                label={t('modal.create.form.preemption.gracePeriod.label')}
                description={t(
                  'modal.create.form.preemption.gracePeriod.description',
                )}
                isRequired
                endContent={
                  <span className="text-sm text-muted">
                    {t('modal.create.form.preemption.gracePeriod.suffix')}
                  </span>
                }
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
