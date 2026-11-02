// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * Drag overlay component that shows when files are being dragged over the upload area
 */
import { cn } from '@heroui/react';
import { IconFile, IconX } from '@tabler/icons-react';
import { memo } from 'react';

const DragOverlay = memo(
  ({
    canDrop,
    multiple,
    t,
  }: {
    canDrop: boolean;
    multiple: boolean;
    t: (key: string, options?: Record<string, unknown>) => string;
  }) => (
    <div
      className={cn(
        'absolute inset-0 z-10 rounded top-0.5 left-0.5 right-0.5 bottom-0.5 border border-dashed flex flex-col items-center justify-center transition-colors gap-2',
        canDrop
          ? 'bg-background/80 border-success text-success'
          : 'bg-background/80 border-danger text-danger',
      )}
    >
      {canDrop ? (
        <IconFile size={32} className="text-inherit" />
      ) : (
        <IconX size={32} className="text-inherit" />
      )}
      <span className="text-sm text-inherit">
        {canDrop
          ? t('drop', { count: +multiple + 1 })
          : t('dropFail', { count: +multiple + 1 })}
      </span>
    </div>
  ),
);

DragOverlay.displayName = 'DragOverlay';

export default DragOverlay;
