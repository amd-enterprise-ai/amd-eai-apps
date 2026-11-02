// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import {
  acceleratorTypeKey,
  acceleratorModelToDeviceId,
  buildContainerImageRef,
  deviceIdToAcceleratorModel,
  getDefaultAcceleratorDeviceId,
  getDefaultImageFamilySelection,
  getFirstSelectableImageFamily,
  getLatestImageTag,
  intersectCombinations,
  reachableRuntimeAxes,
  resolveDefaultOnboardImageRef,
  resolveProfileImage,
  runtimeSelectionBlock,
  supportedAcceleratorCounts,
  toAcceleratorSelectOptions,
  toAcceleratorTypeSelectOptions,
  toImageSelectOptions,
  toSelectableImageSelectOptions,
  toTagSelectOptions,
} from '@/lib/app/runtimeProfileCatalog';
import type { components } from '@/types/api';
import type { AimImageFamily, ClusterAccelerator } from '@/types/cluster';
import { AUTOMATIC_IMAGE_FAMILY_ID } from '@/types/runtime-profile';

type RuntimeProfileCombination =
  components['schemas']['RuntimeProfileCombination'];

// A base whose matrix is not a full cross product: fp16 only at count 1, fp8
// only at count 8, and throughput only on the fp8/8 tuple.
const sparseCombinations: RuntimeProfileCombination[] = [
  {
    acceleratorModel: 'MI300X',
    acceleratorCount: 1,
    precision: 'fp16',
    metric: 'latency',
  },
  {
    acceleratorModel: 'MI300X',
    acceleratorCount: 8,
    precision: 'fp8',
    metric: 'latency',
  },
  {
    acceleratorModel: 'MI300X',
    acceleratorCount: 8,
    precision: 'fp8',
    metric: 'throughput',
  },
  {
    acceleratorModel: 'MI325X',
    acceleratorCount: 4,
    precision: 'fp8',
    metric: 'latency',
  },
];

const imageFamilies: AimImageFamily[] = [
  {
    familyId: 'automatic',
    displayName: 'Automatic',
    repository: null,
    tags: [],
  },
  {
    familyId: 'aim-base',
    displayName: 'aim-base',
    repository: 'amdenterpriseai/aim-base',
    tags: ['0.11'],
  },
];

const accelerators: ClusterAccelerator[] = [
  {
    acceleratorType: 'gpu',
    acceleratorVendor: 'amd',
    deviceId: '74a1',
    productName: 'AMD Instinct MI300X',
    allocatableCount: 8,
    acceleratorModel: 'MI300X',
  },
];

