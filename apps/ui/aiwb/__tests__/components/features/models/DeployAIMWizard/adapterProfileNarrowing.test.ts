// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import {
  resolveEffectivePrecision,
  selectCandidateAdapterProfiles,
} from '@/components/features/models/DeployAIMWizard/DeployAIMWizard';
import {
  PERFORMANCE_MODE_ADVANCED,
  type DeployAIMFormValues,
} from '@/components/features/models/DeployAIMWizard/types';
import { ADVANCED_PARAM_AUTOMATIC } from '@/lib/app/aims/filterProfilesByAdvancedParams';
import type { AIMClusterProfile } from '@/types/aims';
import type { LoraAdapter } from '@/types/artifacts';

// The catalog groups every quantised variant of a model under one aimId, while
// each profile loads one specific set of weights.
const CATALOG_AIM_ID = 'example-org/base-model';
const FP16_MODEL_ID = 'example-org/base-model-fp16';
const FP8_MODEL_ID = 'example-org/base-model-fp8';

const profile = (
  name: string,
  modelId: string,
  precision: string,
): AIMClusterProfile =>
  ({
    metadata: { name, labels: {} },
    spec: {
      aimId: CATALOG_AIM_ID,
      modelId,
      precision,
      metric: 'latency',
      acceleratorModel: 'MI300X',
      acceleratorCount: 1,
      features: ['adapters'],
    },
    status: { status: 'Ready' },
  }) as unknown as AIMClusterProfile;

const fp16Profile = profile('profile-fp16', FP16_MODEL_ID, 'fp16');
const fp8Profile = profile('profile-fp8', FP8_MODEL_ID, 'fp8');
const adapterCapableProfiles = [fp16Profile, fp8Profile];

const adapter = (name: string, compatibleWith: string[]): LoraAdapter =>
  ({
    id: name,
    name,
    displayName: name,
    compatibleWith,
    rank: 16,
    readiness: 'Ready',
  }) as LoraAdapter;

const fp16Adapter = adapter('fp16-adapter', [FP16_MODEL_ID]);
const fp8Adapter = adapter('fp8-adapter', [FP8_MODEL_ID]);
const pendingAdapter = {
  ...adapter('pending-adapter', [FP8_MODEL_ID]),
  readiness: 'NotReady',
} as LoraAdapter;

const values = (
  overrides: Partial<DeployAIMFormValues> = {},
): DeployAIMFormValues =>
  ({
    performanceMode: PERFORMANCE_MODE_ADVANCED,
    profileName: ADVANCED_PARAM_AUTOMATIC,
    optimizationClass: ADVANCED_PARAM_AUTOMATIC,
    gpuModel: ADVANCED_PARAM_AUTOMATIC,
    precision: ADVANCED_PARAM_AUTOMATIC,
    gpuCount: ADVANCED_PARAM_AUTOMATIC,
    ...overrides,
  }) as DeployAIMFormValues;

const precisions = (all: string[], adapterCapable: string[] = all) => ({
  all,
  adapterCapable,
});

describe('resolveEffectivePrecision', () => {
  it('keeps the precision the user pinned', () => {
    expect(
      resolveEffectivePrecision(
        values({ precision: 'fp16' }),
        'fp8',
        precisions(['fp8', 'fp16']),
      ),
    ).toBe('fp16');
  });

  it('substitutes the preferred precision while the choice is automatic', () => {
    expect(
      resolveEffectivePrecision(values(), 'fp8', precisions(['fp8', 'fp16'])),
    ).toBe('fp8');
  });

  it('leaves the precision open when the preferred one is not published', () => {
    expect(
      resolveEffectivePrecision(values(), 'fp8', precisions(['fp16'])),
    ).toBeUndefined();
  });

  it('leaves the precision open when the model prefers none', () => {
    expect(
      resolveEffectivePrecision(
        values(),
        undefined,
        precisions(['fp8', 'fp16']),
      ),
    ).toBeUndefined();
  });

  it('ignores a stale form value when a metric drives the choice', () => {
    // The precision control is not rendered outside advanced mode, so a value
    // left behind there is not a choice the user made.
    expect(
      resolveEffectivePrecision(
        values({ performanceMode: 'latency', precision: 'fp16' }),
        'fp8',
        precisions(['fp8', 'fp16']),
      ),
    ).toBe('fp8');
  });

  it('ignores a preferred precision no adapter-capable profile publishes', () => {
    // Personalization restricts the Performance step to adapter-capable
    // profiles, so a precision only a non-adapter profile publishes is one the
    // user was never offered and cannot change.
    expect(
      resolveEffectivePrecision(
        values({ personalizationEnabled: true }),
        'fp8',
        precisions(['fp8', 'fp16'], ['fp16']),
      ),
    ).toBeUndefined();
  });

  it('still substitutes the preferred precision without personalization', () => {
    expect(
      resolveEffectivePrecision(
        values({ personalizationEnabled: false }),
        'fp8',
        precisions(['fp8', 'fp16'], ['fp16']),
      ),
    ).toBe('fp8');
  });
});

describe('selectCandidateAdapterProfiles', () => {
  it('keeps every adapter-capable profile while the choices are automatic', () => {
    expect(
      selectCandidateAdapterProfiles(adapterCapableProfiles, values()),
    ).toEqual(adapterCapableProfiles);
  });

  it('narrows to the precision the user picked', () => {
    expect(
      selectCandidateAdapterProfiles(
        adapterCapableProfiles,
        values({ precision: 'fp8' }),
        'fp8',
      ),
    ).toEqual([fp8Profile]);
  });

  it('narrows to the preferred precision while the choice is automatic', () => {
    // Automatic is not open-ended: submit pins the preferred precision, so a
    // candidate set that ignored it would keep offering the sibling variant's
    // adapters until the deploy failed to load them.
    expect(
      selectCandidateAdapterProfiles(
        adapterCapableProfiles,
        values({ performanceMode: 'latency' }),
        resolveEffectivePrecision(
          values({ performanceMode: 'latency' }),
          'fp8',
          precisions(['fp8', 'fp16']),
        ),
      ),
    ).toEqual([fp8Profile]);
  });

  it('narrows to an explicitly pinned profile', () => {
    expect(
      selectCandidateAdapterProfiles(
        adapterCapableProfiles,
        values({ profileName: 'profile-fp16' }),
      ),
    ).toEqual([fp16Profile]);
  });

  it('ignores the advanced fields when a metric drives the choice', () => {
    // Outside advanced mode the precision control is not in play, so a stale
    // value left on the form must not narrow anything.
    expect(
      selectCandidateAdapterProfiles(
        adapterCapableProfiles,
        values({ performanceMode: 'latency', precision: 'fp8' }),
      ),
    ).toEqual(adapterCapableProfiles);
  });

  it('narrows by metric outside advanced mode', () => {
    expect(
      selectCandidateAdapterProfiles(
        adapterCapableProfiles,
        values({ performanceMode: 'throughput' }),
      ),
    ).toEqual([]);
  });
});
