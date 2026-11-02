// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export const EXTERNAL_SECRETS_API_GROUP = 'external-secrets.io';
export const EXTERNAL_SECRETS_KIND = 'ExternalSecret';
export const KUBERNETES_SECRETS_VERSION = 'v1';
export const KUBERNETES_SECRETS_KIND = 'Secret';

/** Annotation key for submitter (raw K8s annotation key, not camelCase). */
export { SUBMITTER_ANNOTATION as SUBMITTER_ANNOTATION_KEY } from '@/types/artifacts';
