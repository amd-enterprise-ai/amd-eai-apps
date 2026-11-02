// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ActionButton, Button, HeroMessage } from '@amdenterpriseai/components';
import { IconChevronDown, IconRefresh } from '@tabler/icons-react';
import { useState } from 'react';

import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';
import { ErrorMessageProps, Intent } from '@amdenterpriseai/types';
import {
  getErrorTitleTranslationKey,
  getErrorDescriptionTranslationKey,
} from '@/lib/app/errorMessages';

export function ErrorMessage({
  message = '',
  code,
  onRefresh,
}: ErrorMessageProps) {
  const { t } = useTranslation('common');
  const [isErrorExpanded, setIsErrorExpanded] = useState(false);
  const router = useRouter();

  const handleRefresh = () => {
    if (onRefresh) {
      onRefresh();
    } else {
      router.replace(router.asPath);
    }
  };

  const toggleErrorDetails = () => {
    setIsErrorExpanded(!isErrorExpanded);
  };

  const titleKey = getErrorTitleTranslationKey(code);
  const descriptionKey = getErrorDescriptionTranslationKey(code);

  return (
    <HeroMessage
      intent={Intent.DANGER}
      title={t(titleKey ?? 'error.unknown.title')}
      description={t(descriptionKey ?? 'error.unknown.description')}
      endContent={
        <>
          {message && (
            <div className="w-full mt-2">
              <Button
                size="sm"
                variant="ghost"
                onPress={toggleErrorDetails}
                endContent={
                  <IconChevronDown
                    size={16}
                    className={`transition-transform ${
                      isErrorExpanded ? 'rotate-180' : ''
                    }`}
                  />
                }
              >
                {t('actions.showDetails.title')}
              </Button>
              <div
                className={`overflow-hidden transition-all duration-300 ${
                  isErrorExpanded ? 'max-h-24 opacity-100' : 'max-h-0 opacity-0'
                }`}
              >
                <div className="text-foreground text-sm mt-3 rounded-md break-all">
                  {t('error.label')}: {message}
                </div>
              </div>
            </div>
          )}
          <ActionButton
            className="mt-4"
            onPress={handleRefresh}
            icon={<IconRefresh size={18} />}
          >
            {t(`error.refreshActionLabel`)}
          </ActionButton>
        </>
      }
    />
  );
}

export default ErrorMessage;
