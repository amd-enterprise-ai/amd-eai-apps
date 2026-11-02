// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconInfoCircle } from '@tabler/icons-react';
import type { ReactElement, ReactNode } from 'react';
import { ButtonContext } from 'react-aria-components';

import { Button } from '../Buttons';
import { Tooltip } from '../Tooltip/Tooltip';

type InfoTooltipProps = {
  content: ReactNode;
};

export const InfoTooltip = ({ content }: InfoTooltipProps): ReactElement => (
  <ButtonContext.Provider value={null}>
    <Tooltip content={content}>
      <Button
        isIconOnly
        size="sm"
        variant="tertiary"
        aria-label={typeof content === 'string' ? content : undefined}
        className="m-0 size-4 min-w-0 cursor-help rounded-none border-0 bg-transparent p-0 text-muted shadow-none data-hovered:bg-transparent data-pressed:bg-transparent"
      >
        <IconInfoCircle aria-hidden size={16} />
      </Button>
    </Tooltip>
  </ButtonContext.Provider>
);
