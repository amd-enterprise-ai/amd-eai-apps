// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import {
  AIM_PROFILE_SOURCE_MODEL_LABEL,
  filterProfilesBySourceModel,
} from '@/lib/app/aims/filterProfilesBySourceModel';
import type { AIMClusterProfile } from '@/types/aims';

const profile = (name: string, sourceModel?: string): AIMClusterProfile => ({
  metadata: {
    name,
    labels: sourceModel
      ? { [AIM_PROFILE_SOURCE_MODEL_LABEL]: sourceModel }
      : {},
  },
  // Every version of a model shares one aimId, which is exactly why it cannot
  // be used to tell the versions' profiles apart.
  spec: { aimId: 'org/demo', metric: 'latency' },
  status: { status: 'Ready' },
});

describe('filterProfilesBySourceModel', () => {
  it('keeps only the profiles the selected version published', () => {
    const result = filterProfilesBySourceModel(
      [
        profile('a-1', 'aim-demo-0-13-0'),
        profile('b-1', 'aim-demo-0-11-1'),
        profile('a-2', 'aim-demo-0-13-0'),
      ],
      'aim-demo-0-13-0',
    );

    expect(result.map((p) => p.metadata.name)).toEqual(['a-1', 'a-2']);
  });

  it('keeps a profile whose provenance label is absent', () => {
    const result = filterProfilesBySourceModel(
      [profile('unstamped'), profile('other', 'aim-demo-0-11-1')],
      'aim-demo-0-13-0',
    );

    expect(result.map((p) => p.metadata.name)).toEqual(['unstamped']);
  });

  it('keeps a profile whose labels map is missing entirely', () => {
    const unlabelled = {
      metadata: { name: 'no-labels' },
      spec: { aimId: 'org/demo' },
      status: { status: 'Ready' },
    } as AIMClusterProfile;

    expect(
      filterProfilesBySourceModel([unlabelled], 'aim-demo-0-13-0'),
    ).toEqual([unlabelled]);
  });

  it('returns the pool unchanged when no version is identified', () => {
    const profiles = [profile('a-1', 'aim-demo-0-13-0'), profile('b-1')];

    expect(filterProfilesBySourceModel(profiles, null)).toEqual(profiles);
    expect(filterProfilesBySourceModel(profiles, undefined)).toEqual(profiles);
    expect(filterProfilesBySourceModel(profiles, '')).toEqual(profiles);
  });

  it('narrows to nothing when every profile names a different version', () => {
    expect(
      filterProfilesBySourceModel(
        [profile('b-1', 'aim-demo-0-11-1')],
        'aim-demo-0-13-0',
      ),
    ).toEqual([]);
  });
});
