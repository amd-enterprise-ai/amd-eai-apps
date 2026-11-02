// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * General workload settings drawer.
 * Currently supports autoscaling configuration, can be extended for other settings.
 */

import { useTranslation } from 'next-i18next';
import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { DrawerForm } from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';
import {
  createAimScalingPolicyConfig,
  DEFAULT_AUTOSCALING,
  AIM_MAX_REPLICAS,
} from '@/lib/app/aims';
import type { AutoscalingFieldValues } from '@/lib/app/aims';
import { updateInferenceScaling } from '@/lib/app/inference';
import { z } from 'zod';

import { AutoscalingFormFields } from '../models/AutoscalingFormFields';

const formSchema = z.object({
  minReplicas: z.number().min(1).max(AIM_MAX_REPLICAS),
  maxReplicas: z.number().min(1).max(AIM_MAX_REPLICAS),
  metricQuery: z.string(),
  operationOverTime: z.string(),
  targetType: z.string(),
  targetValue: z.number().min(1),
});

interface Props {
  isOpen: boolean;
  onClose?: () => void;
  onSuccess?: (savedValues: AutoscalingFieldValues) => void;
  namespace?: string;
  id?: string;
  /** Initial values for the form. */
  initialValues?: AutoscalingFieldValues;
}

export const DeploymentSettingsDrawer = ({
  isOpen,
  onClose,
  onSuccess,
  namespace,
  id,
  initialValues = DEFAULT_AUTOSCALING,
}: Props) => {
  const { t } = useTranslation('autoscaling');
  const { toast } = useSystemToast();
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async (data: AutoscalingFieldValues) => {
    if (!namespace || !id) {
      toast.error(t('notifications.noWorkloadId'));
      return;
    }

    setIsSaving(true);

    try {
      // Build the nested autoScaling structure from flat form values
      const payload = {
        minReplicas: data.minReplicas,
        maxReplicas: data.maxReplicas,
        autoScaling: createAimScalingPolicyConfig({
          metricQuery: data.metricQuery,
          operationOverTime: data.operationOverTime,
          targetType: data.targetType,
          targetValue: data.targetValue,
        }),
      };
      await updateInferenceScaling(namespace, id, payload);
      toast.success(t('notifications.updateSuccess'));
      if (onSuccess) onSuccess(data);
      if (onClose) onClose();
    } catch (error) {
      toast.error(t('notifications.updateError'));
      console.error('Failed to update workload scaling:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const renderFormFields = (form: UseFormReturn<AutoscalingFieldValues>) => {
    return (
      <div className="flex flex-col gap-5">
        <p className="text-sm text-muted">{t('description')}</p>
        <AutoscalingFormFields form={form} className="flex flex-col gap-5" />
      </div>
    );
  };

  return (
    <DrawerForm<AutoscalingFieldValues>
      data-testid="deployment-settings-drawer"
      isOpen={isOpen}
      onCancel={onClose}
      onFormSuccess={handleSave}
      title={t('settingsTitle')}
      confirmText={t('actions.save')}
      cancelText={t('actions.cancel')}
      validationSchema={formSchema}
      isActioning={isSaving}
      defaultValues={initialValues}
      renderFields={renderFormFields}
    />
  );
};

export default DeploymentSettingsDrawer;
