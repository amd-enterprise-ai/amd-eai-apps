// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useEffect } from 'react';
import type { UseFormReturn } from 'react-hook-form';

import type { FinetunableModel, Model } from '@/types/models';

import {
  getEnabledFineTuningTypes,
  getModelTrainingType,
  type FinetuneFormValues,
} from './types';
import { useAdapterServingSupport } from './useAdapterServingSupport';

export const useValidFineTuningType = (
  form: UseFormReturn<FinetuneFormValues>,
  finetunableModels: FinetunableModel[],
  model: Model | undefined,
) => {
  const canonicalName = form.watch('canonicalName');
  const trainingType = getModelTrainingType(
    finetunableModels,
    canonicalName,
    model,
  );
  // Also covers switching base model after picking LoRA: the capability is
  // re-read for the new model, so a selection that just became invalid moves.
  const canServeAdapters = useAdapterServingSupport(
    canonicalName,
    model,
    trainingType,
  );
  const isEnabled = getEnabledFineTuningTypes(
    trainingType,
    canServeAdapters,
  ).includes(form.watch('fineTuningType'));

  useEffect(() => {
    // React Hook Form restores defaults when a controlled field re-registers.
    if (isEnabled) return;
    form.setValue(
      'fineTuningType',
      trainingType === 'lora' ? 'merged' : 'full',
    );
  }, [form, isEnabled, trainingType]);
};
