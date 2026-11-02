// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import {
  formatTemplateGpuCount,
  formatModelDeploymentSubtitle,
  resolveModelDeploymentName,
} from '@/lib/app/modelDeploymentDisplay';

describe('formatTemplateGpuCount', () => {
  it('returns "Nx GPU" when acceleratorType is not provided', () => {
    expect(formatTemplateGpuCount(8)).toBe('8x GPU');
  });

  it('returns "Nx GPU" when acceleratorType is gpu', () => {
    expect(formatTemplateGpuCount(4, 'gpu')).toBe('4x GPU');
  });

  it('returns "Nx GPU" when acceleratorType is null', () => {
    expect(formatTemplateGpuCount(2, null)).toBe('2x GPU');
  });

  it('returns "Nx GPU" when acceleratorType is undefined', () => {
    expect(formatTemplateGpuCount(2, undefined)).toBe('2x GPU');
  });

  it('returns "Nx CPU" when acceleratorType is cpu', () => {
    expect(formatTemplateGpuCount(1, 'cpu')).toBe('1x CPU');
  });

  it('is case-insensitive for acceleratorType', () => {
    expect(formatTemplateGpuCount(1, 'CPU')).toBe('1x CPU');
  });

  it('trims whitespace from acceleratorType before comparison', () => {
    expect(formatTemplateGpuCount(1, ' cpu ')).toBe('1x CPU');
  });
});

describe('formatModelDeploymentSubtitle', () => {
  const t = (key: string) => key;

  it('returns empty string when no parts are present', () => {
    expect(formatModelDeploymentSubtitle(t as any, {})).toBe('');
  });

  it('formats GPU count using acceleratorType', () => {
    const result = formatModelDeploymentSubtitle(t as any, {
      templateGpuCount: 1,
      acceleratorType: 'cpu',
    });
    expect(result).toBe('1x CPU');
  });

  it('formats GPU count as GPU when acceleratorType is gpu', () => {
    const result = formatModelDeploymentSubtitle(t as any, {
      templateGpuCount: 8,
      acceleratorType: 'gpu',
    });
    expect(result).toBe('8x GPU');
  });

  it('formats GPU count as GPU when acceleratorType is absent', () => {
    const result = formatModelDeploymentSubtitle(t as any, {
      templateGpuCount: 4,
    });
    expect(result).toBe('4x GPU');
  });

  it('joins all parts with · separator', () => {
    const result = formatModelDeploymentSubtitle(t as any, {
      imageVersion: '1.0',
      templateGpuCount: 8,
      acceleratorType: 'gpu',
      precision: 'fp16',
    });
    expect(result).toBe('1.0 · 8x GPU · fp16');
  });

  it('names the profile instead of its axes for a custom-model deployment', () => {
    const result = formatModelDeploymentSubtitle(t as any, {
      imageVersion: '1.0',
      metric: 'latency',
      templateGpuCount: 8,
      acceleratorType: 'gpu',
      precision: 'fp16',
      profileDisplayName: 'High speed',
    });
    expect(result).toBe('High speed');
  });

  it('falls back to the axes when the profile label is absent', () => {
    const result = formatModelDeploymentSubtitle(t as any, {
      precision: 'fp16',
      profileDisplayName: null,
    });
    expect(result).toBe('fp16');
  });
});

describe('resolveModelDeploymentName', () => {
  it('prefers the display name when it differs from the resource name', () => {
    const result = resolveModelDeploymentName({
      displayName: 'My Friendly Deployment',
      resourceName: 'svc-llama-8b',
      canonicalName: 'meta-llama/Llama-3.1-8B-Instruct',
      imageVersion: '0.11.0',
    });
    expect(result).toBe('My Friendly Deployment');
  });

  it('falls back to canonical name with version when display equals resource', () => {
    const result = resolveModelDeploymentName({
      displayName: 'svc-llama-8b',
      resourceName: 'svc-llama-8b',
      canonicalName: 'meta-llama/Llama-3.1-8B-Instruct',
      imageVersion: '0.11.0',
    });
    expect(result).toBe('meta-llama/Llama-3.1-8B-Instruct (0.11.0)');
  });

  it('falls back to canonical name without version when version is absent', () => {
    const result = resolveModelDeploymentName({
      displayName: 'svc-llama-8b',
      resourceName: 'svc-llama-8b',
      canonicalName: 'meta-llama/Llama-3.1-8B-Instruct',
      imageVersion: '',
    });
    expect(result).toBe('meta-llama/Llama-3.1-8B-Instruct');
  });

  it('falls back to display name when canonical name is missing', () => {
    const result = resolveModelDeploymentName({
      displayName: 'svc display',
      resourceName: 'svc-resource',
      canonicalName: '',
      imageVersion: '0.11.0',
    });
    expect(result).toBe('svc display');
  });

  it('does not return version-only label when canonical name is missing', () => {
    const result = resolveModelDeploymentName({
      displayName: 'svc-llama-8b',
      resourceName: 'svc-llama-8b',
      canonicalName: '',
      imageVersion: '0.11.0',
    });
    expect(result).toBe('svc-llama-8b');
  });

  it('trims inputs before comparing and selecting', () => {
    const result = resolveModelDeploymentName({
      displayName: '  svc-llama-8b  ',
      resourceName: 'svc-llama-8b',
      canonicalName: '  meta-llama/Llama-3.1-8B-Instruct  ',
      imageVersion: ' 0.11.0 ',
    });
    expect(result).toBe('meta-llama/Llama-3.1-8B-Instruct (0.11.0)');
  });
});
