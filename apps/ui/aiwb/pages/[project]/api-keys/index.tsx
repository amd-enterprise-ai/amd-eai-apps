// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useTranslation } from 'next-i18next';

import ApiKeysTable from '@/components/features/api-keys/ApiKeysTable';
import { getPageTranslations } from '@/lib/server/i18n';
import CreateApiKey from '@/components/features/api-keys/CreateApiKey';
import {
  ActionButton,
  AiwbDocsPage,
  aiwbDocumentationMapping,
  RelevantDocs,
} from '@amdenterpriseai/components';

import { useOverlayState } from '@amdenterpriseai/hooks';

import { useProject } from '@/contexts/ProjectContext';
import {
  DOCS_WORKBENCH_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';

const ApiKeysPage: React.FC & WithDocumentationLink = () => {
  const { t } = useTranslation('api-keys');
  const { activeProject, apiKeysManagementEnabled } = useProject();

  const {
    isOpen: isCreateFormOpen,
    onOpenChange: onCreateFormOpenChange,
    onClose: onCreateFormClose,
  } = useOverlayState();

  if (!apiKeysManagementEnabled) {
    return (
      <div className="min-h-full flex flex-col w-full items-center justify-center">
        <p className="text-muted">{t('list.apiKeysDisabled')}</p>
      </div>
    );
  }

  return (
    <div className="min-h-full flex flex-col w-full">
      <div className="flex-1 flex flex-col min-h-0">
        <ApiKeysTable
          projectId={activeProject!}
          createButton={
            <ActionButton primary onPress={onCreateFormOpenChange}>
              {t('list.actions.create.title')}
            </ActionButton>
          }
        />
        <CreateApiKey
          isOpen={isCreateFormOpen}
          projectId={activeProject!}
          onClose={onCreateFormClose}
        />
      </div>
      <RelevantDocs docs={aiwbDocumentationMapping[AiwbDocsPage.API_KEYS]} />
    </div>
  );
};

export async function getServerSideProps(context: any) {
  const { locale } = context;

  return {
    props: {
      ...(await getPageTranslations(locale, ['api-keys'])),
    },
  };
}

export default ApiKeysPage;

ApiKeysPage.documentationLink = `${DOCS_WORKBENCH_BASE}/api-keys.html`;
