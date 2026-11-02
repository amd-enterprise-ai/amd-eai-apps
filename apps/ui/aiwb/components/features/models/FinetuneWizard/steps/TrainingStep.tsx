// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionsToolbar,
  ClientSideDataTable,
  DateDisplay,
  FormRadioGroup,
  NoDataDisplay,
  Radio,
  type Selection,
  Wizard,
} from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';
import {
  FilterComponentType,
  type FilterValueMap,
  SortDirection,
  type TableColumns,
} from '@amdenterpriseai/types';
import { displayHumanReadableBytes } from '@amdenterpriseai/utils/app';
import { useTranslation } from 'next-i18next';
import { useMemo, useState } from 'react';
import { Controller, type UseFormReturn } from 'react-hook-form';
import { z } from 'zod';

import { TruncatedTagsRow } from '@/components/shared/TruncatedTagsRow';
import { translationKeyGenerator } from '@/lib/app/i18n';
import type { components } from '@/types/api';
import type { FinetunableModel, Model } from '@/types/models';
import type { modelsKeys } from '@/types/react-i18next';

import {
  FINE_TUNING_TYPES,
  getEnabledFineTuningTypes,
  getModelTrainingType,
  MAX_FINETUNE_DATASETS,
  type FineTuningType,
  type FinetuneFormValues,
} from '../types';
import { useAdapterServingSupport } from '../useAdapterServingSupport';

type Dataset = components['schemas']['DatasetResponse'];

const FINE_TUNING_TYPE_LABEL_KEYS = {
  merged: 'finetuneWizard.fields.fineTuningType.merged.label',
  full: 'finetuneWizard.fields.fineTuningType.full.label',
  lora: 'finetuneWizard.fields.fineTuningType.lora.label',
} as const satisfies Record<FineTuningType, modelsKeys>;

const FINE_TUNING_TYPE_DESCRIPTION_KEYS = {
  merged: 'finetuneWizard.fields.fineTuningType.merged.description',
  full: 'finetuneWizard.fields.fineTuningType.full.description',
  lora: 'finetuneWizard.fields.fineTuningType.lora.description',
} as const satisfies Record<FineTuningType, modelsKeys>;

const getFineTuningTypeLabelTranslationKey = translationKeyGenerator(
  FINE_TUNING_TYPE_LABEL_KEYS,
  'full',
);
const getFineTuningTypeDescriptionTranslationKey = translationKeyGenerator(
  FINE_TUNING_TYPE_DESCRIPTION_KEYS,
  'full',
);

const DatasetTableField = {
  NAME: 'name',
  SIZE: 'sizeBytes',
  CREATED_BY: 'createdBy',
  CREATED_AT: 'createdAt',
} as const;

type DatasetTableField =
  (typeof DatasetTableField)[keyof typeof DatasetTableField];

const columns: TableColumns<DatasetTableField> = [
  { key: DatasetTableField.NAME, sortable: true },
  { key: DatasetTableField.SIZE, sortable: true },
  { key: DatasetTableField.CREATED_BY, sortable: true },
  { key: DatasetTableField.CREATED_AT, sortable: true },
];

export const createTrainingStepSchema = (
  requiredDatasetMessage: string,
  maxDatasetsMessage: string,
) =>
  z.object({
    datasetIds: z
      .array(z.string())
      .min(1, requiredDatasetMessage)
      .max(MAX_FINETUNE_DATASETS, maxDatasetsMessage),
  });

