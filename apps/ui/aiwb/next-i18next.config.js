// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

const { createLocalePathResolver } = require('../shared/scripts/i18n-config');

/** @type {import('next-i18next').UserConfig} */
module.exports = {
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'de'],
  },
  // A resolver function cannot be serialized into page props. Both apps pass
  // this config directly to appWithTranslation instead.
  serializeConfig: false,
  // Function-based locale paths cannot discover namespaces from one directory.
  ns: [
    'api-keys',
    'autoscaling',
    'catalog',
    'chat',
    'clusters',
    'common',
    'dashboard',
    'datasets',
    'loras',
    'models',
    'projects',
    'secrets',
    'sharedComponents',
    'storages',
    'workloads',
  ],
  localePath: createLocalePathResolver(),
  reloadOnPrerender: process.env.NODE_ENV === 'development',
};
