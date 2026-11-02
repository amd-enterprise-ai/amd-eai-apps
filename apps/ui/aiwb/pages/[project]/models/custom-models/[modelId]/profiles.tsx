// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { GetServerSidePropsContext } from 'next';
import { getPageTranslations } from '@/lib/server/i18n';

import {
  DOCS_WORKBENCH_BASE,
  type WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import type { PageBreadcrumbs } from '@amdenterpriseai/types';

import { CustomProfilesPage } from '@/components/features/models/CustomProfiles';

interface Props {
  modelId: string;
  pageBreadcrumb?: PageBreadcrumbs;
}

const CustomModelProfilesRoute: React.FC<Props> & WithDocumentationLink = ({
  modelId,
}) => <CustomProfilesPage modelId={modelId} />;

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const locale = context.locale || 'en';
  const project = context.params?.project as string;
  const modelId = context.params?.modelId as string;

  const translations = await getPageTranslations(locale, ['models']);

  const breadcrumb: PageBreadcrumbs = [
    {
      title:
        translations._nextI18Next?.initialI18nStore?.[locale]?.common?.pages
          ?.customModels?.title || 'Custom Models',
      href: `/${project}/models/custom-models`,
    },
    {
      title:
        translations._nextI18Next?.initialI18nStore?.[locale]?.common?.pages
          ?.customProfiles?.title || 'Profiles',
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

export default CustomModelProfilesRoute;

CustomModelProfilesRoute.documentationLink = `${DOCS_WORKBENCH_BASE}/models.html`;
