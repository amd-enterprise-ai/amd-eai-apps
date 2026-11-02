// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { StatisticsCardProps } from '@amdenterpriseai/components';
import {
  ActionButton,
  HorizontalStatisticsCards,
  StatusDisplay,
} from '@amdenterpriseai/components';
import { IconArrowLeft } from '@tabler/icons-react';
import { useCallback, useMemo } from 'react';
import { getServerSession } from 'next-auth';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import { getCluster, getClusterNode } from '@/services/server';
import { getPageTranslations } from '@/utils/i18n';
import {
  displayFixedNumber,
  displayHumanReadableBytes,
  DOCS_RESOURCE_MANAGER_BASE,
  getCurrentTimeRange,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import { authOptions } from '@amdenterpriseai/utils/server';

import { useAccessControl } from '@/hooks/useAccessControl';
import { getNodeDisplayStatus } from '@/utils/node-status';
import { getNodeStatusVariants } from '@/utils/node-status-variants';

import { ClusterNode } from '@/types/clusters';

import {
  NodeDeviceMetricsSection,
  NodeGpuDevicesTable,
  NodeWorkloadsTable,
} from '@/components/features/clusters';

interface Props {
  node: ClusterNode;
  pageBreadcrumb?: { title: string; href?: string }[];
}

const translationKeySet = ['clusters', 'common', 'workloads'] as const;

const NodeDetailPage: React.FC<Props> & WithDocumentationLink = ({ node }) => {
  const { t } = useTranslation(translationKeySet);
  const router = useRouter();
  const { isAdministrator } = useAccessControl();
  const { id: clusterId, nodeId } = router.query;

  const nodeStatusVariants = useMemo(
    () => getNodeStatusVariants(t as (key: string) => string),
    [t],
  );

  const nodeSpecCards = useMemo((): StatisticsCardProps[] => {
    if (!node) return [];
    const tNodes = t as (key: string) => string;
    return [
      {
        title: tNodes('clusters:nodes.detail.specs.gpuType.title'),
        tooltip: tNodes('clusters:nodes.detail.specs.gpuType.tooltip'),
        statistic: 0,
        statisticFormatter: () => node.gpuInfo?.name ?? '-',
        valueClassName: 'text-lg font-extrabold truncate',
      },
      {
        title: tNodes('clusters:nodes.detail.specs.gpuMemory.title'),
        tooltip: tNodes('clusters:nodes.detail.specs.gpuMemory.tooltip'),
        statistic: node.gpuInfo
          ? node.gpuCount * node.gpuInfo.memoryBytesPerDevice
          : 0,
        statisticFormatter: (v) => (v ? displayHumanReadableBytes(v) : '-'),
      },
      {
        title: tNodes('clusters:nodes.detail.specs.cpuCores.title'),
        tooltip: tNodes('clusters:nodes.detail.specs.cpuCores.tooltip'),
        statistic: node.cpuMilliCores / 1000,
        statisticFormatter: (v) => displayFixedNumber(v),
      },
      {
        title: tNodes('clusters:nodes.detail.specs.systemMemory.title'),
        tooltip: tNodes('clusters:nodes.detail.specs.systemMemory.tooltip'),
        statistic: node.memoryBytes,
        statisticFormatter: (v) => displayHumanReadableBytes(v),
      },
    ];
  }, [node, t]);

  const handleBack = useCallback(() => {
    router.push(`/clusters/${clusterId}`);
  }, [router, clusterId]);

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 min-w-0">
          <ActionButton
            secondary
            size="sm"
            onPress={handleBack}
            icon={<IconArrowLeft size={16} />}
            aria-label={t('common:actions.back.title')}
          />
          <span className="text-base font-medium truncate">
            {node?.name} node
          </span>
          {node ? (
            <span
              aria-label={t(
                `clusters:nodes.detail.status.${getNodeDisplayStatus(node.status)}`,
              )}
            >
              <StatusDisplay
                type={getNodeDisplayStatus(node.status)}
                variants={nodeStatusVariants}
              />
            </span>
          ) : null}
        </div>
      </div>

      {nodeSpecCards.length > 0 && (
        <section className="flex flex-col gap-4">
          <HorizontalStatisticsCards cards={nodeSpecCards} />
        </section>
      )}

      <NodeDeviceMetricsSection
        clusterId={clusterId as string}
        nodeId={nodeId as string}
      />

      <section className="flex flex-col gap-4">
        <h3 className="text-base font-medium">
          {t('clusters:nodes.detail.gpuDevices.title')}
        </h3>
        <NodeGpuDevicesTable
          clusterId={clusterId as string}
          nodeId={nodeId as string}
        />
      </section>

      {isAdministrator && (
        <section className="flex flex-col gap-4">
          <h3 className="text-base font-medium">
            {t('clusters:nodes.detail.workloads.title')}
          </h3>
          <NodeWorkloadsTable
            clusterId={clusterId as string}
            nodeId={nodeId as string}
            nodeName={node?.name ?? ''}
          />
        </section>
      )}
    </div>
  );
};

NodeDetailPage.documentationLink = `${DOCS_RESOURCE_MANAGER_BASE}/clusters/node-metrics.html`;

export default NodeDetailPage;

export async function getServerSideProps(context: any) {
  const locale = context.locale ?? 'en';
  const session = await getServerSession(context.req, context.res, authOptions);

  try {
    const clusterId = context.params.id;
    const nodeId = context.params.nodeId;
    const accessToken = session?.accessToken as string;

    const [node, cluster] = await Promise.all([
      getClusterNode(clusterId, nodeId, accessToken),
      getCluster(clusterId, accessToken),
    ]);

    const translations = await getPageTranslations(locale, [
      'clusters',
      'workloads',
    ]);

    const clustersTitle =
      (
        translations._nextI18Next?.initialI18nStore?.[locale]?.clusters as {
          title?: string;
        }
      )?.title ?? 'Clusters';

    const breadcrumb = [
      { title: clustersTitle, href: '/clusters' },
      { title: cluster.name, href: `/clusters/${clusterId}` },
      { title: node.name },
    ];

    return {
      props: {
        ...translations,
        node,
        pageBreadcrumb: breadcrumb,
      },
    };
  } catch (error) {
    console.error('Node not found:', error);
    const clusterId = context.params?.id;
    return {
      redirect: {
        destination: clusterId ? `/clusters/${clusterId}` : '/',
        permanent: false,
      },
    };
  }
}
