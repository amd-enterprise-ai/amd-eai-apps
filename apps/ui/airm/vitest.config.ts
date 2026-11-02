// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import react from '@vitejs/plugin-react';

import path from 'path';
import { defineConfig as defineViteConfig, mergeConfig } from 'vite';
import { defineConfig as defineVitestConfig } from 'vitest/config';

// Vitest only defaults NODE_ENV to 'test' when it is unset, so a value inherited from the
// developer's shell wins silently. Under a production value React's CJS entrypoint loads a build
// with no `act` export, and every @testing-library render fails — locally only, which makes the
// suite disagree with CI in a way that reads as a regression. Only 'production' trips this, so
// the sibling UI packages are equally safe pinning 'development' via a `process.env.NODE_ENV` key
// in their vite `define` block, which vitest hoists into the real process.env. That path works
// but leans on an undocumented vitest internal; assigning here states the intent directly.
// The cast is required because Next.js declares NODE_ENV read-only on NodeJS.ProcessEnv.
(process.env as { NODE_ENV?: string }).NODE_ENV = 'test';

const viteConfig = defineViteConfig({
  plugins: [react()],
});

const vitestConfig = defineVitestConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
    },
  },
  define: process.env.VITEST ? {} : { global: 'window' },
  test: {
    testTimeout: 20000, // Must exceed RTL asyncUtilTimeout (15s, see __tests__/setup.ts): slow CI runners otherwise kill heavy HeroUI/React-Aria tests at the test budget before their waitFor finishes
    setupFiles: ['__tests__/setup.ts'],
    mockReset: true,
    globals: true,
    environment: 'jsdom',
    alias: {
      '\\.(gif|ttf|eot|svg|png)$': '<rootDir>/__mocks__/fileMock.js',
    },
    // maxWorkers trades suite wall-time against contention on the shared self-hosted
    // runners. Vitest otherwise sizes its pool from availableParallelism, so every
    // co-located job slot on one machine claims nearly all of its cores. 25% takes a
    // 16-core runner from ~15 workers to ~4, so a fully occupied machine is ~4x
    // oversubscribed rather than ~15x, at the cost of a slower suite when the machine is
    // idle. Revisit if the slot count per machine or the runner hardware changes.
    ...(process.env.CI ? { maxWorkers: '25%' } : {}),
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
      thresholds: {
        statements: 70.9,
        branches: 58.5,
        functions: 71.4,
        lines: 71.1,
        'components/shared/**/*.{ts,tsx}': {
          statements: 68.8,
          branches: 60.5,
          functions: 68.9,
          lines: 67.6,
        },
        'components/features/**/*.{ts,tsx}': {
          statements: 84,
          branches: 44,
          functions: 78,
          lines: 67,
        },
        'pages/**/*.{ts,tsx}': {
          statements: 66,
          branches: 42,
          functions: 63,
          lines: 67,
        },
        'hooks/**/*.{ts,tsx}': {
          statements: 65,
          branches: 71,
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
