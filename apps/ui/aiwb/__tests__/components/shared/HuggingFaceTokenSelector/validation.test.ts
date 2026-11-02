// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import { createCreateTokenSchema } from '@/components/shared/HuggingFaceTokenSelector/validation';

const validationLabels = {
  nameRequired: 'Name is required when entering a new token',
  invalidSecretName:
    "The secret name must be lowercase alphanumeric characters, '-' or '.', and must start and end with an alphanumeric character",
  tokenRequired: 'Token is required when entering a new token',
  invalidTokenFormat:
    "Please enter a valid Hugging Face token (starts with 'hf_')",
  duplicateName: 'A secret with this name already exists.',
};

const validToken = 'hf_abcdefghijklmnopqrstuvwxyz123456';

const existingTokens = [
  { name: 'k8s-secret-a', displayName: 'token-1-hf' },
  { name: 'k8s-secret-b', displayName: 'token-2-hf' },
];

const parse = (name: string, token: string, tokens = existingTokens) => {
  const schema = createCreateTokenSchema(validationLabels, tokens);
  return schema.safeParse({ name, token });
};

describe('createCreateTokenSchema', () => {
  it('passes for a valid name and token', () => {
    const result = parse('my-new-token', validToken);
    expect(result.success).toBe(true);
  });

  it('reports invalidTokenFormat when token lacks hf_ prefix or is too short', () => {
    const result = parse('my-new-token', 'not-a-token');
    expect(result.success).toBe(false);
    if (!result.success) {
      const tokenIssue = result.error.issues.find((i) => i.path[0] === 'token');
      expect(tokenIssue?.message).toBe(validationLabels.invalidTokenFormat);
    }
  });

  it('reports invalidSecretName for invalid K8s names', () => {
    const result = parse('Invalid-Name', validToken);
    expect(result.success).toBe(false);
    if (!result.success) {
      const nameIssue = result.error.issues.find((i) => i.path[0] === 'name');
      expect(nameIssue?.message).toBe(validationLabels.invalidSecretName);
    }
  });

  it('reports duplicateName when displayName already exists', () => {
    const result = parse('token-1-hf', validToken);
    expect(result.success).toBe(false);
    if (!result.success) {
      const nameIssue = result.error.issues.find((i) => i.path[0] === 'name');
      expect(nameIssue?.message).toBe(validationLabels.duplicateName);
    }
  });

  it('matches displayName only, not metadata name', () => {
    const sameMetadataDifferentDisplay = parse(
      'unique-display-name',
      validToken,
      [{ name: 'token-1-hf', displayName: 'other-label' }],
    );
    expect(sameMetadataDifferentDisplay.success).toBe(true);

    const sameDisplayDifferentMetadata = parse('token-1-hf', validToken, [
      { name: 'different-k8s-name', displayName: 'token-1-hf' },
    ]);
    expect(sameDisplayDifferentMetadata.success).toBe(false);
  });
});
