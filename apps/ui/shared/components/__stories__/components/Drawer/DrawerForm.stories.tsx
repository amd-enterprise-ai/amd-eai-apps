// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { z, type ZodType } from 'zod';

import { DrawerForm } from '../../../src/Drawer';
import { FormInput } from '../../../src/ManagedForm/FormInput';
import { ActionButton } from '../../../src/Buttons';

export default {
  title: 'Components/Drawer/DrawerForm',
} satisfies StoryDefault;

type SecretFormData = { name: string; value: string };

const secretSchema: ZodType<SecretFormData> = z.object({
  name: z.string().trim().nonempty('Name is required'),
  value: z.string().trim().nonempty('Value is required'),
});

const renderSecretFields = (form: UseFormReturn<SecretFormData>) => (
  <div className="flex flex-col gap-4">
    <FormInput<SecretFormData>
      form={form}
      name="name"
      label="Name"
      placeholder="my-secret"
      isRequired
    />
    <FormInput<SecretFormData>
      form={form}
      name="value"
      label="Value"
      placeholder="••••••••"
      isRequired
    />
  </div>
);

export const Basic: Story = () => {
  const [isOpen, setIsOpen] = useState(true);
  const [lastSubmit, setLastSubmit] = useState<SecretFormData | null>(null);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open form drawer
      </ActionButton>
      <DrawerForm<SecretFormData>
        isOpen={isOpen}
        onOpenChange={() => setIsOpen(false)}
        title="Add secret"
        confirmText="Create"
        cancelText="Cancel"
        validationSchema={secretSchema}
        defaultValues={{ name: '', value: '' }}
        onFormSuccess={(data) => {
          setLastSubmit(data);
          setIsOpen(false);
        }}
        renderFields={renderSecretFields}
      />
      {lastSubmit && (
        <pre className="text-xs p-3 bg-default rounded-lg overflow-auto">
          {JSON.stringify(lastSubmit, null, 2)}
        </pre>
      )}
    </div>
  );
};

// isActioning drives the loading state: the confirm button shows a spinner and
// the close affordance is hidden so the in-flight submit cannot be interrupted.
export const Submitting: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open form drawer
      </ActionButton>
      <DrawerForm<SecretFormData>
        isOpen={isOpen}
        isActioning
        onOpenChange={() => setIsOpen(false)}
        title="Add secret"
        confirmText="Create"
        cancelText="Cancel"
        validationSchema={secretSchema}
        defaultValues={{ name: 'in-flight', value: 'secret' }}
        onFormSuccess={() => {}}
        renderFields={renderSecretFields}
      />
    </div>
  );
};

export const DisabledConfirm: Story = () => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="flex flex-col gap-4 p-6">
      <ActionButton primary onPress={() => setIsOpen(true)}>
        Open form drawer
      </ActionButton>
      <DrawerForm<SecretFormData>
        isOpen={isOpen}
        isDisabled
        onOpenChange={() => setIsOpen(false)}
        title="Add secret"
        confirmText="Create"
        cancelText="Cancel"
        validationSchema={secretSchema}
        defaultValues={{ name: '', value: '' }}
        onFormSuccess={() => {}}
        renderFields={renderSecretFields}
      />
    </div>
  );
};
