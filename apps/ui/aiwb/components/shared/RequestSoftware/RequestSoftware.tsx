// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ActionButton, Card, CardBody } from '@amdenterpriseai/components';
import { useSystemInfo } from '@amdenterpriseai/hooks';
import { createMailtoLink } from '@amdenterpriseai/utils/app';
import { IconSend } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import React from 'react';
import BgSvg from './bg.svg';

export type RequestSoftwareVariant = 'model' | 'workspace';

interface RequestSoftwareProps {
  variant: RequestSoftwareVariant;
}

const MAIL_CONTENT: Record<
  RequestSoftwareVariant,
  { subject: string; bodyLines: readonly string[] }
> = {
  model: {
    subject: 'Model request',
    bodyLines: [
      'Model name: ',
      'Hugging Face or other URL of the model: ',
      'Use case: ',
      'Why you need it: ',
    ],
  },
  workspace: {
    subject: 'Workspace request',
    bodyLines: [
      'Workspace: ',
      'Website URL of the tool: ',
      'Use case: ',
      'Why you need it: ',
    ],
  },
};

export const RequestSoftware: React.FC<RequestSoftwareProps> = ({
  variant,
}) => {
  const { t } = useTranslation('common');
  const getSystemInfo = useSystemInfo();
  const { subject, bodyLines } = MAIL_CONTENT[variant];
  const mailtoHref = createMailtoLink({
    subject,
    body: [...bodyLines, '', '--- System info ---', ...getSystemInfo()],
  });
  return (
    <Card className="overflow-hidden p-0" data-testid={`request-${variant}`}>
      <CardBody className="flex flex-row gap-8 p-8 px-12 items-center justify-between overflow-hidden">
        <div className="relative z-10 flex flex-col gap-1">
          <h4>{t(`requestSoftware.${variant}.title`)}</h4>
          <p className="text-sm">
            {t(`requestSoftware.${variant}.description`)}
          </p>
        </div>
        <div className="relative">
          <ActionButton
            href={mailtoHref}
            className="relative z-10"
            primary
            icon={<IconSend />}
            size="lg"
          >
            {t(`requestSoftware.${variant}.button`)}
          </ActionButton>
          <BgSvg
            aria-hidden="true"
            focusable={false}
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none w-[500%] mr-40 animate-spin text-foreground opacity-20"
            style={
              {
                '--animate-spin': 'spin 800s linear infinite',
              } as React.CSSProperties
            }
          />
        </div>
      </CardBody>
    </Card>
  );
};
