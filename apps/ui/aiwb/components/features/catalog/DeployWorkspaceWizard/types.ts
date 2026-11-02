// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export interface DeployWorkspaceFormValues {
  displayName: string;
  containerImage?: string;
  /** Comma-joined while editing (FormSelect multi-select); an array once parsed. */
  imagePullSecrets?: string | string[];
  customizeResources: boolean;
  gpus?: number;
  memoryPerGpu?: number;
  cpuPerGpu?: number;
}
