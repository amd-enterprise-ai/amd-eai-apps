// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

import { PerformanceStepSummary } from '@/components/features/models/DeployAIMWizard/steps/PerformanceStep';
import { PERFORMANCE_MODE_ADVANCED } from '@/components/features/models/DeployAIMWizard/types';
import { getMetricTranslationKey } from '@/lib/app/aims';
import { ADVANCED_PARAM_AUTOMATIC } from '@/lib/app/aims/filterProfilesByAdvancedParams';
import type { AIMClusterProfile } from '@/types/aims';

import { createMockProfile, formValues } from './fixtures';

const unoptimizedLatency = (
  overrides: Partial<AIMClusterProfile['spec']> = {},
): AIMClusterProfile => ({
  ...createMockProfile(
    {
      type: 'preview',
      acceleratorModel: 'EPYC_9965',
      acceleratorCount: 188,
      precision: 'bf16',
      ...overrides,
    },
    'profile-latency-preview',
  ),
});

const optimizedLatency = (
  overrides: Partial<AIMClusterProfile['spec']> = {},
): AIMClusterProfile => ({
  ...createMockProfile(overrides, 'profile-latency-optimized'),
});

const advancedParamDefaults = {
  optimizationClass: ADVANCED_PARAM_AUTOMATIC,
  gpuModel: ADVANCED_PARAM_AUTOMATIC,
  precision: ADVANCED_PARAM_AUTOMATIC,
  gpuCount: ADVANCED_PARAM_AUTOMATIC,
};

describe('PerformanceStepSummary', () => {
  it('shows profile detail rows and no warning for a unique optimized match', () => {
    const profile = optimizedLatency();
    render(
      <PerformanceStepSummary
        data={{
          ...formValues,
          performanceMode: 'latency',
          profileName: ADVANCED_PARAM_AUTOMATIC,
          ...advancedParamDefaults,
        }}
        readyProfiles={[profile]}
      />,
    );

    expect(screen.getByText('MI300X × 8')).toBeInTheDocument();
    expect(screen.getByText('fp8')).toBeInTheDocument();
    expect(screen.getByText('Optimized')).toBeInTheDocument();
    expect(
      screen.queryByText('deployAIM.fields.metric.unoptimizedLabel'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('deployAIM.fields.metric.notOptimized'),
    ).not.toBeInTheDocument();
  });

  it.each([
    {
      name: 'a unique unoptimized match',
      profiles: [unoptimizedLatency()],
      title: 'deployAIM.fields.metric.unoptimizedLabel',
      description: 'deployAIM.fields.metric.notOptimized',
      showsDetails: true,
    },
    {
      name: 'an unoptimized match when another metric is optimized',
      profiles: [
        unoptimizedLatency(),
        optimizedLatency({ metric: 'throughput' }),
      ],
      title: 'deployAIM.fields.metric.unoptimizedSelectedLabel',
      description: 'deployAIM.fields.metric.unoptimizedSelectedDescription',
      showsDetails: true,
    },
    {
      name: 'multiple unoptimized matches',
      profiles: [
        unoptimizedLatency(),
        {
          ...unoptimizedLatency({ acceleratorModel: 'EPYC_9575' }),
          metadata: { name: 'profile-latency-preview-2', labels: {} },
        },
      ],
      title: 'deployAIM.fields.metric.unoptimizedLabel',
      description: 'deployAIM.fields.metric.notOptimized',
      showsDetails: false,
    },
  ])(
    'shows the correct warning for $name',
    ({ profiles, title, description, showsDetails }) => {
      render(
        <PerformanceStepSummary
          data={{
            ...formValues,
            profileName: ADVANCED_PARAM_AUTOMATIC,
            ...advancedParamDefaults,
          }}
          readyProfiles={profiles}
        />,
      );

      expect(screen.getByText(title)).toBeInTheDocument();
      expect(screen.getByText(description)).toBeInTheDocument();
      const accelerator = screen.queryByText('deployAIM.summary.accelerator');
      if (showsDetails) expect(accelerator).toBeInTheDocument();
      else expect(accelerator).not.toBeInTheDocument();
    },
  );

  it('shows no warning when at least one of several matching profiles is optimized', () => {
    const profiles = [
      optimizedLatency({ metric: 'latency' }),
      unoptimizedLatency({ metric: 'latency' }),
    ];

    render(
      <PerformanceStepSummary
        data={{
          ...formValues,
          performanceMode: 'latency',
          profileName: ADVANCED_PARAM_AUTOMATIC,
          ...advancedParamDefaults,
        }}
        readyProfiles={profiles}
      />,
    );

    expect(
      screen.queryByText('deployAIM.fields.metric.notOptimized'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('deployAIM.fields.metric.unoptimizedLabel'),
    ).not.toBeInTheDocument();
  });

  it('advanced mode: shows the resolved profile metric and detail rows, with a single warning (no per-row badge) for an explicit unoptimized selection', () => {
    const profile = unoptimizedLatency();
    render(
      <PerformanceStepSummary
        data={{
          ...formValues,
          performanceMode: PERFORMANCE_MODE_ADVANCED,
          profileName: profile.metadata.name,
          ...advancedParamDefaults,
        }}
        readyProfiles={[profile]}
      />,
    );

    expect(
      screen.getByText(getMetricTranslationKey('latency')),
    ).toBeInTheDocument();
    expect(screen.getByText('EPYC_9965 × 188')).toBeInTheDocument();
    expect(screen.getByText('Preview')).toBeInTheDocument();
    expect(
      screen.getByText('deployAIM.fields.metric.notOptimized'),
    ).toBeInTheDocument();
    // The warning alert is the only "unoptimized" indicator now — no duplicate badge on the Class row.
    expect(
      screen.getAllByText('deployAIM.fields.metric.unoptimizedLabel'),
    ).toHaveLength(1);
  });

  it('advanced mode automatic with an ambiguous match keeps the generic label and no detail rows', () => {
    const profiles = [
      optimizedLatency({ metric: 'latency' }),
      unoptimizedLatency({ metric: 'latency' }),
    ];

    render(
      <PerformanceStepSummary
        data={{
          ...formValues,
          performanceMode: PERFORMANCE_MODE_ADVANCED,
          profileName: ADVANCED_PARAM_AUTOMATIC,
          ...advancedParamDefaults,
        }}
        readyProfiles={profiles}
      />,
    );

    expect(
      screen.getByText('deployAIM.fields.metric.options.advanced.label'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('deployAIM.summary.accelerator'),
    ).not.toBeInTheDocument();
  });

  it('renders the display name row only when provided', () => {
    const profile = optimizedLatency();
    render(
      <PerformanceStepSummary
        data={{
          ...formValues,
          displayName: 'my-deployment',
          performanceMode: 'latency',
          profileName: ADVANCED_PARAM_AUTOMATIC,
          ...advancedParamDefaults,
        }}
        readyProfiles={[profile]}
      />,
    );

    expect(screen.getByText('my-deployment')).toBeInTheDocument();
  });
});
