// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useCallback, useId, useMemo, useState } from 'react';
import {
  ActionButton,
  ActionsDropdown,
  Alert,
  Button,
  ButtonGroup,
  Card,
  CardFooter,
  CardHeader,
  Divider,
  DropdownActionItem,
  Link,
  Status,
  Tooltip,
  cn,
} from '@amdenterpriseai/components';
import { useElementOverflow } from '@amdenterpriseai/hooks';

import { useTranslation } from 'next-i18next';
import { ModelIcon } from '@/components/shared/ModelIcons';
import { TruncatedTagsRow } from '@/components/shared/TruncatedTagsRow';
import {
  IconAlertTriangle,
  IconCheck,
  IconChevronDown,
  IconLock,
} from '@tabler/icons-react';
import { AggregatedAIM } from '@/types/aims';
import { Intent } from '@amdenterpriseai/types';
import {
  AIMService,
  AIMServiceStatus,
  AIMWorkloadStatus,
  ParsedAIM,
} from '@/types/aims';
import { getMetricTranslationKey, getModelCapability } from '@/lib/app/aims';

const DESCRIPTION_CLAMPED_LINES = 3;

interface Props {
  aggregatedAim: AggregatedAIM;
  onDeploy: () => void;
  onOpenDetails: (serviceId: string) => void;
  onChatWithModel: (serviceId: string) => void;
  onConnectToModel: (aim: ParsedAIM) => void;
  onUndeploy: (
    namespace: string,
    serviceId: string,
    displayName: string,
  ) => void;
}

