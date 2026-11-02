// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import type { CustomProfileResponse } from '@/lib/app/custom-profiles';
import {
  customProfileToFormValues,
  formValuesToCustomProfileCreate,
  formValuesToCustomProfilePatch,
  formValuesToProfileOverrides,
  formValuesToProfilePatch,
  imageRefToFamilyTag,
  parseRuntimeYamlMapping,
  profileOverridesToFormValues,
  profileOverridesToOnboardBody,
  RuntimeProfileYamlError,
  type CustomProfileFormInput,
} from '@/lib/app/runtimeProfileMappers';
import type { AimImageFamily, ClusterAccelerator } from '@/types/cluster';
import { AUTOMATIC_IMAGE_FAMILY_ID } from '@/types/runtime-profile';

const imageFamilies: AimImageFamily[] = [
  {
    familyId: AUTOMATIC_IMAGE_FAMILY_ID,
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

const previewFields = {
  sourceType: 'huggingFace' as const,
  repoId: 'org/model',
  revision: 'main',
  sha: 'abc',
  displayName: 'My model',
  tags: [],
};

describe('parseRuntimeYamlMapping', () => {
  it('returns a mapping for valid key/value YAML', () => {
    expect(parseRuntimeYamlMapping('foo: bar', 'engineArgsYaml')).toEqual({
      foo: 'bar',
    });
  });

  it('rejects top-level YAML that parses to a Date (timestamps are not plain maps)', () => {
    expect(() =>
      parseRuntimeYamlMapping(
        '!!timestamp 2001-12-15T02:59:43.1Z',
        'engineArgsYaml',
      ),
    ).toThrow(RuntimeProfileYamlError);
  });

  it('rejects top-level sequences', () => {
    expect(() => parseRuntimeYamlMapping('- a: 1', 'envVarsYaml')).toThrow(
      RuntimeProfileYamlError,
    );
  });
});

describe('runtimeProfileMappers', () => {
  it('builds profile overrides from form values', () => {
    expect(
      formValuesToProfileOverrides(
        {
          containerImage: 'aim-base',
          containerVersion: '0.11',
          acceleratorType: 'gpu',
          accelerator: '74a1',
          acceleratorCount: 2,
          modelPrecision: 'bf16',
          engineArgsYaml: 'foo: bar',
          envVarsYaml: 'VLLM_ROCM_USE_AITER: 1',
        },
        imageFamilies,
      ),
    ).toEqual({
      imageFamilyId: 'aim-base',
      image: 'amdenterpriseai/aim-base:0.11',
      acceleratorType: 'gpu',
      acceleratorModel: '74a1',
      acceleratorCount: 2,
      precision: 'bf16',
      engineArgsYaml: 'foo: bar',
      envVarsYaml: 'VLLM_ROCM_USE_AITER: 1',
    });
  });

  it('always sends precision and the canonical accelerator model on the default path', () => {
    const body = profileOverridesToOnboardBody(
      formValuesToProfileOverrides(
        {
          containerImage: 'aim-base',
          containerVersion: '0.11',
          acceleratorType: 'gpu',
          accelerator: '74a1',
          acceleratorCount: 1,
          modelPrecision: 'bf16',
          engineArgsYaml: '',
          envVarsYaml: '',
        },
        imageFamilies,
      ),
      previewFields,
      imageFamilies,
      accelerators,
    );
    expect(body.image).toBe('amdenterpriseai/aim-base:0.11');
    // bf16 must reach aim-engine (not be stripped), and the device id 74a1 must
    // be translated to the canonical MI300X so the emitted profile is not stuck
    // NotAvailable.
    expect(body.customProfile).toEqual({
      imageFamilyId: 'aim-base',
      acceleratorType: 'gpu',
      acceleratorModel: 'MI300X',
      acceleratorCount: 1,
      precision: 'bf16',
    });
  });

  it('resolves the device id to the canonical accelerator model for non-default precision', () => {
    const body = profileOverridesToOnboardBody(
      formValuesToProfileOverrides(
        {
          containerImage: 'aim-base',
          containerVersion: '0.11',
          acceleratorType: 'gpu',
          accelerator: '74a1',
          acceleratorCount: 1,
          modelPrecision: 'fp16',
          engineArgsYaml: '',
          envVarsYaml: '',
        },
        imageFamilies,
      ),
      previewFields,
      imageFamilies,
      accelerators,
    );
    expect(body.customProfile?.acceleratorModel).toBe('MI300X');
    expect(body.customProfile?.precision).toBe('fp16');
  });

  it('parses engine args and env var YAML into canonical engineArgs/engineEnv', () => {
    const body = profileOverridesToOnboardBody(
      formValuesToProfileOverrides(
        {
          containerImage: 'aim-base',
          containerVersion: '0.11',
          acceleratorType: 'gpu',
          accelerator: '74a1',
          acceleratorCount: 1,
          modelPrecision: 'bf16',
          engineArgsYaml: 'max-model-len: 4096\nattention-backend: TRITON_ATTN',
          envVarsYaml: 'VLLM_ROCM_USE_AITER: 1',
        },
        imageFamilies,
      ),
      previewFields,
      imageFamilies,
      accelerators,
    );
    expect(body.customProfile?.engineArgs).toEqual({
      'max-model-len': 4096,
      'attention-backend': 'TRITON_ATTN',
    });
    expect(body.customProfile?.engineEnv).toEqual([
      { name: 'VLLM_ROCM_USE_AITER', value: '1' },
    ]);
  });

  it('leaves acceleratorModel empty when the form device id is not in the catalog', () => {
    const body = profileOverridesToOnboardBody(
      formValuesToProfileOverrides(
        {
          containerImage: 'aim-base',
          containerVersion: '0.11',
          acceleratorType: 'gpu',
          accelerator: 'MI325X',
          acceleratorCount: 1,
          modelPrecision: 'bf16',
          engineArgsYaml: '',
          envVarsYaml: '',
        },
        imageFamilies,
      ),
      previewFields,
      imageFamilies,
      accelerators,
    );
    expect(body.customProfile?.acceleratorModel).toBe('');
  });
});

describe('imageRefToFamilyTag', () => {
  it('maps a repo:tag ref back to its catalog family and tag', () => {
    expect(
      imageRefToFamilyTag('amdenterpriseai/aim-base:0.11', imageFamilies),
    ).toEqual({ familyId: 'aim-base', tag: '0.11' });
  });

  it('returns the tag without a family when no catalog repo matches', () => {
    expect(
      imageRefToFamilyTag('docker.io/other/img:1.2.3', imageFamilies),
    ).toEqual({ familyId: undefined, tag: '1.2.3' });
  });

  it('handles refs that omit a tag', () => {
    expect(
      imageRefToFamilyTag('amdenterpriseai/aim-base', imageFamilies),
    ).toEqual({ familyId: 'aim-base', tag: undefined });
  });

  it('does not treat a registry port as a tag', () => {
    expect(
      imageRefToFamilyTag('registry:5000/team/img', imageFamilies),
    ).toEqual({ familyId: undefined, tag: undefined });
  });

  it('parses digest refs without treating sha256 colon as a tag separator', () => {
    const digest =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    expect(
      imageRefToFamilyTag(`amdenterpriseai/aim-base@${digest}`, imageFamilies),
    ).toEqual({ familyId: 'aim-base', tag: undefined });
    expect(
      imageRefToFamilyTag(`registry:5000/team/img@${digest}`, imageFamilies),
    ).toEqual({ familyId: undefined, tag: undefined });
  });

  it('parses repo:tag@digest refs using only the name:tag portion', () => {
    const digest =
      'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
    expect(
      imageRefToFamilyTag(
        `amdenterpriseai/aim-base:0.11@${digest}`,
        imageFamilies,
      ),
    ).toEqual({ familyId: 'aim-base', tag: '0.11' });
  });

  it('returns an empty object for blank input', () => {
    expect(imageRefToFamilyTag(undefined, imageFamilies)).toEqual({});
    expect(imageRefToFamilyTag('', imageFamilies)).toEqual({});
  });
});

describe('profileOverridesToFormValues', () => {
  it('falls back to catalog defaults when overrides omit runtime knobs', () => {
    expect(
      profileOverridesToFormValues(
        { image: 'amdenterpriseai/aim-base:0.11' },
        imageFamilies,
        accelerators,
      ),
    ).toEqual({
      containerImage: 'aim-base',
      containerVersion: '0.11',
      acceleratorType: 'gpu',
      accelerator: '74a1',
      acceleratorCount: 1,
      modelPrecision: 'bf16',
      engineArgsYaml: '',
      envVarsYaml: '',
    });
  });

  it('round-trips persisted runtime overrides, mapping model->device and engineArgs->yaml', () => {
    expect(
      profileOverridesToFormValues(
        {
          image: 'amdenterpriseai/aim-base:0.11',
          imageFamilyId: 'aim-base',
          acceleratorType: 'gpu',
          acceleratorModel: 'MI300X',
          acceleratorCount: 4,
          precision: 'fp8',
          engineArgs: { 'max-model-len': 4096 },
          engineEnv: { VLLM_ROCM_USE_AITER: '1' },
        },
        imageFamilies,
        accelerators,
      ),
    ).toEqual({
      containerImage: 'aim-base',
      containerVersion: '0.11',
      acceleratorType: 'gpu',
      accelerator: '74a1',
      acceleratorCount: 4,
      modelPrecision: 'fp8',
      engineArgsYaml: 'max-model-len: 4096',
      envVarsYaml: 'VLLM_ROCM_USE_AITER: "1"',
    });
  });

  it('falls back to the catalog default when persisted acceleratorModel is unrecognized', () => {
    const values = profileOverridesToFormValues(
      {
        acceleratorModel: '74a1',
        engineArgsYaml: 'foo: bar',
        envVarsYaml: 'BAZ: 1',
      },
      imageFamilies,
      accelerators,
    );
    expect(values.engineArgsYaml).toBe('foo: bar');
    expect(values.envVarsYaml).toBe('BAZ: 1');
    expect(values.accelerator).toBe('74a1');
  });

  it('uses catalog defaults when overrides are null', () => {
    const values = profileOverridesToFormValues(
      null,
      imageFamilies,
      accelerators,
    );
    expect(values.containerImage).toBe('aim-base');
    expect(values.containerVersion).toBe('0.11');
    expect(values.accelerator).toBe('74a1');
  });
});

describe('formValuesToProfilePatch', () => {
  const baseValues = {
    containerImage: 'aim-base',
    containerVersion: '0.11',
    acceleratorType: 'gpu',
    accelerator: '74a1',
    acceleratorCount: 2,
    modelPrecision: 'fp16',
    engineArgsYaml: '',
    envVarsYaml: '',
  };

  it('emits the complete profile, nulling cleared engine args/env fields', () => {
    const { image, customProfile } = formValuesToProfilePatch(
      baseValues,
      imageFamilies,
      accelerators,
    );
    expect(image).toBe('amdenterpriseai/aim-base:0.11');
    expect(customProfile).toEqual({
      imageFamilyId: 'aim-base',
      acceleratorType: 'gpu',
      acceleratorModel: 'MI300X',
      acceleratorCount: 2,
      precision: 'fp16',
      engineArgs: null,
      engineEnv: null,
    });
  });

  it('parses engine args/env YAML into canonical fields when provided', () => {
    const { customProfile } = formValuesToProfilePatch(
      {
        ...baseValues,
        engineArgsYaml: '  max-model-len: 8192  ',
        envVarsYaml: 'VLLM_ROCM_USE_AITER: 1',
      },
      imageFamilies,
      accelerators,
    );
    expect(customProfile.engineArgs).toEqual({ 'max-model-len': 8192 });
    expect(customProfile.engineEnv).toEqual([
      { name: 'VLLM_ROCM_USE_AITER', value: '1' },
    ]);
  });

  it('never carries the image inside customProfile', () => {
    const { customProfile } = formValuesToProfilePatch(
      baseValues,
      imageFamilies,
      accelerators,
    );
    expect(customProfile).not.toHaveProperty('image');
  });

  it('coerces accelerator count from string (form state can be string before zod)', () => {
    const { customProfile } = formValuesToProfilePatch(
      { ...baseValues, acceleratorCount: '4' },
      imageFamilies,
      accelerators,
    );
    expect(customProfile.acceleratorCount).toBe(4);
  });
});

const profileFormValues: CustomProfileFormInput = {
  displayName: '  High speed  ',
  containerImage: 'aim-base',
  containerVersion: '0.11',
  acceleratorType: 'gpu',
  accelerator: '74a1',
  // The count select stores its key as a string.
  acceleratorCount: '8',
  modelPrecision: 'fp8',
  metric: 'latency',
  engineArgsYaml: '',
  envVarsYaml: '',
};

describe('formValuesToCustomProfileCreate', () => {
  it('emits the narrowing axes as typed fields, resolving the device id and image', () => {
    expect(
      formValuesToCustomProfileCreate(
        profileFormValues,
        imageFamilies,
        accelerators,
      ),
    ).toEqual({
      displayName: 'High speed',
      acceleratorModel: 'MI300X',
      acceleratorCount: 8,
      precision: 'fp8',
      metric: 'latency',
      image: 'amdenterpriseai/aim-base:0.11',
      customProfile: { acceleratorType: 'gpu' },
    });
  });

  it('parses engine args into a mapping and env vars into named entries', () => {
    const request = formValuesToCustomProfileCreate(
      {
        ...profileFormValues,
        engineArgsYaml: 'max-model-len: 32768',
        envVarsYaml: 'VLLM_LOGGING_LEVEL: DEBUG',
      },
      imageFamilies,
      accelerators,
    );

    expect(request.customProfile).toEqual({
      acceleratorType: 'gpu',
      engineArgs: { 'max-model-len': 32768 },
      engineEnv: [{ name: 'VLLM_LOGGING_LEVEL', value: 'DEBUG' }],
    });
  });

  it('rejects engine args that are not a YAML mapping', () => {
    expect(() =>
      formValuesToCustomProfileCreate(
        { ...profileFormValues, engineArgsYaml: '- not: a mapping' },
        imageFamilies,
        accelerators,
      ),
    ).toThrow(RuntimeProfileYamlError);
  });
});

describe('formValuesToCustomProfilePatch', () => {
  it('resets cleared configuration fields with an explicit null', () => {
    const request = formValuesToCustomProfilePatch(
      profileFormValues,
      imageFamilies,
      accelerators,
    );

    expect(request.customProfile).toEqual({
      acceleratorType: 'gpu',
      engineArgs: null,
      engineEnv: null,
    });
  });

  it('sends the complete desired state so selector and overrides stay in step', () => {
    const request = formValuesToCustomProfilePatch(
      { ...profileFormValues, acceleratorCount: 4 },
      imageFamilies,
      accelerators,
    );

    expect(request).toMatchObject({
      displayName: 'High speed',
      acceleratorModel: 'MI300X',
      acceleratorCount: 4,
      precision: 'fp8',
      metric: 'latency',
      image: 'amdenterpriseai/aim-base:0.11',
    });
  });
});

describe('customProfileToFormValues', () => {
  // engineEnv reads back as the map the server collapsed it to on write, not as
  // the [{name, value}] entries the drawer sent.
  const savedProfile: CustomProfileResponse = {
    name: 'high-speed-7f3b6c8e',
    displayName: 'High speed',
    isDefault: false,
    resourceName: 'high-speed-7f3b6c8e',
    selector: {
      acceleratorModel: 'MI300X',
      acceleratorCount: 8,
      metric: 'latency',
      precision: 'fp8',
    },
    customProfile: {
      image: 'amdenterpriseai/aim-base:0.11',
      engineArgs: { 'max-model-len': 32768 },
      engineEnv: { VLLM_LOGGING_LEVEL: 'DEBUG' },
    },
  };

  it('hydrates the form from authored intent', () => {
    expect(
      customProfileToFormValues(savedProfile, imageFamilies, accelerators),
    ).toEqual({
      displayName: 'High speed',
      containerImage: 'aim-base',
      containerVersion: '0.11',
      acceleratorType: 'gpu',
      accelerator: '74a1',
      acceleratorCount: 8,
      modelPrecision: 'fp8',
      metric: 'latency',
      engineArgsYaml: 'max-model-len: 32768',
      envVarsYaml: 'VLLM_LOGGING_LEVEL: DEBUG',
    });
  });

  it('prefers authored intent over the effective derived configuration', () => {
    const values = customProfileToFormValues(
      {
        ...savedProfile,
        profile: {
          metadata: { name: 'derived' },
          spec: {
            aimId: 'aim-1',
            metric: 'throughput',
            precision: 'fp16',
            acceleratorModel: 'MI300X',
            acceleratorCount: 1,
          },
        },
      },
      imageFamilies,
      accelerators,
    );

    expect(values.metric).toBe('latency');
    expect(values.modelPrecision).toBe('fp8');
    expect(values.acceleratorCount).toBe(8);
  });

  it('reads env vars written as entries by an older client', () => {
    const values = customProfileToFormValues(
      {
        ...savedProfile,
        customProfile: {
          ...savedProfile.customProfile,
          engineEnv: [{ name: 'VLLM_LOGGING_LEVEL', value: 'DEBUG' }],
        },
      },
      imageFamilies,
      accelerators,
    );

    expect(values.envVarsYaml).toBe('VLLM_LOGGING_LEVEL: DEBUG');
  });

  it('falls back to the derived configuration when nothing was authored', () => {
    const values = customProfileToFormValues(
      {
        name: 'default',
        displayName: 'Default',
        isDefault: true,
        resourceName: 'llama-3-8b-default',
        profile: {
          metadata: { name: 'derived' },
          spec: {
            aimId: 'aim-1',
            metric: 'throughput',
            precision: 'fp16',
            acceleratorModel: 'MI300X',
            acceleratorCount: 1,
            acceleratorType: 'gpu',
            image: 'amdenterpriseai/aim-base:0.11',
          },
        },
      },
      imageFamilies,
      accelerators,
    );

    expect(values).toMatchObject({
      displayName: 'Default',
      containerImage: 'aim-base',
      metric: 'throughput',
      modelPrecision: 'fp16',
      acceleratorCount: 1,
      accelerator: '74a1',
      engineArgsYaml: '',
      envVarsYaml: '',
    });
  });
});
