// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { resolve } from 'path';
import { defineConfig } from 'vite';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const ladleReactPath = require.resolve('@ladle/react');
const nextAuthStub = resolve(__dirname, './stubs/next-auth.tsx');

// No React plugin here on purpose: Ladle installs its own only when the config
// declares none, and its MDX loader can drive that one but not `plugin-react`,
// whose `transform` is a Vite 6 object hook rather than the plain function the
// loader looks for. Adding one back breaks every `.stories.mdx`.
export default defineConfig({
  root: resolve(__dirname, '..'),
  resolve: {
    alias: {
      '@': resolve(__dirname, '../'),
      '@ladle/react-original': ladleReactPath,
      '@ladle/react': resolve(__dirname, './ladle-shim.tsx'),
      '@amdenterpriseai/components': resolve(__dirname, '../src'),
      '@amdenterpriseai/assets': resolve(__dirname, '../../assets/src'),
      '@amdenterpriseai/hooks': resolve(__dirname, '../../hooks/src'),
      '@amdenterpriseai/layouts': resolve(__dirname, '../../layouts/src'),
      '@amdenterpriseai/types': resolve(__dirname, '../../types/src'),
      '@amdenterpriseai/utils': resolve(__dirname, '../../utils/src'),
      '@amdenterpriseai/tailwind-config': resolve(
        __dirname,
        '../../tailwind-config/shared-styles.css',
      ),
      // Stubs for Next.js-only dependencies that get pulled in via barrel
      // imports. The chart/UI components never use these directly, but the
      // shared package barrels re-export modules that do.
      'next-auth/react': resolve(__dirname, './stubs/next-auth-react.ts'),
      'next-auth/jwt': resolve(__dirname, './stubs/next-auth-jwt.ts'),
      'next-auth/providers/keycloak': nextAuthStub,
      'next-auth': resolve(__dirname, './stubs/next-auth.ts'),
      'next/router': resolve(__dirname, './stubs/next-router.ts'),
      'next/navigation': resolve(__dirname, './stubs/next-navigation.ts'),
      'next-i18next': resolve(__dirname, './stubs/next-i18next.ts'),
    },
  },
});
