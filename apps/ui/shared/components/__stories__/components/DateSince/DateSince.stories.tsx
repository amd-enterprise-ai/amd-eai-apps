// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { setHours, setMinutes, subDays, subHours, subMinutes } from 'date-fns';
import { DateSince } from '../../../src/DateSince/DateSince';

export default {
  title: 'Components/DateSince/DateSince',
} satisfies StoryDefault;

const now = new Date();

const dates = {
  now,
  oneMinuteAgo: subMinutes(now, 1),
  fiveMinutesAgo: subMinutes(now, 5),
  oneHourAgo: subHours(now, 1),
  fiveHoursAgo: subHours(now, 5),
  yesterdayAt1620: setMinutes(setHours(subDays(now, 1), 16), 20),
  twoDaysAgo: subDays(now, 2),
} as const;

const labels: Record<keyof typeof dates, string> = {
  now: 'Date is now',
  oneMinuteAgo: 'Date is 1 minute ago',
  fiveMinutesAgo: 'Date is 5 minutes ago',
  oneHourAgo: 'Date is 1 hour ago',
  fiveHoursAgo: 'Date is 5 hours ago',
  yesterdayAt1620: 'Date is yesterday at 16:20',
  twoDaysAgo: 'Date is 2 days ago',
};

export const AllStates: Story = () => (
  <div className="flex flex-col gap-4">
    <p className="text-sm text-muted">
      Renders a relative time label (e.g. “5 minutes ago”) with an absolute
      date/time tooltip for today and yesterday.
    </p>
    <ul className="flex flex-col gap-3 list-none p-0 m-0">
      {(Object.keys(dates) as (keyof typeof dates)[]).map((key) => (
        <li key={key} className="flex gap-2 items-baseline">
          <span className="text-sm text-muted min-w-[200px]">
            {labels[key]}:
          </span>
          <DateSince date={dates[key]} />
        </li>
      ))}
    </ul>
  </div>
);
