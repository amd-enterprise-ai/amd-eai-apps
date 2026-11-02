// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Stub for next-i18next in Ladle environment.
// Returns friendly fallbacks for known keys so components (e.g. StatisticsCard) render readably.
import React, {
  type ComponentType,
  type ElementType,
  type ReactNode,
} from 'react';
import translations from '../../locales/en/sharedComponents.json';

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

// Locale files store plurals under the `_one`/`_other` suffixes i18next expects,
// while call sites pass a bare key plus a count. Without this lookup those keys
// would render as the raw key in Ladle even though the translation exists.
function resolve(key: string, values?: Record<string, unknown>) {
  if (key in fallbacks) {
    return fallbacks[key];
  }
  if (typeof values?.count === 'number') {
    return fallbacks[`${key}_${values.count === 1 ? 'one' : 'other'}`];
  }
  return undefined;
}

export const useTranslation = (
  ns?: string,
  options?: { keyPrefix?: string },
) => ({
  t: (key: string, values?: Record<string, unknown>) => {
    const fullKey = options?.keyPrefix ? `${options.keyPrefix}.${key}` : key;
    // Only the shared namespace is stubbed. Resolving every namespace against
    // it would render app-owned keys as shared text and hide a wrong namespace.
    const fallback =
      ns === 'sharedComponents' ? resolve(fullKey, values) : undefined;
    if (fallback === undefined) {
      return fullKey;
    }
    return values ? interpolate(fallback, values) : fallback;
  },
  i18n: {
    language: 'en',
    changeLanguage: () => Promise.resolve(),
  },
  ready: true,
});

type TransProps = {
  children?: ReactNode;
  parent?: ElementType | false;
};

export const Trans = ({ children, parent = 'span' }: TransProps) => {
  if (parent === false) {
    return children ?? null;
  }
  return React.createElement(parent, null, children);
};

export const appWithTranslation = (Component: ComponentType) => Component;
export const serverSideTranslations = () => Promise.resolve({});
