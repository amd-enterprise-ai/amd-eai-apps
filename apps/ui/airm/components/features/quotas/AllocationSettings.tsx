// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  cn,
  FormSliderNumberInput,
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableRow,
} from '@amdenterpriseai/components';
import { useMemo } from 'react';
import { UseFormReturn } from 'react-hook-form';

import { useTranslation } from 'next-i18next';

import { bytesToGigabytes } from '@amdenterpriseai/utils/app';
import { displayFixedNumber } from '@amdenterpriseai/utils/app';

import { Cluster } from '@/types/clusters';
import { QuotaResource } from '@/types/enums/quotas';
import { QuotaAllocationEditFields } from '@/types/enums/quotas-form-fields';
import { Quota } from '@/types/quotas';

import { ProjectQuotaFormData } from '@/types/projects';

interface Props {
  form: UseFormReturn<ProjectQuotaFormData>;
  quota: Quota;
  cluster?: Cluster;
  isReadonly?: boolean;
}

type SettingField = {
  id: string;
  name: QuotaAllocationEditFields;
  label: string;
  availableToAllocate: number;
  displayCapacityUnit?: boolean;
  disabled?: boolean;
};

const translationKeySet = 'projects';

const restrictToPositive = (value: number) => Math.max(value, 0);

export const AllocationSettings: React.FC<Props> = ({
  form,
  quota,
  cluster,
  isReadonly = false,
}) => {
  const { t } = useTranslation(translationKeySet);

  const settings: SettingField[] = useMemo(() => {
    return [
      {
        id: 'gpu',
        name: QuotaAllocationEditFields.GPU,
        label: t('settings.form.guaranteedQuota.fields.gpu'),
        availableToAllocate: cluster?.gpuInfo
          ? restrictToPositive(
              cluster.availableResources[QuotaResource.GPU] -
                cluster.allocatedResources[QuotaResource.GPU] +
                (quota ? quota[QuotaResource.GPU] : 0),
            )
          : 0,
        disabled: !cluster?.gpuInfo,
      },
      {
        id: 'cpu',
        name: QuotaAllocationEditFields.CPU,
        label: t('settings.form.guaranteedQuota.fields.cpu'),
        availableToAllocate: cluster
          ? restrictToPositive(
              (cluster.availableResources[QuotaResource.CPU] -
                cluster.allocatedResources[QuotaResource.CPU] +
                (quota ? quota[QuotaResource.CPU] : 0)) /
                1000,
            )
          : 0,
      },
      {
        id: 'ram',
        name: QuotaAllocationEditFields.RAM,
        label: t('settings.form.guaranteedQuota.fields.ram'),
        availableToAllocate: cluster
          ? bytesToGigabytes(
              restrictToPositive(
                cluster.availableResources[QuotaResource.RAM] -
                  cluster.allocatedResources[QuotaResource.RAM] +
                  (quota ? quota[QuotaResource.RAM] : 0),
              ),
            )
          : 0,
        displayCapacityUnit: true,
      },
      {
        id: 'disk',
        name: QuotaAllocationEditFields.DISK,
        label: t('settings.form.guaranteedQuota.fields.disk'),
        availableToAllocate: cluster
          ? bytesToGigabytes(
              restrictToPositive(
                cluster.availableResources[QuotaResource.DISK] -
                  cluster.allocatedResources[QuotaResource.DISK] +
                  (quota ? quota[QuotaResource.DISK] : 0),
              ),
            )
          : 0,
        displayCapacityUnit: true,
      },
    ];
  }, [quota, cluster, t]);

  const columns = [
    {
      id: 'resource',
      label: t('settings.form.guaranteedQuota.groups.resource'),
      className: 'w-36',
      isRowHeader: true,
    },
    {
      id: 'allocation',
      label: t('settings.form.guaranteedQuota.groups.allocation'),
    },
    {
      id: 'available',
      label: t('settings.form.guaranteedQuota.groups.available'),
      className: 'w-36 whitespace-normal',
    },
  ];

  return (
    <Table.Root className="shadow-none p-0">
      <Table.ScrollContainer>
        <Table.Content
          aria-label={t('settings.form.guaranteedQuota.title') || ''}
          className="table-fixed w-full"
        >
          <Table.Header columns={columns}>
            {(column) => (
              <TableColumn
                className={cn('text-sm', column.className)}
                id={column.id}
                isRowHeader={column.isRowHeader}
              >
                {column.label}
              </TableColumn>
            )}
          </Table.Header>
          <TableBody items={settings}>
            {(item: SettingField) => (
              <TableRow
                className={cn({
                  'text-foreground': item.disabled,
                  'text-opacity-disabled': item.disabled,
                })}
                id={item.id}
              >
                <TableCell className="max-w-1/4">{item.label}</TableCell>
                <TableCell className="min-w-0">
                  {isReadonly ? (
                    <span>
                      {`${displayFixedNumber(form.watch(item.name) ?? 0)} ${
                        item.displayCapacityUnit ? 'GB' : ''
                      }`}
                    </span>
                  ) : (
                    <FormSliderNumberInput
                      form={form}
                      name={item.name}
                      aria-label={item.label}
                      minValue={0}
                      maxValue={item.availableToAllocate}
                      step={1}
                      isDisabled={
                        item.disabled || item.availableToAllocate === 0
                      }
                    />
                  )}
                </TableCell>
                <TableCell>
                  {`${displayFixedNumber(item.availableToAllocate)} ${
                    item.displayCapacityUnit ? 'GB' : ''
                  }`}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table.Content>
      </Table.ScrollContainer>
    </Table.Root>
  );
};

export default AllocationSettings;
