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

import AIMCatalog from '@/components/features/models/AIMCatalog';
import { buildPageBreadcrumb } from '@/lib/app/breadcrumbs';

const AIMCatalogPage: React.FC & WithDocumentationLink = () => (
  <div className="min-h-full flex flex-col w-full">
    <div className="flex-1 flex flex-col min-h-0">
      <div className="mt-8">
        <AIMCatalog />
      </div>
    </div>
    <RelevantDocs docs={aiwbDocumentationMapping[AiwbDocsPage.MODELS]} />
  </div>
);

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const locale = context.locale || 'en';
  const translations = await getPageTranslations(locale, [
    'catalog',
    'loras',
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
        'aimCatalog',
      ),
    },
  };
}

AIMCatalogPage.documentationLink = `${DOCS_WORKBENCH_BASE}/models.html`;

export default AIMCatalogPage;
