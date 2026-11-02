// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

// Wire shapes are sourced from the generated OpenAPI schema so the FE can never
// drift from the backend. `metadata.namespace` and `useCase` are nullable here
// (K8s metadata / label-derived), so consumers must tolerate null/undefined.
export type SecretResponseData = components['schemas']['SecretResponse'];

export type CreateSecretRequest = components['schemas']['SecretCreate'];
