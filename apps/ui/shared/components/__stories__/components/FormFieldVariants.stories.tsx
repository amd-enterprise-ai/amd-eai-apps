// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';

import { Input } from '../../src/Input/InputPrimitive';
import { NumberField } from '../../src/NumberField/NumberField';
import type { Selection } from '../../src/Select';
import { Select, SelectItem } from '../../src/Select';
import { Textarea } from '../../src/Textarea/Textarea';

export default {
  title: 'Components/FormFieldVariants',
} satisfies StoryDefault;

const selectOptions = [
  {
    key: 'running',
    label: 'Inference Running',
    description: '1.0.0 · Throughput',
  },
  {
    key: 'pending',
    label: 'Inference Pending',
    description: '2.0.0 · Latency',
  },
];

const FieldRow = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <div className="flex flex-col gap-3">
    <h3 className="text-sm font-medium text-muted">{title}</h3>
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      {children}
    </div>
  </div>
);

const SelectDemo = ({ variant }: { variant?: 'primary' | 'secondary' }) => {
  const [selected, setSelected] = useState<Selection>(new Set(['running']));
  return (
    <Select
      label="Model"
      className="w-full max-w-xs"
      variant={variant}
      selectedKeys={selected}
      onSelectionChange={setSelected}
    >
      {selectOptions.map((option) => (
        <SelectItem key={option.key} description={option.description}>
          {option.label}
        </SelectItem>
      ))}
    </Select>
  );
};

export const DefaultSecondary: Story = () => (
  <div className="flex flex-col gap-8 p-8">
    <FieldRow title="No variant prop (defaults to secondary)">
      <Input label="Input" placeholder="Enter text…" />
      <SelectDemo />
      <Textarea label="Textarea" placeholder="Enter description" minRows={3} />
      <NumberField
        label="Replicas"
        defaultValue={2}
        minValue={0}
        maxValue={10}
      />
    </FieldRow>
  </div>
);

export const PagePrimary: Story = () => (
  <div className="bg-background flex flex-col gap-8 p-8">
    <FieldRow title="variant=&quot;primary&quot; on page background">
      <Input label="Input" placeholder="Enter text…" variant="primary" />
      <SelectDemo variant="primary" />
      <Textarea
        label="Textarea"
        placeholder="Enter description"
        minRows={3}
        variant="primary"
      />
      <NumberField
        label="Replicas"
        defaultValue={2}
        minValue={0}
        maxValue={10}
        variant="primary"
      />
    </FieldRow>
  </div>
);

export const ComparePrimarySecondary: Story = () => (
  <div className="flex flex-col gap-10 p-8">
    <FieldRow title="Primary vs secondary — Input">
      <Input label="Primary" placeholder="Page background" variant="primary" />
      <Input
        label="Secondary"
        placeholder="Modal / drawer"
        variant="secondary"
      />
    </FieldRow>
    <FieldRow title="Primary vs secondary — Select">
      <SelectDemo variant="primary" />
      <SelectDemo variant="secondary" />
    </FieldRow>
    <FieldRow title="Primary vs secondary — Textarea">
      <Textarea
        label="Primary"
        placeholder="Page background"
        minRows={3}
        variant="primary"
      />
      <Textarea
        label="Secondary"
        placeholder="Modal / drawer"
        minRows={3}
        variant="secondary"
      />
    </FieldRow>
    <FieldRow title="Primary vs secondary — NumberField">
      <NumberField
        label="Primary"
        defaultValue={2}
        minValue={0}
        maxValue={10}
        variant="primary"
      />
      <NumberField
        label="Secondary"
        defaultValue={2}
        minValue={0}
        maxValue={10}
        variant="secondary"
      />
    </FieldRow>
  </div>
);
