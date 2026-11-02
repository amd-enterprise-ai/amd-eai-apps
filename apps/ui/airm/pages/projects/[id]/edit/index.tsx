// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Button, Divider, Tab, Tabs } from '@amdenterpriseai/components';
import { useQuery } from '@tanstack/react-query';

import { getServerSession } from 'next-auth';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import {
  getCluster as fetchCluster,
  fetchProjectStorages,
} from '@/services/app';
import { fetchProject } from '@/services/app';
import { getCluster } from '@/services/server';
import { getProject } from '@/services/server';

import { getProjectDashboardUrl, getProjectEditUrl } from '@/utils/projects';
import { getPageTranslations } from '@/utils/i18n';
import {
  DOCS_RESOURCE_MANAGER_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import { authOptions } from '@amdenterpriseai/utils/server';

import { UserRole } from '@amdenterpriseai/types';
import { Cluster } from '@/types/clusters';
import { ProjectStoragesResponse } from '@/types/storages';

import { ProjectWithMembers } from '@/types/projects';

import DeleteProject from '@/components/features/projects/DeleteProject';
import { ReducedWidthLayout } from '@amdenterpriseai/layouts';

import {
  InvitedUsers,
  Members,
  ProjectSecrets,
  ProjectStorages,
} from '@/components/features/projects';
import { useAccessControl } from '@/hooks/useAccessControl';
import { IconChevronLeft } from '@tabler/icons-react';
import { getProjectSecrets, getSecrets } from '@/services/server';
import { getProjectStorages, getStorages } from '@/services/server';
import { ProjectSecretsResponse } from '@/types/secrets';
import {
  ProjectSecretWithParentSecret,
  Secret,
  SecretsResponse,
} from '@/types/secrets';
import {
  ProjectStorageWithParentStorage,
  Storage,
  StoragesResponse,
} from '@/types/storages';
import ProjectQuotaForm from '@/components/features/projects/ProjectQuotaForm';
import ProjectBasicInfoForm from '@/components/features/projects/ProjectBasicInfoForm';
import { fetchProjectSecrets, fetchSecrets } from '@/services/app';

const tranlationKeySet = 'projects';

interface Props {
  project: ProjectWithMembers;
  cluster: Cluster;
}

interface Props {
  project: ProjectWithMembers;
  cluster: Cluster;
  projectSecrets: ProjectSecretWithParentSecret[];
  projectStorages: ProjectStorageWithParentStorage[];
  secrets: Secret[];
  storages: Storage[];
}

const ProjectEditPage: React.FC<Props> & WithDocumentationLink = ({
  project,
  cluster,
  projectSecrets,
  projectStorages,
  secrets,
  storages,
}) => {
  const router = useRouter();
  const { id } = router.query;
  const { t } = useTranslation(tranlationKeySet);
  const { isInviteEnabled, isAdministrator } = useAccessControl();
  const { push } = useRouter();

  const { data: projectData } = useQuery<ProjectWithMembers>({
    queryKey: ['project'],
    queryFn: () => fetchProject(id as string),
    initialData: project,
  });

  const { data: clusterData } = useQuery<Cluster>({
    queryKey: ['cluster'],
    queryFn: () => fetchCluster(cluster.id as string),
    initialData: cluster,
  });

  const { data: secretsData } = useQuery<SecretsResponse>({
    queryKey: ['secrets'],
    queryFn: () => fetchSecrets(),
    initialData: {
      data: secrets,
    },
    enabled: !!isAdministrator,
  });

  const { data: projectSecretsData } = useQuery<ProjectSecretsResponse>({
    queryKey: ['secrets', project.id],
    queryFn: () => fetchProjectSecrets(project.id as string),
    initialData: {
      data: projectSecrets,
    },
  });

  const { data: projectStoragesData } = useQuery<ProjectStoragesResponse>({
    queryKey: ['project-storages', project.id],
    queryFn: () => fetchProjectStorages(project.id as string),
    initialData: {
      data: projectStorages,
    },
  });

  return (
    <div className="flex gap-8 mt-8">
      <div className="flex-1 min-w-0">
        <div className="flex gap-3 items-center">
          <Button
            size="sm"
            isIconOnly
            onPress={() => push(`/projects/${project.id}`)}
            aria-label={t('actions.back')}
          >
            <IconChevronLeft size={16} />
          </Button>
          <h2>{t('settings.title')}</h2>
        </div>

        <Tabs
          aria-label={t('tab.title')}
          variant="secondary"
          classNames={{
            tabWrapper: 'w-full mt-8',
            panel: 'overflow-y-scroll h-full w-full mt-4',
          }}
        >
          <Tab key="quota" title={t('tab.quota.title')}>
            <ReducedWidthLayout padded={false}>
              <ProjectQuotaForm project={projectData} cluster={clusterData} />
            </ReducedWidthLayout>
          </Tab>
          <Tab key="secrets" title={t('tab.secrets.title')}>
            <ProjectSecrets
              projectStorages={projectStoragesData}
              projectSecrets={projectSecretsData}
              project={projectData}
              secrets={secretsData.data}
            />
          </Tab>
          <Tab key="storages" title={t('tab.storages.title')}>
            <ProjectStorages
              project={projectData}
              projectStorages={projectStoragesData.data}
              storages={storages}
            />
          </Tab>
          <Tab key="users" title={t('tab.users.title')}>
            <Members project={projectData} />
            {isInviteEnabled && <InvitedUsers project={projectData} />}
          </Tab>
          <Tab key="details" title={t('tab.details.title')}>
            <ReducedWidthLayout padded={false} className="flex flex-col gap-8">
              <ProjectBasicInfoForm
                project={projectData}
                cluster={clusterData}
              />
              {isAdministrator ? (
                <section id="delete-project" className="scroll-mt-6">
                  <h2 className="text-lg text-danger font-semibold mb-3">
                    {t('settings.form.deleteProject.title')}
                  </h2>
                  <Divider />
                  <div className="flex flex-col gap-6 my-3">
                    <DeleteProject project={projectData} />
                  </div>
                </section>
              ) : null}
            </ReducedWidthLayout>
          </Tab>
        </Tabs>
      </div>
    </div>
  );
};

ProjectEditPage.documentationLink = `${DOCS_RESOURCE_MANAGER_BASE}/projects/project-settings.html`;

export default ProjectEditPage;

export async function getServerSideProps(context: any) {
  const { locale } = context;

  const session = await getServerSession(context.req, context.res, authOptions);

  try {
    const project = await getProject(
      context.params.id,
      session?.accessToken as string,
    );
    const clusterResponse = await getCluster(
      project.clusterId,
      session?.accessToken as string,
    );

    const projectSecrets = await getProjectSecrets(
      session?.accessToken as string,
      context.params.id,
    );

    const projectStorages = await getProjectStorages(
      session?.accessToken as string,
      context.params.id,
    );

    const userRoles = session?.user?.roles ?? [];
    const isPlatformAdmin = userRoles.includes(UserRole.PLATFORM_ADMIN);

    let secrets: SecretsResponse = { data: [] };
    let storages: StoragesResponse = { data: [] };

    if (isPlatformAdmin) {
      secrets = await getSecrets(session?.accessToken as string);
      storages = await getStorages(session?.accessToken as string);
    }

    const translations = await getPageTranslations(locale, [
      'projects',
      'users',
      'secrets',
      'storages',
    ]);

    const breadcrumb = [
      {
        title:
          translations._nextI18Next?.initialI18nStore[locale]?.projects?.title,
        href: '/projects',
      },
      {
        title: `${project.name}`,
        href: getProjectDashboardUrl(context.params.id),
      },
      {
        title:
          translations._nextI18Next?.initialI18nStore[locale]?.projects
            ?.settings.navigation,
        href: getProjectEditUrl(context.params.id),
      },
    ];

    return {
      props: {
        session: session ? JSON.parse(JSON.stringify(session)) : null,
        ...translations,
        cluster: clusterResponse,
        project,
        pageBreadcrumb: breadcrumb,
        secrets: secrets?.data || [],
        storages: storages?.data || [],
        projectSecrets: projectSecrets?.data || [],
        projectStorages: projectStorages?.data || [],
      },
    };
  } catch (error) {
    console.error('Project not found: ' + error);
    return {
      redirect: {
        destination: '/',
        permanent: false,
      },
    };
  }
}
