// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';

import {
  DropdownItem,
  DropdownSection,
  UserMenu,
} from '@amdenterpriseai/components';

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { name: 'Test User', email: 'test@example.com' } },
    status: 'authenticated',
  }),
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({
    theme: 'dark',
    setTheme: vi.fn(),
  }),
}));

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {},
  }),
}));

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/hooks')>();
  return {
    ...actual,
    useSystemInfo: () => () => ['Version: 1.0.0', 'Platform: mac'],
  };
});

vi.mock('@amdenterpriseai/utils/app', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/utils/app')>();
  return {
    ...actual,
    logout: vi.fn(),
  };
});

// HeroUI Dropdown mock with compound subcomponents for our adapter
vi.mock('@heroui/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@heroui/react')>();
  const MockDropdownMenu = ({ children }: { children: React.ReactNode }) => (
    <div role="menu">{children}</div>
  );
  const MockDropdownTrigger = ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  );
  const MockDropdown = Object.assign(
    ({ children }: { children: React.ReactNode }) => {
      const childArray = React.Children.toArray(children);
      return (
        <div data-testid="dropdown-mock">
          <div data-testid="dropdown-trigger">{childArray[0]}</div>
          <div data-testid="dropdown-menu" role="menu">
            {childArray[1]}
          </div>
        </div>
      );
    },
    {
      Trigger: MockDropdownTrigger,
      Popover: ({ children }: { children: React.ReactNode }) => <>{children}</>,
      Menu: MockDropdownMenu,
      Section: ({ children }: { children: React.ReactNode }) => (
        <div>{children}</div>
      ),
      Item: ({
        children,
        href,
        target,
        rel,
        onPress,
      }: {
        children: React.ReactNode;
        href?: string;
        target?: string;
        rel?: string;
        onPress?: () => void;
      }) =>
        href ? (
          <a href={href} target={target} rel={rel}>
            {children}
          </a>
        ) : (
          <div
            role="menuitem"
            onClick={onPress}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') onPress?.();
            }}
            tabIndex={0}
          >
            {children}
          </div>
        ),
    },
  );

  return {
    ...actual,
    Dropdown: MockDropdown,
    DropdownTrigger: MockDropdownTrigger,
    DropdownMenu: MockDropdownMenu,
    DropdownSection: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
    DropdownItem: ({
      children,
      href,
      target,
      rel,
      onPress,
    }: {
      children: React.ReactNode;
      href?: string;
      target?: string;
      rel?: string;
      onPress?: () => void;
    }) =>
      href ? (
        <a href={href} target={target} rel={rel}>
          {children}
        </a>
      ) : (
        <div
          role="menuitem"
          onClick={onPress}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') onPress?.();
          }}
          tabIndex={0}
        >
          {children}
        </div>
      ),
  };
});

describe('UserMenu', () => {
  it('renders additional menu items when render prop is provided', async () => {
    const additionalItems = (
      <DropdownSection showDivider key="switch-app-section">
        <DropdownItem
          href="https://airm.example.com"
          target="_blank"
          rel="noopener noreferrer"
          key="menu-switch-app"
        >
          Resource Manager
        </DropdownItem>
      </DropdownSection>
    );

    render(<UserMenu additionalMenuItems={additionalItems} />);

    const link = await screen.findByRole('link', { name: 'Resource Manager' });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', 'https://airm.example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('does not render additional menu items when render prop is not provided', () => {
    render(<UserMenu />);

    expect(
      screen.queryByRole('link', { name: 'Resource Manager' }),
    ).not.toBeInTheDocument();
  });

  it('does not render additional menu items when render prop returns null', () => {
    render(<UserMenu additionalMenuItems={null} />);

    expect(
      screen.queryByRole('link', { name: 'Resource Manager' }),
    ).not.toBeInTheDocument();
  });

  it('renders a Report issue entry before the Logout entry', () => {
    render(<UserMenu />);
    const reportIssue = screen.getByText('menu.actions.reportIssue');
    const logout = screen.getByText('menu.actions.logout');
    expect(reportIssue).toBeInTheDocument();
    expect(logout).toBeInTheDocument();
    expect(
      reportIssue.compareDocumentPosition(logout) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).not.toBe(0);
  });

  it('renders Report issue as a pre-filled support mailto link', () => {
    render(<UserMenu />);
    const link = screen.getByRole('link', { name: 'menu.actions.reportIssue' });
    const href = link.getAttribute('href');
    expect(href).not.toBeNull();
    const url = new URL(href as string);
    expect(url.protocol).toBe('mailto:');
    expect(url.searchParams.get('subject')).toBe(
      'Issue report: [describe the problem shortly]',
    );
    expect(url.searchParams.get('body')).toBe(
      [
        'Issue:',
        '[Please describe the issue in detail, include steps to reproduce and what result was expected]',
        '',
        '--- System info ---',
        'Version: 1.0.0',
        'Platform: mac',
      ].join('\n'),
    );
  });
});
