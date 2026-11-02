// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { CodeBlock } from '../src/CodeBlock';

export default { title: 'Components/CodeBlock' } satisfies StoryDefault;

export const InlineCode: Story = () => (
  <div className="flex w-full max-w-md flex-col gap-4 p-4">
    <p className="text-sm">
      Run <CodeBlock as="code">pnpm install</CodeBlock> to get started.
    </p>
  </div>
);

export const BlockCode: Story = () => (
  <div className="flex w-full max-w-md flex-col gap-4 p-4">
    <CodeBlock as="pre" className="block w-full p-4">
      {`const answer = 42;\nconsole.log(answer);`}
    </CodeBlock>
  </div>
);

export const CustomClassName: Story = () => (
  <div className="flex w-full max-w-md flex-col gap-4 p-4">
    <CodeBlock as="code" className="text-accent">
      themed inline code
    </CodeBlock>
  </div>
);
