// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * File element component that shows file in the list
 */
import { IconFile, IconX } from '@tabler/icons-react';
import { memo } from 'react';

import { ActionButton } from '../../Buttons';
import { displayBytesInOptimalUnit } from '@amdenterpriseai/utils/app';

const FileElement = memo(
  ({
    file,
    onRemove,
    t,
  }: {
    file: File;
    onRemove: () => void;
    t: (key: string, options?: Record<string, unknown>) => string;
  }) => (
    <div className="flex w-full min-w-0 items-center overflow-hidden gap-1 rounded p-1 bg-default">
      <IconFile size={16} className="shrink-0" />
      <span
        className="text-sm truncate text-foreground min-w-0 flex-1"
        title={file.name}
      >
        {file.name}
      </span>
      <span className="text-sm text-muted shrink-0 text-nowrap">
        {displayBytesInOptimalUnit(file.size)}
      </span>
      <ActionButton
        tertiary
        size="sm"
        className="rounded shrink-0"
        aria-label={t('remove')}
        onPress={onRemove}
        icon={<IconX size={16} />}
      />
    </div>
  ),
);

FileElement.displayName = 'FileElement';

export default FileElement;
