// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { SecretResponseData } from '@/types/secrets';

/**
 * Normalizes a multi-select secret field to a list of secret names. FormSelect
 * stores multi-select selections as a comma-joined string, while parsed form
 * values and defaults hold an array.
 */
export const toSecretNames = (value?: string | string[]): string[] =>
  (Array.isArray(value) ? value : (value ?? '').split(',')).filter(Boolean);

/** Resolves secret names to the display names users gave them, falling back to the name. */
export const toSecretDisplayNames = (
  names: string[],
  secrets: SecretResponseData[],
): string[] =>
  names.map(
    (name) =>
      secrets.find((secret) => secret.metadata.name === name)?.displayName ??
      name,
  );
