// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Stable entry point for backend API types. Import from '@/types/api' rather
// than the generated file directly, e.g. components['schemas']['SomeResponse'].
export type { components, paths, operations } from './api.generated';