describe('runtimeProfileCatalog transforms', () => {
  it('maps image families to select options', () => {
    expect(toImageSelectOptions(imageFamilies)).toEqual([
      { key: 'automatic', label: 'Automatic' },
      { key: 'aim-base', label: 'aim-base' },
    ]);
  });

  it('excludes automatic from selectable image options', () => {
    expect(toSelectableImageSelectOptions(imageFamilies)).toEqual([
      { key: 'aim-base', label: 'aim-base' },
    ]);
  });

  it('returns no tags for automatic family', () => {
    expect(
      toTagSelectOptions(imageFamilies, AUTOMATIC_IMAGE_FAMILY_ID),
    ).toEqual([]);
  });

  it('maps aim-base tags to select options', () => {
    expect(toTagSelectOptions(imageFamilies, 'aim-base')).toEqual([
      { key: '0.11', label: '0.11' },
    ]);
  });

  it('maps accelerators to select options', () => {
    expect(toAcceleratorSelectOptions(accelerators)).toEqual([
      { key: '74a1', label: 'AMD Instinct MI300X' },
    ]);
  });

  it('maps accelerator types from API payload and deduplicates case-insensitively', () => {
    expect(
      toAcceleratorTypeSelectOptions([
        accelerators[0],
        {
          acceleratorType: 'cpu',
          acceleratorVendor: 'amd',
          deviceId: 'cpu-0',
          productName: 'AMD EPYC',
          allocatableCount: 96,
          acceleratorModel: 'EPYC_ZEN4',
        },
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a2',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
      ]),
    ).toEqual([
      { key: 'gpu', label: 'GPU' },
      { key: 'cpu', label: 'CPU' },
    ]);
  });

  it('falls back to accelerator model when product name is blank', () => {
    expect(
      toAcceleratorSelectOptions([
        {
          ...accelerators[0],
          acceleratorType: 'gpu',
          productName: '   ',
        },
      ]),
    ).toEqual([{ key: '74a1', label: 'MI300X' }]);
  });

  it('returns empty label when both product and model are missing', () => {
    expect(
      toAcceleratorSelectOptions([
        {
          ...accelerators[0],
          acceleratorType: 'gpu',
          productName: '',
          acceleratorModel: null,
        },
      ]),
    ).toEqual([{ key: '74a1', label: '' }]);
  });

  it('uses translated model labels when product name is unavailable', () => {
    expect(
      toAcceleratorSelectOptions(
        [
          {
            ...accelerators[0],
            acceleratorType: 'cpu',
            productName: '',
            acceleratorModel: 'EPYC_ZEN4',
          },
        ],
        (model) => `translated-${model}`,
      ),
    ).toEqual([{ key: '74a1', label: 'translated-EPYC_ZEN4' }]);
  });

  it('buildContainerImageRef combines repository and tag', () => {
    expect(buildContainerImageRef('amdenterpriseai/aim-base', '0.11')).toBe(
      'amdenterpriseai/aim-base:0.11',
    );
  });

  it('resolveProfileImage omits image for automatic selection', () => {
    expect(resolveProfileImage('automatic', '', imageFamilies)).toBeUndefined();
  });

  it('resolveProfileImage builds concrete image ref', () => {
    expect(resolveProfileImage('aim-base', '0.11', imageFamilies)).toBe(
      'amdenterpriseai/aim-base:0.11',
    );
  });

  it('resolveDefaultOnboardImageRef uses first selectable catalog family', () => {
    expect(resolveDefaultOnboardImageRef(imageFamilies)).toBe(
      'amdenterpriseai/aim-base:0.11',
    );
  });

  it('resolveDefaultOnboardImageRef preselects a radeon-only family and latest discovered tag', () => {
    expect(
      resolveDefaultOnboardImageRef([
        {
          familyId: 'automatic',
          displayName: 'Automatic',
          repository: null,
          tags: [],
        },
        {
          familyId: 'radeon-aim-base',
          displayName: 'radeon-aim-base',
          repository: 'docker.io/silogenai/radeon-aim-base',
          tags: ['0.11-preview', '0.12-preview'],
        },
      ]),
    ).toBe('docker.io/silogenai/radeon-aim-base:0.12-preview');
  });

  it('resolveDefaultOnboardImageRef falls back to unpinned aim-base when catalog is empty', () => {
    expect(resolveDefaultOnboardImageRef([])).toBe('amdenterpriseai/aim-base');
  });

  it('getLatestImageTag picks the newest semver-like tag', () => {
    expect(getLatestImageTag(['0.9', '0.11', '0.10'])).toBe('0.11');
    expect(getLatestImageTag(['latest', '0.11'])).toBe('latest');
  });

  it('getFirstSelectableImageFamily skips automatic', () => {
    expect(getFirstSelectableImageFamily(imageFamilies)?.familyId).toBe(
      'aim-base',
    );
  });

  it('getDefaultImageFamilySelection returns first family and latest tag', () => {
    expect(getDefaultImageFamilySelection(imageFamilies)).toEqual({
      familyId: 'aim-base',
      tag: '0.11',
    });
  });

  it('getDefaultAcceleratorDeviceId returns the first catalog device id', () => {
    expect(getDefaultAcceleratorDeviceId(accelerators)).toBe('74a1');
    expect(getDefaultAcceleratorDeviceId([])).toBe('');
  });
});

