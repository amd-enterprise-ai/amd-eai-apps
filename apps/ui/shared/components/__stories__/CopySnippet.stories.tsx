// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';

import { CopySnippet } from '../src/CopySnippet';

export default { title: 'Components/CopySnippet' } satisfies StoryDefault;

export const Default: Story = () => (
  <CopySnippet>npm install @amdenterpriseai/components</CopySnippet>
);

export const WithDescription: Story = () => (
  <CopySnippet
    label="API endpoint"
    description="Use this URL from within your cluster network."
  >
    https://api.example.com/v1/chat/completions
  </CopySnippet>
);

export const HideCopyButton: Story = () => (
  <CopySnippet hideCopyButton>
    https://api.example.com/v1/chat/completions
  </CopySnippet>
);

export const ButtonOnly: Story = () => (
  <CopySnippet buttonOnly value="https://api.example.com/v1/chat/completions" />
);
