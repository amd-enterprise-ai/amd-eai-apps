// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

const path = require('path');
const { SHARED_NAMESPACES } = require('./i18n-namespaces');

function createLocalePathResolver(appRoot = process.cwd()) {
  // This resolver runs on the server; i18n-namespaces stays client-safe because
  // next-i18next can bundle that metadata through appWithTranslation.
  // Turbopack rewrites __dirname to a virtual root, while both development and
  // standalone servers run with the app directory as their working directory.
  const appLocales = path.resolve(appRoot, 'public/locales');
  const sharedLocales = path.resolve(appRoot, '../shared/components/locales');
  const shared = new Set(SHARED_NAMESPACES);

  return (locale, namespace) =>
    path.join(
      shared.has(namespace) ? sharedLocales : appLocales,
      locale,
      `${namespace}.json`,
    );
}

module.exports = { createLocalePathResolver };
