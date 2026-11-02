// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  RuntimeProfileFields,
  type RuntimeProfileSelectionState,
} from '@/components/features/models/runtime-profile/RuntimeProfileFields';
import type { RuntimeProfileCatalogState } from '@/hooks/useRuntimeProfileCatalog';
import { getBaseImageRuntimeProfileOptions } from '@/lib/app/custom-models';
import type { ClusterAccelerator } from '@/types/cluster';

let capturedAccelerators: ClusterAccelerator[] = [];
let capturedAcceleratorCounts: number[] = [];
let capturedPrecisionOptions: Array<{ key: string; label: string }> = [];
let capturedConstrained = false;

vi.mock('@/lib/app/custom-models', () => ({
  getBaseImageRuntimeProfileOptions: vi.fn(),
}));

vi.mock(
  '@/components/features/models/runtime-profile/RuntimeProfileAcceleratorFields',
  () => ({
    RuntimeProfileAcceleratorFields: ({
      accelerators,
      acceleratorCounts,
      isConstrained,
    }: {
      accelerators: ClusterAccelerator[];
      acceleratorCounts?: number[];
      isConstrained?: boolean;
    }) => {
      capturedAccelerators = accelerators;
      capturedAcceleratorCounts = acceleratorCounts ?? [];
      capturedConstrained = Boolean(isConstrained);
      return <div data-testid="accelerator-fields" />;
    },
  }),
);

vi.mock(
  '@/components/features/models/runtime-profile/RuntimeProfileImageFields',
  () => ({
    RuntimeProfileImageFields: () => <div data-testid="image-fields" />,
  }),
);

vi.mock(
  '@/components/features/models/runtime-profile/RuntimeProfilePrecisionField',
  () => ({
    RuntimeProfilePrecisionField: ({
      options,
    }: {
      options?: Array<{ key: string; label: string }>;
    }) => {
      capturedPrecisionOptions = options ?? [];
      return <div data-testid="precision-field" />;
    },
  }),
);

vi.mock(
  '@/components/features/models/runtime-profile/RuntimeProfileCatalogStatus',
  () => ({
    RuntimeProfileCatalogStatus: () => <div data-testid="catalog-status" />,
  }),
);

type FormValues = {
  containerImage: string;
  containerVersion: string;
  acceleratorType: string;
  accelerator: string;
  acceleratorCount: number;
  modelPrecision: string;
};

const labels = {
  containerImage: { label: 'Container image', placeholder: 'Select image' },
  containerVersion: { label: 'Version', placeholder: 'Select version' },
  acceleratorType: { label: 'Type', placeholder: 'Select type' },
  accelerator: { label: 'Accelerator', placeholder: 'Select accelerator' },
  acceleratorCount: { label: 'Count' },
  modelPrecision: { label: 'Precision', placeholder: 'Select precision' },
  catalogLoading: 'Loading',
  catalogError: 'Error',
  catalogRetry: 'Retry',
  baseImageOptionsWarning: 'Using project defaults',
  noValidCombinationsWarning: 'No valid runtime combination',
  emptyAccelerators: 'No accelerators',
};

function Harness({
  catalog,
  overrides,
  onSelectionStateChange,
}: {
  catalog: RuntimeProfileCatalogState;
  overrides?: Partial<FormValues>;
  onSelectionStateChange?: (state: RuntimeProfileSelectionState) => void;
}) {
  const firstFamily = catalog.imageFamilies[0];
  const form = useForm<FormValues>({
    defaultValues: {
      containerImage: firstFamily?.familyId ?? '',
      containerVersion: firstFamily?.tags?.[0] ?? '',
      acceleratorType: 'gpu',
      accelerator: '',
      acceleratorCount: 1,
      modelPrecision: 'bf16',
      ...overrides,
    },
  });
  return (
    <RuntimeProfileFields
      form={form}
      catalog={catalog}
      labels={labels}
      onSelectionStateChange={onSelectionStateChange}
    />
  );
}

