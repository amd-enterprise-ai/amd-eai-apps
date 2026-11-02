// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

export enum ModelOnboardingStatus {
  READY = 'ready',
  PENDING = 'pending',
  FAILED = 'failed',
}

type FineTuningJobRequest = components['schemas']['FineTuningJobRequest'];
type OptionalFinetuneField =
  | 'description'
  | 'epochs'
  | 'learningRate'
  | 'batchSize'
  | 'hfTokenSecretName'
  | 'output'
  | 'lora';

export type ModelFinetuneParams = Pick<
  FineTuningJobRequest,
  'displayName' | 'datasetIds'
> & {
  [Key in OptionalFinetuneField]?: NonNullable<FineTuningJobRequest[Key]>;
};

export interface Model {
  id?: string;
  name: string;
  canonicalName: string;
  createdAt?: string;
  onboardingStatus?: ModelOnboardingStatus;
  createdBy?: string;
  /** Source URI of the model weights. */
  sourceUri?: string | null;
  /** Kubernetes resource name (AIMModel CR name or fine-tuning Job name). */
  resourceName?: string;
  /** WorkloadStatus value for K8s-sourced models (e.g., 'Pending', 'Running', 'Complete'). */
  status?: string;
  /** Workload UUID tracked in AIWB. */
  workloadId?: string;
  /** Whether fine-tuning this model needs a Hugging Face token. */
  hfTokenRequired?: boolean | null;
}

export interface InferenceSettings {
  systemPrompt: string;
  temperature: number;
  frequencyPenalty: number;
  presencePenalty: number;
}

type FinetunableModelResponse =
  components['schemas']['FinetunableModelResponse'];

/** API model normalized with defaults for fields the backend may omit. */
export type FinetunableModel = Required<
  Omit<FinetunableModelResponse, 'hfTokenRequired'>
> &
  Pick<FinetunableModelResponse, 'hfTokenRequired'>;

export const DEFAULT_SETTINGS: InferenceSettings = {
  systemPrompt: '',
  temperature: 0,
  frequencyPenalty: 0,
  presencePenalty: 0,
};
