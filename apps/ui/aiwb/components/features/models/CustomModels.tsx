// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconCloudUpload } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { useRouter } from 'next/router';
import { useTranslation } from 'next-i18next';

import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';
import { ActionButton, ActionsToolbar } from '@amdenterpriseai/components';
import { PageLoader } from '@/components/shared/PageLoader';
import { FilterComponentType, FilterValueMap } from '@amdenterpriseai/types';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { useProject } from '@/contexts/ProjectContext';
import {
  CustomModelDeleteConflictError,
  customModelDeployTarget,
  deleteCustomModel,
  listCustomModels,
} from '@/lib/app/custom-models';
import { AggregatedAIM, OnboardPhase, ParsedAIM } from '@/types/aims';
import { Model } from '@/types/models';

import { CustomModelCard } from './CustomModelCard';
import DeleteModelModal from './DeleteModelModal';
import { DeployCustomAIMDrawer } from './DeployCustomAIMDrawer';

const CUSTOM_MODELS_REFETCH_INTERVAL = 30000;

/**
 * Maps the status filter dropdown selection to predicates against the
 * derived {@link OnboardPhase}, which is what the card's status pill displays.
 * Filtering on `onboardPhase` keeps the filter and card in sync — a model
 * shown as "Importing" on its card will appear under the "Onboarding" bucket.
 */
const STATUS_FILTER_PREDICATES: Record<
  string,
  (phase: OnboardPhase | undefined) => boolean
> = {
  onboarding: (phase) =>
    phase !== OnboardPhase.READY && phase !== OnboardPhase.FAILED,
  ready: (phase) => phase === OnboardPhase.READY,
  failed: (phase) => phase === OnboardPhase.FAILED,
};

/**
 * Search and status filtering is applied to the aggregated families rather
 * than to the underlying {@link ParsedAIM} list, so {@link AggregatedAIM.isSupported}
 * (which drives the Deploy button) keeps reflecting the full family — picking
 * "Onboarding" must not turn a deployable family into a non-deployable one
 * because some other version was filtered out.
 */
const matchesSearch = (aggregatedAim: AggregatedAIM, query: string) => {
  const needle = query.toLowerCase();
  const tagsHaystack = (aggregatedAim.aggregated.tags ?? [])
    .join(' ')
    .toLowerCase();
  if (tagsHaystack.includes(needle)) {
    return true;
  }
  if (
    aggregatedAim.repository.toLowerCase().includes(needle) ||
    aggregatedAim.aggregated.title.toLowerCase().includes(needle) ||
    aggregatedAim.aggregated.canonicalName.toLowerCase().includes(needle) ||
    aggregatedAim.aggregated.description.short.toLowerCase().includes(needle)
  ) {
    return true;
  }
  return aggregatedAim.parsedAIMs.some((aim) => {
    const haystack = [
      aim.title,
      aim.canonicalName,
      aim.model,
      aim.imageVersion,
      aim.imageReference,
      aim.sourceUri ?? '',
      (aim.tags ?? []).join(' '),
    ]
      .join(' ')
      .toLowerCase();
    return haystack.includes(needle);
  });
};

function aggregatedToDeleteModalModel(aggregatedAim: AggregatedAIM): Model {
  return {
    name: aggregatedAim.aggregated.title,
    resourceName: aggregatedAim.repository,
    canonicalName: aggregatedAim.aggregated.canonicalName,
  };
}

const matchesStatusSelection = (
  aggregatedAim: AggregatedAIM,
  selection: string[],
) => {
  if (selection.length === 0) return true;
  const predicates = selection
    .map((key) => STATUS_FILTER_PREDICATES[key])
    .filter((p): p is (phase: OnboardPhase | undefined) => boolean =>
      Boolean(p),
    );
  if (predicates.length === 0) return true;
  return predicates.some((predicate) =>
    predicate(aggregatedAim.aggregated.onboardPhase),
  );
};

