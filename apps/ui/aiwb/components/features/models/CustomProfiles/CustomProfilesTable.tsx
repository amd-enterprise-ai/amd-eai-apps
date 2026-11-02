// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconEdit, IconRocket, IconTrash } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import type { TFunction } from 'i18next';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';
import {
  ActionsToolbar,
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
} from '@amdenterpriseai/components';
import {
  FilterComponentType,
  SortDirection,
  type ActionItem,
  type CustomComparatorConfig,
  type FilterValueMap,
  type TableColumns,
} from '@amdenterpriseai/types';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { PageLoader } from '@/components/shared/PageLoader';
import { getMetricTranslationKey } from '@/lib/app/aims';
import {
  CustomProfileConflictError,
  deleteCustomProfile,
  isProfileDeployable,
  listCustomProfiles,
  type CustomProfileResponse,
} from '@/lib/app/custom-profiles';
import { formatTemplateGpuCount } from '@/lib/app/modelDeploymentDisplay';
import type { AIMProfileSpec } from '@/types/aims';

import { DeleteCustomProfileModal } from './DeleteCustomProfileModal';

const CustomProfilesTableField = {
  DISPLAY_NAME: 'displayName',
  ACCELERATOR: 'accelerator',
  METRIC: 'metric',
  PRECISION: 'precision',
  CREATED_BY: 'createdBy',
  CREATED_AT: 'createdAt',
} as const;

type CustomProfilesTableField =
  (typeof CustomProfilesTableField)[keyof typeof CustomProfilesTableField];

const columns: TableColumns<CustomProfilesTableField | null> = [
  { key: CustomProfilesTableField.DISPLAY_NAME, sortable: true },
  { key: CustomProfilesTableField.ACCELERATOR, sortable: true },
  { key: CustomProfilesTableField.METRIC, sortable: true },
  { key: CustomProfilesTableField.PRECISION, sortable: true },
  { key: CustomProfilesTableField.CREATED_BY, sortable: true },
  { key: CustomProfilesTableField.CREATED_AT, sortable: true },
];

/**
 * Flat row shape. The summary parameters live under `profile.spec` on the wire,
 * but `ClientSideDataTable` sorts with a comparator that only reads top-level
 * fields, so they are projected up here. Translated values are stored rather
 * than raw ones so sorting orders by what the user actually reads.
 */
type CustomProfileRow = {
  name: string;
  displayName: string;
  isDefault: boolean;
  accelerator: string;
  metric: string;
  precision: string;
  createdBy: string;
  createdAt: string;
  blockingDeployments: string[];
  isReady: boolean;
};

function formatAccelerator(spec: AIMProfileSpec | undefined): string {
  const model = spec?.acceleratorModel?.trim();
  const count = spec?.acceleratorCount;
  if (model && count != null) {
    return `${count}x ${model}`;
  }
  if (model) {
    return model;
  }
  if (count != null) {
    return formatTemplateGpuCount(count, spec?.acceleratorType);
  }
  return '';
}

function toRow(
  profile: CustomProfileResponse,
  tModels: TFunction<'models'>,
): CustomProfileRow {
  const spec = profile.profile?.spec;
  return {
    name: profile.name,
    displayName: profile.displayName,
    isDefault: profile.isDefault,
    accelerator: formatAccelerator(spec),
    metric: spec?.metric
      ? String(
          tModels(getMetricTranslationKey(spec.metric), {
            defaultValue: spec.metric,
          }),
        )
      : '',
    precision: spec?.precision ?? '',
    createdBy: profile.createdBy ?? '',
    createdAt: profile.createdAt ?? '',
    blockingDeployments: (profile.inUseBy ?? [])
      .map((ref) => ref.displayName)
      .filter((name): name is string => Boolean(name)),
    isReady: isProfileDeployable(profile),
  };
}

const createdAtRank = (row: CustomProfileRow): number => {
  const time = new Date(row.createdAt).getTime();
  // A profile the API reported without a creation timestamp belongs at the end of
  // its group rather than ahead of every dated row.
  return Number.isNaN(time) ? Number.MAX_SAFE_INTEGER : time;
};

const profileComparators: CustomComparatorConfig<
  CustomProfileRow,
  CustomProfilesTableField
