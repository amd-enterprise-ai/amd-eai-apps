// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';

import { WorkbenchSecretsPageContent } from '@/components/features/secrets/WorkbenchSecretsPageContent';
import { getPageTranslations } from '@/lib/server/i18n';
import {
  DOCS_WORKBENCH_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';

const WorkbenchSecretsPage: React.FC & WithDocumentationLink = () => {
  return <WorkbenchSecretsPageContent />;
};

export default WorkbenchSecretsPage;

WorkbenchSecretsPage.documentationLink = `${DOCS_WORKBENCH_BASE}/secrets.html`;

export async function getServerSideProps(context: any) {
  const { locale } = context;

  return {
    props: {
      ...(await getPageTranslations(locale, ['secrets'])),
    },
  };
}
