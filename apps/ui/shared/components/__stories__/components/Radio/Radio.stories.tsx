// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';

import { Radio, RadioGroup } from '../../../src/Radio';

export default { title: 'Components/Radio' } satisfies StoryDefault;

export const WithDescription: Story = () => (
  <RadioGroup
    aria-label="Deployment preference"
    defaultValue="automatic"
    className="max-w-xs"
  >
    <Radio
      value="automatic"
      description="Selects the best available deployment profile."
    >
      Automatically select the best accelerator and deployment profile
    </Radio>
  </RadioGroup>
);
