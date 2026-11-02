// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { serverSideTranslations } from 'next-i18next/serverSideTranslations';

const defaultNamespaces = ['common', 'sharedComponents'];

export function getPageTranslations(locale: string, namespaces: string[] = []) {
  return serverSideTranslations(
    locale,
    Array.from(new Set([...defaultNamespaces, ...namespaces])),
  );
}
