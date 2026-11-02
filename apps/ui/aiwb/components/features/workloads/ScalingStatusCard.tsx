// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * Displays the current scaling status of a deployed AIMService.
 * When autoscaling is disabled (minReplicas === maxReplicas === 1),
 * this card should be hidden and "Autoscaling Disabled" shown in Resources card.
 */

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
  StatusDisplay,
} from '@amdenterpriseai/components';
import {
  IconArrowsMaximize,
  IconChevronDown,
  IconCircleCaretRight,
  IconQuestionMark,
  IconSettings,
} from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'next-i18next';
import { AutoscalingPolicyConfig } from '@/types/aims';
import { SCALING_METRIC_KEYS } from '@/lib/app/aims';
import type { AutoscalingFieldValues } from '@/lib/app/aims';
import type { components } from '@/types/api';
import {
  Intent,
  StatusBadgeVariant,
  TableColumns,
} from '@amdenterpriseai/types';
import { DeploymentSettingsDrawer } from './DeploymentSettingsDrawer';

type AIMServiceSpec = components['schemas']['AIMServiceSpec'];
type AIMServiceRuntime = components['schemas']['AIMServiceRuntime'];

// Flat display type for the replicas table, derived from the nested replica response
type ReplicaRow = {
  name: string;
  gpuCount?: string;
  createdAt?: string | null;
  status?: string | null;
};

type ReplicaColumnKey = 'name' | 'gpuCount' | 'createdAt' | 'status';

const replicaColumns: TableColumns<ReplicaColumnKey> = [
  { key: 'name', sortable: false },
  { key: 'gpuCount', sortable: true },
  { key: 'createdAt', sortable: true },
  { key: 'status', sortable: true },
];

const getPodPhaseVariants = (
  t: (key: string) => string,
): Record<string, StatusBadgeVariant> => ({
  Running: {
    label: t('podPhase.running'),
    color: 'primary',
    icon: IconCircleCaretRight,
  },
  Pending: { label: t('podPhase.pending'), intent: Intent.PENDING },
  Succeeded: { label: t('podPhase.succeeded'), intent: Intent.SUCCESS },
  Failed: { label: t('podPhase.failed'), intent: Intent.DANGER },
  Unknown: {
    label: t('podPhase.unknown'),
    icon: IconQuestionMark,
    color: 'danger',
  },
});

function toReplicaRow(
  replica: components['schemas']['InferenceReplicaResponse'],
): ReplicaRow {
  const gpuRaw =
    replica.spec?.containers?.[0]?.resources?.limits?.['amd.com/gpu'];
  return {
    name: replica.metadata.name,
    gpuCount: gpuRaw,
    createdAt: replica.metadata.creationTimestamp ?? undefined,
    status: replica.status?.phase ?? undefined,
  };
}

interface Props {
  /** The AIMService spec containing scaling configuration */
  spec: AIMServiceSpec;
  /** Runtime scaling status from the CRD status.runtime */
  runtime?: AIMServiceRuntime;
  /** Namespace (project) where the workload is deployed */
  namespace?: string;
  /** Workload ID for the settings drawer */
  id?: string;
  /** Called after autoscaling settings are saved successfully with all saved form values */
  onSettingsSaved?: (savedValues: AutoscalingFieldValues) => void;
  /** Pod-level replica info for the running service */
  replicas?: components['schemas']['InferenceReplicaResponse'][];
}