export const TrainingStepFields = ({
  form,
  datasets,
  model,
  finetunableModels,
}: {
  form: UseFormReturn<FinetuneFormValues>;
  datasets: Dataset[];
  model?: Model;
  finetunableModels: FinetunableModel[];
}) => {
  const { t } = useTranslation('models', {
    keyPrefix: 'finetuneWizard.datasetSelector',
  });
  const { t: tModels } = useTranslation('models');
  const { toast } = useSystemToast();
  const [searchQuery, setSearchQuery] = useState('');
  const canonicalName = form.watch('canonicalName');
  const trainingType = getModelTrainingType(
    finetunableModels,
    canonicalName,
    model,
  );
  const canServeAdapters = useAdapterServingSupport(
    canonicalName,
    model,
    trainingType,
  );
  const enabledTypes = getEnabledFineTuningTypes(
    trainingType,
    canServeAdapters,
  );
  // Only this reason is worth spelling out: the other disabled combinations
  // follow from the recipe the user already chose, whereas an unservable
  // adapter is a property of the cluster they cannot infer from the form.
  const adaptersUnservable = canServeAdapters === false;
  const filteredDatasets = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query) return datasets;
    return datasets.filter((dataset) =>
      [dataset.name, dataset.description].some((value) =>
        value.toLocaleLowerCase().includes(query),
      ),
    );
  }, [datasets, searchQuery]);
  const filterConfig = useMemo(
    () => ({
      search: {
        name: 'search',
        label: t('filters.search.placeholder'),
        placeholder: t('filters.search.placeholder'),
        type: FilterComponentType.TEXT,
        variant: 'secondary' as const,
      },
    }),
    [t],
  );
  const customRenderers = {
    [DatasetTableField.NAME]: (dataset: Dataset) => (
      <div className="flex flex-col gap-1">
        <span>{dataset.name}</span>
        {dataset.description ? (
          <span className="text-xs text-muted">{dataset.description}</span>
        ) : null}
      </div>
    ),
    [DatasetTableField.SIZE]: (dataset: Dataset) =>
      dataset.sizeBytes == null ? (
        <NoDataDisplay />
      ) : (
        displayHumanReadableBytes(dataset.sizeBytes)
      ),
    [DatasetTableField.CREATED_BY]: (dataset: Dataset) =>
      dataset.createdBy || <NoDataDisplay />,
    [DatasetTableField.CREATED_AT]: (dataset: Dataset) =>
      dataset.createdAt ? (
        <DateDisplay date={dataset.createdAt} />
      ) : (
        <NoDataDisplay />
      ),
  };

  return (
    <>
      <FormRadioGroup
        form={form}
        name="fineTuningType"
        label={tModels('finetuneWizard.fields.fineTuningType.label')}
        data-testid="fine-tuning-type-selector"
      >
        <div className="grid grid-cols-3 gap-4">
          {FINE_TUNING_TYPES.map((type) => (
            <Radio
              key={type}
              value={type}
              isDisabled={!enabledTypes.includes(type)}
              description={
                type === 'lora' && adaptersUnservable
                  ? tModels(
                      'finetuneWizard.fields.fineTuningType.lora.unavailableDescription',
                    )
                  : tModels(getFineTuningTypeDescriptionTranslationKey(type))
              }
            >
              {tModels(getFineTuningTypeLabelTranslationKey(type))}
            </Radio>
          ))}
        </div>
      </FormRadioGroup>
      <Controller
        control={form.control}
        name="datasetIds"
        render={({ field }) => (
          <div className="flex flex-col" data-testid="dataset-selector">
            <ActionsToolbar
              canClear={false}
              filterConfig={filterConfig}
              onFilterChange={(filters: FilterValueMap) =>
                setSearchQuery(filters.search?.[0] ?? '')
              }
            />
            <ClientSideDataTable
              data={filteredDatasets}
              columns={columns}
              customRenderers={customRenderers}
              defaultSortByField={DatasetTableField.CREATED_AT}
              defaultSortDirection={SortDirection.DESC}
              idKey="id"
              isSelectable
              selectedKeys={new Set(field.value)}
              onSelectionChange={(selection: Selection) => {
                const datasetIds =
                  selection === 'all'
                    ? Array.from(
                        new Set([
                          ...field.value,
                          ...filteredDatasets.map((dataset) => dataset.id),
                        ]),
                      )
                    : Array.from(selection, String);
                if (datasetIds.length > MAX_FINETUNE_DATASETS) {
                  toast.error(
                    tModels('finetuneWizard.validation.datasetsMaxReached', {
                      max: MAX_FINETUNE_DATASETS,
                    }),
                  );
                  return;
                }
                field.onChange(datasetIds);
              }}
              translation={t}
            />
          </div>
        )}
      />
    </>
  );
};

export const TrainingStepSummary = ({
  data,
  datasets,
}: {
  data: FinetuneFormValues;
  datasets: Dataset[];
}) => {
  const { t } = useTranslation('models');
  const selectedDatasetNames = data.datasetIds.map(
    (id) => datasets.find((dataset) => dataset.id === id)?.name ?? id,
  );

  return (
    <>
      <Wizard.SummaryRow
        label={t('finetuneWizard.summary.fineTuningType')}
        value={t(getFineTuningTypeLabelTranslationKey(data.fineTuningType))}
      />
      <Wizard.SummaryRow
        label={t('finetuneWizard.summary.datasets')}
        value={
          <TruncatedTagsRow
            tags={selectedDatasetNames}
            formatMoreCount={(count) =>
              t('finetuneWizard.summary.datasetsMoreCount', { count })
            }
          />
        }
      />
    </>
  );
};
