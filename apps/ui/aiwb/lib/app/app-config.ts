// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { APIRequestError } from '@amdenterpriseai/utils/app';

export interface AppConfig {
  isStandaloneMode: boolean;
  defaultNamespace: string | null;
  apiKeysManagementEnabled: boolean;
  aiGatewayEnabled: boolean;
  aiGatewayUrl?: string;
  airmAppUrl?: string;
}

export const getAppConfig = async (): Promise<AppConfig> => {
  const response = await fetch('/api/config');
  if (!response.ok) {
    throw new APIRequestError('Failed to fetch app config', response.status);
  }
  const data = await response.json();
  return data.config;
};
