// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'next-i18next';
import { useFormState, type UseFormReturn } from 'react-hook-form';

import { Alert, Select, SelectItem } from '@amdenterpriseai/components';
import { IconPlus } from '@tabler/icons-react';

import { CustomProfileDrawer } from '@/components/features/models/CustomProfiles/CustomProfileDrawer';
import { ModelProfileSummary } from '@/components/shared/ModelProfileSummary';
import { getMetricTranslationKey } from '@/lib/app/aims';
import {
  isProfileDeployable,
  listCustomProfiles,
  profileSummaryFields,
  type CustomProfileResponse,
} from '@/lib/app/custom-profiles';

const NO_PROFILES_KEY = '__no_profiles__';

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const KeyValueRows = ({
  label,
  values,
  testId,
}: {
  label: string;
  values: Record<string, unknown> | null;
  testId: string;
}) => {
  const entries = Object.entries(values ?? {});
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-1" data-testid={testId}>
      <span className="text-xs text-muted">{label}</span>
      <div className="flex flex-col gap-0.5">
        {entries.map(([key, value]) => (
          <span key={key} className="text-xs font-mono wrap-break-words">
            {key}: {typeof value === 'string' ? value : JSON.stringify(value)}
          </span>
        ))}
      </div>
    </div>
  );
};

KeyValueRows.displayName = 'KeyValueRows';

interface Props {
  // Shared like AutoscalingFormFields: the drawer owns the form.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  form: UseFormReturn<any>;
  project: string;
  /** AIMModel resource name. */
  modelId: string;
  /** Display name, for the create drawer's heading. */
  modelName: string;
  /**
   * Profile to open on, for a deploy started from one. Defaults to the Default.
   * The profile itself rather than its name, because a deploy started from a
   * profile saved a moment ago can meet a list that does not carry it yet.
   */
  initialProfile?: CustomProfileResponse;
  isDisabled?: boolean;
}