const CustomModels = () => {
  const { t } = useTranslation('models');
  const { toast } = useSystemToast();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { activeProject, projectPath } = useProject();

  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusSelection, setStatusSelection] = useState<string[]>([]);

  const [aimForDeployment, setAimForDeployment] = useState<
    AggregatedAIM | undefined
  >(undefined);
  const deployDisclosure = useOverlayState();

  const [aggregatedForDeletion, setAggregatedForDeletion] = useState<
    AggregatedAIM | undefined
  >(undefined);
  const deleteDisclosure = useOverlayState();

  const {
    data: allAggregatedAims,
    isLoading,
    refetch,
    error,
    dataUpdatedAt,
    isFetching,
  } = useQuery<AggregatedAIM[]>({
    queryKey: ['project', activeProject, 'custom-models'],
    queryFn: () => listCustomModels(activeProject!),
    refetchInterval: CUSTOM_MODELS_REFETCH_INTERVAL,
    enabled: !!activeProject,
  });

  useEffect(() => {
    if (error) {
      toast.error(
        t('notifications.refresh.error', {
          error: String(error.message),
        }),
      );
    }
  }, [error, toast, t]);

  const aggregatedAims = useMemo(() => {
    const trimmed = searchQuery.trim();
    return (allAggregatedAims ?? []).filter((aggregatedAim) => {
      if (trimmed.length > 0 && !matchesSearch(aggregatedAim, trimmed)) {
        return false;
      }
      return matchesStatusSelection(aggregatedAim, statusSelection);
    });
  }, [allAggregatedAims, searchQuery, statusSelection]);

  const filterConfig = useMemo(
    () => ({
      search: {
        className: 'w-full',
        name: 'search',
        label: t('customModels.list.filters.search.placeholder'),
        placeholder: t('customModels.list.filters.search.placeholder'),
        type: FilterComponentType.TEXT,
      },
      status: {
        name: 'status',
        label: t('customModels.list.filters.status.label'),
        placeholder: t('customModels.list.filters.status.placeholder'),
        type: FilterComponentType.DROPDOWN,
        fields: [
          {
            key: 'onboarding',
            label: t('customModels.card.status.onboarding'),
          },
          { key: 'ready', label: t('customModels.card.status.ready') },
          { key: 'failed', label: t('customModels.card.status.failed') },
        ],
      },
    }),
    [t],
  );

  const handleFilterChange = useCallback((next: FilterValueMap) => {
    // FilterValueMap models every field as string[]; the TEXT search field is
    // delivered as a single-element array (or empty when cleared).
    const search = next?.search;
    setSearchQuery(Array.isArray(search) ? (search[0] ?? '') : '');
    setStatusSelection(next?.status ?? []);
  }, []);

  const handleImportClick = useCallback(() => {
    router.push(projectPath('/models/custom-models/onboard'));
  }, [router, projectPath]);

  const handleEditModel = useCallback(
    (aggregatedAim: AggregatedAIM) => {
      router.push(
        projectPath(
          `/models/custom-models/${encodeURIComponent(aggregatedAim.repository)}/edit`,
        ),
      );
    },
    [router, projectPath],
  );

  const handleViewProfiles = useCallback(
    (aggregatedAim: AggregatedAIM) => {
      router.push(
        projectPath(
          `/models/custom-models/${encodeURIComponent(aggregatedAim.repository)}/profiles`,
        ),
      );
    },
    [router, projectPath],
  );

  const deleteCustomModelMutation = useMutation({
    mutationFn: async ({
      project,
      modelName,
    }: {
      project: string;
      modelName: string;
      displayName: string;
    }) => {
      if (!project) {
        throw new Error('No active project selected');
      }
      await deleteCustomModel(project, modelName);
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['project', variables.project, 'custom-models'],
      });
      toast.success(t('customModels.list.actions.delete.notification.success'));
      deleteDisclosure.onClose();
      setAggregatedForDeletion(undefined);
    },
    onError: (error: unknown, variables) => {
      const displayName = variables.displayName;
      if (error instanceof CustomModelDeleteConflictError) {
        const services = error.blockingServices.join(', ');
        toast.error(
          services.length > 0
            ? t(
                'customModels.list.actions.delete.notification.conflictWithServices',
                { displayName, services },
              )
            : t(
                'customModels.list.actions.delete.notification.conflictGeneric',
                { displayName },
              ),
        );
        deleteDisclosure.onClose();
        setAggregatedForDeletion(undefined);
        return;
      }
      if (error instanceof APIRequestError && error.statusCode === 404) {
        queryClient.invalidateQueries({
          queryKey: ['project', variables.project, 'custom-models'],
        });
        toast.error(
          t('customModels.list.actions.delete.notification.notFound'),
        );
        deleteDisclosure.onClose();
        setAggregatedForDeletion(undefined);
        return;
      }
      deleteDisclosure.onClose();
      setAggregatedForDeletion(undefined);
      const message =
        error instanceof APIRequestError ? error.message : undefined;
      toast.error(
        message ?? t('customModels.list.actions.delete.notification.error'),
      );
    },
  });

  const handleOpenDeleteModal = useCallback(
    (aggregatedAim: AggregatedAIM) => {
      setAggregatedForDeletion(aggregatedAim);
      deleteDisclosure.onOpen();
    },
    [deleteDisclosure],
  );

  const handleCloseDeleteModal = useCallback(() => {
    deleteDisclosure.onClose();
    setAggregatedForDeletion(undefined);
  }, [deleteDisclosure]);

  const handleConfirmDelete = useCallback(
    ({ name }: { name: string }) => {
      if (!aggregatedForDeletion || !activeProject) {
        return;
      }
      deleteCustomModelMutation.mutate({
        project: activeProject,
        modelName: name,
        displayName: aggregatedForDeletion.aggregated.title,
      });
    },
    [activeProject, aggregatedForDeletion, deleteCustomModelMutation],
  );

  // The remaining "..." menu callbacks are intentionally stubbed for now.
  // They will be wired to real flows in follow-up tickets; until
  // then, surface a "coming soon" toast instead of writing to the production
  // console so the menu is exercisable in QA without leaking implementation
  // noise to users.
  const stubAction = useCallback(
    (actionLabel: string) => () => {
      toast.info(
        t('customModels.card.actions.comingSoon', { action: actionLabel }),
      );
    },
    [toast, t],
  );

  const handleDeploy = useCallback(
    (aggregatedAim: AggregatedAIM) => {
      setAimForDeployment(aggregatedAim);
      deployDisclosure.onOpen();
    },
    [deployDisclosure],
  );

  const deployTarget = useMemo(
    () => (aimForDeployment ? customModelDeployTarget(aimForDeployment) : null),
    [aimForDeployment],
  );
  const deployAim = deployTarget?.aim ?? null;
  const deployModel = deployTarget?.model ?? null;

  if (isLoading) {
    return (
      <PageLoader
        label={t('customModels.list.loading')}
        testId="custom-models-loading"
        className="h-64"
      />
    );
  }

  // Distinguish the two empty cases so we don't tell the user "no custom
  // models yet" when models exist but are hidden by their current filters.
  const hasAnyCustomModels = (allAggregatedAims ?? []).length > 0;
  const isFiltered =
    searchQuery.trim().length > 0 || statusSelection.length > 0;
  const isEmpty = aggregatedAims.length === 0;
  const emptyCopyKey =
    hasAnyCustomModels && isFiltered
      ? ('customModels.list.empty.filtered' as const)
      : ('customModels.list.empty' as const);
  const emptyTestId =
    hasAnyCustomModels && isFiltered
      ? 'custom-models-empty-filtered'
      : 'custom-models-empty';

  return (
    <div data-testid="custom-models" className="flex flex-col w-full">
      <p className="text-lg mb-4">{t('customModels.list.description')}</p>

      <ActionsToolbar
        filterConfig={filterConfig}
        onFilterChange={handleFilterChange}
        onRefresh={refetch}
        updatedTimestamp={dataUpdatedAt}
        isRefreshing={isFetching}
        endContent={
          <ActionButton
            primary
            onPress={handleImportClick}
            icon={<IconCloudUpload size={16} stroke={2} />}
            data-testid="custom-models-import-model"
          >
            {t('customModels.list.actions.importModel.title')}
          </ActionButton>
        }
      />

      {isEmpty ? (
        <div
          data-testid={emptyTestId}
          className="flex flex-col items-center justify-center text-center gap-2 py-12"
        >
          <p className="text-lg font-semibold">{t(`${emptyCopyKey}.title`)}</p>
          <p className="text-sm text-foreground/60">
            {t(`${emptyCopyKey}.description`)}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-1 lg:grid-cols-2 xl:grid-cols-2 2xl:grid-cols-3 gap-6 mb-6">
          {aggregatedAims.map((aggregatedAim) => (
            <CustomModelCard
              key={aggregatedAim.repository}
              aggregatedAim={aggregatedAim}
              onDeploy={handleDeploy}
              onModelSettings={handleEditModel}
              onProfiles={handleViewProfiles}
              onDelete={handleOpenDeleteModal}
            />
          ))}
        </div>
      )}

      {aggregatedForDeletion && (
        <DeleteModelModal
          isOpen={deleteDisclosure.isOpen}
          onClose={handleCloseDeleteModal}
          onConfirmAction={handleConfirmDelete}
          model={aggregatedToDeleteModalModel(aggregatedForDeletion)}
          hasActiveDeployments={false}
          loading={deleteCustomModelMutation.isPending}
        />
      )}

      {deployModel && activeProject && (
        <DeployCustomAIMDrawer
          isOpen={deployDisclosure.isOpen}
          onClose={() => {
            deployDisclosure.onClose();
            setAimForDeployment(undefined);
          }}
          onDeployed={() => {
            queryClient.invalidateQueries({
              queryKey: ['project', activeProject, 'custom-models'],
            });
          }}
          model={deployModel}
          namespace={activeProject}
          sourceUri={deployAim?.sourceUri}
          supportsProfileSelection
        />
      )}
    </div>
  );
};

export default CustomModels;
