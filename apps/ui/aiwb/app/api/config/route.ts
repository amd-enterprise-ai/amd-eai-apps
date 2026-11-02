// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NextResponse } from 'next/server';

import { isHttpUrl } from '@amdenterpriseai/utils/app';

export async function GET() {
  const isStandaloneMode =
    (process.env.STANDALONE_MODE ?? '').trim().toLowerCase() === 'true';
  const rawAirmAppUrl = process.env.AIRM_APP_URL?.trim();
  const airmAppUrl =
    rawAirmAppUrl && isHttpUrl(rawAirmAppUrl) ? rawAirmAppUrl : undefined;
  const aiGatewayEnabled =
    (process.env.AI_GATEWAY_ENABLED ?? 'true').trim().toLowerCase() !== 'false';
  // Gates the API-keys page/menu. Generic feature flag (replaces the old
  // CLUSTER_AUTH_ENABLED gate now that the key store is cluster-auth-free).
  const apiKeysManagementEnabled =
    (process.env.API_KEYS_MANAGEMENT_ENABLED ?? 'true').trim().toLowerCase() !==
    'false';
  const rawAiGatewayUrl = process.env.AI_GATEWAY_URL?.trim();
  const aiGatewayUrl =
    rawAiGatewayUrl && isHttpUrl(rawAiGatewayUrl) ? rawAiGatewayUrl : undefined;
  const config: {
    isStandaloneMode: boolean;
    defaultNamespace: string | null;
    apiKeysManagementEnabled: boolean;
    aiGatewayEnabled: boolean;
    aiGatewayUrl?: string;
    airmAppUrl?: string;
  } = {
    isStandaloneMode,
    defaultNamespace: process.env.DEFAULT_NAMESPACE?.trim() ?? null,
    apiKeysManagementEnabled,
    aiGatewayEnabled,
  };
  if (aiGatewayUrl) {
    config.aiGatewayUrl = aiGatewayUrl;
  }
  if (!isStandaloneMode && airmAppUrl) {
    config.airmAppUrl = airmAppUrl;
  }
  return NextResponse.json({ config });
}
