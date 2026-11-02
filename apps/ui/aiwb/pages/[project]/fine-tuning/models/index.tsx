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

import FineTuneModels from '@/components/features/models/FineTuneModels';
import { buildPageBreadcrumb } from '@/lib/app/breadcrumbs';

const FineTuningModelsPage: React.FC & WithDocumentationLink = () => (
  <div className="min-h-full flex flex-col w-full">
    <FineTuneModels />
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
        'fineTuning',
        'fineTuneModels',
      ),
    },
  };
}

FineTuningModelsPage.documentationLink = `${DOCS_WORKBENCH_BASE}/models.html`;

export default FineTuningModelsPage;
