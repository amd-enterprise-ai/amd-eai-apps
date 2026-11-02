// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Alert as HeroUIAlert, cn } from '@heroui/react';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconInfoCircle,
} from '@tabler/icons-react';
import React from 'react';

export type AlertStatus =
  | 'default'
  | 'accent'
  | 'success'
  | 'warning'
  | 'danger';

/** Composes HeroUI v3 Alert subcomponents with flat convenience props. */
export interface AlertProps {
  status?: AlertStatus;
  icon?: React.ReactNode;
  hideIcon?: boolean;
  isTight?: boolean;
  title?: React.ReactNode;
  description?: React.ReactNode;
  className?: string;
  classNames?: {
    base?: string;
    content?: string;
    title?: string;
    description?: string;
    indicator?: string;
  };
  children?: React.ReactNode;
}

const statusToBackground: Record<AlertStatus, string> = {
  // HeroUI `.alert` sets unlayered `bg-surface`, which beats layered utilities;
  // `!` + soft tokens override it with the intended semi-transparent tint.
  default: 'bg-default-soft',
  accent: 'bg-accent-soft',
  success: 'bg-success-soft',
  warning: 'bg-warning-soft',
  danger: 'bg-danger-soft',
};

const statusToTextColor: Record<AlertStatus, string> = {
  // HeroUI `.alert__description` sets `text-muted`; `!` beats unlayered slot styles.
  // Soft-foreground tokens mix status with foreground for text on soft backgrounds.
  default: '!text-foreground',
  accent: '!text-accent-soft-foreground',
  success: '!text-success-soft-foreground',
  warning: '!text-warning-soft-foreground',
  danger: '!text-danger-soft-foreground',
};

const getIconForStatus = (status: AlertStatus, size = 16): React.ReactNode => {
  switch (status) {
    case 'danger':
    case 'warning':
      return <IconAlertTriangle size={size} />;
    case 'success':
      return <IconCircleCheck size={size} />;
    default:
      return <IconInfoCircle size={size} />;
  }
};

export const Alert: React.FC<AlertProps> = ({
  status = 'default',
  icon,
  hideIcon = false,
  isTight = false,
  title,
  description,
  className,
  classNames,
  children,
  ...restProps
}) => {
  const resolvedIcon = icon === undefined ? getIconForStatus(status) : icon;
  const showIcon = !hideIcon && resolvedIcon !== null;
  return (
    <HeroUIAlert
      status={status}
      className={cn(
        statusToBackground[status],
        'shadow-none gap-2!',
        isTight && 'rounded-small p-2',
        classNames?.base,
        className,
      )}
      role="alert"
      {...restProps}
    >
      {showIcon ? (
        // fill-none keeps stroke-based Tabler icons from rendering solid.
        <HeroUIAlert.Indicator
          className={cn(
            'fill-none',
            statusToTextColor[status],
            classNames?.indicator,
          )}
        >
          {resolvedIcon}
        </HeroUIAlert.Indicator>
      ) : null}
      <HeroUIAlert.Content
        className={cn(statusToTextColor[status], classNames?.content)}
      >
        {title ? (
          <HeroUIAlert.Title
            className={cn(
              statusToTextColor[status],
              isTight && 'text-xs leading-3.5',
              classNames?.title,
            )}
          >
            {title}
          </HeroUIAlert.Title>
        ) : null}
        {description ? (
          <HeroUIAlert.Description
            className={cn(
              statusToTextColor[status],
              isTight && 'text-xs leading-tight',
              classNames?.description,
            )}
          >
            {description}
          </HeroUIAlert.Description>
        ) : null}
        {children}
      </HeroUIAlert.Content>
    </HeroUIAlert>
  );
};

export default Alert;
