// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it, vi } from 'vitest';

import { createTargetStepSchema } from '@/components/features/models/FinetuneWizard/steps/TargetStep';
import {
  MAX_DESCRIPTION_LENGTH,
  MAX_DISPLAY_NAME_LENGTH,
  sanitizeModelNameLabel,
} from '@/components/features/models/FinetuneWizard/types';

const values = {
  displayName: 'fine-tuned-model',
  description: '',
  fineTuningType: 'full' as const,
};

describe('createTargetStepSchema', () => {
  const createSchema = (checkNameAvailable = vi.fn().mockResolvedValue(true)) =>
    createTargetStepSchema({
      requiredMessage: 'required',
      tooLongMessage: 'too long',
      descriptionTooLongMessage: 'description too long',
      duplicateModelMessage: 'duplicate model',
      duplicateLoraMessage: 'duplicate LoRA',
      checkNameAvailable,
    });

  it('requires a model name', async () => {
    expect(
      (await createSchema().safeParseAsync({ ...values, displayName: '' }))
        .success,
    ).toBe(false);
  });

  it('limits model names to 255 characters', async () => {
    const schema = createSchema();

    expect(
      (
        await schema.safeParseAsync({
          ...values,
          displayName: 'a'.repeat(MAX_DISPLAY_NAME_LENGTH),
        })
      ).success,
    ).toBe(true);
    expect(
      (
        await schema.safeParseAsync({
          ...values,
          displayName: 'a'.repeat(MAX_DISPLAY_NAME_LENGTH + 1),
        })
      ).success,
    ).toBe(false);
  });

  it('requires a unique model name', async () => {
    const result = await createSchema(
      vi.fn().mockResolvedValue(false),
    ).safeParseAsync(values);

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toBe('duplicate model');
    }
  });

  it('uses the LoRA duplicate-name message for adapters', async () => {
    const result = await createSchema(
      vi.fn().mockResolvedValue(false),
    ).safeParseAsync({ ...values, fineTuningType: 'lora' });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toBe('duplicate LoRA');
    }
  });

  it('limits descriptions to 2,048 characters', async () => {
    const schema = createSchema();

    expect(
      (
        await schema.safeParseAsync({
          ...values,
          description: 'a'.repeat(MAX_DESCRIPTION_LENGTH),
        })
      ).success,
    ).toBe(true);
    expect(
      (
        await schema.safeParseAsync({
          ...values,
          description: 'a'.repeat(MAX_DESCRIPTION_LENGTH + 1),
        })
      ).success,
    ).toBe(false);
  });
});

describe('sanitizeModelNameLabel', () => {
  it('matches Kubernetes label sanitization', () => {
    expect(sanitizeModelNameLabel(' /Fine tuned! model._ ')).toBe(
      'Fine-tuned-model',
    );
    expect(sanitizeModelNameLabel(`${'-'.repeat(64)}model`)).toBe('model');
    expect(sanitizeModelNameLabel('a'.repeat(64))).toHaveLength(63);
  });
});
