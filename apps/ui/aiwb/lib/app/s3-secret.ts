// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { SecretUseCase } from '@amdenterpriseai/types';

import type { CreateSecretRequest } from '@/types/secrets';

export type CreateS3SecretInput = {
  name: string;
  accessKeyId: string;
  secretAccessKey: string;
};

export const createS3SecretRequest = (
  input: CreateS3SecretInput,
): CreateSecretRequest => {
  return {
    displayName: input.name.trim(),
    useCase: SecretUseCase.S3,
    data: {
      accessKeyId: Buffer.from(input.accessKeyId.trim(), 'utf-8').toString(
        'base64',
      ),
      secretAccessKey: Buffer.from(
        input.secretAccessKey.trim(),
        'utf-8',
      ).toString('base64'),
    },
  };
};
