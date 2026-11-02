// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { useState } from 'react';

import { TagInput } from '../../../src/TagInput/TagInput';

export default {
  title: 'Components/TagInput',
} satisfies StoryDefault;

export const Default: Story = () => {
  const [tags, setTags] = useState<string[]>([]);
  return (
    <div className="w-full max-w-md p-6">
      <TagInput
        label="Tags"
        value={tags}
        onChange={setTags}
        placeholder="Type and press Enter, Tab, or comma…"
      />
      <p className="mt-3 text-xs text-default-500">
        Tags: {tags.length > 0 ? tags.join(', ') : '—'}
      </p>
    </div>
  );
};

export const WithInitialTags: Story = () => {
  const [tags, setTags] = useState<string[]>(['nlp', 'vision', 'fine-tuning']);
  return (
    <div className="w-full max-w-md p-6">
      <TagInput label="Tags" value={tags} onChange={setTags} />
    </div>
  );
};

export const WithValidationLimits: Story = () => {
  const [tags, setTags] = useState<string[]>([]);
  return (
    <div className="w-full max-w-md p-6">
      <TagInput
        label="Short tags only (max 10 chars)"
        value={tags}
        onChange={setTags}
        maxTagLength={10}
        placeholder="Max 10 characters per tag"
      />
    </div>
  );
};

export const WithCustomPattern: Story = () => {
  const [tags, setTags] = useState<string[]>([]);
  return (
    <div className="w-full max-w-md p-6">
      <TagInput
        label="Lowercase letters only"
        value={tags}
        onChange={setTags}
        allowedPattern={/^[a-z]+$/}
        placeholder="Only a–z characters allowed"
      />
    </div>
  );
};

export const Disabled: Story = () => (
  <div className="w-full max-w-md p-6">
    <TagInput
      label="Tags (disabled)"
      value={['read-only', 'locked']}
      onChange={() => {}}
      isDisabled
    />
  </div>
);
