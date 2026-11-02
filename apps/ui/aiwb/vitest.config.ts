// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import react from '@vitejs/plugin-react';

import path from 'path';
import { defineConfig as defineViteConfig, mergeConfig } from 'vite';
import { defineConfig as defineVitestConfig } from 'vitest/config';

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
      '@': path.resolve(__dirname, './'),
    },
  },
  define: process.env.VITEST ? {} : { global: 'window' },
  test: {
    setupFiles: ['__tests__/setup.ts'],
    mockReset: true,
    globals: true,
    environment: 'jsdom',
    // The test budget must exceed the RTL asyncUtilTimeout (15s, see __tests__/setup.ts):
    // otherwise a single waitFor can consume the whole budget, and a slow CI runner kills
    // the test at the budget before that waitFor finishes.
    //
    // maxWorkers trades suite wall-time against contention on the shared self-hosted
    // runners. Vitest otherwise sizes its pool from availableParallelism, so every
    // co-located job slot on one machine claims nearly all of its cores. 25% takes a
    // 16-core runner from ~15 workers to ~4, so a fully occupied machine is ~4x
    // oversubscribed rather than ~15x, at the cost of a slower suite when the machine is
    // idle. Revisit if the slot count per machine or the runner hardware changes.
    ...(process.env.CI
      ? { testTimeout: 20_000, hookTimeout: 20_000, maxWorkers: '25%' }
      : {}),
    alias: {
      '\\.(gif|ttf|eot|svg|png)$': '<rootDir>/__mocks__/fileMock.js',
    },
    pool: 'threads',
    coverage: {
      provider: 'v8',
      reporter: ['html'],
      enabled: true,
      include: ['**/*.{ts,tsx}'],
      exclude: [
        'app/api/**',
        '__tests__/**',
        '__mocks__/**',
        '.next/**',
        'node_modules/**',
        'dist/**',
        'coverage/**',
        'vite.config.ts',
        'vitest.config.ts',
        'components/shared/Metrics/**/{AreaChart,BarChart,LineChart,CategoryBar}.tsx', // trust tremor chart component to be tested
        'utils/app/tremor-charts/*.ts', // trust tremor charts have been tested
        '*.js',
      ],
      // Coverage baseline (from CI `pnpm test --coverage`, rounded down slightly). Raise when coverage
      // improves; avoid small upticks that fail CI (see git history for last adjustment).
      thresholds: {
        statements: 59,
        branches: 53.5,
        functions: 59.5,
        lines: 59.5,
        'components/shared/**/*.{ts,tsx}': {
          statements: 68.8,
          branches: 60.5,
          functions: 68.9,
          lines: 67.6,
        },
        'components/features/**/*.{ts,tsx}': {
          statements: 71,
          branches: 44,
          functions: 68,
          lines: 67,
        },
        'pages/**/*.{ts,tsx}': {
          statements: 49.9,
          branches: 33.6,
          functions: 48.2,
          lines: 50.3,
        },
        'hooks/**/*.{ts,tsx}': {
          statements: 65,
          branches: 54,
          functions: 57,
          lines: 67,
        },
        'utils/**/*.{ts,tsx}': {
          statements: 67.7,
          branches: 55,
          functions: 77.4,
          lines: 67.6,
        },
      },
    },
  },
});

export default mergeConfig(viteConfig, vitestConfig);
