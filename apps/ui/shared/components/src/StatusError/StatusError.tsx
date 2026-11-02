// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Button } from '../Buttons/Button';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useState } from 'react';

import { useTranslation } from 'next-i18next';

import { SecondaryStatusReason } from '@amdenterpriseai/types';

interface Props {
  statusReason: string | null;
  secondaryStatusReasons?: SecondaryStatusReason[];
}

export const StatusError: React.FC<Props> = ({
  statusReason,
  secondaryStatusReasons,
}) => {
  const [currentReason, setCurrentReason] =
    useState<SecondaryStatusReason | null>(
      secondaryStatusReasons && secondaryStatusReasons.length > 0
        ? secondaryStatusReasons[0]
        : null,
    );
  const { t } = useTranslation('sharedComponents');
  const [currentIndex, setCurrentIndex] = useState(0);

  return (
    <div className="px-1 py-2 max-w-[400px] flex flex-col gap-2">
      <div>{t('status.description')}</div>

      {statusReason ? (
        <div className="text-sm bg-default-hover my-2 p-1 whitespace-pre-line">
          <code>{statusReason}</code>
        </div>
      ) : null}

      {secondaryStatusReasons && secondaryStatusReasons.length > 0 && (
        <>
          <strong>{t('status.errorDetail.title')}</strong>

          {currentReason ? (
            <>
              <span>{currentReason.key}</span>
              <div className="text-sm bg-default-hover my-1 p-1 whitespace-pre-line">
                <code>{currentReason.description}</code>
              </div>
            </>
          ) : null}
          <div className="flex items-center gap-2 justify-center">
            <Button
              size="sm"
              isIconOnly
              isDisabled={currentIndex === 0}
              aria-label={t('status.errorDetail.action.prev')}
              onPress={() => {
                setCurrentIndex((prev) => {
                  const newIndex = prev - 1;
                  setCurrentReason(secondaryStatusReasons[newIndex]);
                  return newIndex;
                });
              }}
            >
              <IconChevronLeft size={16} />
            </Button>
            <span>
              {currentIndex + 1} / {secondaryStatusReasons.length}
            </span>
            <Button
              size="sm"
              isIconOnly
              isDisabled={currentIndex === secondaryStatusReasons.length - 1}
              aria-label={t('status.errorDetail.action.next')}
              onPress={() => {
                setCurrentIndex((prev) => {
                  const newIndex = prev + 1;
                  setCurrentReason(secondaryStatusReasons[newIndex]);
                  return newIndex;
                });
              }}
            >
              <IconChevronRight size={16} />
            </Button>
          </div>
        </>
      )}
    </div>
  );
};

export default StatusError;
