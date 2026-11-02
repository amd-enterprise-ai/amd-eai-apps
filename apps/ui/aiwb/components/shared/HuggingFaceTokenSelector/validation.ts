// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { z } from 'zod';

import { isValidHuggingFaceToken } from '@/lib/app/huggingface-secret';
import { isValidK8sDnsSubdomain } from '@/lib/app/k8s-names';

import type { HuggingFaceTokenOption } from './HuggingFaceTokenSelector';

export type CreateTokenForm = {
  name: string;
  token: string;
};

export type HuggingFaceTokenValidationLabels = {
  nameRequired: string;
  invalidSecretName: string;
  tokenRequired: string;
  invalidTokenFormat: string;
  duplicateName: string;
};

export const createCreateTokenSchema = (
  validation: HuggingFaceTokenValidationLabels,
  existingTokens: HuggingFaceTokenOption[],
) =>
  z
    .object({
      name: z.string(),
      token: z.string(),
    })
    .superRefine((data, ctx) => {
      const name = data.name.trim();
      const token = data.token.trim();

      if (!name) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: validation.nameRequired,
          path: ['name'],
        });
      } else if (!isValidK8sDnsSubdomain(name)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: validation.invalidSecretName,
          path: ['name'],
        });
      } else if (
        existingTokens.some((existing) => existing.displayName.trim() === name)
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: validation.duplicateName,
          path: ['name'],
        });
      }

      if (!token) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: validation.tokenRequired,
          path: ['token'],
        });
      } else if (!isValidHuggingFaceToken(token)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: validation.invalidTokenFormat,
          path: ['token'],
        });
      }
    });
