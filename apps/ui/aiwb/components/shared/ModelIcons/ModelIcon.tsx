// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';

import { ModelIconType, ModelIcons } from './index';

interface ModelIconProps {
  iconName?: string;
  width?: number;
  height?: number;
}

export const ModelIcon: React.FC<ModelIconProps> = ({
  iconName,
  width = 48,
  height = 48,
}) => {
  const iconKey = (Object.keys(ModelIcons) as ModelIconType[]).find((key) =>
    iconName?.toLowerCase().includes(key.toLowerCase()),
  );

  const IconComponent = iconKey ? ModelIcons[iconKey] : ModelIcons.default;

  const firstLetters =
    (iconName?.charAt(0) ?? '').toUpperCase() +
    (iconName?.split('/')[1]?.charAt(0) ?? '').toUpperCase();

  // Generate a deterministic background color based on the iconName
  // 151.258 is a magic number that ensures the color is sufficiently different for each icon
  const backgroundColor = iconName
    ? `hsl(${
        (iconName
          .split('/')[0]
          .split('')
          .reduce((acc, char) => acc + char.charCodeAt(0), 0) *
          151.258) %
        360
      }, 70%, 60%)`
    : '#E0E0E0';

  const iconWrapperProps = {
    'aria-label': `${iconName || 'Default'} model icon`,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      minWidth: `${width}px`,
      minHeight: `${height}px`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
  };

  const defaultIconOffset = 2;
  const defaultIconWrapperProps = {
    ...iconWrapperProps,
    style: {
      ...iconWrapperProps.style,
      width: `${width - defaultIconOffset}px`,
      height: `${height - defaultIconOffset}px`,
      minWidth: `${width - defaultIconOffset}px`,
      minHeight: `${height - defaultIconOffset}px`,
      backgroundColor,
      borderRadius: '100%',
    },
  };

  return iconKey ? (
    <div {...iconWrapperProps}>
      <IconComponent style={{ width: '100%', height: 'auto' }} />
    </div>
  ) : (
    <div {...defaultIconWrapperProps}>
      <span
        style={{
          fontSize: `${Math.min(width, height) / 2.8}px`,
          color: '#FFFFFF',
          fontWeight: 'bold',
        }}
      >
        {firstLetters}
      </span>
    </div>
  );
};