> = {
  // The API orders Default ahead of named profiles, so the default view pins it
  // instead of inferring precedence from creation order. Toggling to descending
  // reverses this and moves Default last, which is what "newest first" means for
  // a set the Default always predates.
  [CustomProfilesTableField.CREATED_AT]: (a, b) =>
    a.isDefault === b.isDefault
      ? createdAtRank(a) - createdAtRank(b)
      : Number(b.isDefault) - Number(a.isDefault),
};

const textCell = (value: string) => (value ? value : <NoDataDisplay />);

interface Props {
  project: string;
  modelId: string;
  /**
   * Opens the edit drawer for a named profile. The screen owns the drawer
   * because the New profile button in its header opens the same surface.
   */
  onEditProfile: (profileName: string) => void;
  /**
   * Opens the deploy drawer on a profile, for the same reason. Carries the
   * profile rather than its name so the drawer can show it before its own copy
   * of the list has been fetched.
   */
  onDeployProfile: (profile: CustomProfileResponse) => void;
  /**
   * Whether the model itself can be deployed at all. A deploy needs both the
   * model and the profile, so a ready profile on a model still importing its
   * weights offers nothing but a rejected request.
   */
  isModelDeployable: boolean;
}

export const CustomProfilesTable = ({
  project,
  modelId,
  onEditProfile,
  onDeployProfile,
  isModelDeployable,
}: Props) => {
  const { t } = useTranslation('models', {
    keyPrefix: 'customModels.profiles',
  });
  const { t: tModels } = useTranslation('models');
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useSystemToast();

  const [searchQuery, setSearchQuery] = useState('');
  const [profileForDeletion, setProfileForDeletion] = useState<
    CustomProfileRow | undefined
  >(undefined);
  const deleteDisclosure = useOverlayState();

  const profilesQueryKey = useMemo(
    () => ['project', project, 'custom-model', modelId, 'profiles'],
    [project, modelId],
  );

  const {
    data: profiles,
    isLoading,
    isFetching,
    refetch,
    dataUpdatedAt,
    error,
  } = useQuery<CustomProfileResponse[]>({
    queryKey: profilesQueryKey,
    queryFn: () => listCustomProfiles(project, modelId),
    enabled: Boolean(project) && Boolean(modelId),
  });

  useEffect(() => {
    if (error) {
      toast.error(
        t('notifications.loadError', { error: String(error.message) }),
      );
    }
  }, [error, toast, t]);

  const rows = useMemo(
    () => (profiles ?? []).map((profile) => toRow(profile, tModels)),
    [profiles, tModels],
  );
  const filteredRows = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query) return rows;
    return rows.filter((row) =>
      [
        row.displayName,
        row.accelerator,
        row.metric,
        row.precision,
        row.createdBy,
      ].some((value) => value.toLocaleLowerCase().includes(query)),
    );
  }, [rows, searchQuery]);
  const filterConfig = useMemo(
    () => ({
      search: {
        name: 'search',
        label: t('filters.search.placeholder'),
        placeholder: t('filters.search.placeholder'),
        type: FilterComponentType.TEXT,
      },
    }),
    [t],
  );
  const handleFilterChange = useCallback((filters: FilterValueMap) => {
    setSearchQuery(filters.search?.[0] ?? '');
  }, []);

  const closeDeleteModal = useCallback(() => {
    deleteDisclosure.onClose();
    setProfileForDeletion(undefined);
  }, [deleteDisclosure]);

  const deleteProfileMutation = useMutation({
    mutationFn: ({ profileName }: { profileName: string }) =>
      deleteCustomProfile(project, modelId, profileName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profilesQueryKey });
      // The card's profile count comes from the custom models list, so it has
      // to be refreshed too.
      queryClient.invalidateQueries({
        queryKey: ['project', project, 'custom-models'],
      });
      toast.success(t('actions.delete.notification.success'));
      closeDeleteModal();
    },
    onError: (mutationError: unknown) => {
      closeDeleteModal();
      if (mutationError instanceof CustomProfileConflictError) {
        const services = mutationError.blockingServices.join(', ');
        toast.error(
          services.length > 0
            ? t('actions.delete.notification.conflictWithServices', {
                services,
              })
            : t('actions.delete.notification.conflictGeneric'),
        );
        return;
      }
      if (
        mutationError instanceof APIRequestError &&
        mutationError.statusCode === 404
      ) {
        queryClient.invalidateQueries({ queryKey: profilesQueryKey });
        toast.error(t('actions.delete.notification.notFound'));
        return;
      }
      toast.error(
        mutationError instanceof APIRequestError
          ? mutationError.message
          : t('actions.delete.notification.error'),
      );
    },
  });

  const handleEdit = useCallback(
    (row: CustomProfileRow) => {
      // The Default profile is the model's onboarding configuration, so it is
      // edited through model settings rather than the profile drawer.
      if (row.isDefault) {
        router.push(
          `/${encodeURIComponent(project)}/models/custom-models/${encodeURIComponent(modelId)}/edit`,
        );
        return;
      }
      onEditProfile(row.name);
    },
    [router, project, modelId, onEditProfile],
  );

  const rowActions = useCallback(
    (row: CustomProfileRow): ActionItem<CustomProfileRow>[] => {
      // A profile a deployment references cannot be changed; named profiles
      // otherwise open the edit drawer, and Default routes to model settings.
      const isInUse = row.blockingDeployments.length > 0;
      const isEditBlocked = isInUse;
      return [
        {
          key: 'edit',
          label: t('actions.edit.label'),
          color: 'default',
          startContent: <IconEdit />,
          isDisabled: isEditBlocked,
          onPress: handleEdit,
        },
        {
          key: 'deploy',
          label: t('actions.deploy.label'),
          color: 'default',
          startContent: <IconRocket />,
          // Deploy refuses a profile that has not reconciled, and a model that
          // is not ready to serve whichever profile it is asked for.
          isDisabled: !row.isReady || !isModelDeployable,
          onPress: (item: CustomProfileRow) => {
            const profile = profiles?.find((entry) => entry.name === item.name);
            if (profile) {
              onDeployProfile(profile);
            }
          },
        },
        {
          key: 'delete',
          label: t('actions.delete.label'),
          color: 'danger',
          startContent: <IconTrash />,
          isDisabled: row.isDefault || isInUse,
          onPress: (item: CustomProfileRow) => {
            setProfileForDeletion(item);
            deleteDisclosure.onOpen();
          },
        },
      ];
    },
    [
      t,
      handleEdit,
      onDeployProfile,
      isModelDeployable,
      profiles,
      deleteDisclosure,
    ],
  );

  const customRenderers: Partial<
    Record<
      CustomProfilesTableField,
      (item: CustomProfileRow) => React.ReactNode | string
    >
  > = {
    [CustomProfilesTableField.DISPLAY_NAME]: (item) =>
      textCell(item.displayName),
    [CustomProfilesTableField.ACCELERATOR]: (item) =>
      textCell(item.accelerator),
    [CustomProfilesTableField.METRIC]: (item) => textCell(item.metric),
    [CustomProfilesTableField.PRECISION]: (item) => textCell(item.precision),
    [CustomProfilesTableField.CREATED_BY]: (item) => textCell(item.createdBy),
    [CustomProfilesTableField.CREATED_AT]: (item) =>
      item.createdAt ? (
        <DateDisplay date={item.createdAt} />
      ) : (
        <NoDataDisplay />
      ),
  };

  if (isLoading) {
    return (
      <PageLoader
        label={t('loading')}
        testId="custom-profiles-loading"
        className="h-64"
      />
    );
  }

  return (
    <div data-testid="custom-profiles">
      <ActionsToolbar
        filterConfig={filterConfig}
        onFilterChange={handleFilterChange}
        onRefresh={refetch}
        updatedTimestamp={dataUpdatedAt}
        isRefreshing={isFetching}
      />
      <ClientSideDataTable
        data={filteredRows}
        columns={columns}
        customRenderers={customRenderers}
        rowActions={rowActions}
        customComparator={profileComparators}
        defaultSortByField={CustomProfilesTableField.CREATED_AT}
        defaultSortDirection={SortDirection.ASC}
        translation={t}
        idKey="name"
      />
      <DeleteCustomProfileModal
        isOpen={deleteDisclosure.isOpen}
        onClose={closeDeleteModal}
        onConfirmAction={(profileName) =>
          deleteProfileMutation.mutate({ profileName })
        }
        profile={profileForDeletion}
        loading={deleteProfileMutation.isPending}
      />
    </div>
  );
};

CustomProfilesTable.displayName = 'CustomProfilesTable';
