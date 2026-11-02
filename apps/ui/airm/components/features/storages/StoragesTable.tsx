// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import { useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { ActionItem, TableColumns } from '@amdenterpriseai/types';
import { StoragesTableField } from '@/types/enums/storages';
import { ProjectStorage, Storage } from '@/types/storages';

import {
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
  StatusDisplay,
  StatusError,
  Tooltip,
} from '@amdenterpriseai/components';

import { getStorageStatusVariants } from '@/utils/storages-status-variants';
import { StorageStatus } from '@/types/enums/storages';
interface Props {
  actions?: ActionItem<Storage>[];
  storages: Storage[];
  isStoragesLoading: boolean;
}

export const StoragesTable: React.FC<Props> = ({
  actions,
  storages,
  isStoragesLoading,
}) => {
  const { t } = useTranslation('storages');

  const columns: TableColumns<StoragesTableField | null> = [
    {
      key: StoragesTableField.NAME,
      sortable: true,
    },
    {
      key: StoragesTableField.TYPE,
      sortable: true,
    },
    {
      key: StoragesTableField.STATUS,
      sortable: true,
    },

    {
      key: StoragesTableField.SCOPE,
      sortable: true,
    },

    {
      key: StoragesTableField.ASSIGNED_TO,
    },

    {
      key: StoragesTableField.CREATED_AT,
      sortable: true,
    },
    {
      key: StoragesTableField.CREATED_BY,
      sortable: true,
    },
  ];
  const customRenderers = useMemo(
    () => ({
      [StoragesTableField.NAME]: (item: Storage) => {
        return <span>{item.name}</span>;
      },
      [StoragesTableField.TYPE]: (item: Storage) => {
        return <span>{t(`storageType.${item.type}`)}</span>;
      },
      [StoragesTableField.STATUS]: (item: Storage) => {
        const secondaryStatusReasons = item.projectStorages
          .filter((s) => s.statusReason !== null)
          .map((s) => ({
            key: s.project.name,
            description: s.statusReason ?? '',
          }));

        const hasError =
          item.status === StorageStatus.FAILED ||
          item.status === StorageStatus.DELETE_FAILED ||
          item.status === StorageStatus.SYNCED_ERROR;

        return item.status === StorageStatus.UNASSIGNED ? (
          <NoDataDisplay />
        ) : (
          <StatusDisplay
            type={item.status}
            variants={getStorageStatusVariants(t)}
            additionalProps={
              hasError &&
              !!item.statusReason &&
              secondaryStatusReasons.length > 0
                ? {
                    isClickable: true,
                    helpContent: (
                      <StatusError
                        statusReason={item.statusReason}
                        secondaryStatusReasons={secondaryStatusReasons}
                      />
                    ),
                  }
                : undefined
            }
          />
        );
      },
      [StoragesTableField.SCOPE]: (item: Storage) => {
        return t(`storageScope.${item.scope}`);
      },
      [StoragesTableField.ASSIGNED_TO]: (item: Storage) => {
        return item.projectStorages && item.projectStorages.length === 1 ? (
          <span>{item.projectStorages[0].project.name}</span>
        ) : item.projectStorages && item.projectStorages.length > 1 ? (
          <Tooltip
            content={
              <ul className="p-2 list-disc list-inside">
                {item.projectStorages.map((projectStorage: ProjectStorage) => (
                  <li key={projectStorage.id}>{projectStorage.project.name}</li>
                ))}
              </ul>
            }
            placement="top"
          >
            {/* biome-ignore lint/a11y/useSemanticElements: the element reveals supplemental text rather than performing an action. */}
            <span
              className="cursor-pointer underline"
              role="button"
              tabIndex={0}
            >{`${item.projectStorages.length} projects`}</span>
          </Tooltip>
        ) : (
          <NoDataDisplay />
        );
      },
      [StoragesTableField.CREATED_AT]: (item: Storage) => (
        <DateDisplay date={item[StoragesTableField.CREATED_AT]} />
      ),
      [StoragesTableField.CREATED_BY]: (item: Storage) => {
        return <span>{item.createdBy}</span>;
      },
    }),
    [t],
  );

  return (
    <div>
      <ClientSideDataTable
        data={storages}
        columns={columns}
        customRenderers={customRenderers}
        defaultSortByField={'name'}
        translation={t}
        idKey={'id'}
        isLoading={isStoragesLoading}
        rowActions={actions}
      />
    </div>
  );
};

export default StoragesTable;
