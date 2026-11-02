// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { useSession } from 'next-auth/react';

import { Navigation } from '@amdenterpriseai/components';
import { SidebarItem, UserRole } from '@amdenterpriseai/types';

import { ProviderWrapper } from '@/__tests__/ProviderWrapper';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
}));

vi.mock('next/router', () => ({
  useRouter: () => ({ locale: 'en', defaultLocale: 'en' }),
}));

vi.mock('next-auth/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next-auth/react')>();
  return { ...actual, useSession: vi.fn() };
});

vi.mock('@amdenterpriseai/assets/svg/logo', () => ({
  AMDLogoSymbol: () => <div data-testid="amd-symbol" />,
}));

const menuItems: SidebarItem[] = [
  {
    href: '/dashboard',
    stringKey: 'pages.dashboard.title',
    icon: <span data-testid="dashboard-icon" />,
  },
  {
    href: '/models',
    stringKey: 'pages.models.title',
    icon: <span data-testid="models-icon" />,
    subItems: [
      {
        href: '/models/catalog',
        stringKey: 'pages.aimCatalog.title',
      },
    ],
  },
];

const defaultProps = {
  appTitle: 'sections.aiWorkbench.title',
  menuItems,
  isMobileOpen: false,
  onMobileClose: vi.fn(),
};

const renderNavigation = (
  props: Partial<React.ComponentProps<typeof Navigation>> = {},
) =>
  render(
    <ProviderWrapper>
      <Navigation {...defaultProps} {...props} />
    </ProviderWrapper>,
  );

describe('Navigation', () => {
  beforeEach(() => {
    vi.mocked(useSession).mockReturnValue({
      data: {
        user: {
          id: 'user-1',
          email: 'user@example.com',
          roles: [UserRole.PLATFORM_ADMIN],
        },
        expires: '2099-01-01',
      },
      status: 'authenticated',
    } as ReturnType<typeof useSession>);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the expanded desktop sidebar in normal flow', () => {
    renderNavigation();

    expect(screen.getByTestId('desktop-navigation-spacer')).toHaveClass('w-80');
    expect(document.querySelector('#sidebar-nav-panel')).toHaveClass('w-80');
    expect(document.querySelector('#sidebar-nav-panel')).not.toHaveClass(
      'shadow-overlay',
    );
    expect(screen.getByText('sections.aiWorkbench.title')).toBeInTheDocument();
  });

  it('keeps the collapsed layout width while expanding the panel on hover', () => {
    renderNavigation();
    fireEvent.click(screen.getByTestId('sidebar-toggle-button'));

    const spacer = screen.getByTestId('desktop-navigation-spacer');
    const panel = document.querySelector('#sidebar-nav-panel')!;
    expect(spacer).toHaveClass('w-16');
    expect(panel).toHaveClass('w-80', 'transition-[clip-path]');
    expect(panel).not.toHaveClass('shadow-overlay');
    expect(panel).toHaveClass('bg-background');
    expect(panel).toHaveStyle({ clipPath: 'inset(0 16rem 0 0)' });
    expect(screen.getByTestId('collapsed-navigation-border')).toHaveClass(
      'z-50',
      'border-r',
      'border-default',
    );
    expect(panel.querySelector('[aria-current="page"]')).toHaveClass(
      'h-11',
      'w-12',
    );

    fireEvent.mouseEnter(panel);

    expect(spacer).toHaveClass('w-16');
    expect(panel).toHaveClass('w-80', 'bg-background', 'shadow-overlay');
    expect(panel).toHaveStyle({ clipPath: 'inset(0)' });
    expect(
      screen.queryByTestId('collapsed-navigation-border'),
    ).not.toBeInTheDocument();
    expect(panel.querySelector('[aria-current="page"]')).toHaveClass(
      'h-11',
      'w-full',
    );
    expect(screen.getByTestId('navigation-dim-layer')).toBeInTheDocument();
  });

  it('waits 300ms before hiding the hovered collapsed panel', () => {
    vi.useFakeTimers();
    renderNavigation();
    fireEvent.click(screen.getByTestId('sidebar-toggle-button'));

    const panel = document.querySelector('#sidebar-nav-panel')!;
    fireEvent.mouseEnter(panel);
    fireEvent.mouseLeave(panel);

    act(() => vi.advanceTimersByTime(299));
    expect(panel).toHaveStyle({ clipPath: 'inset(0)' });

    act(() => vi.advanceTimersByTime(1));
    expect(panel).toHaveStyle({ clipPath: 'inset(0 16rem 0 0)' });
    expect(
      screen.queryByTestId('navigation-dim-layer'),
    ).not.toBeInTheDocument();
  });

  it('cancels a pending collapse when the pointer returns', () => {
    vi.useFakeTimers();
    renderNavigation();
    fireEvent.click(screen.getByTestId('sidebar-toggle-button'));

    const panel = document.querySelector('#sidebar-nav-panel')!;
    fireEvent.mouseEnter(panel);
    fireEvent.mouseLeave(panel);
    act(() => vi.advanceTimersByTime(200));
    fireEvent.mouseEnter(panel);
    act(() => vi.advanceTimersByTime(100));

    expect(panel).toHaveStyle({ clipPath: 'inset(0)' });
  });

  it('renders the shared navigation items in the mobile dialog', () => {
    renderNavigation({ isMobileOpen: true });

    const dialog = screen.getByRole('dialog', { name: 'menu.navigation' });
    expect(
      within(dialog).getByRole('link', { name: 'pages.dashboard.title' }),
    ).toHaveAttribute('href', '/dashboard');
    expect(
      within(dialog).getByRole('button', { name: 'pages.models.title' }),
    ).toBeInTheDocument();
  });

  it('closes the mobile dialog after navigation or Escape', () => {
    const onMobileClose = vi.fn((event?: React.MouseEvent) =>
      event?.preventDefault(),
    );
    renderNavigation({ isMobileOpen: true, onMobileClose });

    const dialog = screen.getByRole('dialog', { name: 'menu.navigation' });
    fireEvent.click(
      within(dialog).getByRole('link', { name: 'pages.dashboard.title' }),
    );
    fireEvent.keyDown(dialog, { key: 'Escape' });

    expect(onMobileClose).toHaveBeenCalledTimes(2);
  });

  it('prefixes links with the selected project', () => {
    renderNavigation({ isMobileOpen: true, projectPrefix: 'my-project' });

    expect(
      within(screen.getByRole('dialog')).getByRole('link', {
        name: 'pages.dashboard.title',
      }),
    ).toHaveAttribute('href', '/my-project/dashboard');
  });
});
