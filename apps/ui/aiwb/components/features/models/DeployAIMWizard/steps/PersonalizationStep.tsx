// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  FormSelect,
  FormSwitch,
  SelectItem,
  Wizard,
} from '@amdenterpriseai/components';
import { useEffect, useMemo } from 'react';
import { Controller, type UseFormReturn } from 'react-hook-form';
import { z } from 'zod';
import { useTranslation } from 'next-i18next';

import { LoraAdapterSelectionTable } from '@/components/features/loras/LoraAdapterSelectionTable';
import { TruncatedTagsRow } from '@/components/shared/TruncatedTagsRow';
import type { LoraAdapter } from '@/types/artifacts';

import type { DeployAIMFormValues } from '../types';
import { IconSquareRotatedAsterisk } from '@tabler/icons-react';

export const MAX_LORA_RANK_OPTIONS = [
  1, 8, 16, 32, 64, 128, 256, 320, 512,
] as const;
export const DEFAULT_MAX_LORA_RANK = 32;
const MAX_SUPPORTED_ADAPTER_RANK =
  MAX_LORA_RANK_OPTIONS[MAX_LORA_RANK_OPTIONS.length - 1];

export const personalizationStepSchema = z.object({
  personalizationEnabled: z.boolean().default(false),
  adapters: z.array(z.string()).default([]),
  maxLoraRank: z.string().default(String(DEFAULT_MAX_LORA_RANK)),
});

export const personalizationStepDefaults: Partial<DeployAIMFormValues> = {
  personalizationEnabled: false,
  adapters: [],
  maxLoraRank: String(DEFAULT_MAX_LORA_RANK),
};

function snapToMaxLoraRank(rank: number): number | null {
  if (rank > MAX_SUPPORTED_ADAPTER_RANK) return null;
  return (
    MAX_LORA_RANK_OPTIONS.find((option) => option >= rank) ??
    MAX_SUPPORTED_ADAPTER_RANK
  );
}

function minimumRequiredMaxLoraRank(
  selectedNames: string[],
  adapters: LoraAdapter[],
): number {
  const selectedNamesSet = new Set(selectedNames);
  const ranks = adapters.flatMap((adapter) =>
    selectedNamesSet.has(adapter.name) &&
    adapter.servable !== false &&
    adapter.readiness === 'Ready' &&
    adapter.rank != null
      ? [adapter.rank]
      : [],
  );

  // With nothing selected no adapter constrains the ceiling, so the floor is
  // the lowest offered tier and every option stays selectable.
  // DEFAULT_MAX_LORA_RANK is only the form's initial value, never a floor.
  return ranks.length
    ? (snapToMaxLoraRank(Math.max(...ranks)) ?? DEFAULT_MAX_LORA_RANK)
    : MAX_LORA_RANK_OPTIONS[0];
}

function raiseMaxLoraRankIfNeeded(
  form: UseFormReturn<DeployAIMFormValues>,
  selectedNames: string[],
  adapters: LoraAdapter[],
) {
  const required = minimumRequiredMaxLoraRank(selectedNames, adapters);
  const current = Number(
    form.getValues('maxLoraRank') ?? DEFAULT_MAX_LORA_RANK,
  );
  if (required > current) {
    form.setValue('maxLoraRank', String(required));
  }
}

type PersonalizationStepFieldsProps = {
  form: UseFormReturn<DeployAIMFormValues>;
  adapters: LoraAdapter[];
  isLoading: boolean;
};

