// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { QueryClient } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';

import { fetchOrganization } from '@/services/app';
import { fetchProjects } from '@/services/app';
import { useAccessControl } from '@/hooks/useAccessControl';

import { generateMockProjects } from '@/__mocks__/utils/project-mock';

import { Organization } from '@/types/organization';
import { ProjectWithMembers } from '@/types/projects';

import { InvitedUsers } from '@/components/features/projects';

import wrapper from '@/__tests__/ProviderWrapper';
import { Mock } from 'vitest';
import { UserRole } from '@amdenterpriseai/types';

vi.mock('@/services/app', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    fetchProjects: vi.fn(),
    fetchOrganization: vi.fn(),
  };
});

// Mock useAccessControl to ensure resend invitation button is enabled
vi.mock('@/hooks/useAccessControl', () => ({
  useAccessControl: vi.fn(() => ({
    isRoleManagementEnabled: true,
    isInviteEnabled: true,
    isAdministrator: true,
    smtpEnabled: true,
    isTempPasswordRequired: false,
  })),
}));

const mockProject: ProjectWithMembers = {
  ...generateMockProjects(1)[0],
  users: [
    {
      id: 'user1',
      firstName: 'User 1',
      lastName: 'Last 1',
      role: UserRole.TEAM_MEMBER,
      email: 'user1@example.com',
    },
  ],
  invitedUsers: [
    {
      id: 'user2',
      email: 'user2@example.com',
      role: UserRole.PLATFORM_ADMIN,
      invitedAt: '2025-10-01T00:00:00Z',
      invitedBy: 'test@example.com',
    },
    {
      id: 'user3',
      email: 'user3@example.com',
      role: UserRole.TEAM_MEMBER,
      invitedAt: '2025-10-01T00:00:00Z',
      invitedBy: 'test@example.com',
    },
  ],
};

const mockFullOrganization: Organization = {
  idpLinked: false,
  smtpEnabled: false,
};

describe('InvitedUsers', () => {
  const mockFetchProjects = fetchProjects as Mock;

  beforeEach(async () => {
    mockFetchProjects.mockClear();

    vi.mocked(useAccessControl).mockReturnValue({
      isRoleManagementEnabled: true,
      isInviteEnabled: false,
      isAdministrator: true,
      smtpEnabled: false,
      isTempPasswordRequired: false,
    });
  });

  it('renders the component with Invited Users', () => {
    act(() => {
      render(<InvitedUsers project={mockProject} />, { wrapper });
    });
    expect(
      screen.getByText('settings.membersAndInvitedUsers.invitedUsers.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('user2@example.com')).toBeInTheDocument();
    expect(screen.getByText('user3@example.com')).toBeInTheDocument();
  });

  it('renders the component without Invited Users', () => {
    act(() => {
      render(<InvitedUsers project={{ ...mockProject, invitedUsers: [] }} />, {
        wrapper,
      });
    });
    expect(
      screen.getByText('settings.membersAndInvitedUsers.invitedUsers.title'),
    ).toBeInTheDocument();
  });

  it('Able to open the invite user modal with the project pre-selected', async () => {
    mockFetchProjects.mockResolvedValue({
      data: [mockProject],
    });
    await act(async () => {
      render(<InvitedUsers project={mockProject} />, { wrapper });
    });
    const addButton = screen.getByLabelText(
      'settings.membersAndInvitedUsers.invitedUsers.actions.add.title',
    ) as HTMLInputElement;

    await waitFor(() => expect(mockFetchProjects).toBeCalled());

    await fireEvent.click(addButton);

    const projectSelect = within(screen.getByTestId('project-select'));
    expect(projectSelect.getAllByText(mockProject.name).length).toBeGreaterThan(
      0,
    );
  });
});

describe('Invite User button enabled/disabled state', () => {
  const mockFetchOrg = fetchOrganization as Mock;
  let queryClient: QueryClient;

  beforeEach(async () => {
    vi.mocked(useAccessControl).mockReturnValue({
      isRoleManagementEnabled: true,
      isInviteEnabled: false,
      isAdministrator: true,
      smtpEnabled: false,
      isTempPasswordRequired: false,
    });
  });

  it('disables the Invite User button if org has identity provider', async () => {
    mockFetchOrg.mockResolvedValue({
      ...mockFullOrganization,
      idpLinked: true,
    });
    await act(() => {
      render(<InvitedUsers project={mockProject} />, { wrapper });
    });

    const inviteButton = screen.getByLabelText(
      'settings.membersAndInvitedUsers.invitedUsers.actions.add.title',
    ) as HTMLInputElement;
    await waitFor(() => {
      expect(inviteButton).toBeDisabled();
    });
  });

  it('enables the Invite User button if org does not have identity provider', async () => {
    mockFetchOrg.mockResolvedValue({
      ...mockFullOrganization,
      idpLinked: false,
    });
    await act(() => {
      render(<InvitedUsers project={mockProject} />, { wrapper });
    });
    const inviteButton = screen.getByLabelText(
      'settings.membersAndInvitedUsers.invitedUsers.actions.add.title',
    ) as HTMLInputElement;
    await waitFor(() => {
      expect(inviteButton).toBeEnabled();
    });
  });

  it('enables the Invite User button if identity provider info fails to load', async () => {
    mockFetchOrg.mockRejectedValue(new Error('API Error'));
    await act(() => {
      render(<InvitedUsers project={mockProject} />, { wrapper });
    });
    const inviteButton = screen.getByLabelText(
      'settings.membersAndInvitedUsers.invitedUsers.actions.add.title',
    ) as HTMLInputElement;
    await waitFor(() => {
      expect(inviteButton).toBeEnabled();
    });
  });
});
