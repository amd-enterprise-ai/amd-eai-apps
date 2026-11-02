// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Card, CardBody } from '@amdenterpriseai/components';
import { IconBubbleText, IconGitCompare } from '@tabler/icons-react';

import { useTranslation } from 'next-i18next';

interface Props {
  mode: 'chat' | 'compare';
  /** Bordered card for empty state at `lg` and up; `belowDesktop` when ChatView is below `lg`. */
  variant?: 'card' | 'belowDesktop';
}

const ChatInfoCard = ({ mode, variant = 'card' }: Props) => {
  const { t } = useTranslation('chat');

  const icon = (
    <span className="inline-flex items-center justify-center w-8 h-8 lg:w-10 lg:h-10 rounded-full bg-accent-soft dark:bg-accent-soft">
      {mode === 'chat' ? (
        <IconBubbleText className="w-5 h-5 lg:w-7 lg:h-7 text-accent dark:text-accent" />
      ) : (
        <IconGitCompare className="w-5 h-5 lg:w-7 lg:h-7 text-accent dark:text-accent" />
      )}
    </span>
  );

  if (variant === 'belowDesktop') {
    return (
      <div className="flex flex-col items-start text-left w-full">
        <div className="flex items-center gap-3">
          {icon}
          <h2 className="font-bold text-xl text-foreground tracking-tight">
            {t(`${mode}.title`)}
          </h2>
        </div>
        <p className="mt-4 text-base leading-relaxed text-foreground">
          {t(`${mode}.description`)}
        </p>
        <ul className="mt-3 list-disc pl-5 text-sm leading-normal text-foreground space-y-2 marker:text-muted">
          <li>{t(`${mode}.tips.tip1`)}</li>
          <li>{t(`${mode}.tips.tip2`)}</li>
        </ul>
      </div>
    );
  }

  return (
    <Card className="max-w-[600px] mx-4 lg:mx-8 p-5 lg:p-8">
      <CardBody className="overflow-visible flex flex-col gap-2 lg:gap-3 items-start">
        <div className="flex items-center gap-2 lg:gap-3 mb-1 lg:mb-2">
          {icon}
          <h2 className="font-bold text-xl lg:text-2xl text-foreground">
            {t(`${mode}.title`)}
          </h2>
        </div>
        <p className="mb-2 lg:mb-3">{t(`${mode}.description`)}</p>
        <ul className="list-disc pl-4 text-foreground text-sm space-y-1 mb-1">
          <li>{t(`${mode}.tips.tip1`)}</li>
          <li>{t(`${mode}.tips.tip2`)}</li>
          <li>{t(`${mode}.tips.tip3`)}</li>
        </ul>
      </CardBody>
    </Card>
  );
};

export default ChatInfoCard;
