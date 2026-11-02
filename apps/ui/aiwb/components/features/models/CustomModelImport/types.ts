// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { z } from 'zod';

import { MODEL_SOURCE_TYPE } from '@/types/model-import';

/**
 * Base schema for the three-step custom model import wizard.
 *
 * Defines the field shapes without cross-field refinements (which depend on
 * runtime data like the catalog). Refinements are layered on top in the
 * component via superRefine inside useMemo.
 */
export const customModelImportBaseSchema = z.object({
  // Step 1 — Model source. Only the selected source type's credential field is
  // sent; the other is cleared when the user switches between them.
  sourceType: z.enum([MODEL_SOURCE_TYPE.HUGGING_FACE, MODEL_SOURCE_TYPE.S3]),
  source: z.string(),
  hfTokenSecretName: z.string(),
  s3StorageName: z.string(),

  // Step 2 — Model information (display name starts empty per spec)
  displayName: z.string(),
  description: z.string(),
  tagsInput: z.string(),

  // Step 3 — Runtime profile (maps to AIMProfile.spec / profiles.overrides)
  containerImage: z.string(),
  containerVersion: z.string(),
  acceleratorType: z.string(),
  accelerator: z.string(),
  acceleratorCount: z.coerce.number().int(),
  modelPrecision: z.string(),
  engineArgsYaml: z.string(),
  envVarsYaml: z.string(),
});

/**
 * Field values for the three-step custom model import wizard.
 *
 * A single React Hook Form instance owns this entire object; each step
 * validates and edits its own subset of fields. The shape mirrors the
 * generated `OnboardRequest` schema (`components['schemas']['OnboardRequest']`);
 * preview fields and the onboard payload are assembled in the wizard host on
 * submit.
 */
export type CustomModelImportFormValues = z.infer<
  typeof customModelImportBaseSchema
>;

export const DEFAULT_CUSTOM_MODEL_IMPORT_VALUES: CustomModelImportFormValues = {
  sourceType: MODEL_SOURCE_TYPE.HUGGING_FACE,
  source: '',
  hfTokenSecretName: '',
  s3StorageName: '',
  displayName: '',
  description: '',
  tagsInput: '',
  containerImage: '',
  containerVersion: '',
  acceleratorType: 'gpu',
  accelerator: '',
  acceleratorCount: 1,
  modelPrecision: 'bf16',
  engineArgsYaml: '',
  envVarsYaml: '',
};
