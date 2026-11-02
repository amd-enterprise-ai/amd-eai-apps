// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconCheckupList } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import { HeroMessage } from '@amdenterpriseai/components';
import { ErrorCodes, Intent } from '@amdenterpriseai/types';
import {
  getErrorTitleTranslationKey,
  getErrorDescriptionTranslationKey,
} from '@/lib/app/errorMessages';
import { ProjectSelect } from './ProjectSelect';

interface ProjectSelectPromptProps {
  errorCode?: string;
}

export function ProjectSelectPrompt({ errorCode }: ProjectSelectPromptProps) {
  const { t } = useTranslation('common');

  const isError =
    errorCode && Object.values(ErrorCodes).includes(errorCode as ErrorCodes);

  const titleKey = getErrorTitleTranslationKey(errorCode);
  const descriptionKey = getErrorDescriptionTranslationKey(errorCode);

  return (
    <HeroMessage
      intent={isError ? Intent.DANGER : undefined}
      icon={IconCheckupList}
      title={titleKey ? t(titleKey) : t('projectSelectPrompt.title')}
      description={
        descriptionKey
          ? t(descriptionKey)
          : t('projectSelectPrompt.description')
      }
      endContent={<ProjectSelect showTooltip={false} />}
    />
  );
}
