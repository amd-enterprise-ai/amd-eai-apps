// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionButton,
  ActionsDropdown,
  Card,
  CardFooter,
  CardHeader,
  Divider,
  DropdownActionItem,
  Status,
  Tooltip,
} from '@amdenterpriseai/components';
import { IconDotsVertical, IconLock } from '@tabler/icons-react';
import { useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { Intent } from '@amdenterpriseai/types';

import { TruncatedTagsRow } from '@/components/shared/TruncatedTagsRow';
import { ModelProfileSummary } from '@/components/shared/ModelProfileSummary';
import { profileSummaryFields } from '@/lib/app/custom-profiles';

import { AggregatedAIM, OnboardPhase } from '@/types/aims';

interface CustomModelCardActionHandlers {
  onModelSettings: (aggregatedAim: AggregatedAIM) => void;
  onProfiles: (aggregatedAim: AggregatedAIM) => void;
  onDelete: (aggregatedAim: AggregatedAIM) => void;
  onDeploy: (aggregatedAim: AggregatedAIM) => void;
}

interface Props extends CustomModelCardActionHandlers {
  aggregatedAim: AggregatedAIM;
}

const CardStatusKind = {
  IMPORTING: 'importing',
  ONBOARDING: 'onboarding',
  FAILED: 'failed',
} as const;
type CardStatusKind = (typeof CardStatusKind)[keyof typeof CardStatusKind];

/**
 * Status pill rendered in the card header, driven directly by the composed
 * onboard phase so it always agrees with the Deploy button:
 * - No pill when the model is `Ready` (the only deployable state).
 * - "Failed" when onboarding failed, including legacy import-state failures.
 * - "Importing" when backend reports a transitional import phase (legacy
 *   records or fallback status composition).
 * - "Onboarding" for `Pending` (and any model without a composed phase) —
 *   still being prepared or awaiting engine reconciliation.
 */
const resolveCardStatus = (
  aggregatedAim: AggregatedAIM,
): CardStatusKind | null => {
  switch (aggregatedAim.aggregated.onboardPhase) {
    case OnboardPhase.READY:
      return null;
    case OnboardPhase.FAILED:
      return CardStatusKind.FAILED;
    case OnboardPhase.IMPORTING:
      return CardStatusKind.IMPORTING;
    default:
      return CardStatusKind.ONBOARDING;
  }
};

export const CustomModelCard = ({
  aggregatedAim,
  onDeploy,
  onModelSettings,
  onProfiles,
  onDelete,
}: Props) => {
  const { t } = useTranslation('models');
  const tags = aggregatedAim.aggregated.tags ?? [];
  const isHfTokenRequired = aggregatedAim.aggregated.isHfTokenRequired;
  const profileCount = aggregatedAim.aggregated.profileCount;
  const defaultProfile = aggregatedAim.aggregated.defaultProfile;
  // profileSummaryFields returns an all-null object when the Default has no
  // effective profile spec yet; that object is truthy, so render the summary
  // only when at least one field has a value. Otherwise the wrapper would be an
  // empty container with a misleading testid while ModelProfileSummary renders
  // nothing.
  const defaultProfileSummary = defaultProfile
    ? profileSummaryFields(defaultProfile)
    : null;
  const hasDefaultProfileSummary =
    defaultProfileSummary != null &&
    Object.values(defaultProfileSummary).some((value) => value != null);

  const cardStatusKind = useMemo(
    () => resolveCardStatus(aggregatedAim),
    [aggregatedAim],
  );

  const cardStatus = useMemo(() => {
    if (cardStatusKind === CardStatusKind.FAILED) {
      return {
        intent: Intent.DANGER,
        label: t('customModels.card.status.failed'),
      };
    }
    if (cardStatusKind === CardStatusKind.IMPORTING) {
      return {
        intent: Intent.PENDING,
        label: t('customModels.card.status.importing'),
      };
    }
    if (cardStatusKind === CardStatusKind.ONBOARDING) {
      return {
        intent: Intent.PENDING,
        label: t('customModels.card.status.onboarding'),
      };
    }
    return null;
  }, [cardStatusKind, t]);

  const isDeployable =
    aggregatedAim.aggregated.onboardPhase === OnboardPhase.READY;

  const cardActions = useMemo<DropdownActionItem[]>(
    () => [
      {
        key: 'settings',
        label: t('customModels.card.actions.settings.label'),
        onPress: () => onModelSettings(aggregatedAim),
      },
      {
        key: 'profiles',
        label: t('customModels.card.actions.profiles.label'),
        onPress: () => onProfiles(aggregatedAim),
      },
      {
        key: 'delete',
        label: t('customModels.card.actions.delete.label'),
        color: 'danger',
        onPress: () => onDelete(aggregatedAim),
      },
    ],
    [aggregatedAim, onDelete, onModelSettings, onProfiles, t],
  );

  return (
    <Card
      data-testid="custom-model-card"
      className="p-0 grid grid-cols-1 grid-rows-[1fr_auto_auto] gap-0"
    >
      <CardHeader>
        <div className="p-5 flex flex-col gap-2">
          <div className="flex items-start flex-col gap-1 w-full">
            <div className="flex flex-row items-start justify-between w-full gap-2">
              <div className="text-md font-semibold leading-tight">
                {aggregatedAim.aggregated.title}
              </div>
              {cardStatus && (
                <Status
                  label={cardStatus.label}
                  intent={cardStatus.intent}
                  size="sm"
                  isTextColored
                />
              )}
            </div>
            <div className="flex flex-row gap-1 text-sm text-foreground/60">
              <span>{aggregatedAim.aggregated.aiLabName}</span>
              <span>&bull;</span>
              <span>
                {t('aimCatalog.card.versionCount', {
                  count: aggregatedAim.parsedAIMs.length,
                })}
              </span>
              {profileCount != null && (
                <>
                  <span>&bull;</span>
                  <span data-testid="custom-model-card-profile-count">
                    {t('customModels.card.profileCount', {
                      count: profileCount,
                    })}
                  </span>
                </>
              )}
              {isHfTokenRequired && (
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
            <p className="text-sm line-clamp-3">
              {aggregatedAim.aggregated.description.short}
            </p>
            {hasDefaultProfileSummary && (
              <div data-testid="custom-model-card-default-profile">
                <ModelProfileSummary profile={defaultProfileSummary} t={t} />
              </div>
            )}
          </div>
        </div>
      </CardHeader>
      <Divider />
      <CardFooter className="flex flex-col">
        <div className="flex p-5 pt-3 flex-row flex-nowrap justify-between items-center w-full">
          <TruncatedTagsRow
            tags={tags}
            formatMoreCount={(count) =>
              t('customModels.card.tagsMoreCount', { count })
            }
          />

          <div className="flex flex-row items-center gap-2">
            <ActionsDropdown actions={cardActions}>
              <ActionButton
                tertiary
                size="sm"
                aria-label={t('customModels.card.actionsMenu')}
                icon={<IconDotsVertical size={16} />}
                data-testid="custom-model-card-actions"
              />
            </ActionsDropdown>
            <ActionButton
              primary
              color="primary"
              size="sm"
              isDisabled={!isDeployable}
              onPress={() => onDeploy(aggregatedAim)}
              data-testid="custom-model-card-deploy"
            >
              {t('aimCatalog.actions.deploy.label')}
            </ActionButton>
          </div>
        </div>
      </CardFooter>
    </Card>
  );
};

CustomModelCard.displayName = 'CustomModelCard';
