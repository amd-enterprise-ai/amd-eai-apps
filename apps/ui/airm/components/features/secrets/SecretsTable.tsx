// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { getFilteredData } from '@amdenterpriseai/utils/app';

import { ActionItem, TableColumns } from '@amdenterpriseai/types';
import { SecretsTableField } from '@amdenterpriseai/types';
import { ClientSideDataFilter } from '@amdenterpriseai/types';
import { Secret } from '@/types/secrets';

import { SecretStatus } from '@/types/enums/secrets';

import {
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
  StatusDisplay,
  StatusError,
  Tooltip,
} from '@amdenterpriseai/components';

import SecretProjectAssignedTo from './SecretProjectAssignedTo';
import { getSecretStatusVariants } from '@/utils/secrets-status-variants';

interface Props {
  filters?: ClientSideDataFilter<Secret>[];
  actions?: ActionItem<Secret>[];
  secrets: Secret[];
  isSecretsLoading: boolean;
}

export const SecretsTable: React.FC<Props> = ({
  filters,
  actions,
  secrets,
  isSecretsLoading,
}) => {
  const { t } = useTranslation('secrets');

  const filteredData = useMemo(() => {
    const data = secrets;
    return getFilteredData(data, filters);
  }, [secrets, filters]);

  const columns: TableColumns<SecretsTableField | null> = useMemo(() => {
    const columns = [
      {
        key: SecretsTableField.NAME,
        sortable: true,
      },
      {
        key: SecretsTableField.TYPE,
        sortable: true,
      },
      {
        key: SecretsTableField.USE_CASE,
        sortable: false,
      },
      {
        key: SecretsTableField.STATUS,
        sortable: true,
      },
      {
        key: SecretsTableField.SCOPE,
        sortable: true,
      },
      {
        key: SecretsTableField.ASSIGNED_TO,
        sortable: false,
      },
      {
        key: SecretsTableField.UPDATED_AT,
        sortable: true,
      },
    ];

    return columns;
  }, []);
  const customRenderers = useMemo(
    () => ({
      [SecretsTableField.NAME]: (item: Secret) => {
        return (
          <Tooltip content={item.name} placement="top">
            {/* biome-ignore lint/a11y/useSemanticElements: the element reveals the full name rather than performing an action. */}
            <div className="max-w-64 truncate" role="button" tabIndex={0}>
              {item.name}
            </div>
          </Tooltip>
        );
      },
      [SecretsTableField.TYPE]: (item: Secret) => {
        return (
          <span data-testid={`secret-type-${item.type}`}>
            {t(`secretType.${item.type}`)}
          </span>
        );
      },
      [SecretsTableField.STATUS]: (item: Secret) => {
        const { status, statusReason } = item;
        const secondaryStatusReasons = item.projectSecrets
          .filter((s) => s.statusReason !== null)
          .map((s) => ({
            key: s.project?.name,
            description: s.statusReason ?? '',
          }));

        const hasError =
          (status === SecretStatus.FAILED ||
            status === SecretStatus.DELETE_FAILED ||
            status === SecretStatus.SYNCED_ERROR) &&
          (!!statusReason || secondaryStatusReasons.length > 0);

        return (
          <>
            {status === SecretStatus.UNASSIGNED ? (
              <NoDataDisplay />
            ) : (
              <StatusDisplay
                type={status}
                variants={getSecretStatusVariants(t)}
                additionalProps={
                  hasError
                    ? {
                        isClickable: true,
                        helpContent: (
                          <StatusError
                            statusReason={statusReason}
                            secondaryStatusReasons={secondaryStatusReasons}
                          />
                        ),
                      }
                    : undefined
                }
              />
            )}
          </>
        );
      },
      [SecretsTableField.SCOPE]: (item: Secret) => {
        return t(`secretScope.${item.scope}`);
      },
      [SecretsTableField.USE_CASE]: (item: Secret) => {
        return item.useCase ? (
          <span>{t(`useCase.${item.useCase}`)}</span>
        ) : (
          <NoDataDisplay />
        );
      },
      [SecretsTableField.ASSIGNED_TO]: (item: Secret) => {
        return <SecretProjectAssignedTo secret={item} />;
      },
      [SecretsTableField.UPDATED_AT]: (item: Secret) => (
        <DateDisplay date={item[SecretsTableField.UPDATED_AT]} />
      ),
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
