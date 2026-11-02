// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormRadioGroup,
  Radio,
  Select,
  SelectItem,
  SortableColumnHeader,
  Table,
  cn,
  type Selection,
  type SortDescriptor,
} from '@amdenterpriseai/components';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'next-i18next';
import type { UseFormReturn } from 'react-hook-form';

import { getMetricTranslationKey } from '@/lib/app/aims';
import {
  ADVANCED_PARAM_AUTOMATIC,
  formatAccelerator,
  formatClass,
} from '@/lib/app/aims/filterProfilesByAdvancedParams';
import {
  AIM_PROFILE_TYPE_OPTIMIZED,
  type AIMClusterProfile,
} from '@/types/aims';

import type { AdvancedProfileOptions, DeployAIMFormValues } from './types';
import { UnoptimizedProfileBadge } from './UnoptimizedProfileBadge';

type AdvancedProfileFieldsProps = {
  form: UseFormReturn<DeployAIMFormValues>;
  advancedProfileOptions: AdvancedProfileOptions;
  filteredProfiles: AIMClusterProfile[];
  noProfileMatches: boolean;
};

type ProfileSortColumn = 'accelerator' | 'precision' | 'metric' | 'class';
type AdvancedParamName =
  | 'optimizationClass'
  | 'gpuModel'
  | 'precision'
  | 'gpuCount';

const selectionToString = (keys: Selection): string =>
  String(Array.from(keys)[0] ?? ADVANCED_PARAM_AUTOMATIC);

const profileSortKey = (
  profile: AIMClusterProfile,
  column: ProfileSortColumn,
  translateMetric: (metric: string) => string,
): string => {
  const spec = profile.spec;
  switch (column) {
    case 'accelerator':
      return `${spec?.acceleratorModel ?? ''}\0${spec?.acceleratorCount ?? 0}`;
    case 'precision':
      return spec?.precision ?? '';
    case 'metric':
      return spec?.metric ? translateMetric(String(spec.metric)) : '';
    case 'class':
      return spec?.type ?? '';
  }
};

