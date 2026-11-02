// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

export const ARTIFACT_DESCRIPTION_ANNOTATION =
  'aiwb.apps.eai.amd.com/description';
export const SUBMITTER_ANNOTATION = 'airm.silogen.ai/submitter';
export const MAX_LORA_ADAPTERS = 64;

export type LoraAdapter = {
  id: string;
  name: string;
  displayName: string;
  description?: string;
  compatibleWith: string[];
  status?: components['schemas']['AIMArtifactStatusFields']['status'];
  readiness: components['schemas']['ReadinessState'];
  createdAt?: string | null;
  createdBy?: string;
} & Pick<components['schemas']['ArtifactResponse'], 'servable'> &
  Pick<components['schemas']['AIMArtifactSpec'], 'modelId' | 'rank'> &
  Pick<components['schemas']['ArtifactStorage'], 'uri'>;
