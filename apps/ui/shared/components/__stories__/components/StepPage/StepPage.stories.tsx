// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useRef, useState } from 'react';

import { StepPageHandle, StepPageStep } from '@amdenterpriseai/types';

import { ActionButton } from '../../../src/Buttons/ActionButton';
import { StepPage } from '../../../src/StepPage/StepPage';

export default {
  title: 'Components/StepPage',
} satisfies StoryDefault;

const FormSection = ({
  title,
  fields,
}: {
  title: string;
  fields: string[];
}) => (
  <section className="flex flex-col gap-4 rounded-lg border border-default bg-surface p-6">
    <h2 className="text-xl font-semibold">{title}</h2>
    <div className="grid grid-cols-1 gap-3">
      {fields.map((field) => (
        <label
          key={field}
          className="flex flex-col gap-1 text-sm text-foreground"
        >
          {field}
          <input
            type="text"
            placeholder={`Enter ${field.toLowerCase()}…`}
            className="rounded border border-default bg-surface-secondary px-3 py-2"
          />
        </label>
      ))}
    </div>
  </section>
);

const wizardSteps: StepPageStep[] = [
  {
    label: 'Model source',
    content: (
      <FormSection
        title="Model source"
        fields={['Model source address', 'Hugging Face token']}
      />
    ),
    nextActionLabel: 'Next - Define profile',
  },
  {
    label: 'Model information',
    content: (
      <FormSection
        title="Model information"
        fields={['Display name', 'Description', 'Tags']}
      />
    ),
  },
  {
    label: 'Runtime profile',
    content: (
      <FormSection
        title="Runtime profile"
        fields={['Container image', 'Container version', 'Accelerator']}
      />
    ),
    nextActionLabel: 'Save and start onboarding',
    hideNext: true,
  },
];

export const ThreeStepWizard: Story = () => (
  <div className="mx-auto w-full max-w-4xl p-6">
    <StepPage steps={wizardSteps} />
  </div>
);

export const StartingOnLastStep: Story = () => (
  <div className="mx-auto w-full max-w-4xl p-6">
    <StepPage steps={wizardSteps} initialStep={2} />
  </div>
);

export const WithCustomActions: Story = () => {
  const ref = useRef<StepPageHandle>(null);

  const steps: StepPageStep[] = [
    {
      label: 'Form',
      content: <FormSection title="Form" fields={['Name', 'Email']} />,
      customActions: (
        <div className="flex gap-2">
          <ActionButton secondary>Discard changes</ActionButton>
          <ActionButton primary onPress={() => ref.current?.incrementStep()}>
            Save and continue
          </ActionButton>
        </div>
      ),
    },
    {
      label: 'Confirm',
      content: <FormSection title="Confirm" fields={['Notes']} />,
      customActions: (
        <ActionButton primary onPress={() => alert('Submitted!')}>
          Submit
        </ActionButton>
      ),
    },
  ];

  return (
    <div className="mx-auto w-full max-w-4xl p-6">
      <StepPage ref={ref} steps={steps} />
    </div>
  );
};

export const AsyncTransition: Story = () => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const ref = useRef<StepPageHandle>(null);

  const steps: StepPageStep[] = [
    {
      label: 'Step 1',
      content: <FormSection title="Step 1" fields={['Field A', 'Field B']} />,
      onStepChange: () => {
        setIsSubmitting(true);
        setTimeout(() => {
          setIsSubmitting(false);
          ref.current?.incrementStep();
        }, 1500);
      },
    },
    {
      label: 'Step 2',
      content: <FormSection title="Step 2" fields={['Field C']} />,
    },
  ];

  return (
    <div className="mx-auto w-full max-w-4xl p-6">
      <StepPage ref={ref} steps={steps} isActioning={isSubmitting} />
    </div>
  );
};
