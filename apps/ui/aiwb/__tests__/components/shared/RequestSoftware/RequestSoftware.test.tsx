// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';

import { RequestSoftware } from '@/components/shared/RequestSoftware/RequestSoftware';

vi.mock('@/components/shared/RequestSoftware/bg.svg', () => ({
  default: (props: React.SVGProps<SVGSVGElement>) => <svg {...props} />,
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {},
  }),
}));

vi.mock('@amdenterpriseai/hooks', () => ({
  useSystemInfo: () => () => ['Version: 1.0.0', 'Platform: mac'],
}));

const getMailtoFromLink = (linkLabel: string) => {
  // HeroUI v3 renders an href-bearing Button as a real <a>, so it exposes the
  // implicit "link" role. Query by link role and verify the mailto href.
  const link = screen.getByRole('link', { name: linkLabel });
  expect(link.tagName).toBe('A');
  const href = link.getAttribute('href');
  expect(href).not.toBeNull();
  return new URL(href as string);
};

describe('RequestSoftware', () => {
  it('renders model-variant copy and links to a model-request mailto', () => {
    render(<RequestSoftware variant="model" />);
    expect(screen.getByText('requestSoftware.model.title')).toBeInTheDocument();
    expect(
      screen.getByText('requestSoftware.model.description'),
    ).toBeInTheDocument();
    const url = getMailtoFromLink('requestSoftware.model.button');
    expect(url.protocol).toBe('mailto:');
    expect(url.searchParams.get('subject')).toBe('Model request');
    expect(url.searchParams.get('body')).toBe(
      [
        'Model name: ',
        'Hugging Face or other URL of the model: ',
        'Use case: ',
        'Why you need it: ',
        '',
        '--- System info ---',
        'Version: 1.0.0',
        'Platform: mac',
      ].join('\n'),
    );
  });

  it('renders workspace-variant copy and links to a workspace-request mailto', () => {
    render(<RequestSoftware variant="workspace" />);
    expect(
      screen.getByText('requestSoftware.workspace.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('requestSoftware.workspace.description'),
    ).toBeInTheDocument();
    const url = getMailtoFromLink('requestSoftware.workspace.button');
    expect(url.protocol).toBe('mailto:');
    expect(url.searchParams.get('subject')).toBe('Workspace request');
    expect(url.searchParams.get('body')).toBe(
      [
        'Workspace: ',
        'Website URL of the tool: ',
        'Use case: ',
        'Why you need it: ',
        '',
        '--- System info ---',
        'Version: 1.0.0',
        'Platform: mac',
      ].join('\n'),
    );
  });
});
