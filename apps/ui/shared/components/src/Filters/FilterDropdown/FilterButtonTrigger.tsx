// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Tooltip } from '../../Tooltip';
import { cn, InputGroup } from '@heroui/react';
import { IconChevronDown } from '@tabler/icons-react';
import { ReactNode, useMemo } from 'react';
import { InlineBadge } from '../../InlineBadge';

export interface FilterButtonTriggerProps {
  label: string;
  numberOfSelectedKeys: number;
  startContent?: ReactNode;
  tooltipText?: string;
  isActive?: boolean;
  showClearButton?: boolean;
}

/** Input-styled visual for `Popover.Trigger`; interaction is owned by the trigger. */
export const FilterButtonTrigger: React.FC<FilterButtonTriggerProps> = ({
  label,
  startContent,
  numberOfSelectedKeys,
  tooltipText,
  isActive = false,
  showClearButton = false,
}) => {
  const badgeContent = useMemo(() => {
    if (!isActive) return null;
    return (
      <Tooltip content={tooltipText} delay={500} size="sm" className="max-w-40">
        <div className="cursor-help">
          <InlineBadge color="primary" size="sm" variant="solid">
            {numberOfSelectedKeys.toString()}
          </InlineBadge>
        </div>
      </Tooltip>
    );
  }, [isActive, tooltipText, numberOfSelectedKeys]);

  const prefixContent = isActive ? badgeContent : startContent;

  return (
    <InputGroup variant="primary" className="w-full cursor-pointer">
      {prefixContent && (
        <InputGroup.Prefix className="gap-1.5 shrink-0">
          {prefixContent}
        </InputGroup.Prefix>
      )}
      <InputGroup.Input
        readOnly
        tabIndex={-1}
        value={label}
        aria-hidden
        className={cn(
          'min-w-0 flex-1 truncate select-none pointer-events-none',
          showClearButton && 'pr-8',
        )}
        onMouseDown={(e) => e.preventDefault()}
      />
      {!showClearButton && (
        <InputGroup.Suffix className="shrink-0">
          <IconChevronDown size={16} stroke={2} />
        </InputGroup.Suffix>
      )}
    </InputGroup>
  );
};

export default FilterButtonTrigger;
