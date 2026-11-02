// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconChartBar, IconEdit, IconTrash } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import { useProject } from '@/contexts/ProjectContext';

import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';

import { deleteApiKey, fetchProjectApiKeys } from '@/lib/app/api-keys';

import { getFilteredData } from '@amdenterpriseai/utils/app';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import type { components } from '@/types/api';
import { TableColumns } from '@amdenterpriseai/types';
import { FilterComponentType } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';
import { ClientSideDataFilter } from '@amdenterpriseai/types';

import CreateApiKey from '@/components/features/api-keys/CreateApiKey';
import DeleteApiKeyModal from '@/components/features/api-keys/DeleteApiKeyModal';
import {
  ActionsToolbar,
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
} from '@amdenterpriseai/components';

const ApiKeysTableField = {
  NAME: 'name',
  SECRET_KEY: 'secretKey',
  CREATED_AT: 'createdAt',
  CREATED_BY: 'createdBy',
} as const;

type ApiKeysTableField =
  (typeof ApiKeysTableField)[keyof typeof ApiKeysTableField];

type ApiKey = components['schemas']['ApiKeyResponse'];

interface Props {
  projectId: string;
  createButton?: React.ReactNode;
}

const columns: TableColumns<ApiKeysTableField | null> = [
  {
    key: ApiKeysTableField.NAME,
    sortable: true,
  },
  {
    key: ApiKeysTableField.SECRET_KEY,
    sortable: false,
  },
  {
    key: ApiKeysTableField.CREATED_AT,
    sortable: true,
  },
  {
    key: ApiKeysTableField.CREATED_BY,
    sortable: true,
  },
];

const API_KEYS_QUERY_KEY = 'project-api-keys';

export const ApiKeysTable: React.FC<Props> = ({ projectId, createButton }) => {
  const { t } = useTranslation('api-keys');
  const router = useRouter();
  const { projectPath, aiGatewayEnabled } = useProject();
  const queryClient = useQueryClient();
  const { toast } = useSystemToast();
  const [apiKeySelected, setApiKeySelected] = useState<ApiKey | undefined>();
  const [filters, setFilters] = useState<ClientSideDataFilter<ApiKey>[]>([]);

  const {
    isOpen: isDeleteApiKeyModalOpen,
    onOpen: onDeleteApiKeyModalOpen,
    onOpenChange,
  } = useOverlayState();

  const {
    isOpen: isEditApiKeyModalOpen,
    onOpen: onEditApiKeyModalOpen,
    onClose: onEditApiKeyModalClose,
  } = useOverlayState();

  const { mutate: deleteApiKeyMutation } = useMutation({
    mutationFn: ({
      projectId,
      apiKeyId,
    }: {
      projectId: string;
      apiKeyId: string;
    }) => deleteApiKey(projectId, apiKeyId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [API_KEYS_QUERY_KEY, projectId],
      });
      toast.success(t('list.actions.delete.notification.success'));
    },
    onError: (error) => {
      toast.error(
        t('list.actions.delete.notification.error'),
        error as APIRequestError,
      );
    },
  });

  const {
    data: apiKeysData,
    isFetching: isApiKeysLoading,
    refetch: refetchApiKeys,
    dataUpdatedAt: apiKeysUpdatedAt,
  } = useQuery({
    queryKey: [API_KEYS_QUERY_KEY, projectId],
    queryFn: () => fetchProjectApiKeys(projectId),
    enabled: !!projectId,
  });

  const filteredApiKeys = useMemo(
    () => getFilteredData(apiKeysData?.data ?? [], filters),
    [apiKeysData?.data, filters],
  );

  const customRenderers: Partial<
    Record<ApiKeysTableField, (item: ApiKey) => React.ReactNode | string>
  > = {
    [ApiKeysTableField.NAME]: (item) => item.displayName,
    [ApiKeysTableField.SECRET_KEY]: (item) => (
      <code className="text-sm font-mono">{item.truncatedKey}</code>
    ),
    [ApiKeysTableField.CREATED_AT]: (item) => {
      if (item.createdAt) {
        return <DateDisplay date={item.createdAt} />;
      }
      return <NoDataDisplay />;
    },
  };

  const rowActions = () => [
    ...(aiGatewayEnabled
      ? [
          {
            key: 'viewDetails',
            label: t('list.actions.viewDetails.title'),
            color: 'default',
            startContent: <IconChartBar />,
            onPress: (apiKey: ApiKey) => {
              router.push(
                projectPath(
                  `/api-keys/${apiKey.id}?name=${encodeURIComponent(apiKey.displayName)}`,
                ),
              );
            },
          },
        ]
      : []),
    {
      key: 'edit',
      label: t('list.actions.edit.title'),
      color: 'default',
      startContent: <IconEdit />,
      onPress: (apiKey: ApiKey) => {
        setApiKeySelected(apiKey);
        onEditApiKeyModalOpen();
      },
    },
    {
      key: 'delete',
      label: t('list.actions.delete.title'),
      color: 'danger',
      startContent: <IconTrash />,
      onPress: (apiKey: ApiKey) => {
        setApiKeySelected(apiKey);
        onDeleteApiKeyModalOpen();
      },
    },
  ];

  const filterConfig = useMemo(
    () => ({
      search: {
        name: 'search',
        label: t('list.filters.search.placeholder'),
        placeholder: t('list.filters.search.placeholder'),
        type: FilterComponentType.TEXT,
      },
    }),
    [t],
  );

  const handleFilterChange = (newFilters: Record<string, string[]>) => {
    const clientFilters: ClientSideDataFilter<ApiKey>[] = [];

    if (
      newFilters?.search &&
      newFilters.search.length > 0 &&
      !(newFilters.search.length === 1 && newFilters.search[0] === '')
    ) {
      clientFilters.push({
        field: 'displayName',
        values: newFilters.search,
      });
    }

    setFilters(clientFilters);
  };

  return (
    <div>
      <ActionsToolbar
        filterConfig={filterConfig}
        onFilterChange={handleFilterChange}
        onRefresh={refetchApiKeys}
        updatedTimestamp={apiKeysUpdatedAt}
        isRefreshing={isApiKeysLoading}
        endContent={createButton}
      />
      <ClientSideDataTable
        data={filteredApiKeys}
        columns={columns}
        customRenderers={customRenderers}
        defaultSortByField={ApiKeysTableField.CREATED_AT}
        defaultSortDirection={SortDirection.DESC}
        rowActions={rowActions}
        translation={t}
        idKey="id"
        translationKeyPrefix="apiKeys"
        isLoading={isApiKeysLoading}
      />
      <DeleteApiKeyModal
        isOpen={isDeleteApiKeyModalOpen}
        onOpenChange={onOpenChange}
        apiKey={apiKeySelected}
        onConfirmAction={(apiKey) =>
          deleteApiKeyMutation({ projectId, apiKeyId: apiKey.id })
        }
      />
      <CreateApiKey
        isOpen={isEditApiKeyModalOpen}
        projectId={projectId}
        apiKey={apiKeySelected}
        onClose={onEditApiKeyModalClose}
      />
    </div>
  );
};

export default ApiKeysTable;
