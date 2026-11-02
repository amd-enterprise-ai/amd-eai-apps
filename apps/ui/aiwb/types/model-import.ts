// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';
import type { ModelOnboardingStatus } from '@/types/models';

/** Preview success body returned by the BFF, sourced from the backend schema. */
export type ModelSourcePreviewResponse =
  components['schemas']['PreviewResponse'];

/** Source family a custom model is imported from. */
export type ModelSourceType = components['schemas']['CustomModelImportType'];

export const MODEL_SOURCE_TYPE = {
  HUGGING_FACE: 'huggingFace',
  S3: 's3',
} as const satisfies Record<string, ModelSourceType>;

/**
 * Runtime profile overrides forwarded on onboard using v1alpha2 AIMProfile.spec
 * field names. Today this travels on `customProfile`; the API may later accept
 * nested `profiles.overrides` directly.
 */
export interface ModelCustomProfile {
  imageFamilyId?: string;
  image?: string;
  acceleratorType?: string;
  acceleratorModel?: string;
  acceleratorCount?: number;
  precision?: string;
  /** Inference-engine CLI args as a free-form object (aim-engine `engineArgs`). */
  engineArgs?: Record<string, unknown>;
  /**
   * Inference-engine env vars as `[{name, value}]` entries. Env var names are
   * UPPER_SNAKE_CASE, so they ride as values (not keys) to stay outside the
   * camelCase contract; the server collapses them into the aim-engine
   * `engineEnv` map.
   */
  engineEnv?: EngineEnvEntry[];
}

/** A single inference-engine environment variable as a name/value pair. */
export interface EngineEnvEntry {
  name: string;
  value: string;
}

/** Onboarding status response (envelope unwrapped). */
export interface ModelOnboardingStatusResponse {
  onboardingStatus: ModelOnboardingStatus;
  phase?: string;
  percentComplete?: number;
  lastError?: string | null;
  modelWeightsPath?: string | null;
}
