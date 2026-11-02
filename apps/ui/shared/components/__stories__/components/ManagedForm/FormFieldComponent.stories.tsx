// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/// <reference types="vite/client" />

import type { Story, StoryDefault } from '@ladle/react';
import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';

import formFieldComponentSource from '../../../src/ManagedForm/FormFieldComponent.tsx?raw';

function extractJsDoc(source: string): string {
  const match = source.match(/\/\*\*([\s\S]*?)\*\//);
  if (!match) return '';
  return match[1]
    .split('\n')
    .map((line) => line.replace(/^\s*\*\s?/, '').trimEnd())
    .join('\n')
    .trim();
}

export default {
  title: 'Components/ManagedForm/FormFieldComponent',
} satisfies StoryDefault;

export const FormFieldComponentBestPractices: Story = () => {
  const jsDoc = useMemo(() => extractJsDoc(formFieldComponentSource), []);

  return (
    <div className="max-w-2xl">
      {jsDoc && (
        <div className="prose prose-sm dark:prose-invert max-w-none text-muted">
          <ReactMarkdown>{jsDoc}</ReactMarkdown>
        </div>
      )}
    </div>
  );
};
