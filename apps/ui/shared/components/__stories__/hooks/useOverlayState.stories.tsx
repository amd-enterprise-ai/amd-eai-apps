// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';

import { useOverlayState } from '@amdenterpriseai/hooks';
import { ActionButton } from '../../src/Buttons/ActionButton';
import {
  ModalPrimitive,
  ModalPrimitiveBody,
  ModalPrimitiveContent,
  ModalPrimitiveFooter,
  ModalPrimitiveHeader,
} from '../../src/Modal';

export default {
  title: 'Hooks/useOverlayState',
} satisfies StoryDefault;

// useOverlayState is a hook, not a renderable component, so the story drives a
// small demo that wires the hook's API to a real overlay. Reviewers can watch
// isOpen change as the open/close/toggle handlers fire.
export const DrivingAModal: Story = () => {
  const { isOpen, onOpen, onClose, onOpenChange } = useOverlayState();

  return (
    <div className="flex flex-col items-start gap-4 p-6">
      <p className="text-sm text-muted">
        isOpen:{' '}
        <span className="font-mono font-semibold">{String(isOpen)}</span>
      </p>

      <div className="flex gap-2">
        <ActionButton primary onPress={onOpen}>
          onOpen
        </ActionButton>
        <ActionButton secondary onPress={onClose}>
          onClose
        </ActionButton>
        <ActionButton tertiary onPress={() => onOpenChange()}>
          onOpenChange (toggle)
        </ActionButton>
      </div>

      <ModalPrimitive isOpen={isOpen} onOpenChange={onOpenChange}>
        <ModalPrimitiveContent>
          {(close) => (
            <>
              <ModalPrimitiveHeader>
                Overlay driven by useOverlayState
              </ModalPrimitiveHeader>
              <ModalPrimitiveBody>
                <p className="text-sm text-muted">
                  This modal&apos;s visibility is bound to the hook&apos;s
                  isOpen and onOpenChange. Pressing Escape or the backdrop also
                  routes through onOpenChange.
                </p>
              </ModalPrimitiveBody>
              <ModalPrimitiveFooter>
                <ActionButton secondary onPress={close}>
                  Close
                </ActionButton>
              </ModalPrimitiveFooter>
            </>
          )}
        </ModalPrimitiveContent>
      </ModalPrimitive>
    </div>
  );
};
