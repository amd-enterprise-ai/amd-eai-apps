// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import React, { useState } from 'react';
import { Slider } from '../src/Slider';

export default { title: 'Components/Slider' } satisfies StoryDefault;

export const SingleValue: Story = () => {
  const [value, setValue] = useState(0.5);
  return (
    <div className="w-80 p-4">
      <Slider
        aria-label="Temperature"
        value={value}
        minValue={0}
        maxValue={1}
        step={0.05}
        onChange={(n) => typeof n === 'number' && setValue(n)}
      />
      <p className="mt-2 text-sm text-muted">Value: {value}</p>
    </div>
  );
};

export const Range: Story = () => {
  const [value, setValue] = useState<[number, number]>([20, 80]);
  return (
    <div className="w-80 p-4">
      <Slider
        aria-label="Replica range"
        value={value}
        minValue={0}
        maxValue={100}
        step={1}
        onChange={(n) => {
          if (Array.isArray(n)) setValue(n as [number, number]);
        }}
      />
      <p className="mt-2 text-sm text-muted">
        Range: {value[0]} – {value[1]}
      </p>
    </div>
  );
};

export const Disabled: Story = () => (
  <div className="w-80 p-4">
    <Slider
      aria-label="Disabled slider"
      value={40}
      minValue={0}
      maxValue={100}
      step={5}
      isDisabled
    />
  </div>
);
