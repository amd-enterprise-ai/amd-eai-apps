// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useRef, useState } from 'react';

import { StepModalHandle, StepModalStep } from '@amdenterpriseai/types';
import { ActionButton } from '../../../src/Buttons/ActionButton';
import { StepModal } from '../../../src/StepModal/StepModal';

export default {
  title: 'Components/StepModal',
} satisfies StoryDefault;

const StepBody = ({ title, body }: { title: string; body: string }) => (
  <div className="flex flex-col gap-2 py-4">
    <h3 className="text-lg font-semibold">{title}</h3>
    <p className="text-sm text-muted">{body}</p>
  </div>
);

const basicSteps: StepModalStep[] = [
  {
    label: 'Start',
    content: (
      <StepBody
        title="Welcome"
        body="Kick off the workflow. The default Next button advances to step 2."
      />
    ),
  },
  {
    label: 'Configure',
    content: (
      <StepBody
        title="Configuration"
        body="Showing the second step body with default Previous and Next actions."
      />
    ),
  },
  {
    label: 'Done',
    content: (
      <StepBody
        title="All set"
        body="Final step. The Next button is hidden by default."
      />
    ),
    hideNext: true,
  },
];

export const Basic: Story = () => {
  const [isOpen, setIsOpen] = useState(true);
  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open modal
      </ActionButton>
      <StepModal
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        initialStep={0}
        steps={basicSteps}
        allowPrevious
        size="lg"
        title="Sample wizard"
      />
    </div>
  );
};

export const WithCustomActions: Story = () => {
  const [isOpen, setIsOpen] = useState(true);
  const ref = useRef<StepModalHandle>(null);

  const steps: StepModalStep[] = [
    {
      label: 'Confirm',
      content: (
        <StepBody
          title="Confirm submission"
          body="Custom footer with a single submit button that programmatically advances."
        />
      ),
      customActions: (
        <ActionButton primary onPress={() => ref.current?.incrementStep()}>
          Submit
        </ActionButton>
      ),
    },
    {
      label: 'Result',
      content: <StepBody title="Success" body="Submitted!" />,
      customActions: (
        <ActionButton secondary onPress={() => setIsOpen(false)}>
          Close
        </ActionButton>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open modal
      </ActionButton>
      <StepModal
        ref={ref}
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        initialStep={0}
        steps={steps}
        size="lg"
        title="Custom actions"
      />
    </div>
  );
};
