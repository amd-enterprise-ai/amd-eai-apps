// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { type GlobalProvider, useLadleContext, ThemeState } from '@ladle/react';
import { ThemeProvider as NextThemesProvider } from 'next-themes';
import { MDXProvider } from '@mdx-js/react';

import '@amdenterpriseai/components/styles.css';
import './ladle-tailwind.css';
import './minimal-markdown.css';
import { Grid } from './components/Grid';
import { JSX } from './components/JSX';
import { mdxComponents } from './components/CustomMDXProvider';

const themeMap: Record<ThemeState, string> = {
  [ThemeState.Light]: 'light',
  [ThemeState.Dark]: 'dark',
  [ThemeState.Auto]: 'system',
};

// Export components for MDX global scope
export const components = {
  ...mdxComponents,
  JSX,
  Grid,
};

export const Provider: GlobalProvider = ({ children }) => {
  const { globalState } = useLadleContext();
  const theme = themeMap[globalState.theme] || 'dark';

  return (
    <NextThemesProvider
      disableTransitionOnChange
      attribute="class"
      forcedTheme={theme}
    >
      <MDXProvider components={components}>{children}</MDXProvider>
    </NextThemesProvider>
  );
};
