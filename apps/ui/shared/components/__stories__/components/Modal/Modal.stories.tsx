// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { type ComponentProps, useState } from 'react';

import { ActionButton } from '../../../src/Buttons/ActionButton';
import { Modal } from '../../../src/Modal/Modal';
import { ModalPrimitive } from '../../../src/Modal/ModalPrimitive';

export default {
  title: 'Components/Modal',
} satisfies StoryDefault;

export const Primitive: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open modal
      </ActionButton>
      <ModalPrimitive isOpen={isOpen} onOpenChange={setIsOpen}>
        <ModalPrimitive.Content>
          <ModalPrimitive.Header>Modal Title</ModalPrimitive.Header>
          <ModalPrimitive.Body>
            <p>
              This is the ModalPrimitive adapter — a thin wrapper that
              re-exports the HeroUI Modal with compound sub-components.
            </p>
          </ModalPrimitive.Body>
          <ModalPrimitive.Footer>
            <ActionButton secondary onPress={() => setIsOpen(false)}>
              Cancel
            </ActionButton>
            <ActionButton primary onPress={() => setIsOpen(false)}>
              Confirm
            </ActionButton>
          </ModalPrimitive.Footer>
        </ModalPrimitive.Content>
      </ModalPrimitive>
    </div>
  );
};

export const HighLevelWrapper: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open modal
      </ActionButton>
      {isOpen && (
        <Modal
          onClose={() => setIsOpen(false)}
          title="High-level Modal"
          subTitle="Uses ModalPrimitive internally"
          footer={
            <ActionButton primary onPress={() => setIsOpen(false)}>
              Done
            </ActionButton>
          }
        >
          <p>
            This is the existing high-level Modal wrapper, now backed by
            ModalPrimitive instead of direct HeroUI imports.
          </p>
        </Modal>
      )}
    </div>
  );
};

export const TitleOnly: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open modal
      </ActionButton>
      {isOpen && (
        <Modal onClose={() => setIsOpen(false)} title="Just a title">
          <p>
            A bare wrapper with only a title — no subtitle and no footer slot.
          </p>
        </Modal>
      )}
    </div>
  );
};

export const NonDismissible: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open modal
      </ActionButton>
      {isOpen && (
        <Modal
          onClose={() => setIsOpen(false)}
          title="Non-dismissible Modal"
          subTitle="Clicking the backdrop will not close it"
          isDismissible={false}
          footer={
            <ActionButton primary onPress={() => setIsOpen(false)}>
              Acknowledge
            </ActionButton>
          }
        >
          <p>
            With <code>isDismissible={'{false}'}</code> the modal can only be
            closed through an explicit action, not by clicking outside.
          </p>
        </Modal>
      )}
    </div>
  );
};

type ModalSize = NonNullable<ComponentProps<typeof Modal>['size']>;

const MODAL_SIZES: ModalSize[] = ['xs', 'sm', 'md', 'lg', 'full', 'cover'];

export const Sizes: Story = () => {
  const [openSize, setOpenSize] = useState<ModalSize | null>(null);

  return (
    <div className="flex flex-wrap gap-3 p-6">
      {MODAL_SIZES.map((size) => (
        <ActionButton key={size} secondary onPress={() => setOpenSize(size)}>
          {size}
        </ActionButton>
      ))}
      {openSize && (
        <Modal
          onClose={() => setOpenSize(null)}
          size={openSize}
          title={`Size: ${openSize}`}
          subTitle="Pick a button to preview each supported width"
          footer={
            <ActionButton primary onPress={() => setOpenSize(null)}>
              Close
            </ActionButton>
          }
        >
          <p>
            The <code>size</code> prop accepts HeroUI v3 modal widths:{' '}
            <code>xs</code>, <code>sm</code>, <code>md</code>, <code>lg</code>,{' '}
            <code>full</code>, and <code>cover</code>. It defaults to{' '}
            <code>lg</code>.
          </p>
        </Modal>
      )}
    </div>
  );
};

type PlaygroundArgs = {
  size: ModalSize;
  title: string;
  subTitle: string;
  isDismissible: boolean;
  showFooter: boolean;
};

export const Playground: Story<PlaygroundArgs> = ({
  size = 'lg',
  title = 'Playground Modal',
  subTitle = 'Tweak the controls to explore the adapter API',
  isDismissible = true,
  showFooter = true,
}) => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open modal
      </ActionButton>
      {isOpen && (
        <Modal
          onClose={() => setIsOpen(false)}
          size={size}
          title={title}
          subTitle={subTitle || undefined}
          isDismissible={isDismissible}
          footer={
            showFooter ? (
              <>
                <ActionButton secondary onPress={() => setIsOpen(false)}>
                  Cancel
                </ActionButton>
                <ActionButton primary onPress={() => setIsOpen(false)}>
                  Confirm
                </ActionButton>
              </>
            ) : undefined
          }
        >
          <p>
            This story wires the wrapper props to Ladle controls so you can
            exercise sizes, dismissibility, the subtitle, and the footer slot.
          </p>
        </Modal>
      )}
    </div>
  );
};

Playground.args = {
  size: 'lg',
  title: 'Playground Modal',
  subTitle: 'Tweak the controls to explore the adapter API',
  isDismissible: true,
  showFooter: true,
};

Playground.argTypes = {
  size: {
    control: { type: 'select' },
    options: MODAL_SIZES,
    defaultValue: 'xl',
  },
  title: {
    control: { type: 'text' },
    defaultValue: 'Playground Modal',
  },
  subTitle: {
    control: { type: 'text' },
    defaultValue: 'Tweak the controls to explore the adapter API',
  },
  isDismissible: {
    control: { type: 'boolean' },
    defaultValue: true,
  },
  showFooter: {
    control: { type: 'boolean' },
    defaultValue: true,
  },
};
