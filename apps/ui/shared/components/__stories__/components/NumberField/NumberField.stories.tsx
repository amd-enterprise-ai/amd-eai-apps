// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import type { Story, StoryDefault } from '@ladle/react';
import { NumberField, NumberInput } from '../../../src/NumberField';
export default { title: 'Components/NumberField' } satisfies StoryDefault;
export const NumberFieldDefault: Story = () => (
  <div className="w-full max-w-xs p-4">
    <NumberField
      label="Replicas"
      defaultValue={2}
      minValue={0}
      maxValue={10}
      step={1}
    />
  </div>
);
export const NumberInputAlias: Story = () => (
  <div className="w-full max-w-xs p-4">
    <NumberInput
      label="Replicas (v2 alias)"
      defaultValue={1}
      minValue={0}
      maxValue={10}
      step={1}
    />
  </div>
);
export const Disabled: Story = () => (
  <div className="w-full max-w-xs p-4">
    <NumberField label="Replicas" defaultValue={3} step={1} isDisabled />
  </div>
);
export const Variants: Story = () => (
  <div className="flex w-full max-w-xs flex-col gap-4 p-4">
    <NumberField
      label="Primary"
      defaultValue={2}
      minValue={0}
      maxValue={10}
      variant="primary"
    />
    <NumberField
      label="Secondary (default)"
      defaultValue={2}
      minValue={0}
      maxValue={10}
    />
  </div>
);
export const NarrowContainer: Story = () => (
  <div className="flex w-48 gap-2 border p-2">
    <div className="min-w-0 flex-1 bg-default-100 p-2">flex sibling</div>
    <NumberField
      aria-label="Replicas"
      defaultValue={42}
      className="min-w-0 flex-1"
    />
  </div>
);
