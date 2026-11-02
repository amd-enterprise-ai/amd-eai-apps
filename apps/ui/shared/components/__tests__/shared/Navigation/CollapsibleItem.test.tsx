// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';
import { usePathname } from 'next/navigation';

import { SidebarItem } from '@amdenterpriseai/types';

import { CollapsibleItem } from '../../../src/Navigation/CollapsibleItem';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(),
}));

vi.mock('next/router', () => ({
  useRouter: () => ({ locale: 'en', defaultLocale: 'en' }),
}));

const mockUsePathname = vi.mocked(usePathname);

const item: SidebarItem = {
  href: '/models',
  stringKey: 'pages.models.title',
  icon: <span data-testid="models-icon" />,
  subItems: [
    {
      href: '/models/aim-catalog',
      stringKey: 'pages.aimCatalog.title',
    },
    {
      href: '/models/custom-models',
      stringKey: 'pages.customModels.title',
    },
  ],
};

// Mirrors the derivation in CollapsibleItem so the testid stays in sync with
// the per-instance id the component actually renders.
const submenuId = `sidebar-submenu-${item.stringKey.replace(/[^a-z0-9]/gi, '-').toLowerCase()}`;

describe('CollapsibleItem', () => {
  beforeEach(() => {
    mockUsePathname.mockReturnValue('/dashboard');
  });

  it('renders collapsed when no sub-item is active', () => {
    render(<CollapsibleItem item={item} isCollapsed={false} />);

    expect(
      screen.getByRole('button', { name: 'pages.models.title' }),
    ).toHaveAttribute('aria-expanded', 'false');
  });

  it('renders expanded when a sub-item is active', () => {
    mockUsePathname.mockReturnValue('/models/custom-models');
    render(<CollapsibleItem item={item} isCollapsed={false} />);

    expect(
      screen.getByRole('button', { name: 'pages.models.title' }),
    ).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId(submenuId)).not.toHaveAttribute('inert');
  });

  it('renders the group row as a non-navigating button', () => {
    render(<CollapsibleItem item={item} isCollapsed={false} />);

    const groupButton = screen.getByRole('button', {
      name: 'pages.models.title',
    });

    expect(groupButton).not.toHaveAttribute('href');
    expect(
      screen.queryByRole('link', { name: 'pages.models.title' }),
    ).not.toBeInTheDocument();
  });

  it('toggles expansion when the group row is clicked', () => {
    render(<CollapsibleItem item={item} isCollapsed={false} />);

    const groupButton = screen.getByRole('button', {
      name: 'pages.models.title',
    });
    const submenu = screen.getByTestId(submenuId);
    expect(submenu).toHaveClass('grid-rows-[0fr]');
    expect(submenu).toHaveAttribute('inert');

    fireEvent.click(groupButton);
    expect(groupButton).toHaveAttribute('aria-expanded', 'true');
    expect(submenu).toHaveClass('grid-rows-[1fr]');
    expect(submenu).not.toHaveAttribute('inert');

    fireEvent.click(groupButton);
    expect(groupButton).toHaveAttribute('aria-expanded', 'false');
    expect(submenu).toHaveClass('grid-rows-[0fr]');
    expect(submenu).toHaveAttribute('inert');
  });

  it('does not render sub-items in the collapsed rail', () => {
    render(<CollapsibleItem item={item} isCollapsed />);

    expect(
      screen.queryByRole('link', { name: 'pages.aimCatalog.title' }),
    ).not.toBeInTheDocument();
    const groupButton = screen.getByRole('button', {
      name: 'pages.models.title',
    });
    expect(groupButton).not.toHaveAttribute('aria-expanded');
    expect(groupButton).not.toHaveAttribute('aria-controls');
    expect(groupButton.querySelector('.ml-auto')).toHaveClass('hidden');
  });

  it('highlights the collapsed group when a child is active', () => {
    mockUsePathname.mockReturnValue('/models/custom-models');
    render(<CollapsibleItem item={item} isCollapsed />);

    expect(
      screen.getByRole('button', { name: 'pages.models.title' }),
    ).toHaveAttribute('aria-current', 'true');
  });

  it('highlights only the active child', () => {
    mockUsePathname.mockReturnValue('/models/custom-models');
    render(<CollapsibleItem item={item} isCollapsed={false} />);

    expect(
      screen.getByRole('link', { name: 'pages.customModels.title' }),
    ).toHaveAttribute('aria-current', 'page');
    expect(
      screen.getByRole('button', { name: 'pages.models.title' }),
    ).not.toHaveAttribute('aria-current');
  });
});
