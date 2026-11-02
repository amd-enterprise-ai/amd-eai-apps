// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import react from '@vitejs/plugin-react';

import path from 'path';
import { defineConfig as defineViteConfig, mergeConfig } from 'vite';
import { defineConfig as defineVitestConfig } from 'vitest/config';

const rootDir = __dirname;

const viteConfig = defineViteConfig({
  plugins: [react()],
  // Load-bearing for the test run, not just bundling: vitest hoists `process.env.*` define keys
  // into the real process.env, so this also pins NODE_ENV. Removing it lets a shell's
  // NODE_ENV=production load a React build with no `act` export, failing every render test.
  define: {
    'process.env.NODE_ENV': '"development"',
  },
  esbuild: {
    define: {
      'process.env.NODE_ENV': '"development"',
    },
  },
});

const vitestConfig = defineVitestConfig({
  resolve: {
    alias: {
      '@': path.resolve(rootDir, './'),
      '@amdenterpriseai/components': path.resolve(rootDir, 'src/index.ts'),
      '@amdenterpriseai/types': path.resolve(rootDir, '../types/src/index.ts'),
      '@amdenterpriseai/utils/app': path.resolve(
        rootDir,
        '../utils/src/app/index.ts',
      ),
      '@amdenterpriseai/utils/data': path.resolve(
        rootDir,
        '../utils/src/data/index.ts',
      ),
      '@amdenterpriseai/utils/server': path.resolve(
        rootDir,
        '../utils/src/server/index.ts',
      ),
      '@amdenterpriseai/utils': path.resolve(rootDir, '../utils/src/index.ts'),
      '@amdenterpriseai/hooks': path.resolve(rootDir, '../hooks/src/index.ts'),
      '@amdenterpriseai/layouts': path.resolve(
        rootDir,
        '../layouts/src/index.ts',
      ),
      '@amdenterpriseai/assets/svg/logo': path.resolve(
        rootDir,
        '../assets/src/svg/logo/index.ts',
      ),
    },
  },
  define: process.env.VITEST ? {} : { global: 'window' },
  test: {
    setupFiles: ['__tests__/setup.ts'],
    mockReset: true,
    globals: true,
    environment: 'jsdom',
    // testTimeout must stay above RTL's asyncUtilTimeout, or one waitFor can eat the whole
    // test budget; this package sets no asyncUtilTimeout, so RTL's 1s default applies.
    //
    // maxWorkers trades suite wall-time against contention on the shared self-hosted
    // runners. Vitest otherwise sizes its pool from availableParallelism, so every
    // co-located job slot on one machine claims nearly all of its cores. 25% takes a
    // 16-core runner from ~15 workers to ~4, so a fully occupied machine is ~4x
    // oversubscribed rather than ~15x, at the cost of a slower suite when the machine is
    // idle. Revisit if the slot count per machine or the runner hardware changes.
    ...(process.env.CI
      ? { testTimeout: 15_000, hookTimeout: 15_000, maxWorkers: '25%' }
      : {}),
    pool: 'threads',
    coverage: {
      provider: 'v8',
      reporter: ['html'],
      // Avoid parallel coverage tmp races (ENOENT on coverage/.tmp) in CI
      enabled: process.env.VITEST_COVERAGE === 'true',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        '__tests__/**',
        'node_modules/**',
        'dist/**',
        'coverage/**',
        'vitest.config.ts',
      ],
      thresholds: undefined,
    },
  },
});

export default mergeConfig(viteConfig, vitestConfig);
