// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { UserRole } from '@amdenterpriseai/types';
import {
  Users,
  UsersResponse,
  InvitedUser,
  InvitedUsersResponse,
} from '@/types/users';
import { ClusterStatus } from '@/types/enums/cluster-status';
import { QuotaStatus } from '@/types/enums/quotas';

const generateMockUsers = (count: number): Users => {
  return Array.from({ length: count }, (_, i) => ({
    id: (i + 1).toString(),
    firstName: `FirstName ${i + 1}`,
    lastName: `LastName ${i + 1}`,
    email: `user${i + 1}@amd.com`,
    role: UserRole.PLATFORM_ADMIN,
    createdAt: new Date(
      Date.now() - (i + 1) * 24 * 60 * 60 * 1000,
    ).toISOString(),
    lastActiveAt:
      i === 0
        ? undefined
        : new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString(),
    projects: [
      {
        id: (i + 1).toString(),
        clusterId: '1',
        name: `${(i + 1).toString()} group name`,
        description: `${(i + 1).toString()} group description`,
        quota: {
          status: QuotaStatus.PENDING,
          cpuMilliCores: 1000,
          gpuCount: 1,
          memoryBytes: 2000,
          ephemeralStorageBytes: 10000,
        },
        cluster: {
          id: '456',
          name: 'Test Cluster',
          status: ClusterStatus.HEALTHY,
          lastHeartbeatAt: new Date().toISOString(),
        },
      },
    ],
  }));
};

const generateMockInvitedUsers = (count: number): InvitedUser[] => {
  return Array.from({ length: count }, (_, i) => ({
    id: (i + 1).toString(),
    email: `invited${i + 1}@amd.com`,
    role: UserRole.PLATFORM_ADMIN,
    invitedAt: '2025-01-01T00:00:00Z',
    invitedBy: 'inviter@amd.com',
  }));
};

export const mockUsersResponse: UsersResponse = { data: generateMockUsers(5) };
export const mockInvitedUsersResponse: InvitedUsersResponse = {
  data: generateMockInvitedUsers(3),
};