describe('RuntimeProfileFields', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes all cluster accelerators to the accelerator selectors', () => {
    capturedAccelerators = [];
    const catalog: RuntimeProfileCatalogState = {
      imageFamilies: [],
      accelerators: [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
        {
          acceleratorType: 'cpu',
          acceleratorVendor: 'amd',
          deviceId: 'cpu-epyc',
          productName: 'AMD EPYC',
          allocatableCount: 96,
          acceleratorModel: 'EPYC_ZEN4',
        },
      ],
      runtimeOptions: {
        acceleratorModels: ['MI300X'],
        precisions: ['fp16'],
        acceleratorCounts: [1, 2, 4, 8],
        optimizationClasses: ['general'],
        metrics: ['latency'],
        profilesAvailable: false,
      },
      isLoading: false,
      isError: false,
      error: null,
      invalidateCatalog: vi.fn(),
    };

    render(<Harness catalog={catalog} />);

    expect(capturedAccelerators.map((entry) => entry.deviceId)).toEqual([
      '74a1',
      'cpu-epyc',
    ]);
  });

  it('filters accelerators by image-scoped runtime options when available', async () => {
    capturedAccelerators = [];
    vi.mocked(getBaseImageRuntimeProfileOptions).mockResolvedValue({
      imageRepository: 'amdenterpriseai/aim-base',
      imageTag: '0.13.1',
      acceleratorTypes: ['gpu'],
      acceleratorModels: ['MI300X'],
      acceleratorCountsByModel: { MI300X: [1, 2, 4, 8] },
      precisionsByModel: { MI300X: ['fp16'] },
      metricsByModel: { MI300X: ['latency', 'throughput'] },
      optimizationClassesByModel: {},
      combinations: [],
      profilesAvailable: false,
    });
    const catalog: RuntimeProfileCatalogState = {
      project: 'project1',
      imageFamilies: [
        {
          familyId: 'aim-base',
          displayName: 'aim-base',
          repository: 'amdenterpriseai/aim-base',
          tags: ['0.13.1'],
        },
      ],
      accelerators: [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
        {
          acceleratorType: 'cpu',
          acceleratorVendor: 'amd',
          deviceId: 'cpu-epyc',
          productName: 'AMD EPYC',
          allocatableCount: 96,
          acceleratorModel: 'EPYC_ZEN4',
        },
      ],
      runtimeOptions: null,
      isLoading: false,
      isError: false,
      error: null,
      invalidateCatalog: vi.fn(),
    };

    render(<Harness catalog={catalog} />);

    await waitFor(() => {
      expect(capturedAccelerators.map((entry) => entry.deviceId)).toEqual([
        '74a1',
      ]);
    });
  });

  it('falls back to all cluster accelerators when image-scoped options fail', async () => {
    capturedAccelerators = [];
    vi.mocked(getBaseImageRuntimeProfileOptions).mockRejectedValue(
      new Error('Not found'),
    );
    const catalog: RuntimeProfileCatalogState = {
      project: 'project1',
      imageFamilies: [
        {
          familyId: 'aim-base',
          displayName: 'aim-base',
          repository: 'amdenterpriseai/aim-base',
          tags: ['0.13.1'],
        },
      ],
      accelerators: [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
        {
          acceleratorType: 'cpu',
          acceleratorVendor: 'amd',
          deviceId: 'cpu-epyc',
          productName: 'AMD EPYC',
          allocatableCount: 96,
          acceleratorModel: 'EPYC_ZEN4',
        },
      ],
      runtimeOptions: {
        acceleratorModels: ['MI300X'],
        precisions: ['fp16'],
        acceleratorCounts: [1, 2, 4, 8],
        optimizationClasses: ['general'],
        metrics: ['latency'],
        profilesAvailable: false,
      },
      isLoading: false,
      isError: false,
      error: null,
      invalidateCatalog: vi.fn(),
    };

    render(<Harness catalog={catalog} />);

    await waitFor(() => {
      expect(capturedAccelerators.map((entry) => entry.deviceId)).toEqual([
        '74a1',
        'cpu-epyc',
      ]);
    });
  });

  it('falls back to all cluster accelerators when image-scoped filtering yields no matches', async () => {
    capturedAccelerators = [];
    vi.mocked(getBaseImageRuntimeProfileOptions).mockResolvedValue({
      imageRepository: 'amdenterpriseai/aim-base',
      imageTag: '0.13.1',
      acceleratorTypes: ['gpu'],
      acceleratorModels: ['NON_EXISTENT_MODEL'],
      acceleratorCountsByModel: {},
      precisionsByModel: {},
      metricsByModel: {},
      optimizationClassesByModel: {},
      combinations: [],
      profilesAvailable: false,
    });
    const catalog: RuntimeProfileCatalogState = {
      project: 'project1',
      imageFamilies: [
        {
          familyId: 'aim-base',
          displayName: 'aim-base',
          repository: 'amdenterpriseai/aim-base',
          tags: ['0.13.1'],
        },
      ],
      accelerators: [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
        {
          acceleratorType: 'cpu',
          acceleratorVendor: 'amd',
          deviceId: 'cpu-epyc',
          productName: 'AMD EPYC',
          allocatableCount: 96,
          acceleratorModel: 'EPYC_ZEN4',
        },
      ],
      runtimeOptions: {
        acceleratorModels: ['MI300X'],
        precisions: ['fp16'],
        acceleratorCounts: [1, 2, 4, 8],
        optimizationClasses: ['general'],
        metrics: ['latency'],
        profilesAvailable: false,
      },
      isLoading: false,
      isError: false,
      error: null,
      invalidateCatalog: vi.fn(),
    };

    render(<Harness catalog={catalog} />);

    await waitFor(() => {
      expect(capturedAccelerators.map((entry) => entry.deviceId)).toEqual([
        '74a1',
        'cpu-epyc',
      ]);
    });
  });

  it('cascades count and precision to the emitted combinations of the base image', async () => {
    capturedAcceleratorCounts = [];
    capturedPrecisionOptions = [];
    // MI300X emits fp16 only at count 1 and fp8 only at count 8; the flat
    // per-model precision list would offer both at either count.
    vi.mocked(getBaseImageRuntimeProfileOptions).mockResolvedValue({
      imageRepository: 'amdenterpriseai/aim-base',
      imageTag: '0.13.1',
      acceleratorTypes: ['gpu'],
      acceleratorModels: ['MI300X'],
      acceleratorCountsByModel: { MI300X: [1, 8] },
      precisionsByModel: { MI300X: ['fp16', 'fp8'] },
      metricsByModel: { MI300X: ['latency'] },
      optimizationClassesByModel: {},
      combinations: [
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
      ],
      profilesAvailable: true,
    });
    const catalog: RuntimeProfileCatalogState = {
      project: 'project1',
      imageFamilies: [
        {
          familyId: 'aim-base',
          displayName: 'aim-base',
          repository: 'amdenterpriseai/aim-base',
          tags: ['0.13.1'],
        },
      ],
      accelerators: [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
      ],
      runtimeOptions: null,
      isLoading: false,
      isError: false,
      error: null,
      invalidateCatalog: vi.fn(),
    };

    // Count 1 selected: precision narrows to fp16 (fp8 does not coexist at 1).
    render(
      <Harness
        catalog={catalog}
        overrides={{ accelerator: '74a1', acceleratorCount: 1 }}
      />,
    );
    await waitFor(() => {
      expect(capturedAcceleratorCounts).toEqual([1, 8]);
      expect(capturedPrecisionOptions.map((option) => option.key)).toEqual([
        'fp16',
      ]);
    });
  });

  it('cascades precision to the higher count of a sparse base image', async () => {
    capturedPrecisionOptions = [];
    vi.mocked(getBaseImageRuntimeProfileOptions).mockResolvedValue({
      imageRepository: 'amdenterpriseai/aim-base',
      imageTag: '0.13.1',
      acceleratorTypes: ['gpu'],
      acceleratorModels: ['MI300X'],
      acceleratorCountsByModel: { MI300X: [1, 8] },
      precisionsByModel: { MI300X: ['fp16', 'fp8'] },
      metricsByModel: { MI300X: ['latency'] },
      optimizationClassesByModel: {},
      combinations: [
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
      ],
      profilesAvailable: true,
    });
    const catalog: RuntimeProfileCatalogState = {
      project: 'project1',
      imageFamilies: [
        {
          familyId: 'aim-base',
          displayName: 'aim-base',
          repository: 'amdenterpriseai/aim-base',
          tags: ['0.13.1'],
        },
      ],
      accelerators: [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
      ],
      runtimeOptions: null,
      isLoading: false,
      isError: false,
      error: null,
      invalidateCatalog: vi.fn(),
    };

    render(
      <Harness
        catalog={catalog}
        overrides={{ accelerator: '74a1', acceleratorCount: 8 }}
      />,
    );
    await waitFor(() => {
      expect(capturedPrecisionOptions.map((option) => option.key)).toEqual([
        'fp8',
      ]);
    });
  });

  it('blocks and empties the selectors when the image emitted only ambiguous combinations', async () => {
    capturedAccelerators = [];
    capturedAcceleratorCounts = [];
    capturedPrecisionOptions = [];
    capturedConstrained = false;
    // The image discovered profiles (per-model lists populated) but none resolves
    // to a single tuple, so combinations is empty while profilesAvailable is true.
    vi.mocked(getBaseImageRuntimeProfileOptions).mockResolvedValue({
      imageRepository: 'amdenterpriseai/aim-base',
      imageTag: '0.13.1',
      acceleratorTypes: ['gpu'],
      acceleratorModels: ['MI300X'],
      acceleratorCountsByModel: { MI300X: [1] },
      precisionsByModel: { MI300X: ['fp16'] },
      metricsByModel: { MI300X: ['latency'] },
      optimizationClassesByModel: {},
      combinations: [],
      profilesAvailable: true,
    });
    const catalog: RuntimeProfileCatalogState = {
      project: 'project1',
      imageFamilies: [
        {
          familyId: 'aim-base',
          displayName: 'aim-base',
          repository: 'amdenterpriseai/aim-base',
          tags: ['0.13.1'],
        },
      ],
      accelerators: [
        {
          acceleratorType: 'gpu',
          acceleratorVendor: 'amd',
          deviceId: '74a1',
          productName: 'AMD Instinct MI300X',
          allocatableCount: 8,
          acceleratorModel: 'MI300X',
        },
      ],
      runtimeOptions: null,
      isLoading: false,
      isError: false,
      error: null,
      invalidateCatalog: vi.fn(),
    };
    const onSelectionStateChange = vi.fn();

    render(
      <Harness
        catalog={catalog}
        overrides={{ accelerator: '74a1' }}
        onSelectionStateChange={onSelectionStateChange}
      />,
    );

    await waitFor(() => {
      expect(onSelectionStateChange).toHaveBeenCalledWith(
        expect.objectContaining({ block: 'noValidCombinations' }),
      );
    });
    // No accelerator, count, or precision is offered: there is nothing to pick,
    // and the child fields are told so they render nothing rather than defaults.
    expect(capturedAccelerators).toEqual([]);
    expect(capturedAcceleratorCounts).toEqual([]);
    expect(capturedPrecisionOptions).toEqual([]);
    expect(capturedConstrained).toBe(true);
  });
});
