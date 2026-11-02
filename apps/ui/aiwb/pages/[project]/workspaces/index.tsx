// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import { IconAppWindow } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { useCallback, useMemo, useState } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/router';

import { useTranslation } from 'next-i18next';

import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';
import { getPageTranslations } from '@/lib/server/i18n';

import { getFilteredData } from '@amdenterpriseai/utils/app';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { WorkspaceCatalogTableItem } from '@/types/workspaces';
import type { components } from '@/types/api';
import { FilterComponentType } from '@amdenterpriseai/types';
import { ClientSideDataFilter, FilterValueMap } from '@amdenterpriseai/types';

import { CatalogItemCard } from '@/components/features/catalog/CatalogItemCard';
import { DeployWorkspaceWizard } from '@/components/features/catalog/DeployWorkspaceWizard/DeployWorkspaceWizard';
import UndeployWorkspaceModal, {
  type WorkspaceToUndeploy,
} from '@/components/features/catalog/UndeployWorkspaceModal';
import { RequestSoftware } from '@/components/shared/RequestSoftware/RequestSoftware';
import {
  ActionsToolbar,
  AiwbDocsPage,
  aiwbDocumentationMapping,
  RelevantDocs,
} from '@amdenterpriseai/components';

import { useProject } from '@/contexts/ProjectContext';
import { deleteWorkspace, listAllWorkloads } from '@/lib/app/workloads';
import { listCharts } from '@/lib/app/charts';
import {
  DOCS_WORKBENCH_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';

const WorkspacesPage: React.FC & WithDocumentationLink = () => {
  const router = useRouter();
  const { toast } = useSystemToast();
  const { t } = useTranslation('catalog');
  const { activeProject, projectPath } = useProject();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<
    ClientSideDataFilter<WorkspaceCatalogTableItem>[]
  >([]);

  const { data: session } = useSession();

  const {
    data: catalogData,
    isLoading: isCatalogLoading,
    refetch: refetchCatalog,
    dataUpdatedAt: catalogUpdatedAt,
  } = useQuery({
    queryKey: ['project', activeProject, 'catalog', 'workspace'],
    queryFn: () => listCharts('WORKSPACE'),
    enabled: !!activeProject,
    select: (c) =>
      c.map((item) => ({
        ...item,
        available: true,
      })),
  });
  const {
    data: workloadsData,
    isLoading: isWorkloadsLoading,
    refetch: refetchWorkloads,
    dataUpdatedAt: workloadsUpdatedAt,
  } = useQuery({
    queryKey: ['project', activeProject, 'workloads'],
    queryFn: async () => {
      if (!activeProject) return [];

      return await listAllWorkloads(activeProject, {
        workloadType: ['WORKSPACE'],
        statusFilter: ['Running', 'Pending', 'Failed'],
      });
    },
    refetchInterval: 10000, // Refetch every 10 seconds
    enabled: !!activeProject,
  });

  const { mutate: deleteWorkspaceMutation, isPending: isDeletePending } =
    useMutation({
      mutationFn: (id: string) => deleteWorkspace(activeProject || '', id),
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: ['project', activeProject, 'workloads'],
        });
        toast.success(t('list.notifications.undeploySuccess'));
        onUndeployClose();
      },
      onError: (error) => {
        toast.error(t('list.errors.undeployError'), error as APIRequestError);
      },
    });

  const dataUpdatedAt = catalogUpdatedAt || workloadsUpdatedAt;
  const isLoading = isCatalogLoading || isWorkloadsLoading;

  const categoryFilterOptions = [
    {
      name: t('categories.development'),
      id: 'development',
    },
    { name: t('categories.mlops'), id: 'mlops' },
    { name: t('categories.genai'), id: 'generative_ai' },
  ];

  const [selectedItem, setSelectedItem] = useState<WorkspaceCatalogTableItem>();
  const {
    isOpen: isDrawerOpen,
    onOpen: onDrawerOpen,
    onClose: onDrawerClose,
  } = useOverlayState();
  const handleItemClick = (item: WorkspaceCatalogTableItem) => {
    setSelectedItem(item);
    onDrawerOpen();
  };

  const [workspaceToUndeploy, setWorkspaceToUndeploy] = useState<
    WorkspaceToUndeploy | undefined
  >();

  const isDeployed = (item: WorkspaceCatalogTableItem) => {
    return item.workloads?.some((w) => w.status === 'Running');
  };

  const isPending = (item: WorkspaceCatalogTableItem) => {
    return (
      isCatalogLoading ||
      isWorkloadsLoading ||
      item.workloads?.some((w) => w.status === 'Pending')
    );
  };

  const isFailed = (item: WorkspaceCatalogTableItem) =>
    item.workloads?.some((w) => w.status === 'Failed') ?? false;

  const {
    isOpen: isUndeployOpen,
    onOpen: onUndeployOpen,
    onClose: onUndeployClose,
    onOpenChange: onUndeployOpenChange,
  } = useOverlayState();

  const refreshCatalog = () => {
    refetchCatalog();
    refetchWorkloads();
  };

  const filteredCatalogItems = useMemo(() => {
    let filteredResults: WorkspaceCatalogTableItem[] = catalogData
      ? [...catalogData]
      : [];

    // Check if workloadsData is available and add the workload status and resources
    // TODO/FIXME: It would probably be better to aggregate these in the backend
    if (workloadsData) {
      const statusFilter: components['schemas']['WorkloadStatus'][] = [
        'Running',
        'Pending',
        'Failed',
      ];
      filteredResults = filteredResults.map((item) => {
        // Workloads for this catalog item: running, pending, or failed, for current user or project scope
        const workloads = workloadsData.filter(
          (workload) =>
            workload.name.includes(item.name) &&
            statusFilter.includes(workload.status) &&
            (workload.createdBy === session?.user?.email ||
              item.usageScope !== 'user'),
        );

        return {
          ...item,
          workloadsCount: workloads.length,
          workloads,
          status: workloads[0]?.status,
          createdAt: workloads[0]?.createdAt ?? item.createdAt,
        };
      });
    }

    filteredResults = getFilteredData(filteredResults, filters);

    return filteredResults;
  }, [catalogData, workloadsData, filters, session?.user?.email]);

  const launchWorkload = (item: WorkspaceCatalogTableItem) => {
    const workload = item.workloads?.find((w) => w.status === 'Running');

    if (!workload) {
      toast.error(t('list.errors.noRunningWorkload'));
      return;
    }

    const url =
      workload.endpoints?.external || workload.endpoints?.internal || '';
    window.open(url, '_blank');
  };

  const filterConfig = {
    search: {
      name: 'search',
      label: t('actions.search.label'),
      placeholder: t('actions.search.placeholder'),
      type: FilterComponentType.TEXT,
    },
    category: {
      name: 'category',
      label: t('actions.categoryFilter.label'),
      placeholder: t('actions.categoryFilter.label'),
      className: 'min-w-48',
      type: FilterComponentType.SELECT,
      allowMultipleSelection: true,
      fields: categoryFilterOptions.map((option) => ({
        label: option.name,
        key: option.id,
      })),
    },
  };

  const handleFilterChange = useCallback((filters: FilterValueMap) => {
    const newFilters: ClientSideDataFilter<WorkspaceCatalogTableItem>[] = [];

    if (filters?.search) {
      newFilters.push({
        field: 'displayName',
        values: filters.search,
      });
    }

    if (filters?.category && filters.category.length > 0) {
      newFilters.push({
        field: 'category',
        values: filters.category,
      });
    }

    setFilters(newFilters);
  }, []);

  return (
    <>
      <div className="min-h-full flex flex-col w-full">
        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
          <ActionsToolbar
            filterConfig={filterConfig}
            onFilterChange={handleFilterChange}
            onRefresh={refreshCatalog}
            updatedTimestamp={dataUpdatedAt}
            isRefreshing={isLoading}
          />

          <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-6 pl-2 pr-2 mb-6 w-full">
            {filteredCatalogItems.map((item: WorkspaceCatalogTableItem) => (
              <CatalogItemCard
                item={item}
                onOpenWorkloadDetails={(id) =>
                  router.push(projectPath(`/workloads/${id}`))
                }
                primaryAction={{
                  key: 'deploy',
                  label: t('list.actions.deploy'),
                  onPress: handleItemClick,
                }}
                secondaryActionColor="danger"
                secondaryAction={
                  isDeployed(item)
                    ? {
                        key: 'undeploy',
                        label: t('list.actions.undeploy'),
                        onPress: () => {
                          const running = item.workloads?.find(
                            (w) => w.status === 'Running',
                          );
                          if (!running?.id) return;
                          setWorkspaceToUndeploy({
                            workloadId: running.id,
                            displayName: item.displayName ?? item.name,
                          });
                          onUndeployOpen();
                        },
                      }
                    : isFailed(item)
                      ? {
                          key: 'deleteFailed',
                          label: t('list.actions.deleteFailedWorkload'),
                          onPress: () => {
                            const failed = item.workloads?.find(
                              (w) => w.status === 'Failed',
                            );
                            if (!failed?.id) return;
                            setWorkspaceToUndeploy({
                              workloadId: failed.id,
                              displayName: item.displayName ?? item.name,
                            });
                            onUndeployOpen();
                          },
                        }
                      : undefined
                }
                key={item.id}
                readyAction={{
                  key: 'launch',
                  label: t('list.actions.launch'),
                  onPress: (item: WorkspaceCatalogTableItem) => {
                    launchWorkload(item);
                  },
                }}
                isDeployed={isDeployed(item)}
                isPending={isPending(item)}
                isFailed={isFailed(item)}
                iconComponent={
                  item.featuredImage ? (
                    <Image
                      alt="workload icon"
                      className="rounded-md"
                      height={40}
                      src={item.featuredImage}
                      width={40}
                      unoptimized
                    />
                  ) : (
                    <IconAppWindow size={32} />
                  )
                }
                minHeaderHeight="4.5em"
                iconTopGap
              />
            ))}
          </div>
          <RequestSoftware variant="workspace" />
        </div>

        <RelevantDocs
          docs={aiwbDocumentationMapping[AiwbDocsPage.WORKSPACES]}
        />
      </div>

      {isDrawerOpen && selectedItem ? (
        <DeployWorkspaceWizard
          onClose={onDrawerClose}
          catalogItem={selectedItem}
          onDeploying={() =>
            queryClient.invalidateQueries({
              queryKey: ['project', activeProject, 'workloads'],
            })
          }
        />
      ) : null}

      <UndeployWorkspaceModal
        isOpen={isUndeployOpen}
        onOpenChange={onUndeployOpenChange}
        onConfirmAction={deleteWorkspaceMutation}
        workspaceToUndeploy={workspaceToUndeploy}
        loading={isDeletePending}
      />
    </>
  );
};

export async function getServerSideProps(context: any) {
  const { locale } = context;

  return {
    props: {
      ...(await getPageTranslations(locale, ['catalog'])),
    },
  };
}

export default WorkspacesPage;

WorkspacesPage.documentationLink = `${DOCS_WORKBENCH_BASE}/workspaces/overview.html`;