export const PersonalizationStepFields = ({
  form,
  adapters,
  isLoading,
}: PersonalizationStepFieldsProps) => {
  const { t } = useTranslation('models');
  const personalizationEnabled = form.watch('personalizationEnabled');
  const selectedAdapterNames = form.watch('adapters') ?? [];
  // Rank-valid adapters, plus retained rows marked servable: false so a
  // selection the profiles can no longer load stays visible and clearable.
  const offeredAdapters = useMemo(
    () =>
      adapters.filter(
        (adapter) =>
          adapter.servable === false ||
          (adapter.rank != null &&
            adapter.rank >= 1 &&
            adapter.rank <= MAX_SUPPORTED_ADAPTER_RANK),
      ),
    [adapters],
  );
  const unservableAdapterNames = offeredAdapters.flatMap((adapter) =>
    adapter.servable === false ? [adapter.name] : [],
  );
  const notReadyAdapterNames = offeredAdapters.flatMap((adapter) =>
    adapter.servable !== false && adapter.readiness !== 'Ready'
      ? [adapter.name]
      : [],
  );
  const minimumMaxLoraRank = minimumRequiredMaxLoraRank(
    selectedAdapterNames,
    offeredAdapters,
  );
  useEffect(() => {
    if (isLoading) return;
    const selectedAdapters = form.getValues('adapters') ?? [];
    const offeredNames = new Set(
      offeredAdapters.map((adapter) => adapter.name),
    );
    const compatibleSelection = selectedAdapters.filter((name) =>
      offeredNames.has(name),
    );
    if (compatibleSelection.length !== selectedAdapters.length) {
      form.setValue('adapters', compatibleSelection);
    }
    raiseMaxLoraRankIfNeeded(form, compatibleSelection, offeredAdapters);
  }, [form, isLoading, offeredAdapters]);
  return (
    <div className="flex flex-col gap-4">
      <FormSwitch
        form={form}
        name="personalizationEnabled"
        data-testid="personalization-toggle"
      >
        {t('deployAIM.personalization.enable')}
      </FormSwitch>
      {personalizationEnabled ? (
        <>
          {unservableAdapterNames.length > 0 ? (
            <p
              className="text-sm text-warning"
              data-testid="unservable-adapters-warning"
            >
              {t('deployAIM.personalization.unservableAdapters', {
                names: unservableAdapterNames.join(', '),
              })}
            </p>
          ) : null}
          {notReadyAdapterNames.length > 0 ? (
            <p
              className="text-sm text-warning"
              data-testid="not-ready-adapters-warning"
            >
              {t('deployAIM.personalization.notReadyAdapters', {
                names: notReadyAdapterNames.join(', '),
              })}
            </p>
          ) : null}
          <div className="flex flex-row gap-6 items-end">
            <div className="w-32">
              <FormSelect
                form={form}
                name="maxLoraRank"
                data-testid="deploy-personalization-max-rank"
                label={t('deployAIM.personalization.maxRank.label')}
                aria-label={t('deployAIM.personalization.maxRank.label')}
                disallowEmptySelection
                startContent={
                  <IconSquareRotatedAsterisk size={16} className="text-muted" />
                }
              >
                {MAX_LORA_RANK_OPTIONS.map((rank) => (
                  <SelectItem key={rank} isDisabled={rank < minimumMaxLoraRank}>
                    {rank}
                  </SelectItem>
                ))}
              </FormSelect>
            </div>
            <div className="h-9 max-w-64 flex items-center">
              <p className="text-xs leading-tight text-muted">
                {t('deployAIM.personalization.maxRank.hint')}
              </p>
            </div>
          </div>
          <Controller
            control={form.control}
            name="adapters"
            render={({ field }) => (
              <LoraAdapterSelectionTable
                adapters={offeredAdapters}
                isLoading={isLoading}
                selectedNames={field.value ?? []}
                onSelectionChange={(adapterNames) => {
                  field.onChange(adapterNames);
                  raiseMaxLoraRankIfNeeded(form, adapterNames, offeredAdapters);
                }}
              />
            )}
          />
        </>
      ) : null}
    </div>
  );
};

type PersonalizationStepSummaryProps = {
  data: DeployAIMFormValues;
  adapters: LoraAdapter[];
};

export const PersonalizationStepSummary = ({
  data,
  adapters,
}: PersonalizationStepSummaryProps) => {
  const { t } = useTranslation('models');
  const selectedAdapterNames = (data.adapters ?? []).map(
    (name) =>
      adapters.find((adapter) => adapter.name === name)?.displayName ?? name,
  );

  return (
    <>
      <Wizard.SummaryRow
        label={t('deployAIM.personalization.summary.label')}
        value={
          data.personalizationEnabled
            ? t('deployAIM.personalization.summary.enabled', {
                rank: data.maxLoraRank ?? DEFAULT_MAX_LORA_RANK,
              })
            : t('deployAIM.summary.disabled')
        }
      />
      {data.personalizationEnabled ? (
        <Wizard.SummaryRow
          label={t('deployAIM.personalization.summary.adapters')}
          value={
            selectedAdapterNames.length > 0 ? (
              <TruncatedTagsRow
                tags={selectedAdapterNames}
                formatMoreCount={(count) =>
                  t('aimCatalog.card.tagsMoreCount', { count })
                }
              />
            ) : (
              t('deployAIM.personalization.summary.noneSelected')
            )
          }
        />
      ) : null}
    </>
  );
};
