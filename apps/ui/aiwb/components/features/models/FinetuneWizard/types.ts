// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { z } from 'zod';

import type { FinetunableModel, Model } from '@/types/models';

export const MAX_FINETUNE_DATASETS = 10;
export const MAX_DISPLAY_NAME_LENGTH = 255;
export const MAX_DESCRIPTION_LENGTH = 2048;
export const FINE_TUNING_TYPES = ['full', 'merged', 'lora'] as const;

const stripNonAlphanumericEdges = (value: string): string =>
  value.replace(/^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$/g, '');

export const sanitizeModelNameLabel = (value: string, maxLength = 63): string =>
  stripNonAlphanumericEdges(
    stripNonAlphanumericEdges(
      value.replace(/[ /]/g, '-').replace(/[^a-zA-Z0-9\-_.]/g, ''),
    ).slice(0, maxLength),
  );

export type FineTuningType = (typeof FINE_TUNING_TYPES)[number];

const findRecipe = (
  finetunableModels: FinetunableModel[],
  canonicalName: string | undefined,
  model: Model | undefined,
): FinetunableModel | undefined =>
  finetunableModels.find(
    (candidate) =>
      candidate.canonicalName === (canonicalName || model?.canonicalName),
  );

export const getEnabledFineTuningTypes = (
  trainingType: FinetunableModel['trainingType'],
  // `undefined` means the base model's adapter capability is unknown, which is
  // not the same as absent: only a published "no" withdraws LoRA, so a model
  // whose profiles say nothing keeps the option the API would still accept.
  canServeAdapters?: boolean,
): FineTuningType[] => {
  if (trainingType !== 'lora') return ['full'];
  return canServeAdapters === false ? ['merged'] : ['merged', 'lora'];
};

export const finetuneBaseSchema = z.object({
  canonicalName: z.string().default(''),
  hfTokenSecretName: z.string().default(''),
  fineTuningType: z.enum(FINE_TUNING_TYPES),
  datasetIds: z.array(z.string()).default([]),
  displayName: z.string(),
  description: z.string(),
  customizeHyperparameters: z.boolean(),
  batchSize: z.number().int().optional(),
  epochs: z.number().int().optional(),
  learningRate: z.number().optional(),
  loraRank: z.number().int().optional(),
  loraAlpha: z.number().int().optional(),
  loraDropout: z.number().optional(),
});

export type FinetuneFormValues = z.infer<typeof finetuneBaseSchema>;

export const DEFAULT_FINETUNE_VALUES: FinetuneFormValues = {
  canonicalName: '',
  hfTokenSecretName: '',
  fineTuningType: 'full',
  datasetIds: [],
  displayName: '',
  description: '',
  customizeHyperparameters: false,
  batchSize: undefined,
  epochs: undefined,
  learningRate: undefined,
  loraRank: undefined,
  loraAlpha: undefined,
  loraDropout: undefined,
};

export const getRecipeGpuCount = (
  finetunableModels: FinetunableModel[],
  canonicalName: string | undefined,
  model: Model | undefined,
): number | undefined =>
  findRecipe(finetunableModels, canonicalName, model)?.gpuCount || undefined;

export const getModelTrainingType = (
  finetunableModels: FinetunableModel[],
  canonicalName: string | undefined,
  model: Model | undefined,
): FinetunableModel['trainingType'] =>
  findRecipe(finetunableModels, canonicalName, model)?.trainingType ?? 'full';

export const getRecipeHyperparameters = (
  finetunableModels: FinetunableModel[],
  canonicalName: string | undefined,
  model: Model | undefined,
) => findRecipe(finetunableModels, canonicalName, model)?.hyperparameters;

export const isBaseModelGated = (
  finetunableModels: FinetunableModel[],
  canonicalName: string | undefined,
  model: Model | undefined,
): boolean => {
  if (model?.hfTokenRequired != null) return model.hfTokenRequired;
  return (
    findRecipe(finetunableModels, canonicalName, model)?.hfTokenRequired ===
    true
  );
};
