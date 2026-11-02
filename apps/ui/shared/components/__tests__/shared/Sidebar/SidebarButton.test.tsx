// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { isMenuItemActive } from '@amdenterpriseai/utils/app';

import { SidebarButton } from '../../../src/Navigation/SidebarButton';

import '@testing-library/jest-dom';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(() => '/current-path'),
}));

vi.mock('next/router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    query: {},
    locale: 'en',
    defaultLocale: 'en',
  }),
}));

vi.mock('@amdenterpriseai/utils/app', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/utils/app')>();
  return { ...actual, isMenuItemActive: vi.fn(() => false) };
});

describe('SidebarButton', () => {
  beforeEach(() => {
    vi.mocked(isMenuItemActive).mockReturnValue(false);
  });

  it('renders a link with text and icon when href is provided', () => {
    const { getByRole, getByText } = render(
      <SidebarButton
        isCollapsed={true}
        text="Button Text"
        icon={<span>Icon</span>}
        href="/example"
      />,
    );

    const link = getByRole('link');
    expect(link).toBeInTheDocument();
    expect(link).toHaveTextContent('Button Text');
    expect(getByText('Icon')).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/example');
  });

  it('renders correctly without an icon', () => {
    const { getByRole } = render(
      <SidebarButton isCollapsed={false} text="nav.models" href="/models" />,
    );
    expect(getByRole('link')).toBeInTheDocument();
    expect(getByRole('link')).toHaveTextContent('nav.models');
  });

  describe('Active state', () => {
    beforeEach(() => {
      vi.mocked(isMenuItemActive).mockReturnValue(true);
    });

    it('sets aria-current="page" when item is active', () => {
      const { getByRole } = render(
        <SidebarButton isCollapsed={false} text="nav.models" href="/models" />,
      );
      expect(getByRole('link')).toHaveAttribute('aria-current', 'page');
    });

    it('applies accent background and text classes when active', () => {
      const { getByRole } = render(
        <SidebarButton isCollapsed={false} text="nav.models" href="/models" />,
      );
      const link = getByRole('link');
      expect(link).toHaveClass('bg-accent-soft');
      expect(link).toHaveClass('text-accent-soft-foreground');
    });
  });

  describe('Inactive state', () => {
    it('does not set aria-current when inactive', () => {
      const { getByRole } = render(
        <SidebarButton isCollapsed={false} text="nav.models" href="/models" />,
      );
      expect(getByRole('link')).not.toHaveAttribute('aria-current');
    });

    it('applies bg-transparent when inactive', () => {
      const { getByRole } = render(
        <SidebarButton isCollapsed={false} text="nav.models" href="/models" />,
      );
      expect(getByRole('link')).toHaveClass('bg-transparent');
    });
  });

  describe('Mini sidebar behavior', () => {
    it('gives the label sr-only class when sidebar is mini', () => {
      const { getByRole, getByText } = render(
        <SidebarButton isCollapsed={true} text="nav.models" href="/models" />,
      );
      expect(getByText('nav.models')).toHaveClass('sr-only');
      expect(getByRole('link')).toHaveClass('h-11', 'w-12');
      expect(getByText('nav.models').parentElement).not.toHaveClass('px-2');
    });

    it('does not give the label sr-only class when sidebar is not mini', () => {
      const { getByRole, getByText } = render(
        <SidebarButton isCollapsed={false} text="nav.models" href="/models" />,
      );
      expect(getByText('nav.models')).not.toHaveClass('sr-only');
      expect(getByRole('link')).toHaveClass('h-11', 'w-full');
      expect(getByText('nav.models').parentElement).not.toHaveClass('px-2');
    });
  });

  describe('projectPrefix', () => {
    it('prefixes the href with the project path when projectPrefix is provided', () => {
      const { getByRole } = render(
        <SidebarButton
          isCollapsed={false}
          text="nav.models"
          href="/models"
          projectPrefix="my-project"
        />,
      );
      expect(getByRole('link')).toHaveAttribute('href', '/my-project/models');
    });

    it('leaves href unchanged when projectPrefix is not provided', () => {
      const { getByRole } = render(
        <SidebarButton isCollapsed={false} text="nav.models" href="/models" />,
      );
      expect(getByRole('link')).toHaveAttribute('href', '/models');
    });
  });

  describe('Accessibility', () => {
    it('has focus-visible ring classes on the link', () => {
      const { getByRole } = render(
        <SidebarButton isCollapsed={false} text="nav.models" href="/models" />,
      );
      const link = getByRole('link');
      expect(link).toHaveClass('focus-visible:ring-2');
      expect(link).toHaveClass('focus-visible:ring-accent');
    });
  });

  it('applies active styling when item is active', () => {
    vi.mocked(isMenuItemActive).mockImplementation(
      (href: string) => href === '/active-item',
    );

    const { container } = render(
      <SidebarButton
        isCollapsed={false}
        text="pages.activeItem.title"
        icon={<span>Icon</span>}
        href="/active-item"
      />,
    );

    const menuItem = container.querySelector('.menu-item');
    expect(menuItem).toHaveClass('bg-accent-soft');
    expect(menuItem).toHaveClass('text-accent-soft-foreground');
  });
});
