// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';
import { z } from 'zod';

import { ActionButton } from '../../../src/Buttons/ActionButton';
import { Input } from '../../../src/Input/InputPrimitive';
import { FormInput } from '../../../src/ManagedForm/FormInput';
import ManagedForm from '../../../src/ManagedForm/ManagedForm';
import { Wizard } from '../../../src/Wizard/Wizard';

export default {
  title: 'Components/Wizard',
} satisfies StoryDefault;

const deploymentSchema = z.object({
  modelFamily: z.string().min(1, 'Model family is required'),
  modelVersion: z.string().min(1, 'Model version is required'),
  lora: z.string().optional(),
  cluster: z.string().min(1, 'Cluster is required'),
});
const modelStepSchema = deploymentSchema.pick({
  modelFamily: true,
  modelVersion: true,
});
const targetStepSchema = deploymentSchema.pick({ cluster: true });

type Deployment = z.infer<typeof deploymentSchema>;

const deploymentDefaults = {
  modelFamily: '',
  modelVersion: '',
  lora: '',
  cluster: '',
};

const DeploymentWizard = ({
  title,
  description,
  onClose,
}: {
  title?: string;
  description?: string;
  onClose: () => void;
}) => {
  const complete = (values: Deployment) => {
    // eslint-disable-next-line no-console
    console.log('Wizard complete', values);
    onClose();
  };

  return (
    <ManagedForm<Deployment>
      validationSchema={deploymentSchema}
      defaultValues={deploymentDefaults}
      onFormSuccess={complete}
      renderFields={(form) => {
        const values = { ...deploymentDefaults, ...form.watch() };
        return (
          <Wizard
            title={title}
            description={description}
            onClose={onClose}
            onComplete={() => form.handleSubmit(complete)()}
          >
            <Wizard.Step
              id="model"
              title="Model"
              description="Select model and container version"
              canProceed={modelStepSchema.safeParse(values).success}
              renderSummary={() => (
                <>
                  <Wizard.SummaryRow
                    label="Model family"
                    value={values.modelFamily}
                  />
                  <Wizard.SummaryRow
                    label="Model version"
                    value={values.modelVersion}
                  />
                </>
              )}
            >
              <FormInput
                form={form}
                name="modelFamily"
                label="Model family"
                placeholder="Command"
              />
              <FormInput
                form={form}
                name="modelVersion"
                label="Model version"
                placeholder="1.0.0"
              />
            </Wizard.Step>
            <Wizard.Step
              id="personalization"
              title="Personalization"
              description="Optional model personalization"
              isOptional
              renderSummary={() => (
                <Wizard.SummaryRow
                  label="LoRA"
                  value={values.lora || 'Skipped'}
                />
              )}
            >
              <FormInput
                form={form}
                name="lora"
                label="LoRA"
                placeholder="Optional LoRA"
              />
            </Wizard.Step>
            <Wizard.Step
              id="target"
              title="Target"
              description="Select deployment target"
              canProceed={targetStepSchema.safeParse(values).success}
              renderSummary={() => (
                <Wizard.SummaryRow label="Cluster" value={values.cluster} />
              )}
            >
              <FormInput
                form={form}
                name="cluster"
                label="Cluster"
                placeholder="production"
              />
            </Wizard.Step>
          </Wizard>
        );
      }}
    />
  );
};

/** Wizard owns the fullscreen modal; mounting it opens a new flow. */
export const Default: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open wizard
      </ActionButton>
      {isOpen ? (
        <DeploymentWizard
          title="Model deployment"
          description="Get a model deployed"
          onClose={() => setIsOpen(false)}
        />
      ) : null}
    </div>
  );
};

const stateDeploymentSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  replicas: z
    .string()
    .regex(/^\d+$/, 'Replicas must be a number')
    .regex(/^[1-9]\d*$/, 'Enter at least one replica'),
  // A single replica never rolls out, so the finished deployment may leave this
  // empty; the step that collects it demands a value while it is on screen.
  rollout: z.string(),
});
const stateNameSchema = stateDeploymentSchema.pick({ name: true });
const stateReplicasSchema = stateDeploymentSchema.pick({ replicas: true });

