// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { getCustomModel } from '@/lib/app/custom-models';
import { getProjectFineTunedModel } from '@/lib/app/aims';
import { getInferenceModel } from '@/lib/app/inference';
import {
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
  type AIMService,
} from '@/types/aims';

export type DeploymentModelKind = 'fine-tuned' | 'custom' | 'base';

/**
 * Determines which model endpoint resolves a deployment's canonical aimId.
 * Two deployments can share a model name while resolving to different models
 * depending on these labels, so callers should key any cache/query on the
 * kind alongside the name.
 */
export const getDeploymentModelKind = (
  labels: Record<string, string | undefined>,
): DeploymentModelKind =>
  labels[FINE_TUNED_LABEL] === 'true'
    ? 'fine-tuned'
    : labels[NAMESPACE_AIM_MODEL_LABEL] === 'true'
      ? 'custom'
      : 'base';

/**
 * Resolves the canonical aimId backing a deployment, regardless of whether
 * it deploys a cluster-scoped base model or a project-scoped fine-tuned/BYOM
 * model. The aimId identifies the deployed model and scopes which profile
 * catalogs to fetch for it. It is not the primary adapter-compatibility key:
 * one aimId groups every quantised variant of a model, so adapters are matched
 * against the serving profile's `modelId` first and only fall back to its aimId
 * — see `lib/app/aims/adapterCompatibility`.
 */
export const resolveDeploymentAimId = async (
  namespace: string,
  deployment: AIMService,
): Promise<string | undefined> => {
  const modelName = deployment.spec?.model?.name;
  if (!modelName) return undefined;
  const kind = getDeploymentModelKind(deployment.metadata.labels ?? {});
  const model =
    kind === 'fine-tuned'
      ? await getProjectFineTunedModel(modelName, namespace)
      : kind === 'custom'
        ? await getCustomModel(namespace, modelName)
        : await getInferenceModel(modelName);
  return model.status?.aimId ?? model.spec?.aimId ?? undefined;
};
