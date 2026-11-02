// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';
import { Switch } from '../../../src/Switch';
export default { title: 'Components/Switch' } satisfies StoryDefault;
export const Unselected: Story = () => <Switch isSelected={false}>Off</Switch>;
export const Selected: Story = () => <Switch isSelected>On</Switch>;
export const Disabled: Story = () => (
  <div className="flex flex-col gap-4">
    <Switch isDisabled isSelected={false}>
      Disabled off
    </Switch>
    <Switch isDisabled isSelected>
      Disabled on
    </Switch>
  </div>
);
export const Interactive: Story = () => {
  const [isSelected, setIsSelected] = useState(false);
  return (
    <Switch isSelected={isSelected} onValueChange={setIsSelected}>
      Toggle
    </Switch>
  );
};
export const WithDescription: Story = () => (
  <Switch
    isSelected={false}
    description="Allow others to see your profile information"
  >
    Public profile
  </Switch>
);
