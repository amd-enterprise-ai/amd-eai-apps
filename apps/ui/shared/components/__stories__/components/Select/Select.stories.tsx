// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';
import type { Selection } from '../../../src/Select';
import { Select, SelectItem } from '../../../src/Select';

export default { title: 'Components/Select' } satisfies StoryDefault;

const options = [
  { key: 'apple', label: 'Apple' },
  { key: 'banana', label: 'Banana' },
];

export const SingleFlat: Story = () => {
  const [selected, setSelected] = useState<Selection>(new Set(['apple']));
  return (
    <div className="w-64 p-4">
      <Select
        label="Fruit"
        selectedKeys={selected}
        onSelectionChange={setSelected}
      >
        {options.map((o) => (
          <SelectItem key={o.key}>{o.label}</SelectItem>
        ))}
      </Select>
    </div>
  );
};

export const SingleCompound: Story = () => {
  const [selected, setSelected] = useState<Selection>(new Set(['banana']));
  return (
    <div className="w-64 p-4">
      <Select
        label="Fruit"
        selectedKeys={selected}
        onSelectionChange={setSelected}
      >
        {options.map((o) => (
          <Select.Item key={o.key}>{o.label}</Select.Item>
        ))}
      </Select>
    </div>
  );
};

export const Multiple: Story = () => {
  const [selected, setSelected] = useState<Selection>(
    new Set(['apple', 'banana']),
  );
  return (
    <div className="w-64 p-4">
      <Select
        label="Fruits"
        selectionMode="multiple"
        selectedKeys={selected}
        onSelectionChange={setSelected}
      >
        {options.map((o) => (
          <SelectItem key={o.key}>{o.label}</SelectItem>
        ))}
      </Select>
    </div>
  );
};

const modelOptions = [
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

export const WithItemDescription: Story = () => {
  const [selectedDefault, setSelectedDefault] = useState<Selection>(
    new Set(['running']),
  );
  const [selectedInTrigger, setSelectedInTrigger] = useState<Selection>(
    new Set(['running']),
  );
  return (
    <div className="flex w-full max-w-md flex-col gap-6 p-4">
      <Select
        label="Label only in trigger (default)"
        selectedKeys={selectedDefault}
        onSelectionChange={setSelectedDefault}
      >
        {modelOptions.map((o) => (
          <SelectItem key={o.key} description={o.description}>
            {o.label}
          </SelectItem>
        ))}
      </Select>
      <Select
        label="Label and description in trigger"
        selectedKeys={selectedInTrigger}
        onSelectionChange={setSelectedInTrigger}
        showDescriptionInTrigger
      >
        {modelOptions.map((o) => (
          <SelectItem key={o.key} description={o.description}>
            {o.label}
          </SelectItem>
        ))}
      </Select>
    </div>
  );
};

export const Variants: Story = () => {
  const [selectedPrimary, setSelectedPrimary] = useState<Selection>(
    new Set(['apple']),
  );
  const [selectedSecondary, setSelectedSecondary] = useState<Selection>(
    new Set(['apple']),
  );
  return (
    <div className="flex w-full max-w-md flex-col gap-4 p-4">
      <Select
        label="Primary"
        variant="primary"
        selectedKeys={selectedPrimary}
        onSelectionChange={setSelectedPrimary}
      >
        {options.map((o) => (
          <SelectItem key={o.key}>{o.label}</SelectItem>
        ))}
      </Select>
      <Select
        label="Secondary (default)"
        selectedKeys={selectedSecondary}
        onSelectionChange={setSelectedSecondary}
      >
        {options.map((o) => (
          <SelectItem key={o.key}>{o.label}</SelectItem>
        ))}
      </Select>
    </div>
  );
};

const manyOptions = Array.from({ length: 20 }, (_, index) => ({
  key: `item-${index + 1}`,
  label: `Option ${index + 1}`,
}));

export const WithTopAndBottomSlots: Story = () => {
  const [selected, setSelected] = useState<Selection>(new Set(['item-1']));
  return (
    <div className="w-64 p-4">
      <Select
        label="Fruit"
        selectedKeys={selected}
        onSelectionChange={setSelected}
        topContent={
          <p className="text-sm text-muted">Pinned search or filter area</p>
        }
        bottomContent={
          <button
            type="button"
            className="w-full text-start text-sm text-accent"
          >
            Add new option
          </button>
        }
      >
        {manyOptions.map((o) => (
          <SelectItem key={o.key}>{o.label}</SelectItem>
        ))}
      </Select>
    </div>
  );
};
