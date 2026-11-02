// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  ModelProfileSummary,
  toProfileSummaryFields,
} from '@/components/shared/ModelProfileSummary';

describe('ModelProfileSummary', () => {
  const t = vi.fn(
    (key: string, opts?: { defaultValue?: string; rank?: number }) =>
      key === 'profileSummary.maxRank'
        ? `max rank ${opts?.rank}`
        : (opts?.defaultValue ?? key),
  );

  it('renders the authored profile display name for custom models', () => {
    render(
      <ModelProfileSummary
        profile={{
          profileDisplayName: 'High speed',
          metric: 'latency',
          gpu: 'MI300X',
          templateGpuCount: 8,
          acceleratorType: 'gpu',
          precision: 'fp16',
        }}
        t={t as never}
      />,
    );

    expect(screen.getByText('High speed')).toBeInTheDocument();
    expect(screen.queryByText('MI300X')).not.toBeInTheDocument();
  });

  it('renders hardware axes when no profile display name is set', () => {
    const { container } = render(
      <ModelProfileSummary
        profile={{
          metric: 'latency',
          gpu: 'MI300X',
          templateGpuCount: 1,
          acceleratorType: 'gpu',
          precision: 'fp4',
        }}
        t={t as never}
      />,
    );

    expect(container).toHaveTextContent('MI300X');
    expect(container).toHaveTextContent('fp4');
    expect(container).not.toHaveTextContent('max rank');
  });

  it('renders the maximum LoRA rank from a deployment when available', () => {
    const profile = toProfileSummaryFields(
      { spec: { adapterRuntime: { maxRank: 64 } } } as never,
      new Map(),
    );

    render(<ModelProfileSummary profile={profile} t={t as never} />);

    expect(screen.getByText('max rank 64')).toBeInTheDocument();
  });
});
