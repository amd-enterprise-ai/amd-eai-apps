// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

// Re-export the generated schema types as the single source of truth. The
// backend marks repository/tags/acceleratorModel optional, so consumers must
// tolerate `undefined` (see runtimeProfileCatalog helpers).
export type AimImageFamily = components['schemas']['AimImageFamily'];

export type ClusterAccelerator = components['schemas']['ClusterAccelerator'];
