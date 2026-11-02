// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';

import { useAirmLinkMenuItem } from '@/hooks/useAirmLinkMenuItem';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key === 'userMenu.airmAppLabel' ? 'Resource Manager' : key,
  }),
}));

const mockUseProject = vi.fn();

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => mockUseProject(),
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    DropdownSection: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="dropdown-section">{children}</div>
    ),
    DropdownItem: ({
      children,
      href,
      target,
      rel,
    }: {
      children: React.ReactNode;
      href?: string;
      target?: string;
      rel?: string;
    }) => (
      <a href={href} target={target} rel={rel}>
        {children}
      </a>
    ),
  };
});

const TestComponent = () => {
  const renderMenuItem = useAirmLinkMenuItem();
  return <>{renderMenuItem}</>;
};

describe('useAirmLinkMenuItem', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders AIRM link when airmAppUrl is provided and not in standalone mode', () => {
    mockUseProject.mockReturnValue({
      isStandaloneMode: false,
      airmAppUrl: 'https://airm.example.com',
    });

    render(<TestComponent />);

    const link = screen.getByRole('link', { name: 'Resource Manager' });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', 'https://airm.example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('returns null when in standalone mode', () => {
    mockUseProject.mockReturnValue({
      isStandaloneMode: true,
      airmAppUrl: 'https://airm.example.com',
    });

    const { container } = render(<TestComponent />);

    expect(container).toBeEmptyDOMElement();
  });

  it('returns null when airmAppUrl is not provided', () => {
    mockUseProject.mockReturnValue({
      isStandaloneMode: false,
      airmAppUrl: undefined,
    });

    const { container } = render(<TestComponent />);

    expect(container).toBeEmptyDOMElement();
  });

  it('returns null when airmAppUrl is empty string', () => {
    mockUseProject.mockReturnValue({
      isStandaloneMode: false,
      airmAppUrl: '',
    });

    const { container } = render(<TestComponent />);

    expect(container).toBeEmptyDOMElement();
  });
});
