// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Alert } from '@amdenterpriseai/components';
import type { TFunction } from 'i18next';

import {
  formatGpuPreemptionIdleTimerFromSeconds,
  formatGpuPreemptionThresholdPercent,
  gpuPreemptionPolicyDisplayLabel,
} from '@/utils/gpu-preemption';
import type { GpuPreemptionReadOnlyConfig } from '@/types/projects';

export interface ProjectGpuPreemptionReadOnlyProps {
  config: GpuPreemptionReadOnlyConfig;
  t: TFunction;
}

export function ProjectGpuPreemptionReadOnly({
  config,
  t,
}: ProjectGpuPreemptionReadOnlyProps) {
  return (
    <section
      id="workload-preemption-readonly"
      className="border-t border-default pt-4 mt-2"
    >
      <h3 className="text-sm font-semibold text-foreground mb-3">
        {t('modal.create.form.preemption.sectionTitle')}
      </h3>
      <Alert status="accent" className="w-full">
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex flex-row flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-medium text-foreground">
              {t('modal.create.form.preemption.toggle')}
              {': '}
            </span>
            <span className="text-foreground">
              {config.enabled
                ? t('settings.form.basicInfo.preemption.readonly.enabled')
                : t('settings.form.basicInfo.preemption.readonly.disabled')}
            </span>
          </div>
          {config.enabled ? (
            <dl className="m-0 flex flex-col gap-3">
              <div className="flex min-w-0 flex-row flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <dt className="m-0 shrink-0 font-medium text-foreground">
                  {`${t('modal.create.form.preemption.policy.label')}: `}
                </dt>
                <dd className="m-0 text-foreground">
                  {gpuPreemptionPolicyDisplayLabel(config.policy, t)}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
                <div className="flex min-w-0 flex-row flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <dt className="m-0 shrink-0 font-medium text-foreground">
                    {`${t('modal.create.form.preemption.threshold.label')}: `}
                  </dt>
                  <dd className="m-0 text-foreground">
                    {formatGpuPreemptionThresholdPercent(config.threshold)}
                  </dd>
                </div>
                <div className="flex min-w-0 flex-row flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <dt className="m-0 shrink-0 font-medium text-foreground">
                    {`${t('modal.create.form.preemption.gracePeriod.label')}: `}
                  </dt>
                  <dd className="m-0 text-foreground">
                    {formatGpuPreemptionIdleTimerFromSeconds(
                      config.gracePeriod,
                      t,
                    )}
                  </dd>
                </div>
              </div>
            </dl>
          ) : (
            <p className="text-foreground m-0">
              {t(
                'settings.form.basicInfo.preemption.readonly.bannerDescriptionDisabled',
              )}
            </p>
          )}
        </div>
      </Alert>
    </section>
  );
}