export const AIMCard = ({
  aggregatedAim,
  onDeploy,
  onOpenDetails,
  onChatWithModel,
  onConnectToModel,
  onUndeploy,
}: Props) => {
  const tags = aggregatedAim.aggregated.tags ?? [];
  const description = aggregatedAim.aggregated.description.short;
  const { t } = useTranslation(['models']);
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);
  const descriptionId = useId();

  const measureDescriptionOverflow = useCallback(
    (element: HTMLParagraphElement) => {
      if (!description) return false;
      if (!isDescriptionExpanded) {
        return element.scrollHeight > element.clientHeight;
      }

      // When expanded, the clamp class is removed, so clientHeight no longer
      // reflects the clamped size. Estimate the clamped height from the
      // computed line-height instead of toggling the class, which would
      // mutate the element being observed and can trigger a ResizeObserver
      // feedback loop.
      const parsedLineHeight = Number.parseFloat(
        getComputedStyle(element).lineHeight,
      );
      if (Number.isNaN(parsedLineHeight)) {
        return element.scrollHeight > element.clientHeight;
      }
      return (
        element.scrollHeight > parsedLineHeight * DESCRIPTION_CLAMPED_LINES
      );
    },
    [description, isDescriptionExpanded],
  );
  const { elementRef: descriptionRef, isOverflowing: isDescriptionLong } =
    useElementOverflow(measureDescriptionOverflow);

  const allDeployments = useMemo(() => {
    const deployments: Array<{
      service: AIMService;
      imageVersion: string;
      parsedAim: ParsedAIM;
    }> = [];

    aggregatedAim.parsedAIMs.forEach((version) => {
      version.deployedServices?.forEach((service) => {
        // Only include services with a valid id
        if (service.id) {
          deployments.push({
            service,
            imageVersion: version.imageVersion,
            parsedAim: version,
          });
        }
      });
    });

    return deployments;
  }, [aggregatedAim.parsedAIMs]);

  const getDeploymentStatusIntent = (
    status: AIMServiceStatus | undefined,
  ): Intent => {
    if (status === 'Running') {
      return Intent.SUCCESS;
    }
    if (status === 'Pending' || status === 'Starting') {
      return Intent.PENDING;
    }
    return Intent.WARNING;
  };

  const cardActions = useMemo(() => {
    const actions: DropdownActionItem[] = [];

    if (allDeployments.length > 0) {
      const deploymentActions: DropdownActionItem[] = [];

      allDeployments.forEach(({ service, imageVersion, parsedAim }) => {
        const serviceId = service.id as string;
        const rawMetric = service.spec?.profile?.selector?.metric;
        const metricLabel = t(
          getMetricTranslationKey(
            typeof rawMetric === 'string' ? rawMetric : null,
          ),
        );
        const deploymentInfo = [imageVersion, metricLabel]
          .filter(Boolean)
          .join(' • ');

        const isRunning = service.status?.status === 'Running';

        // Create nested actions for each deployment
        const nestedActions: DropdownActionItem[] = [
          {
            key: `open-details-${serviceId}`,
            label: t('aimCatalog.actions.workloadDetails.label'),
            onPress: () => onOpenDetails(serviceId),
          },
        ];

        if (isRunning) {
          // Speech-to-text deployments have no chat surface, so don't offer the
          // chat-playground action for them.
          if (getModelCapability(parsedAim.tags) !== 'transcription') {
            nestedActions.push({
              key: `chat-${serviceId}`,
              label: t('aimCatalog.actions.chatWithModel.label'),
              onPress: () => onChatWithModel(serviceId),
            });
          }
          nestedActions.push({
            key: `connect-${serviceId}`,
            label: t('aimCatalog.actions.connect.label'),
            onPress: () =>
              onConnectToModel({
                ...parsedAim,
                deployedService: service,
                deployedServices: [service],
              }),
          });
        }

        const serviceNamespace = service.metadata.namespace;
        nestedActions.push({
          key: `undeploy-${serviceId}`,
          label: t('aimCatalog.actions.undeploy.label'),
          color: 'danger',
          // Undeploy targets a namespaced URL; without a namespace the request
          // would be malformed, so disable the action rather than send an empty one.
          isDisabled: !serviceNamespace,
          onPress: () =>
            onUndeploy(serviceNamespace!, serviceId, service.metadata.name),
        });

        // Add deployment as parent item with nested actions
        deploymentActions.push({
          key: `deployment-${serviceId}`,
          label: service.metadata.name,
          description: deploymentInfo,
          onPress: () => {},
          actions: nestedActions,
          startContent: (
            <Status
              intent={getDeploymentStatusIntent(service.status?.status)}
              size="md"
            />
          ),
        });
      });

      actions.push({
        key: 'deployments',
        label: t('aimCatalog.card.deploymentsCount', {
          count: allDeployments.length,
        }),
        onPress: () => {},
        actions: deploymentActions,
        isSection: true,
      });
    }

    return actions;
  }, [
    aggregatedAim.parsedAIMs,
    onDeploy,
    allDeployments,
    onOpenDetails,
    onChatWithModel,
    onConnectToModel,
    onUndeploy,
    t,
  ]);

  const acceleratorLabel = useMemo(
    () =>
      (aggregatedAim.aggregated.acceleratorTypes ?? [])
        .map((type) => ({ cpu: 'CPU', gpu: 'GPU' })[type])
        .filter(Boolean)
        .join(', '),
    [aggregatedAim.aggregated.acceleratorTypes],
  );

  const isSupported = aggregatedAim.isSupported;
  const hasPending =
    aggregatedAim.deploymentCounts[AIMWorkloadStatus.PENDING] > 0;
  const hasStarting =
    aggregatedAim.deploymentCounts[AIMWorkloadStatus.STARTING] > 0;
  const hasDeployedInstances =
    aggregatedAim.deploymentCounts[AIMWorkloadStatus.DEPLOYED] > 0;
  const hasActiveDeployments =
    hasDeployedInstances ||
    aggregatedAim.deploymentCounts[AIMWorkloadStatus.DEGRADED] > 0;

  return (
    <Card className={`p-0 grid grid-cols-1 grid-rows-[1fr_auto_auto] gap-0`}>
      <CardHeader>
        {!isSupported && (
          <Alert
            data-testid="unsupported-banner"
            status="danger"
            icon={<IconAlertTriangle />}
            className="w-full rounded-b-none px-2 py-1 gap-2 shadow-none"
            description={
              <span className="text-xs">
                {t('aimCatalog.unsupported.message')}{' '}
                <Link
                  href={t('aimCatalog.unsupported.linkUrl', {
                    canonicalName: aggregatedAim.aggregated.canonicalName,
                  })}
                  isExternal
                  showAnchorIcon={false}
                  className="text-inherit text-xs font-bold hover:opacity-60"
                >
                  {t('aimCatalog.unsupported.linkText')}
                </Link>
                .
              </span>
            }
          />
        )}

        <div
          className={cn(
            'p-5 flex flex-col gap-2',
            !isSupported ? 'opacity-50' : '',
          )}
        >
          <div className="flex items-start flex-col gap-1 w-full">
            <div className="flex flex-row gap-2 items-start w-full">
              <div className="mb-1">
                <ModelIcon
                  iconName={aggregatedAim.aggregated.canonicalName}
                  width={48}
                  height={48}
                />
              </div>
              <div className="ml-auto flex flex-row gap-1 items-start">
                {hasPending && (
                  <Status
                    label={t('models:status.pending')}
                    intent={Intent.PENDING}
                    size="sm"
                    isTextColored
                  />
                )}
                {hasStarting && (
                  <Status
                    label={t('models:status.starting')}
                    intent={Intent.PENDING}
                    size="sm"
                    isTextColored
                  />
                )}
                {hasActiveDeployments && (
                  <Tooltip content={t('aimCatalog.card.hasDeploymentsTooltip')}>
                    {/* biome-ignore lint/a11y/useSemanticElements: the element describes status rather than performing an action. */}
                    <span
                      data-testid="aim-card-has-deployments"
                      role="button"
                      tabIndex={0}
                    >
                      <Status
                        label={t('aimCatalog.card.hasDeployments')}
                        intent={
                          hasDeployedInstances ? Intent.SUCCESS : Intent.WARNING
                        }
                        icon={IconCheck}
                        size="sm"
                        isTextColored
                      />
                    </span>
                  </Tooltip>
                )}
              </div>
            </div>
            <div className="text-md font-semibold leading-tight w-full">
              {aggregatedAim.aggregated.title}
            </div>
            <div className="flex flex-row gap-1 text-sm text-foreground/60">
              <span>{aggregatedAim.aggregated.aiLabName}</span>
              <span>&bull;</span>
              <span>
                {t('aimCatalog.card.versionCount', {
                  count: aggregatedAim.parsedAIMs.length,
                })}
              </span>
              {acceleratorLabel && (
                <>
                  <span>&bull;</span>
                  <span data-testid="aim-card-accelerator-types">
                    {acceleratorLabel}
                  </span>
                </>
              )}
              {aggregatedAim.aggregated.isHfTokenRequired && (
                <>
                  <span>&bull;</span>
                  <Tooltip
                    content={t('aimCatalog.tooltips.hfTokenRequired')}
                    delay={300}
                  >
                    {/* biome-ignore lint/a11y/useSemanticElements: the element reveals supplemental text rather than performing an action. */}
                    <span
                      className="cursor-help underline decoration-dotted flex items-center gap-0.5"
                      role="button"
                      tabIndex={0}
                    >
                      <IconLock size={12} />
                      {t('aimCatalog.card.gated')}
                    </span>
                  </Tooltip>
                </>
              )}
            </div>
            <p
              ref={descriptionRef}
              id={descriptionId}
              className={`text-sm ${isDescriptionExpanded ? '' : 'line-clamp-3'}`}
            >
              {description}
            </p>
            {isDescriptionLong && (
              <Button
                variant="ghost"
                size="sm"
                onPress={() =>
                  setIsDescriptionExpanded((expanded) => !expanded)
                }
                aria-expanded={isDescriptionExpanded}
                aria-controls={descriptionId}
                endContent={
                  <IconChevronDown
                    size={14}
                    className={cn(
                      'transition-transform duration-200',
                      isDescriptionExpanded ? 'rotate-180' : '',
                    )}
                  />
                }
                className="self-start -ml-2 mt-1 h-auto min-h-0 px-2 text-xs"
              >
                {isDescriptionExpanded
                  ? t('aimCatalog.card.showLess')
                  : t('aimCatalog.card.showMore')}
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <Divider />
      <CardFooter className="flex flex-col">
        <div className="flex p-5 pt-3 flex-row justify-between items-center w-full">
          <TruncatedTagsRow
            tags={tags}
            formatMoreCount={(count) =>
              t('aimCatalog.card.tagsMoreCount', { count })
            }
            className={!isSupported ? 'opacity-50' : ''}
          />

          {isSupported && (
            <ButtonGroup>
              <ActionButton
                primary
                color="primary"
                size="sm"
                onPress={() => onDeploy()}
              >
                {t('aimCatalog.actions.deploy.label')}
              </ActionButton>
              {allDeployments.length > 0 ? (
                <ActionsDropdown actions={cardActions}>
                  <ActionButton
                    primary
                    color="primary"
                    size="sm"
                    aria-label={t('aimCatalog.card.actionsMenu')}
                    isDisabled={
                      !hasPending && !hasStarting && !hasActiveDeployments
                    }
                    icon={<IconChevronDown size={16} />}
                  />
                </ActionsDropdown>
              ) : (
                <ActionButton
                  primary
                  color="primary"
                  size="sm"
                  aria-label={t('aimCatalog.card.actionsMenu')}
                  isDisabled
                  icon={<IconChevronDown size={16} />}
                />
              )}
            </ButtonGroup>
          )}
        </div>
      </CardFooter>
    </Card>
  );
};

AIMCard.displayName = 'AIMCard';
