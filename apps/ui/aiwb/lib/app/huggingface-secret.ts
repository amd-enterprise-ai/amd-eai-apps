// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { SecretUseCase } from '@amdenterpriseai/types';
import { CreateSecretRequest } from '@/types/secrets';

export const createHuggingFaceSecretRequest = (
  name: string,
  token: string,
): CreateSecretRequest => {
  return {
    displayName: name,
    useCase: SecretUseCase.HUGGING_FACE,
    data: {
      token: Buffer.from(token, 'utf-8').toString('base64'),
    },
  };
};

/**
 * Validates the format of a HuggingFace token.
 *
 * @param token - The token string to validate
 * @returns `true` if the token matches the HuggingFace format, `false` otherwise
 *
 * @remarks
 * Valid HuggingFace tokens must:
 * - Start with the prefix 'hf_'
 * - Followed by at least 20 alphanumeric characters (uppercase or lowercase)
 *
 * @example
 * ```typescript
 * isValidHuggingFaceToken('hf_abcdefghijklmnopqrstuvwxyz123456'); // true
 * isValidHuggingFaceToken('invalid_token'); // false
 * isValidHuggingFaceToken('hf_short'); // false (too short)
 * ```
 */
export const isValidHuggingFaceToken = (token: string): boolean => {
  const hfTokenPattern = /^hf_[a-zA-Z0-9]{20,}$/;
  return hfTokenPattern.test(token);
};
