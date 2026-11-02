// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Namespaces resolved from shared/components/locales rather than an app's own
// public/locales. The locale-path resolver and the namespace validator must
// agree on this list, or a new shared namespace silently resolves to the app.
//
// Kept free of Node-only modules: next-i18next.config.js reaches this module
// and can bundle it into the client through appWithTranslation.
const SHARED_NAMESPACES = ['sharedComponents'];

// Namespaces getPageTranslations always serializes, so every page can render
// app chrome and shared components without listing them.
const DEFAULT_PAGE_NAMESPACES = ['common', ...SHARED_NAMESPACES];

module.exports = { SHARED_NAMESPACES, DEFAULT_PAGE_NAMESPACES };