describe('accelerator model resolution', () => {
  it('normalizes accelerator type keys for comparisons', () => {
    expect(acceleratorTypeKey(' GPU ')).toBe('gpu');
    expect(acceleratorTypeKey('cpu')).toBe('cpu');
    expect(acceleratorTypeKey(undefined)).toBe('');
  });

  it('deviceIdToAcceleratorModel maps a device id to the canonical model', () => {
    expect(deviceIdToAcceleratorModel('74a1', accelerators)).toBe('MI300X');
    expect(
      deviceIdToAcceleratorModel('7551', [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '7551',
          productName: 'AMD Radeon AI PRO R9700S',
          allocatableCount: 8,
          acceleratorModel: 'R9700',
        },
      ]),
    ).toBe('R9700');
    expect(
      deviceIdToAcceleratorModel('74a1', [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X OAM',
          allocatableCount: 8,
          acceleratorModel: null,
        },
      ]),
    ).toBe('');
  });

  it('deviceIdToAcceleratorModel returns empty for unknown or blank device ids', () => {
    expect(deviceIdToAcceleratorModel('MI325X', accelerators)).toBe('');
    expect(deviceIdToAcceleratorModel('', accelerators)).toBe('');
  });

  it('acceleratorModelToDeviceId resolves a canonical model back to its device id', () => {
    expect(acceleratorModelToDeviceId('MI300X', accelerators)).toBe('74a1');
    expect(
      acceleratorModelToDeviceId('R9700', [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '7551',
          productName: 'AMD Radeon AI PRO R9700S',
          allocatableCount: 8,
          acceleratorModel: 'R9700',
        },
      ]),
    ).toBe('7551');
    // Edit prefill: persisted MI300X resolves back via catalog acceleratorModel.
    expect(
      acceleratorModelToDeviceId('MI300X', [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X OAM',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
      ]),
    ).toBe('74a1');
  });

  it('acceleratorModelToDeviceId returns empty for unknown models', () => {
    expect(acceleratorModelToDeviceId('MI325X', accelerators)).toBe('');
    expect(acceleratorModelToDeviceId(undefined, accelerators)).toBe('');
  });

  it('supportedAcceleratorCounts caps the base sizes by allocatable capacity', () => {
    expect(supportedAcceleratorCounts([1, 2, 4, 8], 4)).toEqual([1, 2, 4]);
    expect(supportedAcceleratorCounts([8, 1, 4, 2], 8)).toEqual([1, 2, 4, 8]);
  });

  it('supportedAcceleratorCounts deduplicates sizes', () => {
    expect(supportedAcceleratorCounts([2, 1, 2, 1, 4], 8)).toEqual([1, 2, 4]);
  });

  it('supportedAcceleratorCounts ignores the cap when capacity is unknown', () => {
    expect(supportedAcceleratorCounts([1, 2, 4, 8], 0)).toEqual([1, 2, 4, 8]);
  });

  it('supportedAcceleratorCounts keeps the full set when the cap would empty it', () => {
    // Incomplete capacity data must not block onboarding entirely.
    expect(supportedAcceleratorCounts([2, 4, 8], 1)).toEqual([2, 4, 8]);
  });

  it('supportedAcceleratorCounts drops non-positive/non-integer sizes and returns [] when none remain', () => {
    expect(supportedAcceleratorCounts([0, -2, 1.5], 8)).toEqual([]);
    expect(supportedAcceleratorCounts([], 8)).toEqual([]);
  });
});

describe('reachableRuntimeAxes', () => {
  it('returns every distinct axis value when nothing is selected', () => {
    const axes = reachableRuntimeAxes(sparseCombinations, {});
    expect(axes.acceleratorModels).toEqual(['MI300X', 'MI325X']);
    expect(axes.acceleratorCounts).toEqual([1, 4, 8]);
    expect(axes.precisions).toEqual(['fp16', 'fp8']);
    expect(axes.metrics).toEqual(['latency', 'throughput']);
  });

  it('narrows counts to the selected model', () => {
    expect(
      reachableRuntimeAxes(sparseCombinations, { acceleratorModel: 'MI325X' })
        .acceleratorCounts,
    ).toEqual([4]);
    expect(
      reachableRuntimeAxes(sparseCombinations, { acceleratorModel: 'MI300X' })
        .acceleratorCounts,
    ).toEqual([1, 8]);
  });

  it('narrows precision to the selected model and count', () => {
    // MI300X coexists with fp16 only at count 1 and fp8 only at count 8, so the
    // cartesian product (both precisions at both counts) is never offered.
    expect(
      reachableRuntimeAxes(sparseCombinations, {
        acceleratorModel: 'MI300X',
        acceleratorCount: 1,
      }).precisions,
    ).toEqual(['fp16']);
    expect(
      reachableRuntimeAxes(sparseCombinations, {
        acceleratorModel: 'MI300X',
        acceleratorCount: 8,
      }).precisions,
    ).toEqual(['fp8']);
  });

  it('narrows metric to the selected model, count and precision', () => {
    expect(
      reachableRuntimeAxes(sparseCombinations, {
        acceleratorModel: 'MI300X',
        acceleratorCount: 8,
        precision: 'fp8',
      }).metrics,
    ).toEqual(['latency', 'throughput']);
    expect(
      reachableRuntimeAxes(sparseCombinations, {
        acceleratorModel: 'MI300X',
        acceleratorCount: 1,
        precision: 'fp16',
      }).metrics,
    ).toEqual(['latency']);
  });

  it('ignores a lower-priority selection that is unreachable for the higher-priority ones', () => {
    // count 1 does not coexist with fp8 on MI300X; rather than empty the metric
    // list, the stale precision is ignored so a snap can recover.
    const axes = reachableRuntimeAxes(sparseCombinations, {
      acceleratorModel: 'MI300X',
      acceleratorCount: 1,
      precision: 'fp8',
    });
    expect(axes.precisions).toEqual(['fp16']);
    expect(axes.metrics).toEqual(['latency']);
  });

  it('returns empty axes when no combinations are known', () => {
    expect(reachableRuntimeAxes([], { acceleratorModel: 'MI300X' })).toEqual({
      acceleratorModels: [],
      acceleratorCounts: [],
      precisions: [],
      metrics: [],
    });
  });
});

