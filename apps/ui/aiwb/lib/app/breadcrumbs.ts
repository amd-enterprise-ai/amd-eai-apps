// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { PageBreadcrumbs } from '@amdenterpriseai/types';
import type { serverSideTranslations } from 'next-i18next/serverSideTranslations';

export const buildPageBreadcrumb = (
  translations: Awaited<ReturnType<typeof serverSideTranslations>>,
  locale: string,
  ...pageKeys: string[]
): PageBreadcrumbs =>
  pageKeys.map((key) => ({
    title:
      translations._nextI18Next?.initialI18nStore?.[locale]?.common?.pages?.[
        key
      ]?.title ?? key,
  }));
