// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  ActionButton,
  ActionsDropdown,
  ButtonGroup,
  Card,
  CardFooter,
  CardHeader,
  Divider,
  DropdownActionItem,
  Status,
} from '@amdenterpriseai/components';
import {
  IconChevronDown,
  IconExternalLink,
  IconTrash,
} from '@tabler/icons-react';

import { TruncatedTagsRow } from '@/components/shared/TruncatedTagsRow';

import { useTranslation } from 'next-i18next';

import { WorkspaceCatalogTableItem } from '@/types/workspaces';
import { ActionItem, Color, Intent } from '@amdenterpriseai/types';

function getPrimaryWorkloadId(
  workloads: WorkspaceCatalogTableItem['workloads'],
): string | undefined {
  if (!workloads?.length) return undefined;
  for (const status of ['Running', 'Failed', 'Pending']) {
    const workload = workloads.find((item) => item.status === status);
    if (workload) return workload.id;
  }
  return workloads[0]?.id;
}

interface Props {
  isDeployed?: boolean;
  isPending?: boolean;
  isFailed?: boolean;
  item: WorkspaceCatalogTableItem;
  primaryAction?: ActionItem<any>;
  secondaryAction?: ActionItem<any>;
  secondaryActionColor?: Color;
  readyAction?: ActionItem<any>;
  iconComponent?: React.ReactNode;
  minHeaderHeight?: string;
  iconTopGap?: boolean;
  onOpenWorkloadDetails?: (workloadId: string) => void;
}

export const CatalogItemCard = ({
  isDeployed,
  isPending,
  isFailed,
  item,
  primaryAction,
  secondaryAction,
  secondaryActionColor,
  readyAction,
  iconComponent,
  minHeaderHeight,
  iconTopGap,
  onOpenWorkloadDetails,
}: Props) => {
  const { t } = useTranslation('catalog');
  const isDeploying =
    isPending &&
    !isFailed &&
    !isDeployed &&
    item.workloads?.some((w) => w.status === 'Pending');
  const isFailedMain = isFailed && !!secondaryAction;
  const failedActionColor = secondaryActionColor ?? 'danger';
  const detailsWorkloadId = getPrimaryWorkloadId(item.workloads);
  const overflowActions: DropdownActionItem[] = [];
  if (onOpenWorkloadDetails && detailsWorkloadId) {
    overflowActions.push({
      key: 'details',
      label: t('list.actions.details'),
      onPress: () => onOpenWorkloadDetails(detailsWorkloadId),
    });
  }
  if (!isFailedMain && secondaryAction) {
    overflowActions.push({
      key: secondaryAction.key,
      label: secondaryAction.label,
      color: secondaryActionColor,
      isDisabled: !item.available,
      onPress: () => secondaryAction.onPress(item),
    });
  }
  const mainButton = isDeploying ? (
    <ActionButton primary size="sm" color="secondary" isDisabled>
      {t('list.actions.launch')}
    </ActionButton>
  ) : isFailedMain ? (
    <ActionButton
      primary
      size="sm"
      color={failedActionColor}
      onPress={() => secondaryAction!.onPress(item)}
      isDisabled={!item.available}
      startContent={<IconTrash size={16} />}
    >
      {secondaryAction!.label}
    </ActionButton>
  ) : !isPending && isDeployed && readyAction ? (
    <ActionButton
      primary
      size="sm"
      color="secondary"
      onPress={() => readyAction.onPress(item)}
    >
      {readyAction.label}
    </ActionButton>
  ) : primaryAction ? (
    <ActionButton
      primary
      size="sm"
      onPress={() => primaryAction.onPress(item)}
      isDisabled={!item.available}
    >
      {primaryAction.label}
    </ActionButton>
  ) : null;

  return (
    <Card
      className="w-full min-w-0 p-0 grid grid-cols-1 grid-rows-[1fr_auto_auto] gap-0"
      data-testid="workspace-card"
      key={item.id}
    >
      <CardHeader>
        <div
          className="p-5 flex flex-col gap-2"
          style={{ minHeight: minHeaderHeight }} // style override as tailwind does not work with dynamic min-h-* classes
        >
          <div className="flex flex-row gap-2 items-start w-full">
            <div className={iconTopGap ? 'mt-1' : ''}>{iconComponent}</div>
            <div className="ml-auto flex flex-row gap-1 items-start">
              {isDeploying && (
                <Status
                  label={t('status.Deploying')}
                  intent={Intent.PENDING}
                  size="sm"
                  isTextColored
                />
              )}
              {isFailed && (
                <Status
                  label={t('status.Failed')}
                  intent={Intent.DANGER}
                  size="sm"
                  isTextColored
                />
              )}
            </div>
          </div>
          <div className="flex items-start flex-col flex-1 min-w-0 gap-2">
            <span className="text-md font-semibold">
              {item.displayName ?? item.name}
            </span>
            <div className="text-sm flex flex-col gap-1">
              <p className="min-w-0">{item.description}</p>
              {item.externalUrl && (
                <span className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => window.open(item.externalUrl!, '_blank')}
                    className="text-accent inline-flex items-center gap-1 hover:underline focus:outline-none focus:underline"
                  >
                    <span>{t('card.moreInformation')}</span>
                    <IconExternalLink size={14} />
                  </button>
                </span>
              )}
            </div>
          </div>
        </div>
      </CardHeader>
      <Divider />
      <CardFooter className="flex flex-col">
        <div className="flex p-5 pt-3 flex-row justify-between items-center w-full gap-2">
          <div className="min-w-0 overflow-hidden">
            <TruncatedTagsRow
              tags={item.tags ?? []}
              formatMoreCount={(count) => t('card.tagsMoreCount', { count })}
            />
          </div>
          <ButtonGroup>
            {mainButton}
            <ActionsDropdown
              actions={overflowActions}
              isDisabled={overflowActions.length === 0}
            >
              <ActionButton
                primary
                size="sm"
                color={isFailedMain ? failedActionColor : undefined}
                aria-label={t('card.actionsMenu')}
                isDisabled={overflowActions.length === 0}
                icon={<IconChevronDown size={16} />}
              />
            </ActionsDropdown>
          </ButtonGroup>
        </div>
      </CardFooter>
    </Card>
  );
};

CatalogItemCard.displayName = 'CatalogItemCard';
