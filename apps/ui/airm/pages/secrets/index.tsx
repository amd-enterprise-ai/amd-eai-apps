// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import { useQuery } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'next-i18next';
import { getServerSession } from 'next-auth';

import { fetchStorages } from '@/services/app';
import { getPageTranslations } from '@/utils/i18n';
import { getProjects } from '@/services/server';
import { getSecrets } from '@/services/server';
import { getStorages } from '@/services/server';

import { DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA } from '@amdenterpriseai/utils/app';
import { doesStorageDataNeedToBeRefreshed } from '@/utils/storages';
import {
  DOCS_RESOURCE_MANAGER_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import { authOptions } from '@amdenterpriseai/utils/server';
import {
  doesSecretDataNeedToBeRefreshed,
  isSecretActioning,
} from '@/utils/secrets';

import {
  ActionFieldHintType,
  ClientSideDataFilter,
  FilterValueMap,
} from '@amdenterpriseai/types';
import { ProjectStatus } from '@/types/enums/projects';
import { ProjectSecretStatus, SecretScope } from '@/types/enums/secrets';
import { Project } from '@/types/projects';
import { Secret, SecretsResponse } from '@/types/secrets';
import { StoragesResponse } from '@/types/storages';

import {
  AddSecret,
  AssignSecret,
  SecretsTable,
} from '@/components/features/secrets';
import DeleteSecretModal from '@/components/features/secrets/DeleteSecretModal';
import {
  ActionButton,
  AirmDocsPage,
  airmDocumentationMapping,
  RelevantDocs,
} from '@amdenterpriseai/components';
import { fetchSecrets } from '@/services/app';
import { SecretsFilter } from '@/components/features/secrets';
import { useOverlayState } from '@amdenterpriseai/hooks';

interface Props {
  projects: Project[];
  secrets: SecretsResponse;
  storages: StoragesResponse;
}

const SecretsPage: React.FC<Props> & WithDocumentationLink = ({
  projects,
  secrets,
  storages,
}) => {
  const { t } = useTranslation('secrets');

  // Additional modals for Resource Manager
  const {
    isOpen: isAddSecretFormOpen,
    onOpenChange: onAddSecretFormOpenChange,
    onClose,
  } = useOverlayState();

  const {
    isOpen: isAssignSecretFormOpen,
    onOpenChange: onAssignSecretFormOpenChange,
  } = useOverlayState();

  const { isOpen: isDeleteSecretOpen, onOpenChange: onDeleteSecretOpenChange } =
    useOverlayState();

  const { data: storagesData } = useQuery<StoragesResponse>({
    queryKey: ['storages'],
    queryFn: () => fetchStorages(),
    initialData: storages,
    refetchInterval: (query) => {
      return !query.state.data ||
        doesStorageDataNeedToBeRefreshed(query.state.data.data)
        ? DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA
        : false;
    },
  });
  const [filters, setFilters] = useState<ClientSideDataFilter<Secret>[]>([]);

  const handleFilterChange = useCallback((filters: FilterValueMap) => {
    const newFilters: ClientSideDataFilter<Secret>[] = [];

    if (
      filters?.search &&
      filters.search.length > 0 &&
      !(filters.search.length === 1 && filters.search[0] === '')
    ) {
      newFilters.push({
        field: 'name',
        values: filters.search,
      });
    }

    if (filters?.type && filters.type.length > 0) {
      newFilters.push({
        field: 'type',
        values: filters.type,
      });
    }
    if (filters?.scope && filters.scope.length > 0) {
      newFilters.push({
        field: 'scope',
        values: filters.scope,
      });
    }

    setFilters(newFilters);
  }, []);

  const {
    data: secretsData,
    isLoading: isSecretsLoading,
    refetch: refetchSecrets,
  } = useQuery<SecretsResponse>({
    queryKey: ['secrets'],
    queryFn: fetchSecrets,
    initialData: secrets,
    refetchInterval: (query) => {
      return !query.state.data ||
        doesSecretDataNeedToBeRefreshed(query.state.data?.data)
        ? DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA
        : false;
    },
  });

  // State management at page level
  const [targetSecret, setTargetSecret] = useState<Secret | null>(null);

  const checkSecretIsAttachedToStorage = useCallback(
    (s: Secret) => {
      return storagesData?.data.some((storage) => storage.secretId === s.id);
    },
    [storagesData],
  );

  const checkSecretIsOrganizationScoped = useCallback((s: Secret) => {
    return s.scope !== SecretScope.ORGANIZATION;
  }, []);

  const checkDeleteDisabled = useCallback(
    (s: Secret) => {
      return checkSecretIsAttachedToStorage(s);
    },
    [checkSecretIsAttachedToStorage],
  );

  const checkAssignDisabled = useCallback(
    (s: Secret) => {
      return isSecretActioning(s) || checkSecretIsOrganizationScoped(s);
    },
    [checkSecretIsOrganizationScoped],
  );

  // Define all table actions
  const actions = useMemo(
    () => [
      {
        key: 'assign',
        onPress: (s: Secret) => {
          setTargetSecret(s);
          onAssignSecretFormOpenChange();
        },
        isDisabled: checkAssignDisabled,
        label: t('list.actions.assign.label'),
        hint: [
          {
            showHint: checkSecretIsOrganizationScoped,
            message: t('list.actions.assign.hint.scope'),
            type: ActionFieldHintType.WARNING,
          },
        ],
      },
      {
        key: 'delete',
        className: 'text-danger',
        color: 'danger',
        isDisabled: checkDeleteDisabled,
        onPress: (s: Secret) => {
          setTargetSecret(s);
          onDeleteSecretOpenChange();
        },
        label: t('list.actions.delete.label'),
        hint: [
          {
            showHint: checkSecretIsAttachedToStorage,
            message: t('list.actions.delete.hint.storage'),
            type: ActionFieldHintType.WARNING,
          },
        ],
      },
    ],
    [
      checkSecretIsAttachedToStorage,
      checkSecretIsOrganizationScoped,
      checkDeleteDisabled,
      checkAssignDisabled,
      onAssignSecretFormOpenChange,
      onDeleteSecretOpenChange,
      t,
    ],
  );

  const projectsNotReadyIds = useMemo(
    () =>
      projects
        .filter((project) => project.status !== ProjectStatus.READY)
        .map((project) => project.id) ?? [],
    [projects],
  );

  const projectSecretsActioningIds = useMemo(
    () =>
      targetSecret?.projectSecrets
        .filter(
          (ps) =>
            ps.status === ProjectSecretStatus.DELETING ||
            ps.status === ProjectSecretStatus.PENDING,
        )
        .map((ps) => ps.project.id) ?? [],
    [targetSecret],
  );

  return (
    <div className="inline-flex flex-col w-full h-full max-h-full">
      <SecretsFilter
        onFilterChange={handleFilterChange}
        onRefresh={refetchSecrets}
        actionButton={
          <ActionButton primary onPress={onAddSecretFormOpenChange}>
            {t('actions.add')}
          </ActionButton>
        }
      />

      <SecretsTable
        secrets={secretsData.data}
        isSecretsLoading={isSecretsLoading}
        filters={filters}
        actions={actions}
      />

      <AddSecret
        isOpen={isAddSecretFormOpen}
        onClose={onClose}
        onCreateSuccess={refetchSecrets}
        secrets={secretsData.data}
        projects={projects}
        disabledProjectIds={projectsNotReadyIds}
        defaultScope={SecretScope.ORGANIZATION}
        scopeSelectDisabled={false}
        projectSelectDisabled={false}
      />
      <AssignSecret
        isOpen={isAssignSecretFormOpen}
        onClose={onAssignSecretFormOpenChange}
        projects={projects}
        secret={targetSecret}
        selectedProjectIds={
          targetSecret?.projectSecrets.map((ps) => ps.project.id) ?? []
        }
        disabledProjectIds={projectSecretsActioningIds.concat(
          projectsNotReadyIds,
        )}
      />
      <DeleteSecretModal
        isOpen={isDeleteSecretOpen}
        onOpenChange={onDeleteSecretOpenChange}
        secret={targetSecret}
        queryKeyToInvalidate={['secrets']}
      />
      <RelevantDocs docs={airmDocumentationMapping[AirmDocsPage.SECRETS]} />
    </div>
  );
};

SecretsPage.documentationLink = `${DOCS_RESOURCE_MANAGER_BASE}/secrets/overview.html`;

export default SecretsPage;

export async function getServerSideProps(context: any) {
  const { locale } = context;

  const session = await getServerSession(context.req, context.res, authOptions);

  try {
    const [secrets, projects, storages] = await Promise.all([
      getSecrets(session?.accessToken as string),
      getProjects(session?.accessToken as string),
      getStorages(session?.accessToken as string),
    ]);

    return {
      props: {
        ...(await getPageTranslations(locale, ['secrets'])),
        projects: projects?.data || [],
        secrets,
        storages,
      },
    };
  } catch (error) {
    console.error('Error fetching data on secrets page:', error);
    return { redirect: { destination: '/', permanent: false } };
  }
}
