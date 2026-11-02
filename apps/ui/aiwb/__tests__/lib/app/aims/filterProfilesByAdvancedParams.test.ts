// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ADVANCED_PARAM_AUTOMATIC,
  filterProfilesByAdvancedParams,
} from '@/lib/app/aims/filterProfilesByAdvancedParams';
import { AIMClusterProfile, AIM_PROFILE_TYPE_OPTIMIZED } from '@/types/aims';

type LegacyMeta = {
  metric?: string;
  type?: string;
  gpu?: string;
  gpuCount?: number;
  precision?: string;
};

/**
 * Builds an AIMClusterProfile fixture from a legacy v1alpha1-style metadata
 * shape. Centralized here so individual cases keep the readable old field
 * names while the fixture maps them to the v1alpha2 spec layout.
 */
function makeProfile(
  name: string,
  meta: LegacyMeta,
  specMetric: 'latency' | 'throughput' = 'latency',
): AIMClusterProfile {
  return {
    metadata: { name, labels: {} },
    spec: {
      aimId: 'test-model',
      metric: meta.metric ?? specMetric,
      type: meta.type,
      acceleratorModel: meta.gpu,
      acceleratorCount: meta.gpuCount,
      precision: meta.precision,
    },
    status: { status: 'Ready' },
  };
}

const automatic = {
  selectedMetric: undefined,
  optimizationClass: ADVANCED_PARAM_AUTOMATIC,
  gpuModel: ADVANCED_PARAM_AUTOMATIC,
  precision: ADVANCED_PARAM_AUTOMATIC,
  gpuCount: ADVANCED_PARAM_AUTOMATIC,
};

describe('filterProfilesByAdvancedParams', () => {
  const latencyA = makeProfile('a', {
    metric: 'latency',
    type: AIM_PROFILE_TYPE_OPTIMIZED,
    gpu: 'MI300X',
    precision: 'fp8',
    gpuCount: 8,
  });
  const latencyB = makeProfile(
    'b',
    {
      metric: 'latency',
      type: 'unoptimized',
      gpu: 'MI250',
      precision: 'fp16',
      gpuCount: 4,
    },
    'latency',
  );
  const throughputOnly = makeProfile(
    'c',
    {
      metric: 'throughput',
      type: AIM_PROFILE_TYPE_OPTIMIZED,
      gpu: 'MI300X',
      precision: 'fp8',
      gpuCount: 8,
    },
    'throughput',
  );

  it('returns empty when profiles is empty', () => {
    expect(filterProfilesByAdvancedParams([], automatic)).toEqual([]);
  });

  it('keeps all profiles that pass metric when advanced params are all automatic', () => {
    const profiles = [latencyA, latencyB];
    const out = filterProfilesByAdvancedParams(profiles, {
      ...automatic,
      selectedMetric: 'latency',
    });
    expect(out.map((t) => t.metadata.name)).toEqual(['a', 'b']);
  });

  it('excludes templates whose metadata.metric does not match selected metric', () => {
    const profiles = [latencyA, throughputOnly];
    const out = filterProfilesByAdvancedParams(profiles, {
      ...automatic,
      selectedMetric: 'throughput',
    });
    expect(out.map((t) => t.metadata.name)).toEqual(['c']);
  });

  it('excludes profiles with no metric when a metric is selected', () => {
    const noMeta: AIMClusterProfile = {
      metadata: { name: 'x', labels: {} },
      spec: { aimId: 'm' },
      status: { status: 'Ready' },
    };
    const out = filterProfilesByAdvancedParams([noMeta, latencyA], {
      ...automatic,
      selectedMetric: 'latency',
    });
    expect(out).toEqual([latencyA]);
  });

  it('filters by optimization class when set to a concrete value', () => {
    const profiles = [latencyA, latencyB];
    const out = filterProfilesByAdvancedParams(profiles, {
      ...automatic,
      selectedMetric: 'latency',
      optimizationClass: AIM_PROFILE_TYPE_OPTIMIZED,
    });
    expect(out.map((t) => t.metadata.name)).toEqual(['a']);
  });

  it('filters by gpu when set', () => {
    const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
      ...automatic,
      selectedMetric: 'latency',
      gpuModel: 'MI250',
    });
    expect(out.map((t) => t.metadata.name)).toEqual(['b']);
  });

  it('filters by precision when set', () => {
    const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
      ...automatic,
      selectedMetric: 'latency',
      precision: 'fp16',
    });
    expect(out.map((t) => t.metadata.name)).toEqual(['b']);
  });

  it('filters by gpu count as string compare to metadata.gpuCount', () => {
    const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
      ...automatic,
      selectedMetric: 'latency',
      gpuCount: '8',
    });
    expect(out.map((t) => t.metadata.name)).toEqual(['a']);
  });

  it('treats empty string optimizationClass as automatic (matches type equality via empty string)', () => {
    const preview = makeProfile('p', {
      metric: 'latency',
      type: 'preview',
      gpu: 'MI300X',
      precision: 'fp8',
      gpuCount: 8,
    });
    const out = filterProfilesByAdvancedParams([latencyA, preview], {
      selectedMetric: 'latency',
      optimizationClass: '',
      gpuModel: ADVANCED_PARAM_AUTOMATIC,
      precision: ADVANCED_PARAM_AUTOMATIC,
      gpuCount: ADVANCED_PARAM_AUTOMATIC,
    });
    expect(out.length).toBe(2);
  });

  it('combines metric with multiple advanced dimensions', () => {
    const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
      selectedMetric: 'latency',
      optimizationClass: AIM_PROFILE_TYPE_OPTIMIZED,
      gpuModel: 'MI300X',
      precision: 'fp8',
      gpuCount: '8',
    });
    expect(out).toEqual([latencyA]);
  });

  describe('profile selection', () => {
    it('narrows by metric only', () => {
      const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
        selectedMetric: 'latency',
      });
      expect(out.map((p) => p.metadata.name)).toEqual(['a', 'b']);
    });

    it('resolves to a single profile when only one shares the metric', () => {
      const out = filterProfilesByAdvancedParams([latencyA, throughputOnly], {
        selectedMetric: 'throughput',
      });
      expect(out).toEqual([throughputOnly]);
    });

    it('resolves an explicit profile name to that single profile', () => {
      const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
        profileName: 'b',
      });
      expect(out).toEqual([latencyB]);
    });

    it('returns no profiles when an explicit profile name no longer exists', () => {
      const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
        profileName: 'missing',
      });
      expect(out).toEqual([]);
    });

    it('narrows automatic profile selection by advanced dimensions', () => {
      const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
        profileName: ADVANCED_PARAM_AUTOMATIC,
        optimizationClass: ADVANCED_PARAM_AUTOMATIC,
        gpuModel: 'MI250',
        precision: ADVANCED_PARAM_AUTOMATIC,
        gpuCount: ADVANCED_PARAM_AUTOMATIC,
      });
      expect(out).toEqual([latencyB]);
    });

    it('returns all profiles when profile selection and filters are automatic', () => {
      const out = filterProfilesByAdvancedParams([latencyA, latencyB], {
        profileName: ADVANCED_PARAM_AUTOMATIC,
        optimizationClass: ADVANCED_PARAM_AUTOMATIC,
        gpuModel: ADVANCED_PARAM_AUTOMATIC,
        precision: ADVANCED_PARAM_AUTOMATIC,
        gpuCount: ADVANCED_PARAM_AUTOMATIC,
      });
      expect(out.map((p) => p.metadata.name)).toEqual(['a', 'b']);
    });
  });
});
