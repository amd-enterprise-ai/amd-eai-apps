// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { getFilteredData } from '@amdenterpriseai/utils/app';

import { ActionItem, TableColumns } from '@amdenterpriseai/types';
import { SecretsTableField } from '@amdenterpriseai/types';
import { ClientSideDataFilter } from '@amdenterpriseai/types';
import { SecretResponseData } from '@/types/secrets';

import {
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
} from '@amdenterpriseai/components';

import { SUBMITTER_ANNOTATION_KEY } from './constants';

interface Props {
  filters?: ClientSideDataFilter<SecretResponseData>[];
  actions?: ActionItem<SecretResponseData>[];
  secrets: SecretResponseData[];
  isSecretsLoading: boolean;
  showScopeColumn?: boolean;
  showAssignedToColumn?: boolean;
}

export const SecretsTable: React.FC<Props> = ({
  filters,
  actions,
  secrets,
  isSecretsLoading,
  showScopeColumn = true,
  showAssignedToColumn = true,
}) => {
  const { t } = useTranslation('secrets');

  const filteredData = useMemo(() => {
    const data = getFilteredData(secrets, filters);
    return data.map((item) => ({
      ...item,
      id: item.metadata.uid ?? item.metadata.name,
      [SecretsTableField.CREATED_BY]:
        item.metadata?.annotations?.[SUBMITTER_ANNOTATION_KEY],
      [SecretsTableField.CREATED_AT]: item.metadata.creationTimestamp,
    }));
  }, [secrets, filters]);

  const columns: TableColumns<SecretsTableField | null> = useMemo(() => {
    const columns = [
      {
        key: SecretsTableField.NAME,
        sortable: true,
      },
      // TODO: Fix (or clean up) these colums after decoupling
      // {
      //   key: SecretsTableField.TYPE,
      //   sortable: true,
      // },
      {
        key: SecretsTableField.USE_CASE,
        sortable: true,
      },
      {
        key: SecretsTableField.CREATED_BY,
        sortable: true,
      },
    ];

    // Conditionally add scope column
    if (showScopeColumn) {
      columns.push({
        key: SecretsTableField.SCOPE,
        sortable: true,
      });
    }

    // Conditionally add assigned to column
    if (showAssignedToColumn) {
      columns.push({
        key: SecretsTableField.ASSIGNED_TO,
        sortable: false,
      });
    }

    // Always add updated at column at the end
    columns.push({
      key: SecretsTableField.CREATED_AT,
      sortable: true,
    });

    return columns;
  }, [showScopeColumn, showAssignedToColumn]);

  const customRenderers = useMemo(
    () => ({
      [SecretsTableField.NAME]: (item: SecretResponseData) => (
        <div className={'max-w-64 truncate'}>
          {item.displayName ?? item.metadata.name}
        </div>
      ),
      // TODO: Fix (or clean up) these colums after decoupling
      // [SecretsTableField.TYPE]: (item: SecretResponseData) => {
      //   return (
      //     <span data-testid={`secret-type-${item.metadata.type}`}>
      //       {t(`secretType.${item.metadata.type}`)}
      //     </span>
      //   );
      // },
      // [SecretsTableField.SCOPE]: (item: SecretResponseData) => {
      //   return t(`secretScope.${item.scope}`);
      // },
      // [SecretsTableField.ASSIGNED_TO]: (item: SecretResponseData) => {
      //   return <SecretProjectAssignedTo secret={item} />;
      // },
      [SecretsTableField.USE_CASE]: (item: SecretResponseData) => {
        return item.useCase ? (
          <span>{t(`useCase.${item.useCase}`)}</span>
        ) : (
          <NoDataDisplay />
        );
      },
      [SecretsTableField.CREATED_BY]: (item: {
        [SecretsTableField.CREATED_BY]: string | undefined;
      }) =>
        item[SecretsTableField.CREATED_BY] ? (
          <span>{item[SecretsTableField.CREATED_BY]}</span>
        ) : (
          <NoDataDisplay />
        ),
      [SecretsTableField.CREATED_AT]: (item: {
        [SecretsTableField.CREATED_AT]: string | null | undefined;
      }) => {
        const createdAt = item[SecretsTableField.CREATED_AT];
        return createdAt ? <DateDisplay date={createdAt} /> : <NoDataDisplay />;
      },
    }),
    [t],
  );

  return (
    <div>
      <ClientSideDataTable
        data={filteredData}
        columns={columns}
        customRenderers={customRenderers}
        defaultSortByField={'name'}
        translation={t}
        idKey={'id'}
        isLoading={isSecretsLoading}
        rowActions={actions}
      />
    </div>
  );
};

export default SecretsTable;
