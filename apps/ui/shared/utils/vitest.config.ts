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
        '__tests__/**',
        '__mocks__/**',
        '.next/**',
        'node_modules/**',
        'dist/**',
        'coverage/**',
        'vite.config.ts',
        'vitest.config.ts',
        'src/app/tremor-charts/*.ts', // trust tremor charts have been tested
        '*.js',
      ],
      thresholds: process.env.CI
        ? undefined
        : {
            statements: 68.8,
            branches: 60.5,
            functions: 68.9,
            lines: 67.6,
          },
    },
  },
});

export default mergeConfig(viteConfig, vitestConfig);