export const ScalingStatusCard = ({
  spec,
  runtime,
  namespace,
  id,
  onSettingsSaved,
  replicas,
}: Props) => {
  const { t } = useTranslation('autoscaling');
  const podPhaseVariants = useMemo(() => getPodPhaseVariants(t), [t]);
  const replicaCustomRenderers = useMemo(
    () => ({
      status: (item: ReplicaRow) => (
        <StatusDisplay
          type={item.status ?? 'Unknown'}
          variants={podPhaseVariants}
        />
      ),
      gpuCount: (item: ReplicaRow) => item.gpuCount ?? <NoDataDisplay />,
      createdAt: (item: ReplicaRow) =>
        item.createdAt ? (
          <DateDisplay date={item.createdAt} />
        ) : (
          <NoDataDisplay />
        ),
    }),
    [podPhaseVariants],
  );
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isReplicasOpen, setIsReplicasOpen] = useState(false);
  // Increment on every open to remount DeploymentSettingsDrawer, forcing ManagedForm
  // to re-initialize useForm with the latest drawerInitialValues (react-hook-form only
  // reads defaultValues once at mount time, so remounting is required to pick up
  // updated spec data that arrives asynchronously after initial render).
  const [drawerKey, setDrawerKey] = useState(0);

  // Extract scaling info from spec
  // Backend models `autoScaling` as a loose map; read it via the FE-known shape.
  const autoScaling = spec.autoScaling as AutoscalingPolicyConfig | undefined;
  const firstMetric = autoScaling?.metrics?.[0]?.podmetric;
  const metricQuery = firstMetric?.metric?.query || '';

  // Get translated label for metric query
  const metric = SCALING_METRIC_KEYS.find((m) => m.key === metricQuery);
  const metricLabel = metric
    ? t(`scalingMetric.options.${metric.translationKey}`)
    : metricQuery;

  const operationOverTime = firstMetric?.metric?.operationOverTime || 'avg';
  const targetValue = firstMetric?.target?.value
    ? parseInt(firstMetric.target.value, 10)
    : 0;
  const targetType = firstMetric?.target?.type || 'Value';

  // Drawer initial values
  const drawerInitialValues = {
    minReplicas: spec.minReplicas ?? 1,
    maxReplicas: spec.maxReplicas ?? 3,
    metricQuery,
    operationOverTime,
    targetType,
    targetValue,
  };

  return (
    <>
      <Card
        data-testid="scaling-status-card"
        className="break-inside-avoid mb-6"
      >
        <CardHeader className="flex flex-row items-center justify-between">
          <h4 className="flex items-center gap-2 font-semibold">
            <IconArrowsMaximize size={16} className="text-muted" />
            {t('title')}
          </h4>
          <Button
            data-testid="scaling-settings-button"
            size="sm"
            variant="light"
            startContent={<IconSettings size={14} />}
            onPress={() => {
              setDrawerKey((k) => k + 1);
              setIsDrawerOpen(true);
            }}
          >
            {t('actions.settings')}
          </Button>
        </CardHeader>

        <CardBody className="space-y-3">
          {/* Current Replicas Display: current / desired Replicas (min) */}
          {runtime?.currentReplicas != null && (
            <>
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-bold text-foreground">
                  {runtime.currentReplicas}
                </span>
                <span className="text-base text-muted">
                  / {runtime.maxReplicas ?? '–'}
                </span>
              </div>
              <div className="flex items-baseline gap-1">
                <span className="text-base text-muted ml-0">
                  {t('replicasMinimum', { count: spec.minReplicas ?? 1 })}
                </span>
              </div>
            </>
          )}

          {/* Scaling Metric and Target - grouped together, capped at ~30% width, chevron far right */}
          <div className="flex items-center justify-between">
            <div className="flex gap-6 max-w-[30%]">
              <div>
                <div className="text-sm text-muted">
                  {t('scalingMetric.label')}
                </div>
                <div className="text-sm font-medium text-foreground truncate">
                  {metricLabel}
                </div>
              </div>
              <div>
                <div className="text-sm text-muted">
                  {t('targetValue.label')}
                </div>
                <div className="text-sm font-medium text-foreground">
                  {targetValue} ({operationOverTime})
                </div>
              </div>
            </div>
            {replicas && (
              <Button
                isIconOnly
                variant="light"
                size="sm"
                className="text-muted"
                aria-label={t('replicas.toggle')}
                aria-expanded={isReplicasOpen}
                onPress={() => setIsReplicasOpen((v) => !v)}
              >
                <IconChevronDown
                  size={32}
                  className={`transition-transform duration-200 ${isReplicasOpen ? 'rotate-180' : ''}`}
                />
              </Button>
            )}
          </div>

          {/* Replicas table - expanded by chevron with slide animation */}
          {replicas && (
            <div
              className={`grid transition-[grid-template-rows] duration-300 ease-out ${
                isReplicasOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
              }`}
            >
              <div className="overflow-hidden">
                <div className="border-t border-default pt-3">
                  <ClientSideDataTable
                    data={replicas.map(toReplicaRow)}
                    columns={replicaColumns}
                    customRenderers={replicaCustomRenderers}
                    defaultSortByField="createdAt"
                    translation={t}
                    idKey="name"
                    translationKeyPrefix="replicas"
                  />
                </div>
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Autoscaling Settings Drawer */}
      <DeploymentSettingsDrawer
        key={drawerKey}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        onSuccess={onSettingsSaved}
        namespace={namespace}
        id={id}
        initialValues={drawerInitialValues}
      />
    </>
  );
};

export default ScalingStatusCard;
