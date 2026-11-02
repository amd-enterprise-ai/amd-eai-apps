// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';
import { useQuery } from '@tanstack/react-query';

import { fetchUsers } from '@/services/app';
import { getFilteredData } from '@amdenterpriseai/utils/app';
import { compareUsersByFullName } from '@amdenterpriseai/utils/app';
import { dateComparator } from '@amdenterpriseai/utils/app';

import { TableColumns } from '@amdenterpriseai/types';
import { CustomComparatorConfig } from '@amdenterpriseai/types';
import { FilterComponentType } from '@amdenterpriseai/types';
import { UserTableField } from '@/types/enums/user-table-fields';
import { ClientSideDataFilter, FilterValueMap } from '@amdenterpriseai/types';
import { User, UsersResponse } from '@/types/users';

import { InviteUserButton } from '@/components/features/users/InviteUserButton';
import {
  ActionsToolbar,
  ClientSideDataTable,
  DateDisplay,
} from '@amdenterpriseai/components';
import { useAccessControl } from '@/hooks/useAccessControl';

const customComparator: CustomComparatorConfig<User, UserTableField> = {
  [UserTableField.NAME]: compareUsersByFullName,
  [UserTableField.CREATED_AT]: (a, b) =>
    dateComparator(a.createdAt, b.createdAt),
  [UserTableField.ROLES]: (a: User, b: User): number =>
    a.role.localeCompare(b.role),
};

const columns: TableColumns<UserTableField | null> = [
  {
    key: UserTableField.NAME,
    sortable: true,
  },
  {
    key: UserTableField.EMAIL,
    sortable: true,
  },
  { key: UserTableField.CREATED_AT, sortable: true },
  { key: UserTableField.ROLES, sortable: true },
];

interface ActiveUsersTabProps {
  initialData: UsersResponse;
  onInviteUserClick: () => void;
}

export const ActiveUsersTab = ({
  initialData,
  onInviteUserClick,
}: ActiveUsersTabProps) => {
  const { t } = useTranslation('users');
  const router = useRouter();
  const [filter, setFilter] = useState<ClientSideDataFilter<User>[]>([]);
  const { isInviteEnabled } = useAccessControl();

  const handleFilterChange = useCallback(
    (filterValues: FilterValueMap) => {
      const filterableFields: (keyof User)[] = [
        'firstName',
        'lastName',
        'email',
      ];
      if (
        filterValues.search &&
        !(
          Array.isArray(filterValues.search) &&
          filterValues.search.length === 1 &&
          filterValues.search[0] === ''
        )
      ) {
        setFilter([
          {
            values: filterValues.search,
            compositeFields: filterableFields.map((field) => ({ field })),
          },
        ]);
      } else {
        setFilter([]);
      }
    },
    [setFilter],
  );

  const { data, isFetching, isRefetching, refetch, dataUpdatedAt } =
    useQuery<UsersResponse>({
      queryKey: ['users'],
      queryFn: fetchUsers,
      initialData,
    });

  const filteredUsersData = useMemo(() => {
    if (data?.data) {
      return getFilteredData(data.data, filter);
    }
  }, [filter, data?.data]);

  const customRenderers: Partial<
    Record<UserTableField, (item: User) => React.ReactNode | string>
  > = {
    [UserTableField.NAME]: (item) => `${item.firstName} ${item.lastName}`,
    [UserTableField.CREATED_AT]: (item) =>
      item.createdAt ? <DateDisplay date={item.createdAt} /> : '-',
    [UserTableField.ROLES]: (item) => item.role,
  };

  const navigateToUserDetails = (id: string) => {
    router.push(`/users/${id}`);
  };

  const filterConfig = {
    search: {
      name: 'search',
      label: t('list.filter.label'),
      placeholder: t('list.filter.placeholder'),
      type: FilterComponentType.TEXT,
    },
  };

  return (
    <div className="inline-flex flex-col w-full h-full max-h-full">
      <ActionsToolbar
        filterConfig={filterConfig}
        onFilterChange={handleFilterChange}
        onRefresh={refetch}
        isRefreshing={isFetching || isRefetching}
        updatedTimestamp={dataUpdatedAt}
        endContent={
          isInviteEnabled ? (
            <InviteUserButton
              onClick={onInviteUserClick}
              label={t('actions.addUser.label')}
            />
          ) : undefined
        }
      />
      {filteredUsersData && (
        <ClientSideDataTable
          data={filteredUsersData}
          className="flex-1 overflow-y-auto"
          columns={columns}
          defaultSortByField={UserTableField.NAME}
          customComparator={customComparator}
          customRenderers={customRenderers}
          translation={t}
          idKey="id"
          isFetching={isFetching || isRefetching}
          onRowPressed={navigateToUserDetails}
          rowActions={[
            {
              key: 'edit',
              onPress: (item) => navigateToUserDetails(item.id),
              label: t('actions.editUser.label'),
            },
          ]}
        />
      )}
    </div>
  );
};
