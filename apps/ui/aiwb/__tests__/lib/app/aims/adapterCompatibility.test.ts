// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import {
  ADAPTER_FEATURE,
  canProfilesServeAdapter,
  isAdapterCapableProfileSpec,
} from '@/lib/app/aims/adapterCompatibility';
import type { AIMProfileSpec } from '@/types/aims';

// The catalog groups every quantised variant under one aimId, while each
// profile names the weights it actually loads.
const GROUPING_AIM_ID = 'meta-llama/Llama-3.1-8B-Instruct';
const QUANTISED_MODEL_ID = 'amd/Llama-3.1-8B-Instruct-FP8-KV';

const profileSpec = (overrides: Partial<AIMProfileSpec> = {}): AIMProfileSpec =>
  ({
    aimId: GROUPING_AIM_ID,
    modelId: QUANTISED_MODEL_ID,
    features: [ADAPTER_FEATURE],
    ...overrides,
  }) as AIMProfileSpec;

const adapterFor = (...compatibleWith: string[]) => ({ compatibleWith });

describe('isAdapterCapableProfileSpec', () => {
  it('accepts a profile whose runtime advertises the adapter feature', () => {
    expect(isAdapterCapableProfileSpec(profileSpec())).toBe(true);
  });

  it('ignores capabilities it does not know about', () => {
    expect(
      isAdapterCapableProfileSpec(
        profileSpec({ features: ['speculative-decoding', ADAPTER_FEATURE] }),
      ),
    ).toBe(true);
    expect(
      isAdapterCapableProfileSpec(
        profileSpec({ features: ['speculative-decoding'] }),
      ),
    ).toBe(false);
  });

  it('rejects a profile with no capabilities at all', () => {
    expect(isAdapterCapableProfileSpec(profileSpec({ features: [] }))).toBe(
      false,
    );
    expect(
      isAdapterCapableProfileSpec(profileSpec({ features: undefined })),
    ).toBe(false);
  });

  it.each([
    ['null', null],
    ['undefined', undefined],
  ])('rejects a %s spec', (_label, spec) => {
    expect(isAdapterCapableProfileSpec(spec)).toBe(false);
  });
});

describe('canProfilesServeAdapter', () => {
  it('serves an adapter trained against the profile weights', () => {
    expect(
      canProfilesServeAdapter({
        adapter: adapterFor(QUANTISED_MODEL_ID),
        profileSpecs: [profileSpec()],
      }),
    ).toBe(true);
  });

  // Accepted only because every producer on the platform still writes the
  // grouping id; the deploy and attach endpoints accept it for the same reason,
  // and a modelId-only rule here would hide adapters they would have taken.
  it('serves an adapter that only names the grouping id of the model', () => {
    expect(
      canProfilesServeAdapter({
        adapter: adapterFor(GROUPING_AIM_ID),
        profileSpecs: [profileSpec()],
      }),
    ).toBe(true);
  });

  it('refuses an adapter that names neither identity of the profile', () => {
    expect(
      canProfilesServeAdapter({
        adapter: adapterFor('some-other-org/unrelated-model'),
        profileSpecs: [profileSpec()],
      }),
    ).toBe(false);
  });

  it('refuses a profile whose runtime cannot load adapters at all', () => {
    expect(
      canProfilesServeAdapter({
        adapter: adapterFor(QUANTISED_MODEL_ID),
        profileSpecs: [profileSpec({ features: [] })],
      }),
    ).toBe(false);
  });

  it.each([
    ['missing', undefined],
    ['empty', ''],
    ['null', null],
  ])(
    'refuses a profile that states %s for both identities, so an unknown lineage never matches',
    (_label, identity) => {
      expect(
        canProfilesServeAdapter({
          adapter: adapterFor(QUANTISED_MODEL_ID, GROUPING_AIM_ID, ''),
          profileSpecs: [
            profileSpec({
              modelId: identity,
              aimId: identity,
            } as Partial<AIMProfileSpec>),
          ],
        }),
      ).toBe(false);
    },
  );

  it('refuses an adapter when there is no profile to serve it', () => {
    expect(
      canProfilesServeAdapter({
        adapter: adapterFor(QUANTISED_MODEL_ID),
        profileSpecs: [],
      }),
    ).toBe(false);
  });

  it('ignores unresolved entries and serves the adapter if any candidate can', () => {
    expect(
      canProfilesServeAdapter({
        adapter: adapterFor(QUANTISED_MODEL_ID),
        profileSpecs: [
          null,
          undefined,
          profileSpec({ modelId: 'amd/Llama-3.1-8B-Instruct-FP16' }),
          profileSpec(),
        ],
      }),
    ).toBe(true);
  });
});
