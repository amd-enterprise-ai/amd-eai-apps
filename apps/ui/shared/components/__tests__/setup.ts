// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import React from 'react';

import {
  installPackageTestJsdom,
  resetActiveProjectLocalStorage,
} from '@/../utils/__tests__/vitestJsdomSetup';
import translations from '../locales/en/sharedComponents.json';

installPackageTestJsdom();

function flattenTranslations(
  translations: Record<string, string | Record<string, unknown>>,
  prefix = '',
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(translations).flatMap(([key, value]) => {
      const fullKey = prefix ? `${prefix}.${key}` : key;
      return typeof value === 'string'
        ? [[fullKey, value]]
        : Object.entries(flattenTranslations(value, fullKey));
    }),
  );
}

const fallbacks = flattenTranslations(translations);

const interpolate = (template: string, values: Record<string, unknown>) =>
  template.replace(/{{(\w+)}}/g, (match, name) =>
    name in values ? String(values[name]) : match,
  );

function resolve(key: string, values?: Record<string, unknown>) {
  if (key in fallbacks) {
    return fallbacks[key];
  }
  if (typeof values?.count === 'number') {
    return fallbacks[`${key}_${values.count === 1 ? 'one' : 'other'}`];
  }
  return undefined;
}

const defaultSession = {
  data: {
    user: {
      email: 'test@example.com',
      id: 'test-user-id',
      roles: [] as string[],
    },
  },
  status: 'authenticated' as const,
  update: vi.fn(),
};

vi.mock('next-auth/react', () => ({
  useSession: vi.fn(() => defaultSession),
  SessionProvider: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  signIn: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock('next-i18next', () => ({
  useTranslation: (ns?: string, options?: { keyPrefix?: string }) => ({
    t: (key: string, values?: Record<string, unknown>) => {
      const fullKey = options?.keyPrefix ? `${options.keyPrefix}.${key}` : key;
      const fallback =
        ns === 'sharedComponents' ? resolve(fullKey, values) : undefined;

      return fallback === undefined
        ? fullKey
        : values
          ? interpolate(fallback, values)
          : fallback;
    },
  }),
}));

beforeEach(() => {
  resetActiveProjectLocalStorage();
});

afterEach(() => {
  cleanup();
});