export function AdvancedProfileFields({
  form,
  advancedProfileOptions,
  filteredProfiles,
  noProfileMatches,
}: AdvancedProfileFieldsProps) {
  const { t } = useTranslation('models');
  const [sortDescriptor, setSortDescriptor] = useState<SortDescriptor>({
    column: 'accelerator',
    direction: 'ascending',
  });

  const profileAutomaticLabel = t(
    'deployAIM.fields.advancedProfileParams.automaticSelection',
  );
  const profileAutomaticPlaceholder = t(
    'deployAIM.fields.advancedProfileParams.automaticSelectionFromProfiles',
    { count: filteredProfiles.length },
  );

  const profileSelectPlaceholder = noProfileMatches
    ? t('deployAIM.fields.advancedProfileParams.noMatchingProfiles')
    : profileAutomaticPlaceholder;

  const translateMetric = (metric: string) =>
    t(getMetricTranslationKey(metric));

  const column = sortDescriptor.column as ProfileSortColumn;
  const direction = sortDescriptor.direction === 'descending' ? -1 : 1;
  const sortedProfiles = [...filteredProfiles].sort(
    (a, b) =>
      direction *
      profileSortKey(a, column, translateMetric).localeCompare(
        profileSortKey(b, column, translateMetric),
        undefined,
        { numeric: true },
      ),
  );

  const setAdvancedParam = (name: AdvancedParamName, keys: Selection) => {
    form.setValue(name, selectionToString(keys), { shouldDirty: true });
  };

  const profileTableLabel = t('deployAIM.fields.advancedProfileParams.profile');
  const advancedParams: Array<{
    name: AdvancedParamName;
    label: string;
    options: string[];
    capitalize?: boolean;
  }> = [
    {
      name: 'gpuModel',
      label: t('deployAIM.fields.advancedProfileParams.gpu'),
      options: advancedProfileOptions.gpuModels,
    },
    {
      name: 'gpuCount',
      label: t('deployAIM.fields.advancedProfileParams.gpuCount'),
      options: advancedProfileOptions.gpuCounts,
    },
    {
      name: 'precision',
      label: t('deployAIM.fields.advancedProfileParams.precision'),
      options: advancedProfileOptions.precisions,
    },
    {
      name: 'optimizationClass',
      label: t('deployAIM.fields.advancedProfileParams.optimizationClass'),
      options: advancedProfileOptions.optimizationClasses,
      capitalize: true,
    },
  ];
  const columns: Array<{
    id: ProfileSortColumn;
    label: string;
    isRowHeader?: boolean;
  }> = [
    {
      id: 'accelerator',
      label: t('deployAIM.fields.advancedProfileParams.gpu'),
      isRowHeader: true,
    },
    {
      id: 'precision',
      label: t('deployAIM.fields.advancedProfileParams.precision'),
    },
    {
      id: 'metric',
      label: t('deployAIM.fields.advancedProfileParams.metric'),
    },
    {
      id: 'class',
      label: t('deployAIM.fields.advancedProfileParams.class'),
    },
  ];

  const selectProfile = (profileName: string) => {
    form.setValue('profileName', profileName, {
      shouldDirty: true,
      shouldValidate: true,
    });
  };

  return (
    <div className="flex flex-col gap-4 pl-1">
      <div className="grid grid-cols-4 gap-4">
        {advancedParams.map(({ name, label, options, capitalize }) => (
          <Select
            key={name}
            name={name}
            defaultSelectedKeys={[
              form.getValues(name) ?? ADVANCED_PARAM_AUTOMATIC,
            ]}
            onSelectionChange={(keys) => setAdvancedParam(name, keys)}
            label={label}
            aria-label={label}
            placeholder={t(
              'deployAIM.fields.advancedProfileParams.placeholder',
            )}
            className={cn(
              '[&_[data-slot=select-trigger]]:w-full [&_[data-slot=select-trigger]]:min-w-0',
              capitalize && '[&_[data-slot=select-value]]:capitalize',
            )}
          >
            <SelectItem key={ADVANCED_PARAM_AUTOMATIC}>
              {t('deployAIM.fields.advancedProfileParams.automatic')}
            </SelectItem>
            {options.map((value) => (
              <SelectItem
                key={value}
                className={capitalize ? 'capitalize' : undefined}
              >
                {value}
              </SelectItem>
            ))}
          </Select>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        <FormRadioGroup
          name="profileName"
          form={form}
          aria-label={profileTableLabel}
          className="[&_[data-slot=radio]]:mt-0"
        >
          <Table.Root>
            <Table.ScrollContainer>
              <Table.Content
                aria-label={profileTableLabel}
                sortDescriptor={sortDescriptor}
                onSortChange={setSortDescriptor}
                onRowAction={(rowId) => selectProfile(String(rowId))}
                selectionMode="none"
                className="w-full"
                data-testid="deployAimAdvancedProfileTable"
              >
                <Table.Header>
                  <Table.Column id="select" className="w-10 pr-0">
                    <span className="sr-only">
                      {t('deployAIM.fields.advancedProfileParams.select')}
                    </span>
                  </Table.Column>
                  {columns.map(({ id, label, isRowHeader }) => (
                    <Table.Column
                      key={id}
                      id={id}
                      allowsSorting
                      isRowHeader={isRowHeader}
                    >
                      {({
                        sortDirection,
                      }: {
                        sortDirection?: 'ascending' | 'descending';
                      }) => (
                        <SortableColumnHeader sortDirection={sortDirection}>
                          {label}
                        </SortableColumnHeader>
                      )}
                    </Table.Column>
                  ))}
                </Table.Header>
                <Table.Body>
                  <Table.Row
                    id={ADVANCED_PARAM_AUTOMATIC}
                    className="cursor-pointer"
                  >
                    <Table.Cell className="pr-0">
                      <Radio
                        value={ADVANCED_PARAM_AUTOMATIC}
                        aria-label={profileAutomaticLabel}
                      />
                    </Table.Cell>
                    <Table.Cell colSpan={4}>
                      <span className="inline-flex items-center gap-2 text-sm">
                        {noProfileMatches ? (
                          <IconAlertTriangle
                            size={18}
                            className="shrink-0 text-warning"
                            aria-hidden
                          />
                        ) : null}
                        <span className="font-medium">
                          {profileAutomaticLabel}
                        </span>
                        <span className="text-muted">
                          {profileSelectPlaceholder}
                        </span>
                      </span>
                    </Table.Cell>
                  </Table.Row>
                  {sortedProfiles.map((profile) => {
                    const spec = profile.spec;
                    const isOptimized =
                      spec?.type === AIM_PROFILE_TYPE_OPTIMIZED;
                    const accelerator = formatAccelerator(profile);
                    const precision = spec?.precision ?? '—';
                    const metric = spec?.metric
                      ? translateMetric(String(spec.metric))
                      : '—';
                    const profileClass = formatClass(spec?.type ?? undefined);
                    const rowLabel = `${accelerator}, ${precision}, ${metric}, ${profileClass}`;
                    return (
                      <Table.Row
                        key={profile.metadata.name}
                        id={profile.metadata.name}
                        className="cursor-pointer"
                      >
                        <Table.Cell className="pr-0">
                          <Radio
                            value={profile.metadata.name}
                            aria-label={rowLabel}
                          />
                        </Table.Cell>
                        <Table.Cell>{accelerator}</Table.Cell>
                        <Table.Cell>{precision}</Table.Cell>
                        <Table.Cell className="capitalize">{metric}</Table.Cell>
                        <Table.Cell>
                          <span className="inline-flex items-center gap-2 capitalize">
                            {profileClass}
                            {!isOptimized ? <UnoptimizedProfileBadge /> : null}
                          </span>
                        </Table.Cell>
                      </Table.Row>
                    );
                  })}
                </Table.Body>
              </Table.Content>
            </Table.ScrollContainer>
          </Table.Root>
        </FormRadioGroup>
      </div>
    </div>
  );
}