describe('runtimeSelectionBlock', () => {
  const combo: RuntimeProfileCombination = {
    acceleratorModel: 'MI300X',
    acceleratorCount: 1,
    precision: 'fp16',
    metric: 'latency',
  };

  it('does not block when the governing matrix has combinations', () => {
    expect(
      runtimeSelectionBlock({
        imageSelected: true,
        baseImageLoading: false,
        baseImageError: false,
        baseImageMatrix: { combinations: [combo], profilesAvailable: true },
        namespaceMatrix: null,
      }),
    ).toBeNull();
  });

  it('blocks when the selected image emitted profiles but none is resolvable', () => {
    expect(
      runtimeSelectionBlock({
        imageSelected: true,
        baseImageLoading: false,
        baseImageError: false,
        baseImageMatrix: { combinations: [], profilesAvailable: true },
        namespaceMatrix: null,
      }),
    ).toBe('noValidCombinations');
  });

  it('does not block when the base emitted nothing yet (static fallback applies)', () => {
    expect(
      runtimeSelectionBlock({
        imageSelected: true,
        baseImageLoading: false,
        baseImageError: false,
        baseImageMatrix: { combinations: [], profilesAvailable: false },
        namespaceMatrix: null,
      }),
    ).toBeNull();
  });

  it('falls back to the namespace matrix while the image lookup is loading', () => {
    // The resolver validates against namespace base-role profiles, so namespace
    // gating is authoritative; a base-image outage must not hard-block every save.
    expect(
      runtimeSelectionBlock({
        imageSelected: true,
        baseImageLoading: true,
        baseImageError: false,
        baseImageMatrix: null,
        namespaceMatrix: { combinations: [combo], profilesAvailable: true },
      }),
    ).toBeNull();
    expect(
      runtimeSelectionBlock({
        imageSelected: true,
        baseImageLoading: false,
        baseImageError: true,
        baseImageMatrix: null,
        namespaceMatrix: { combinations: [], profilesAvailable: true },
      }),
    ).toBe('noValidCombinations');
  });

  it('gates on the namespace matrix when no image is selected', () => {
    expect(
      runtimeSelectionBlock({
        imageSelected: false,
        baseImageLoading: false,
        baseImageError: false,
        baseImageMatrix: null,
        namespaceMatrix: { combinations: [], profilesAvailable: true },
      }),
    ).toBe('noValidCombinations');
  });

  it('does not let a settled image relax the authoritative namespace gate', () => {
    // Namespace (the resolver's source) has resolvable combinations, so even an
    // ambiguous-only image matrix must not block — the image only refines which
    // options are shown.
    expect(
      runtimeSelectionBlock({
        imageSelected: true,
        baseImageLoading: false,
        baseImageError: false,
        baseImageMatrix: { combinations: [], profilesAvailable: true },
        namespaceMatrix: { combinations: [combo], profilesAvailable: true },
      }),
    ).toBeNull();
  });
});

describe('intersectCombinations', () => {
  const a: RuntimeProfileCombination = {
    acceleratorModel: 'MI300X',
    acceleratorCount: 1,
    precision: 'fp16',
    metric: 'latency',
  };
  const b: RuntimeProfileCombination = {
    acceleratorModel: 'MI300X',
    acceleratorCount: 8,
    precision: 'fp8',
    metric: 'throughput',
  };

  it('keeps only tuples present in both, from the authoritative side', () => {
    expect(intersectCombinations([a, b], [a])).toEqual([a]);
    expect(intersectCombinations([a], [b])).toEqual([]);
  });
});
