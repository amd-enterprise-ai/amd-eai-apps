// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Tooltip, cn } from '@amdenterpriseai/components';
import { useElementOverflow } from '@amdenterpriseai/hooks';
import { useCallback } from 'react';

export const TruncatedDescription = ({
  description,
}: {
  description: string;
}) => {
  const measureOverflow = useCallback(
    (element: HTMLSpanElement) =>
      Boolean(description) && element.scrollWidth > element.clientWidth,
    [description],
  );
  const { elementRef, isOverflowing } =
    useElementOverflow<HTMLSpanElement>(measureOverflow);

  return (
    <Tooltip content={description} isDisabled={!isOverflowing}>
      <span
        ref={elementRef}
        className={cn(
          'block w-full truncate text-xs text-muted',
          isOverflowing && 'cursor-help',
        )}
      >
        {description}
      </span>
    </Tooltip>
  );
};
