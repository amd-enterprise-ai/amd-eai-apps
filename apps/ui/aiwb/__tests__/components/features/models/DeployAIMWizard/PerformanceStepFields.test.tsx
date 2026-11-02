// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, within } from '@testing-library/react';
import { useForm } from 'react-hook-form';

import {
  performanceStepDefaults,
  PerformanceStepFields,
} from '@/components/features/models/DeployAIMWizard/steps/PerformanceStep';
import type { DeployAIMFormValues } from '@/components/features/models/DeployAIMWizard/types';
import type { AIMClusterProfile } from '@/types/aims';

import { createMockProfile, formValues } from './fixtures';

const readyProfile = (metric: 'latency' | 'throughput'): AIMClusterProfile => ({
  ...createMockProfile({ metric }, `profile-${metric}`),
});

const emptyAdvancedProfileOptions = {
  optimizationClasses: [],
  gpuModels: [],
  precisions: [],
  gpuCounts: [],
  profiles: [],
};

const Wrapper = ({
  profiles,
  profilesLoading = false,
  metricsStatusMap,
  performanceMode = 'latency',
}: {
  profiles: AIMClusterProfile[];
  profilesLoading?: boolean;
  metricsStatusMap: Record<string, boolean>;
  performanceMode?: DeployAIMFormValues['performanceMode'];
}) => {
  const form = useForm<DeployAIMFormValues>({
    defaultValues: {
      ...formValues,
      ...performanceStepDefaults,
      performanceMode,
    },
  });

  return (
    <PerformanceStepFields
      form={form}
      metricsStatusMap={metricsStatusMap}
      isAtleastOneOptimized={Object.values(metricsStatusMap).some((v) => v)}
      profilesLoading={profilesLoading}
      advancedProfileOptions={{ ...emptyAdvancedProfileOptions, profiles }}
    />
  );
};

describe('PerformanceStepFields', () => {
  it('disables all performance mode radios, including Advanced, when there are no profiles', () => {
    render(<Wrapper profiles={[]} metricsStatusMap={{}} />);

    expect(
      screen.getByTestId('deployAimPerformanceMode-latency'),
    ).toHaveAttribute('data-disabled', 'true');
    expect(
      screen.getByTestId('deployAimPerformanceMode-throughput'),
    ).toHaveAttribute('data-disabled', 'true');
    expect(
      screen.getByTestId('deployAimPerformanceMode-advanced'),
    ).toHaveAttribute('data-disabled', 'true');
  });

  it('enables the Advanced radio (and any metric with a ready profile) when profiles exist', () => {
    const profiles = [readyProfile('latency')];
    render(
      <Wrapper profiles={profiles} metricsStatusMap={{ latency: true }} />,
    );

    expect(
      screen.getByTestId('deployAimPerformanceMode-latency'),
    ).not.toHaveAttribute('data-disabled', 'true');
    expect(
      screen.getByTestId('deployAimPerformanceMode-throughput'),
    ).toHaveAttribute('data-disabled', 'true');
    expect(
      screen.getByTestId('deployAimPerformanceMode-advanced'),
    ).not.toHaveAttribute('data-disabled', 'true');
  });

  it('shows the generic unoptimized warning when the model has no optimized profiles at all', () => {
    const profiles = [
      {
        ...readyProfile('latency'),
        spec: {
          ...readyProfile('latency').spec,
          aimId: 'test-model',
          type: 'preview',
        },
      },
    ];
    render(
      <Wrapper profiles={profiles} metricsStatusMap={{ latency: false }} />,
    );

    // "unoptimizedLabel" appears twice here: once as the radio's badge, once as the alert title.
    expect(
      screen.getAllByText('deployAIM.fields.metric.unoptimizedLabel'),
    ).toHaveLength(2);
    expect(
      screen.getByText('deployAIM.fields.metric.notOptimized'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('deployAIM.fields.metric.unoptimizedSelectedLabel'),
    ).not.toBeInTheDocument();
  });

  it('shows the "profile selected" warning when the model has an optimized profile for another metric but the selected metric is unoptimized', () => {
    const profiles = [
      {
        ...readyProfile('latency'),
        spec: {
          ...readyProfile('latency').spec,
          aimId: 'test-model',
          type: 'preview',
        },
      },
      readyProfile('throughput'),
    ];
    render(
      <Wrapper
        profiles={profiles}
        metricsStatusMap={{
          latency: false,
          throughput: true,
        }}
      />,
    );

    expect(
      screen.getByText('deployAIM.fields.metric.unoptimizedSelectedLabel'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'deployAIM.fields.metric.unoptimizedSelectedDescription',
      ),
    ).toBeInTheDocument();
  });

  it('excludes a profile from the Advanced table when the caller restricts advancedProfileOptions, not just disables it', () => {
    // DeployAIMWizard restricts advancedProfileOptions to adapter-capable
    // profiles whenever personalization is enabled, before any adapter is
    // selected. This asserts the table actually reflects that restriction
    // (row is gone) rather than merely rendering every ready profile.
    const adapterCapableProfile = createMockProfile(
      { metric: 'latency', features: ['adapters'] },
      'profile-adapters',
    );
    render(
      <Wrapper
        profiles={[adapterCapableProfile]}
        metricsStatusMap={{ latency: true }}
        performanceMode="advanced"
      />,
    );

    const profileTable = screen.getByTestId('deployAimAdvancedProfileTable');
    // Automatic selection plus the single adapter-capable profile — a
    // non-adapter profile passed by the caller would add a second row.
    expect(within(profileTable).getAllByRole('radio')).toHaveLength(2);
  });
});
