// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import {
  IconCircleCheck,
  IconAlertTriangle,
  IconLoaderQuarter,
} from '@tabler/icons-react';
import { Intent } from '@amdenterpriseai/types';

export type HeroMessageProps = {
  title: string;
  description: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  intent?: Intent;
  endContent?: React.ReactNode;
};

const INTENT_TO_PROPS = {
  [Intent.SUCCESS]: {
    color: 'text-success',
    icon: IconCircleCheck,
  },
  [Intent.WARNING]: {
    color: 'text-warning',
    icon: IconAlertTriangle,
  },
  [Intent.DANGER]: {
    color: 'text-danger',
    icon: IconAlertTriangle,
  },
  [Intent.PENDING]: {
    color: 'text-warning',
    icon: IconLoaderQuarter,
  },
} as const;

export function HeroMessage({
  title,
  description,
  icon: iconProp,
  intent,
  endContent,
}: HeroMessageProps) {
  const intentDefaults = intent ? INTENT_TO_PROPS[intent] : null;
  const IconComponent = iconProp ?? intentDefaults?.icon ?? null;
  const iconColorClass = intentDefaults?.color ?? 'text-accent';

  return (
    <div className="w-full h-full flex justify-center items-center">
      <div className="dark:bg-surface-secondary max-w-[600px] flex flex-col items-start border dark:border-default border-default p-12 rounded-md">
        {IconComponent && (
          <IconComponent className={iconColorClass} size={48} />
        )}
        <div className="flex flex-col gap-4 my-8">
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        {endContent}
      </div>
    </div>
  );
}

export default HeroMessage;
