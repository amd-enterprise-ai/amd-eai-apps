// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { IconInfoCircle } from '@tabler/icons-react';
import React from 'react';
import { ActionButton } from '../src/Buttons';
import { Tooltip } from '../src/Tooltip';

export default { title: 'Components/Tooltip' } satisfies StoryDefault;

export const Default: Story = () => (
  <div className="p-8">
    <Tooltip content="Additional information">
      <ActionButton primary>Hover me</ActionButton>
    </Tooltip>
  </div>
);

export const NonInteractiveTriggers: Story = () => (
  <div className="flex items-center gap-16 p-8">
    <Tooltip content="Icon trigger">
      <IconInfoCircle className="text-muted" size={16} />
    </Tooltip>
    <Tooltip content="Span trigger">
      <span>Hover this text</span>
    </Tooltip>
    <Tooltip content="Truncated cell value">
      <div className="max-w-24 truncate">A very long value that truncates</div>
    </Tooltip>
  </div>
);

export const Placements: Story = () => (
  <div className="grid grid-cols-2 gap-16 p-24">
    {(['top-start', 'bottom-end', 'left-start', 'right'] as const).map(
      (placement) => (
        <Tooltip
          content={`Placed ${placement}`}
          key={placement}
          placement={placement}
        >
          <ActionButton secondary>{placement}</ActionButton>
        </Tooltip>
      ),
    )}
  </div>
);
