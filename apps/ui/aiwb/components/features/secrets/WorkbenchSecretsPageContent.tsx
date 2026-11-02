// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React, { useCallback, useState } from 'react';
import { useTranslation } from 'next-i18next';
import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';

import {
  ActionButton,
  ActionsToolbar,
  AiwbDocsPage,
  aiwbDocumentationMapping,
  RelevantDocs,
} from '@amdenterpriseai/components';
import DeleteSecretModal from './DeleteSecretModal';
import { SecretsTable } from './SecretsTable';

import { fetchProjectSecrets } from '@/lib/app/secrets';
import { FilterComponentType, FilterValueMap } from '@amdenterpriseai/types';
import { useProject } from '@/contexts/ProjectContext';
import { SecretResponseData } from '@/types/secrets';
import AddSecret from './AddSecret';
import { useOverlayState } from '@amdenterpriseai/hooks';

type ClientSideDataFilter<T> = {
  field: keyof T;
  path?: string;
  values: string[];
};

export const WorkbenchSecretsPageContent: React.FC = () => {
  const { t } = useTranslation('secrets');

  // State management at component level
  const [targetSecret, setTargetSecret] = useState<SecretResponseData | null>(
    null,
  );

  const { isOpen: isAddSecretOpen, onOpenChange: onAddSecretOpenChange } =
    useOverlayState();

  // Get active project from context
  const { activeProject } = useProject();

  // Session for RBAC
  const { data: session } = useSession();

  // React Query for fetching workbench secrets - refetch when project changes
  const {
    data: secretsData,
    isLoading: isSecretsLoading,
    refetch: refetchSecrets,
  } = useQuery<{
    data: SecretResponseData[];
  }>({
    queryKey: ['project', activeProject, 'secrets'],
    queryFn: () => fetchProjectSecrets(activeProject!),
    refetchInterval: false,
    enabled: !!session?.user, // Fetch for all authenticated users
  });

  // Inline filter logic for SecretResponseData
  const [filters, setFilters] = useState<
    ClientSideDataFilter<SecretResponseData>[]
  >([]);

  // Filter change handler
  const handleFilterChange = useCallback((filters: FilterValueMap) => {
    const newFilters: ClientSideDataFilter<SecretResponseData>[] = [];

    if (filters?.search?.[0]) {
      newFilters.push({
        field: 'displayName',
        values: filters.search,
      });
    }

    setFilters(newFilters);
  }, []);

  // Filter configuration
  const filterConfig = {
    search: {
      name: 'search',
      className: 'w-full',
      label: t('list.filter.search.label'),
      placeholder: t('list.filter.search.placeholder'),
      type: FilterComponentType.TEXT,
    },
  };

  // Disclosure for delete modal
  const { isOpen: isDeleteSecretOpen, onOpenChange: onDeleteSecretOpenChange } =
    useOverlayState();

  // Check if user can delete secrets
  const canDeleteSecrets = useCallback(
    (secret: SecretResponseData) => {
      // Basic auth check
      if (!session?.user || !activeProject) return false;

      // Check if the secret is assigned to the current project
      return secret.metadata.namespace === activeProject;
    },
    [session, activeProject],
  );

  // Actions for secrets table
  const actions = [
    {
      key: 'delete',
      className: 'text-danger',
      color: 'danger',
      isDisabled: (s: SecretResponseData) => !canDeleteSecrets(s),
      onPress: (s: SecretResponseData) => {
        setTargetSecret(s);
        onDeleteSecretOpenChange();
      },
      label: t('list.actions.delete.label'),
    },
  ];

  return (
    <div className="min-h-full flex flex-col">
      <div className="flex-1 flex flex-col min-h-0">
        <ActionsToolbar
          filterConfig={filterConfig}
          onFilterChange={handleFilterChange}
          endContent={
            <ActionButton primary onClick={onAddSecretOpenChange}>
              {t('actions.add')}
            </ActionButton>
          }
        />

        {isAddSecretOpen && (
          <AddSecret
            isOpen={isAddSecretOpen}
            namespace={activeProject!}
            secrets={secretsData?.data}
            onClose={() => {
              onAddSecretOpenChange();
              refetchSecrets();
            }}
          />
        )}

        <SecretsTable
          secrets={secretsData?.data || []}
          isSecretsLoading={isSecretsLoading}
          filters={filters}
          actions={actions}
          showScopeColumn={false}
          showAssignedToColumn={false}
        />

        <DeleteSecretModal
          isOpen={isDeleteSecretOpen}
          onOpenChange={onDeleteSecretOpenChange}
          secret={targetSecret}
          projectId={activeProject!}
          queryKeyToInvalidate={['project', activeProject!, 'secrets']}
        />
      </div>
      <RelevantDocs docs={aiwbDocumentationMapping[AiwbDocsPage.SECRETS]} />
    </div>
  );
};

export default WorkbenchSecretsPageContent;
