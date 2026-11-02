// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
} from '@tabler/icons-react';
import { ToggleButton } from '@heroui/react';
import React from 'react';

interface SidebarToggleButtonProps {
  isExpanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  ariaLabel: string;
  controlsId?: string;
  className?: string;
}

const DEFAULT_COLOR_STYLE = {
  '--toggle-button-bg-selected': 'var(--default-hover)',
  '--toggle-button-bg-selected-hover':
    'color-mix(in srgb, var(--default-hover) 85%, light-dark(black, white))',
  '--toggle-button-bg-selected-pressed':
    'color-mix(in srgb, var(--default-hover) 80%, light-dark(black, white))',
  '--toggle-button-fg-selected': 'var(--default-foreground)',
} as React.CSSProperties;

export const SidebarToggleButton: React.FC<SidebarToggleButtonProps> = ({
  isExpanded,
  onExpandedChange,
  ariaLabel,
  controlsId,
  className,
}) => (
  <ToggleButton
    isSelected={isExpanded}
    onChange={onExpandedChange}
    isIconOnly
    variant="ghost"
    size="sm"
    aria-label={ariaLabel}
    aria-expanded={isExpanded}
    aria-controls={controlsId}
    data-testid="sidebar-toggle-button"
    className={className}
    style={DEFAULT_COLOR_STYLE}
  >
    {isExpanded ? (
      <IconLayoutSidebarLeftCollapse aria-hidden="true" size={14} />
    ) : (
      <IconLayoutSidebarLeftExpand aria-hidden="true" size={14} />
    )}
  </ToggleButton>
);
