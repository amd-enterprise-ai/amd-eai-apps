// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';

import { Radio, RadioGroup } from '../../../src/Radio';

export default { title: 'Components/RadioGroup' } satisfies StoryDefault;

export const Default: Story = () => (
  <RadioGroup
    label="Deployment preference"
    description="Choose how the deployment should balance resources."
    defaultValue="balanced"
  >
    <Radio value="balanced">Balanced</Radio>
    <Radio value="performance">Performance</Radio>
    <Radio value="efficiency">Efficiency</Radio>
  </RadioGroup>
);

export const Horizontal: Story = () => (
  <RadioGroup
    label="Performance mode"
    tooltipContent="Choose whether to optimize for latency or throughput, or select a profile manually."
    defaultValue="latency"
    orientation="horizontal"
    className="w-full"
  >
    <Radio
      value="latency"
      className="flex-1"
      description="Optimizes response time for interactive workloads."
    >
      Latency
    </Radio>
    <Radio
      value="throughput"
      className="flex-1"
      description="Optimizes total output for batch workloads."
    >
      Throughput
    </Radio>
    <Radio
      value="advanced"
      className="flex-1"
      description="Select the deployment profile manually."
    >
      Advanced
    </Radio>
  </RadioGroup>
);

export const WithDescription: Story = () => (
  <RadioGroup aria-label="Visibility" defaultValue="private">
    <Radio
      value="private"
      description="Only members of your project can use it."
    >
      Private
    </Radio>
    <Radio value="public" description="Anyone in your organization can use it.">
      Public
    </Radio>
  </RadioGroup>
);

export const WrappingLabel: Story = () => (
  <RadioGroup
    aria-label="Resource allocation"
    defaultValue="automatic"
    className="max-w-xs"
  >
    <Radio
      value="automatic"
      description="Resources are selected from the available deployment profiles."
    >
      Automatically choose the best available accelerator and deployment profile
    </Radio>
    <Radio value="manual" description="Choose all resource settings yourself.">
      Configure resources manually
    </Radio>
  </RadioGroup>
);

export const Disabled: Story = () => (
  <RadioGroup aria-label="Disabled options" defaultValue="selected">
    <Radio value="selected" isDisabled>
      Selected
    </Radio>
    <Radio value="unselected" isDisabled>
      Unselected
    </Radio>
  </RadioGroup>
);

export const Interactive: Story = () => {
  const [value, setValue] = useState<string | null>('balanced');

  return (
    <div className="flex flex-col gap-4">
      <RadioGroup
        aria-label="Interactive preference"
        value={value}
        onChange={setValue}
      >
        <Radio value="balanced">Balanced</Radio>
        <Radio value="performance">Performance</Radio>
      </RadioGroup>
      <span className="text-sm text-muted">Selected: {value ?? 'none'}</span>
    </div>
  );
};
