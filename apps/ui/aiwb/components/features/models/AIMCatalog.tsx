// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import { IconCpu, IconRocket, IconTag } from '@tabler/icons-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { useTranslation } from 'next-i18next';

import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';

import { getFilteredData } from '@amdenterpriseai/utils/app';

import { FilterComponentType } from '@amdenterpriseai/types';
import { ClientSideDataFilter, FilterValueMap } from '@amdenterpriseai/types';

import { ActionsToolbar } from '@amdenterpriseai/components';
import { PageLoader } from '@/components/shared/PageLoader';

import { AIMCard } from './AIMCard';
import { DeployAIMWizard } from './DeployAIMWizard';
import UndeployAIMModal from './UndeployAIMModal';
import AIMConnectModal from './AIMConnectModal';

import { useProject } from '@/contexts/ProjectContext';
import {
  buildFilteredCatalog,
  transformToAggregatedAIMs,
  getModelCapability,
  type InferenceCapability,
} from '@/lib/app/aims';
import {
  deleteInferenceDeployment,
  getInferenceCatalog,
} from '@/lib/app/inference';
import { AIMWorkloadStatus, ParsedAIM, AggregatedAIM } from '@/types/aims';
import { useRouter } from 'next/router';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { RequestSoftware } from '@/components/shared/RequestSoftware/RequestSoftware';

const AIMS_REFETCH_INTERVAL = 30000; // Refetch every 30 seconds

