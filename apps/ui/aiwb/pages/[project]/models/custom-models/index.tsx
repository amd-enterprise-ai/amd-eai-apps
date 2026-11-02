// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { GetServerSidePropsContext } from 'next';
import { getPageTranslations } from '@/lib/server/i18n';

import {
  AiwbDocsPage,
  aiwbDocumentationMapping,
  RelevantDocs,
} from '@amdenterpriseai/components';
import {
  DOCS_WORKBENCH_BASE,
  type WithDocumentationLink,
} from '@amdenterpriseai/utils/app';

import CustomModels from '@/components/features/models/CustomModels';
import { buildPageBreadcrumb } from '@/lib/app/breadcrumbs';

const CustomModelsPage: React.FC & WithDocumentationLink = () => (
  <div className="min-h-full flex flex-col w-full">
    <div className="flex-1 flex flex-col min-h-0">
      <div className="mt-8">
        <CustomModels />
      </div>
    </div>
    <RelevantDocs docs={aiwbDocumentationMapping[AiwbDocsPage.MODELS]} />
  </div>
);

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const locale = context.locale || 'en';
  const translations = await getPageTranslations(locale, [
    'catalog',
    'models',
    'workloads',
    'autoscaling',
  ]);

  return {
    props: {
      ...translations,
      pageBreadcrumb: buildPageBreadcrumb(
        translations,
        locale,
        'models',
        'customModels',
      ),
    },
  };
}

CustomModelsPage.documentationLink = `${DOCS_WORKBENCH_BASE}/models.html`;

export default CustomModelsPage;
