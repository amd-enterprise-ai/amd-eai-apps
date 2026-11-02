// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import type { Story, StoryDefault } from '@ladle/react';
import { Textarea } from '../../../src/Textarea';
export default { title: 'Components/Textarea' } satisfies StoryDefault;
export const Default: Story = () => (
  <div className="w-full max-w-md p-4">
    <Textarea
      label="Description"
      placeholder="Enter a description"
      minRows={3}
    />
  </div>
);
export const WithValue: Story = () => (
  <div className="w-full max-w-md p-4">
    <Textarea
      label="Secret value"
      value="pre-filled content"
      minRows={4}
      onChange={() => undefined}
    />
  </div>
);
export const Disabled: Story = () => (
  <div className="w-full max-w-md p-4">
    <Textarea
      label="Description"
      value="Read-only content"
      minRows={3}
      isDisabled
    />
  </div>
);
export const Variants: Story = () => (
  <div className="flex w-full max-w-md flex-col gap-4 p-4">
    <Textarea
      label="Primary"
      placeholder="Page background"
      minRows={3}
      variant="primary"
    />
    <Textarea
      label="Secondary (default)"
      placeholder="Modal / drawer"
      minRows={3}
    />
  </div>
);
