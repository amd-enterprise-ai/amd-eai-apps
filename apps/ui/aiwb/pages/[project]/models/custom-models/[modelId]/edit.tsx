// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { GetServerSidePropsContext } from 'next';

import {
  DOCS_WORKBENCH_BASE,
  type WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import type { PageBreadcrumbs } from '@amdenterpriseai/types';

import CustomModelImportPage from '@/components/features/models/CustomModelImport';
import { getPageTranslations } from '@/lib/server/i18n';

interface Props {
  modelId: string;
  pageBreadcrumb?: PageBreadcrumbs;
}

const EditCustomModelRoute: React.FC<Props> & WithDocumentationLink = ({
  modelId,
}) => <CustomModelImportPage mode="edit" modelId={modelId} />;

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const locale = context.locale || 'en';
  const project = context.params?.project as string;
  const modelId = context.params?.modelId as string;

  const translations = await getPageTranslations(locale, ['models']);

  const breadcrumb: PageBreadcrumbs = [
    {
      title:
        translations._nextI18Next?.initialI18nStore?.[locale]?.common?.pages
          ?.models?.title || 'Models',
      href: `/${project}/models/custom-models`,
    },
    {
      title:
        translations._nextI18Next?.initialI18nStore?.[locale]?.common?.pages
          ?.customModels?.title || 'Custom Models',
      href: `/${project}/models/custom-models`,
    },
    {
      title:
        translations._nextI18Next?.initialI18nStore?.[locale]?.models
          ?.customModels?.import?.editTitle || 'Edit model',
    },
  ];

  return {
    props: {
      ...translations,
      modelId,
      pageBreadcrumb: breadcrumb,
    },
  };
}

export default EditCustomModelRoute;

EditCustomModelRoute.documentationLink = `${DOCS_WORKBENCH_BASE}/models.html`;