export const DeployProfileFields = ({
  form,
  project,
  modelId,
  modelName,
  initialProfile,
  isDisabled,
}: Props) => {
  const { t } = useTranslation('models', {
    keyPrefix: 'deployCustomAIMDrawer.fields.profile',
  });
  const { t: tModels } = useTranslation('models');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isSelectOpen, setIsSelectOpen] = useState(false);
  // form.formState only tracks the component that called useForm.
  const { errors } = useFormState({ control: form.control });
  const error = errors.profileName?.message as string | undefined;

  // Same key the profiles screen reads, so either surface refreshes both.
  const {
    data: listed,
    isLoading,
    isError,
  } = useQuery<CustomProfileResponse[]>({
    queryKey: ['project', project, 'custom-model', modelId, 'profiles'],
    queryFn: () => listCustomProfiles(project, modelId),
    enabled: Boolean(project) && Boolean(modelId),
    // A profile added from here reconciles in the background, and one the deploy
    // was started from may take a refresh or two to be listed at all.
    refetchInterval: (query) => {
      const entries = query.state.data ?? [];
      const isListed =
        !initialProfile ||
        entries.some((entry) => entry.name === initialProfile.name);
      return isListed && entries.every(isProfileDeployable) ? false : 10_000;
    },
  });

  // The profile the deploy was started from stands in for its own listing until
  // a refresh carries it, so the choice never rests on when the list catches up.
  const profiles = useMemo(() => {
    if (!listed || !initialProfile) {
      return listed;
    }
    return listed.some((entry) => entry.name === initialProfile.name)
      ? listed
      : [...listed, initialProfile];
  }, [listed, initialProfile]);

  const selectedName = form.watch('profileName') as string | undefined;
  const selected = useMemo(
    () => profiles?.find((entry) => entry.name === selectedName),
    [profiles, selectedName],
  );
  const deployable = useMemo(
    () => (profiles ?? []).filter(isProfileDeployable),
    [profiles],
  );

  const selectProfile = useCallback(
    (name: string, ready: boolean, byUser = true) => {
      form.setValue('profileName', name, {
        shouldDirty: byUser,
        shouldValidate: byUser,
      });
      form.setValue('profileReady', ready, { shouldValidate: byUser });
    },
    [form],
  );

  // Whatever the deploy was started from, else the Default, ready or not,
  // because that is what an unqualified deploy serves: a reconciling one blocks
  // the submit rather than moving the deploy onto a sibling. Only a model
  // without a Default falls back. Runs again on each refresh, since the list may
  // carry nothing when the drawer opens.
  useEffect(() => {
    if (!profiles || selectedName) {
      return;
    }
    const requested = initialProfile
      ? profiles.find((entry) => entry.name === initialProfile.name)
      : undefined;
    const preferred =
      requested ?? profiles.find((entry) => entry.isDefault) ?? deployable[0];
    if (preferred) {
      selectProfile(preferred.name, isProfileDeployable(preferred), false);
    }
  }, [profiles, selectedName, deployable, selectProfile, initialProfile]);

  // Readiness follows the list. A selection it once carried and no longer does
  // was deleted elsewhere; one never carried is a create still landing.
  // Revalidated only while an error is up, so none appears before a submit.
  const listedNames = useRef(new Set<string>());
  useEffect(() => {
    if (!profiles || !selectedName) {
      return;
    }
    const current = profiles.find((entry) => entry.name === selectedName);
    if (!current) {
      if (listedNames.current.has(selectedName)) {
        form.setValue('profileName', '');
        form.setValue('profileReady', false);
      }
      return;
    }
    listedNames.current.add(selectedName);
    form.setValue('profileReady', isProfileDeployable(current));
    if (error) {
      void form.trigger('profileName');
    }
  }, [profiles, selectedName, form, error]);

  const handleCreated = useCallback(
    (created: CustomProfileResponse) => {
      // Adopted even though it has not reconciled: the form then says so,
      // rather than quietly keeping the previous selection.
      selectProfile(created.name, isProfileDeployable(created));
      setIsCreateOpen(false);
    },
    [selectProfile],
  );

  const hasProfiles = (profiles?.length ?? 0) > 0;
  const unavailableKeys = useMemo(
    () =>
      (profiles ?? [])
        .filter((entry) => !isProfileDeployable(entry))
        .map((entry) => entry.name),
    [profiles],
  );

  const summaryRow = (label: string, value: string | null | undefined) =>
    value ? (
      <div className="flex justify-between gap-4">
        <span className="text-xs text-muted">{label}</span>
        <span className="text-xs">{value}</span>
      </div>
    ) : null;

  const spec = selected?.profile?.spec;
  const metric = spec?.metric
    ? String(tModels(getMetricTranslationKey(String(spec.metric))))
    : null;

  return (
    <div className="flex flex-col gap-3" data-testid="runtime-profile-slot">
      <Select
        label={t('label')}
        placeholder={isLoading ? t('loading') : t('placeholder')}
        selectedKeys={selectedName ? [selectedName] : []}
        onSelectionChange={(keys) => {
          const name = String(Array.from(keys)[0] ?? '');
          if (!name || name === NO_PROFILES_KEY) {
            return;
          }
          const picked = profiles?.find((entry) => entry.name === name);
          selectProfile(name, picked ? isProfileDeployable(picked) : false);
        }}
        isOpen={isSelectOpen}
        onOpenChange={setIsSelectOpen}
        isRequired
        isInvalid={Boolean(error)}
        errorMessage={error}
        isDisabled={isDisabled || isLoading}
        disabledKeys={
          hasProfiles ? unavailableKeys : [NO_PROFILES_KEY, ...unavailableKeys]
        }
        description={t('description')}
        data-testid="deploy-profile-select"
        bottomContent={
          <button
            type="button"
            className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-accent hover:bg-default-100 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="deploy-profile-add-new"
            disabled={isDisabled}
            onClick={() => {
              setIsSelectOpen(false);
              setIsCreateOpen(true);
            }}
          >
            <IconPlus size={16} aria-hidden />
            {t('addNew')}
          </button>
        }
      >
        {hasProfiles
          ? (profiles ?? []).map((profile) => (
              <SelectItem
                key={profile.name}
                textValue={profile.displayName}
                data-testid={`deploy-profile-option-${profile.name}`}
              >
                <div className="flex flex-col gap-0.5">
                  <span className="text-sm">
                    {profile.displayName}
                    {!isProfileDeployable(profile) && (
                      <span className="ml-2 text-xs text-muted">
                        {t('unavailable')}
                      </span>
                    )}
                  </span>
                  <ModelProfileSummary
                    profile={profileSummaryFields(profile)}
                    t={tModels}
                  />
                </div>
              </SelectItem>
            ))
          : [
              <SelectItem key={NO_PROFILES_KEY} textValue={t('empty')}>
                {t('empty')}
              </SelectItem>,
            ]}
      </Select>

      {isError && (
        <Alert
          status="danger"
          title={t('loadError')}
          data-testid="deploy-profile-load-error"
        />
      )}

      {selected && (
        <div
          className="flex flex-col gap-2 rounded-md border border-border p-3"
          data-testid="deploy-profile-details"
        >
          <span className="text-sm font-medium">{t('details.title')}</span>
          {summaryRow(t('details.metric'), metric)}
          {summaryRow(t('details.precision'), spec?.precision ?? null)}
          {summaryRow(t('details.accelerator'), spec?.acceleratorModel ?? null)}
          {summaryRow(
            t('details.acceleratorCount'),
            spec?.acceleratorCount != null
              ? String(spec.acceleratorCount)
              : null,
          )}
          <KeyValueRows
            label={t('details.engineArgs')}
            values={asRecord(spec?.engineArgs)}
            testId="deploy-profile-engine-args"
          />
          <KeyValueRows
            label={t('details.engineEnv')}
            values={asRecord(spec?.engineEnv)}
            testId="deploy-profile-engine-env"
          />
        </div>
      )}

      {isCreateOpen && (
        <CustomProfileDrawer
          isOpen
          onClose={() => setIsCreateOpen(false)}
          onCreated={handleCreated}
          project={project}
          modelId={modelId}
          modelName={modelName}
        />
      )}
    </div>
  );
};

DeployProfileFields.displayName = 'DeployProfileFields';
