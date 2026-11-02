// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import { z } from 'zod';

import type { TFunction } from 'i18next';
import { useTranslation } from 'next-i18next';

import {
  Divider,
  DrawerForm,
  FormInput,
  FormSwitch,
} from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';

import { AutoscalingFormFields } from '@/components/features/models/AutoscalingFormFields';
import { DeployProfileFields } from '@/components/features/models/DeployProfileFields';
import {
  createAimScalingPolicyConfig,
  DEFAULT_AUTOSCALING,
} from '@/lib/app/aims';
import type { CustomProfileResponse } from '@/lib/app/custom-profiles';
import { deployInference } from '@/lib/app/inference';
import type { AIMDeployPayload } from '@/types/aims';
import { Model } from '@/types/models';
import { APIRequestError } from '@amdenterpriseai/utils/app';

type CustomModelDeployPayload = Pick<
  AIMDeployPayload,
  | 'model'
  | 'displayName'
  | 'replicas'
  | 'minReplicas'
  | 'maxReplicas'
  | 'autoScaling'
  | 'profileName'
>;

interface Props {
  model: Model;
  namespace: string;
  /** Source URI of the model weights (AIMModel spec.modelSources[0].sourceUri). */
  sourceUri?: string | null;
  isOpen: boolean;
  onClose: () => void;
  /** Custom-onboarded only: fine-tuned models share this drawer and the API
   * refuses a selection for them. */
  supportsProfileSelection?: boolean;
  /** Profile the deploy was started from, when it began at a specific one. */
  initialProfile?: CustomProfileResponse;
  /**
   * Called after a successful deploy, in addition to the drawer's own
   * invalidation of the canonical aim-services list. Consumers use this to
   * refresh their own view (e.g. the custom-models card grid keyed on a
   * different query) without coupling the drawer to a specific list.
   */
  onDeployed?: () => void;
}

const baseSchema = z.object({
  displayName: z.union([z.literal(''), z.string().min(2).max(253)]).optional(),
  /** AIMProfileSet identifier, or `default`. */
  profileName: z.string().optional(),
  /** Mirrored from the profile list, which is the only thing that knows it. */
  profileReady: z.boolean().optional(),
  autoscalingEnabled: z.boolean(),
  minReplicas: z.number().min(1).max(30).optional(),
  maxReplicas: z.number().min(1).max(30).optional(),
  metricQuery: z.string().optional(),
  operationOverTime: z.string().optional(),
  targetType: z.string().optional(),
  targetValue: z.number().min(1).optional(),
});

type DeployCustomFormValues = z.infer<typeof baseSchema>;

const createFormSchema = (requiresProfile: boolean, t: TFunction<'models'>) =>
  baseSchema.superRefine((data, ctx) => {
    if (
      data.autoscalingEnabled &&
      data.minReplicas &&
      data.maxReplicas &&
      data.minReplicas > data.maxReplicas
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Min replicas must be less than or equal to max replicas',
        path: ['maxReplicas'],
      });
    }
    if (!requiresProfile) {
      return;
    }
    if (!data.profileName) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: t('deployCustomAIMDrawer.fields.profile.errors.required'),
        path: ['profileName'],
      });
    } else if (!data.profileReady) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: t('deployCustomAIMDrawer.fields.profile.errors.notReady'),
        path: ['profileName'],
      });
    }
  });

const buildDeployPayload = (
  model: string,
  data: DeployCustomFormValues,
  withProfile: boolean,
): CustomModelDeployPayload => {
  const payload: CustomModelDeployPayload = {
    model,
    displayName: data.displayName || undefined,
    replicas: 1,
  };
  if (withProfile && data.profileName) {
    payload.profileName = data.profileName;
  }
  if (data.autoscalingEnabled) {
    payload.minReplicas = data.minReplicas;
    payload.maxReplicas = data.maxReplicas;
    payload.autoScaling = createAimScalingPolicyConfig({
      metricQuery: data.metricQuery,
      operationOverTime: data.operationOverTime,
      targetType: data.targetType,
      targetValue: data.targetValue,
    });
  }
  return payload;
};

