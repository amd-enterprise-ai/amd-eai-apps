// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { cn } from '@heroui/react';
import React from 'react';

export interface CodeBlockProps extends React.HTMLAttributes<HTMLElement> {
  children: React.ReactNode;
  className?: string;
  as?: 'code' | 'pre';
  /** Accepted for v2 `Code` compatibility; styling is fixed in v3. */
  size?: 'sm' | 'md' | 'lg';
}

// HeroUI v3 removes the `Code` component, so this renders plain `code`/`pre`
// elements styled to match the previous inline-code look. The `as` prop lets
// callers reuse the same styling for block (`pre`) or inline (`code`) content.
export const CodeBlock = ({
  children,
  className,
  as: As = 'code',
  size: _size,
  ...rest
}: CodeBlockProps): React.JSX.Element => (
  <As
    className={cn(
      'rounded-sm bg-surface-secondary px-1.5 py-0.5 font-mono text-sm text-foreground',
      As === 'pre' && 'block overflow-x-auto whitespace-pre px-3 py-2',
      className,
    )}
    {...rest}
  >
    {children}
  </As>
);

CodeBlock.displayName = 'CodeBlock';