type StateDeployment = z.infer<typeof stateDeploymentSchema>;

const stateDeploymentDefaults: StateDeployment = {
  name: '',
  replicas: '',
  rollout: '',
};

/** React state, Zod validation, conditional steps, and an asynchronous step action. */
export const WithUseStateAndZod: Story = () => {
  const [isOpen, setIsOpen] = useState(true);
  const [values, setValues] = useState<StateDeployment>(
    stateDeploymentDefaults,
  );
  const [submitted, setSubmitted] = useState<StateDeployment>();
  const [isDeployed, setIsDeployed] = useState(false);

  const complete = () => {
    const result = stateDeploymentSchema.safeParse(values);
    if (result.success) {
      setSubmitted(result.data);
      setIsOpen(false);
    }
  };

  const open = () => {
    setValues(stateDeploymentDefaults);
    setIsDeployed(false);
    setIsOpen(true);
  };

  const replicasCheck = stateReplicasSchema.safeParse(values);
  // Held back until the user has typed, so the step does not open in an error state.
  const replicasError =
    values.replicas !== '' && !replicasCheck.success
      ? replicasCheck.error.issues[0]?.message
      : undefined;

  return (
    <div className="flex flex-col gap-4 p-6">
      {submitted ? (
        <p className="text-sm text-success">
          Submitted {submitted.name} with {submitted.replicas} replicas
        </p>
      ) : null}
      <ActionButton primary onPress={open}>
        Open wizard
      </ActionButton>
      {isOpen ? (
        <Wizard
          title="Deploy with useState"
          description="Zod validates plain React state without a form library"
          onClose={() => setIsOpen(false)}
          onComplete={complete}
        >
          <Wizard.Step
            id="name"
            title="Workload"
            canProceed={stateNameSchema.safeParse(values).success}
            renderSummary={() => (
              <Wizard.SummaryRow label="Name" value={values.name} />
            )}
          >
            <Input
              label="Workload name"
              value={values.name}
              onValueChange={(name) =>
                setValues((current) => ({ ...current, name }))
              }
            />
          </Wizard.Step>
          <Wizard.Step
            id="capacity"
            title="Capacity"
            description="Controls the conditional step; try 1 or a larger number"
            canProceed={replicasCheck.success}
            renderSummary={() => (
              <Wizard.SummaryRow label="Replicas" value={values.replicas} />
            )}
          >
            <Input
              label="Replicas"
              inputMode="numeric"
              value={values.replicas}
              isInvalid={replicasError !== undefined}
              errorMessage={replicasError}
              onValueChange={(replicas) =>
                setValues((current) => ({ ...current, replicas }))
              }
            />
          </Wizard.Step>
          {Number(values.replicas) > 1 && (
            <Wizard.Step
              id="rollout"
              title="Rollout"
              description="Asked for only once a deployment has replicas to roll out"
              canProceed={values.rollout !== ''}
              renderSummary={() => (
                <Wizard.SummaryRow label="Strategy" value={values.rollout} />
              )}
            >
              <Input
                label="Rollout strategy"
                placeholder="rolling"
                value={values.rollout}
                onValueChange={(rollout) =>
                  setValues((current) => ({ ...current, rollout }))
                }
              />
            </Wizard.Step>
          )}
          <Wizard.Step
            id="deploy"
            title="Deploy"
            description="Runs an asynchronous action before advancing"
            onNext={async () => {
              await new Promise((resolve) => setTimeout(resolve, 600));
              setIsDeployed(true);
            }}
            renderSummary={() => (
              <Wizard.SummaryRow
                label="Status"
                value={isDeployed ? 'Deployed' : 'Not deployed'}
              />
            )}
          >
            <p className="text-sm text-muted">
              Click Next to simulate deploying the workload.
            </p>
          </Wizard.Step>
        </Wizard>
      ) : null}
    </div>
  );
};