export const DeployCustomAIMDrawer = ({
  model,
  namespace,
  sourceUri,
  isOpen,
  onClose,
  onDeployed,
  supportsProfileSelection = false,
  initialProfile,
}: Props) => {
  const { t } = useTranslation('models');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const modelResourceName = model.resourceName ?? model.id ?? '';
  const formSchema = useMemo(
    () => createFormSchema(supportsProfileSelection, t),
    [supportsProfileSelection, t],
  );
  const defaultValues = useMemo<DeployCustomFormValues>(
    () => ({
      displayName: '',
      profileName: '',
      profileReady: false,
      autoscalingEnabled: false,
      ...DEFAULT_AUTOSCALING,
    }),
    [],
  );

  const deployMutation = useMutation({
    mutationFn: (data: DeployCustomFormValues) =>
      deployInference(
        namespace,
        buildDeployPayload(modelResourceName, data, supportsProfileSelection),
      ),
    onSuccess: () => {
      toast.success(t('deployCustomAIMDrawer.notifications.success'));
      // FineTuneModels' table reads this key; invalidate it so the deployed
      // AIM services refresh after a successful deploy.
      queryClient.invalidateQueries({
        queryKey: ['project', namespace, 'aim-services'],
      });
      queryClient.invalidateQueries({ queryKey: ['inferenceModel'] });
      onDeployed?.();
      onClose();
    },
    onError: (error: Error) => {
      // Keep the drawer open with the user's values intact so they can retry.
      toast.error(
        t('deployCustomAIMDrawer.notifications.error', {
          message:
            error instanceof APIRequestError ? error.message : 'Unknown error',
        }),
      );
    },
  });

  const handleDeploy = useCallback(
    (data: DeployCustomFormValues) => {
      deployMutation.mutate(data);
    },
    [deployMutation],
  );

  return (
    <DrawerForm<DeployCustomFormValues>
      isOpen={isOpen}
      onCancel={onClose}
      onFormSuccess={handleDeploy}
      onFormFailure={() => {}}
      title={t('deployCustomAIMDrawer.title')}
      confirmText={t('deployCustomAIMDrawer.actions.deploy')}
      cancelText={t('deployCustomAIMDrawer.actions.cancel')}
      validationSchema={formSchema}
      isActioning={deployMutation.isPending}
      isDisabled={deployMutation.isPending}
      hideCloseButton={false}
      defaultValues={defaultValues}
      renderFields={(form) => (
        <div className="flex flex-col gap-4 mt-4">
          <div className="flex flex-col gap-1">
            <p className="text-small text-muted">
              {t('deployCustomAIMDrawer.header.deployingInto', { namespace })}
            </p>
            <div className="text-2xl font-bold">{model.name}</div>
            {model.canonicalName && (
              <p className="text-muted">{model.canonicalName}</p>
            )}
            {sourceUri && (
              <p className="text-small text-muted wrap-break-words mt-1">
                <span className="text-muted">
                  {t('deployCustomAIMDrawer.header.sourceUri')}:
                </span>{' '}
                {sourceUri}
              </p>
            )}
          </div>

          <Divider />

          <FormInput<DeployCustomFormValues>
            name="displayName"
            form={form}
            label={t('deployCustomAIMDrawer.fields.displayName.title')}
            placeholder={t(
              'deployCustomAIMDrawer.fields.displayName.placeholder',
            )}
            description={t('deployCustomAIMDrawer.fields.displayName.helper')}
          />

          {supportsProfileSelection ? (
            <DeployProfileFields
              form={form}
              project={namespace}
              modelId={modelResourceName}
              modelName={model.name}
              initialProfile={initialProfile}
              isDisabled={deployMutation.isPending}
            />
          ) : (
            <div data-testid="runtime-profile-slot" />
          )}

          {/* ====== AUTOSCALING SECTION ====== */}
          <Divider />
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-1">
              <h3 className="text-medium font-medium text-foreground">
                {t('deployCustomAIMDrawer.fields.autoscaling.title')}
              </h3>
            </div>
            <FormSwitch
              form={form}
              name="autoscalingEnabled"
              data-testid="autoscaling-toggle"
              description={t('helper', { ns: 'autoscaling' })}
            >
              {t('deployCustomAIMDrawer.fields.autoscaling.enable')}
            </FormSwitch>
            {form.watch('autoscalingEnabled') && (
              <AutoscalingFormFields
                form={form}
                className="flex flex-col gap-4 pl-1"
              />
            )}
          </div>
        </div>
      )}
    />
  );
};

DeployCustomAIMDrawer.displayName = 'DeployCustomAIMDrawer';
