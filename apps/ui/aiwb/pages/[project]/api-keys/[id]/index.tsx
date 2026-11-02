// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { getServerSession } from 'next-auth';
import { useTranslation } from 'next-i18next';
import type { GetServerSidePropsContext } from 'next';
import { useRouter } from 'next/router';

import { authOptions } from '@amdenterpriseai/utils/server';

import { useProject } from '@/contexts/ProjectContext';
import { getPageTranslations } from '@/lib/server/i18n';
import ApiKeyMetricsDashboard from '@/components/features/api-keys/ApiKeyMetricsDashboard';

const ApiKeyDetailsPage: React.FC = () => {
  const { t } = useTranslation('api-keys');
  const router = useRouter();
  const { activeProject, aiGatewayEnabled } = useProject();

  const apiKeyId = router.query.id as string;
  const apiKeyName = (router.query.name as string) ?? t('details.breadcrumb');

  if (!activeProject || !apiKeyId || !aiGatewayEnabled) return null;

  return (
    <div className="min-h-full flex flex-col w-full">
      <ApiKeyMetricsDashboard
        projectId={activeProject}
        apiKeyId={apiKeyId}
        apiKeyName={apiKeyName}
      />
    </div>
  );
};

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const { req, res, locale, params, query } = context;
  const project = params?.project as string;
  const keyName = query?.name as string | undefined;

  const session = await getServerSession(req, res, authOptions);

  if (
    !session ||
    !session.user ||
    !session.user.email ||
    !session.accessToken
  ) {
    return {
      redirect: {
        destination: '/',
        permanent: false,
      },
    };
  }

  const resolvedLocale = locale ?? 'en';
  const translations = await getPageTranslations(resolvedLocale, [
    'api-keys',
    'projects',
    'workloads',
    'models',
  ]);

  const apiKeysTitle =
    (translations._nextI18Next?.initialI18nStore[resolvedLocale]?.['api-keys']
      ?.list?.title as string | undefined) ?? 'API Keys';

  const breadcrumb = [
    {
      title: apiKeysTitle,
      href: `/${project}/api-keys`,
    },
    {
      title:
        keyName ??
        (translations._nextI18Next?.initialI18nStore[resolvedLocale]?.[
          'api-keys'
        ]?.details?.breadcrumb as string | undefined) ??
        'API Key Details',
    },
  ];

  return {
    props: {
      ...translations,
      pageBreadcrumb: breadcrumb,
    },
  };
}

export default ApiKeyDetailsPage;
