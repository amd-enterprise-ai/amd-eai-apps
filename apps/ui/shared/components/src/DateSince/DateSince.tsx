// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Tooltip } from '../Tooltip';
import {
  differenceInCalendarDays,
  format,
  formatDistance,
  formatRelative,
} from 'date-fns';
import { enUS } from 'date-fns/locale';
import type { Locale } from 'date-fns';
import { useRouter } from 'next/router';

export interface DateSinceProps {
  /** Timestamp as Date, number (ms), or ISO string */
  date: Date | number | string;
  /** Optional class name for the wrapper span */
  className?: string;
}

const LOCALE_MAP: Record<string, Locale> = {
  en: enUS,
};

export const DateSince = ({ date, className }: DateSinceProps) => {
  const locale = (useRouter()?.locale as string | undefined) ?? 'en';
  const dateFnsLocale = LOCALE_MAP[locale.split('-')[0]] ?? enUS;
  const now = new Date();
  const resolvedDate = date instanceof Date ? date : new Date(date);
  const absFormatted = format(resolvedDate, 'P, p', {
    locale: dateFnsLocale,
  });
  const days = differenceInCalendarDays(now, resolvedDate);
  let displayText: string;

  switch (days) {
    case 0:
      displayText = formatDistance(resolvedDate, now, {
        addSuffix: true,
        locale: dateFnsLocale,
      });
      break;
    case 1:
      displayText = formatRelative(resolvedDate, now, {
        locale: dateFnsLocale,
      });
      break;
    default:
      displayText = absFormatted;
  }

  return (
    <Tooltip content={absFormatted} placement="top" isDisabled={days > 1}>
      {/* biome-ignore lint/a11y/useSemanticElements: the element reveals the absolute date rather than performing an action. */}
      <span className={className} role="button" tabIndex={0}>
        {displayText}
      </span>
    </Tooltip>
  );
};