const AIMCatalog: React.FC = () => {
  const { t } = useTranslation('models', { keyPrefix: 'aimCatalog' });
  const { toast } = useSystemToast();
  const { activeProject, projectPath, projectUrl } = useProject();
  const queryClient = useQueryClient();
  const router = useRouter();

  const [filters, setFilters] = useState<ClientSideDataFilter<ParsedAIM>[]>([]);

  const [aggregatedAimForDeployment, setAggregatedAimForDeployment] = useState<
    AggregatedAIM | undefined
  >(undefined);
  const [serviceToUndeploy, setServiceToUndeploy] = useState<
    | {
        namespace: string;
        serviceId: string;
        displayName: string;
      }
    | undefined
  >(undefined);
  const [connectInfo, setConnectInfo] = useState<
    | {
        serviceId?: string;
        endpoints?: { internal?: string; external?: string };
        modelName?: string;
        capability?: InferenceCapability;
      }
    | undefined
  >(undefined);

  const deployDisclosure = useOverlayState();
  const undeployDisclosure = useOverlayState();
  const connectDisclosure = useOverlayState();

  const {
    data: aims,
    isLoading: isAIMSLoading,
    refetch: refetchModels,
    error: modelsError,
  } = useQuery<ParsedAIM[]>({
    queryKey: ['project', activeProject, 'aim-catalog'],
    queryFn: () => getInferenceCatalog(activeProject || undefined),
    refetchInterval: AIMS_REFETCH_INTERVAL,
    enabled: !!activeProject,
  });

  const memoizedAims = useMemo(() => {
    return aims || [];
  }, [aims]);

  const aggregatedAims = useMemo(() => {
    return transformToAggregatedAIMs(memoizedAims);
  }, [memoizedAims]);

  const filteredAggregatedAims = useMemo(
    () =>
      buildFilteredCatalog(
        memoizedAims,
        getFilteredData(memoizedAims, filters),
      ),
    [memoizedAims, filters],
  );

  useEffect(() => {
    if (modelsError) {
      toast.error(
        t('actions.notifications.fetchError', {
          error: String(modelsError.message),
        }),
      );
    }
  }, [modelsError, toast, t]);

  const tags = useMemo(() => {
    const allTags = new Set<string>();
    aggregatedAims.forEach((aggregatedAim) => {
      aggregatedAim.parsedAIMs.forEach((aim) => {
        aim.tags?.forEach((tag) => {
          allTags.add(tag);
        });
      });
    });
    return Array.from(allTags).sort();
  }, [aggregatedAims]);

  const handleAimDeploy = useCallback(
    (aggregatedAim: AggregatedAIM) => {
      // Always pass the unfiltered AggregatedAIM so the deploy wizard has the full
      // parsedAIMs list including any Ready versions that the active filter hid.
      setAggregatedAimForDeployment(
        aggregatedAims.find((a) => a.repository === aggregatedAim.repository) ??
          aggregatedAim,
      );
      deployDisclosure.onOpen();
    },
    [deployDisclosure, aggregatedAims],
  );

  const handleOpenDetails = useCallback(
    (serviceId: string) => {
      router.push(projectPath(`/aims/${serviceId}`));
    },
    [router, projectPath],
  );

  const handleChatWithModel = useCallback(
    (serviceId: string) => {
      window.open(projectUrl(`/chat?workload=${serviceId}`), '_blank');
    },
    [projectUrl],
  );

  const handleConnectToModel = useCallback(
    (aim: ParsedAIM) => {
      const service = aim.deployedServices?.[0];
      setConnectInfo({
        serviceId: service?.id ?? undefined,
        endpoints: service?.endpoints,
        modelName: service?.status?.resolvedModel?.name ?? undefined,
        capability: getModelCapability(aim.tags),
      });
      connectDisclosure.onOpen();
    },
    [connectDisclosure],
  );

  const handleConnectConfirm = useCallback(
    (serviceId: string) => {
      handleChatWithModel(serviceId);
      connectDisclosure.onClose();
      setConnectInfo(undefined);
    },
    [connectDisclosure, handleChatWithModel],
  );

  const handleConnectModalClose = useCallback(() => {
    connectDisclosure.onClose();
    setConnectInfo(undefined);
  }, [connectDisclosure]);

  const handleUndeploy = useCallback(
    (namespace: string, serviceId: string, displayName: string) => {
      setServiceToUndeploy({ namespace, serviceId, displayName });
      undeployDisclosure.onOpen();
    },
    [undeployDisclosure],
  );

  const handleConfirmUndeploy = useCallback(
    async (namespace: string, serviceId: string) => {
      try {
        await deleteInferenceDeployment(namespace, serviceId);
        toast.success(t('actions.notifications.deleteSuccess'));
        await refetchModels();
      } catch (error) {
        toast.error(
          t('actions.notifications.deleteError'),
          error as APIRequestError,
        );
      }
    },
    [toast, refetchModels, t],
  );

  const filterConfig = useMemo(
    () => ({
      search: {
        className: 'w-full',
        name: 'search',
        label: t('list.filter.search.placeholder'),
        placeholder: t('list.filter.search.placeholder'),
        type: FilterComponentType.TEXT,
      },
      accelerator: {
        name: 'accelerator',
        icon: <IconCpu />,
        label: t('list.filter.accelerator.placeholder'),
        placeholder: t('list.filter.accelerator.placeholder'),
        type: FilterComponentType.DROPDOWN,
        fields: [
          { label: t('list.filter.accelerator.gpu'), key: 'gpu' },
          { label: t('list.filter.accelerator.cpu'), key: 'cpu' },
        ],
      },
      tags: {
        name: 'tags',
        icon: <IconTag />,
        label: t('list.filter.tag.placeholder'),
        placeholder: t('list.filter.tag.placeholder'),
        type: FilterComponentType.DROPDOWN,
        fields: tags.map((option) => ({
          label: option,
          key: option,
        })),
      },
      deploymentStatus: {
        name: 'deploymentStatus',
        icon: <IconRocket />,
        label: t('list.filter.deploymentStatus.placeholder'),
        placeholder: t('list.filter.deploymentStatus.placeholder'),
        type: FilterComponentType.DROPDOWN,
        fields: [
          {
            label: t('list.filter.deploymentStatus.deployed'),
            key: AIMWorkloadStatus.DEPLOYED,
          },
          {
            label: t('list.filter.deploymentStatus.notDeployed'),
            key: AIMWorkloadStatus.NOT_DEPLOYED,
          },
          {
            label: t('list.filter.deploymentStatus.pending'),
            key: AIMWorkloadStatus.PENDING,
          },
          {
            label: t('list.filter.deploymentStatus.starting'),
            key: AIMWorkloadStatus.STARTING,
          },
        ],
      },
    }),
    [t, tags],
  );

  const handleFilterChange = useCallback((filters: FilterValueMap) => {
    const newFilters: ClientSideDataFilter<ParsedAIM>[] = [];

    if (filters?.search && filters.search.length > 0) {
      newFilters.push({
        compositeFields: [
          { field: 'title' },
          { field: 'canonicalName' },
          { field: 'model' },
          { field: 'aimId' },
          { field: 'imageReference' },
          { field: 'imageVersion' },
          { field: 'description', path: 'short' },
          { field: 'tags' },
          { field: 'sourceUri' },
        ],
        values: filters.search,
      });
    }

    if (filters?.deploymentStatus && filters.deploymentStatus.length > 0) {
      newFilters.push({
        field: 'workloadStatuses',
        values: filters.deploymentStatus,
        exact: true,
      });
    }

    if (filters?.tags && filters.tags.length > 0) {
      newFilters.push({
        field: 'tags',
        values: filters.tags,
      });
    }

    if (filters?.accelerator && filters.accelerator.length > 0) {
      newFilters.push({
        field: 'acceleratorTypes',
        values: filters.accelerator,
        exact: true,
      });
    }

    setFilters(newFilters);
  }, []);

  if (isAIMSLoading) {
    return (
      <PageLoader
        label={t('list.loading')}
        testId="aim-catalog-loading"
        className="h-64"
      />
    );
  }

  const isListEmpty =
    !filteredAggregatedAims || filteredAggregatedAims.length === 0;

  return (
    <div data-testid="aim-catalog">
      <p className="text-lg mb-4">{t('list.description')}</p>
      <ActionsToolbar
        filterConfig={filterConfig}
        onFilterChange={handleFilterChange}
        onRefresh={refetchModels}
      />

      {isListEmpty ? (
        <div
          data-testid="aim-catalog-empty"
          className="flex flex-col items-center justify-center text-center gap-2 py-12"
        >
          <p className="text-sm text-foreground/60">
            {t('list.empty.description')}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-1 lg:grid-cols-2 xl:grid-cols-2 2xl:grid-cols-3 gap-6 mb-6">
          {filteredAggregatedAims.map((aggregatedAim) => (
            <AIMCard
              key={aggregatedAim.repository}
              aggregatedAim={aggregatedAim}
              onDeploy={() => handleAimDeploy(aggregatedAim)}
              onOpenDetails={handleOpenDetails}
              onChatWithModel={handleChatWithModel}
              onConnectToModel={handleConnectToModel}
              onUndeploy={handleUndeploy}
            />
          ))}
        </div>
      )}
      <RequestSoftware variant="model" />
      {deployDisclosure.isOpen && aggregatedAimForDeployment && (
        <DeployAIMWizard
          onClose={deployDisclosure.onClose}
          onDeploying={() => {
            queryClient.invalidateQueries({
              queryKey: ['project', activeProject, 'aim-catalog'],
            });
          }}
          aggregatedAim={aggregatedAimForDeployment}
        />
      )}
      <UndeployAIMModal
        isOpen={undeployDisclosure.isOpen}
        onOpenChange={undeployDisclosure.onOpenChange}
        onConfirmAction={handleConfirmUndeploy}
        serviceToUndeploy={serviceToUndeploy}
      />
      <AIMConnectModal
        isOpen={connectDisclosure.isOpen}
        onOpenChange={(isOpen) => !isOpen && handleConnectModalClose()}
        serviceId={connectInfo?.serviceId}
        endpoints={connectInfo?.endpoints}
        modelName={connectInfo?.modelName}
        capability={connectInfo?.capability ?? 'chat'}
        onChatRequested={handleConnectConfirm}
      />
    </div>
  );
};

export default AIMCatalog;
