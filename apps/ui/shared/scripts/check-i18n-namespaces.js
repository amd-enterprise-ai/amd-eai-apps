#!/usr/bin/env node
// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Validates declared namespaces and shared component translation ownership.

const fs = require('fs');
const path = require('path');
const { getLocaleDirectories, getTranslationFiles } = require('./i18n-locales');
const {
  DEFAULT_PAGE_NAMESPACES,
  SHARED_NAMESPACES,
} = require('./i18n-namespaces');

const appRoot = process.cwd();
const configPath = path.resolve(appRoot, 'next-i18next.config.js');
const pagesDirectory = path.resolve(appRoot, 'pages');
const dockerfilePath = path.resolve(appRoot, 'Dockerfile');
const helperPath = path.resolve(__dirname, '../utils/src/server/i18n.ts');
// The runtime image resolves shared namespaces through these directories, and
// the modules inside each require their siblings, so both have to arrive whole.
const requiredImageDirectories = [
  'shared/scripts',
  'shared/components/locales',
];
const sharedSourceDirectories = [
  path.resolve(__dirname, '../components/src'),
  path.resolve(__dirname, '../hooks/src'),
];
const directServerTranslationsImport =
  /(?:from\s+|import\s+|import\s*\(\s*|require\s*\(\s*)['"]next-i18next\/serverSideTranslations['"]/;
const helperDefaultNamespaces = /defaultNamespaces\s*=\s*\[([^\]]*)\]/;
const pageTranslationsCall =
  /getPageTranslations\s*\(\s*[^,)]+,\s*\[([^\]]*)\]/g;

function fail(message, values = []) {
  console.error(message);
  for (const value of values) {
    console.error(`   - ${value}`);
  }
  process.exitCode = 1;
}

// Reads the string literals out of a source-level array of namespace names.
// Entries built at runtime are skipped rather than guessed at.
function parseNamespaceList(source) {
  return [...source.matchAll(/['"]([^'"]+)['"]/g)].map(([, value]) => value);
}

function getPageFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      return getPageFiles(entryPath);
    }
    return /\.[jt]sx?$/.test(entry.name) ? [entryPath] : [];
  });
}

function getSourceFiles(directory) {
  if (!fs.existsSync(directory)) {
    return [];
  }
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      return getSourceFiles(entryPath);
    }
    return /\.[jt]sx?$/.test(entry.name) ? [entryPath] : [];
  });
}

function getSharedComponentTranslationViolations() {
  const translationHook =
    /const\s*\{\s*t\s*(?::\s*(\w+))?\s*\}\s*=\s*useTranslation\(\s*(['"])([^'"]+)\2/g;

  return sharedSourceDirectories.flatMap((directory) =>
    getSourceFiles(directory).flatMap((filePath) => {
      const contents = fs.readFileSync(filePath, 'utf8');
      const relativePath = path.relative(appRoot, filePath);

      return [...contents.matchAll(translationHook)].flatMap(
        ([, translationFunction = 't', , namespace]) => {
          if (namespace === 'sharedComponents') {
            return [];
          }

          const literalTranslationCall = new RegExp(
            `\\b${translationFunction}\\(\\s*['"][^'"]+['"]`,
          );
          return literalTranslationCall.test(contents)
            ? [`${relativePath} (${namespace})`]
            : [];
        },
      );
    }),
  );
}

function getCopyInstructions(dockerfile) {
  return dockerfile
    .replace(/\\\r?\n/g, ' ')
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+#.*$/, '').trim())
    .filter((line) => /^COPY\s/i.test(line))
    .map((line) => line.replace(/^COPY\s+/i, '').split(/\s+/))
    .map((tokens) => tokens.filter((token) => !token.startsWith('--')))
    .filter((tokens) => tokens.length >= 2);
}

function copiesDirectory(instructions, directory) {
  const imageDirectory = `/app/${directory}`;

  return instructions.some((tokens) => {
    const destination = tokens.at(-1).replace(/\/$/, '');
    const sources = tokens
      .slice(0, -1)
      .map((source) => source.replace(/\/$/, ''));

    return destination === imageDirectory && sources.includes(imageDirectory);
  });
}

let translationFiles;
try {
  translationFiles = getTranslationFiles(getLocaleDirectories(appRoot));
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
}

const config = require(configPath);
if (!Array.isArray(config.ns)) {
  console.error(`Expected an ns array in ${configPath}`);
  process.exit(1);
}

const namespaceSources = new Map();
for (const { namespace, source } of translationFiles) {
  const sources = namespaceSources.get(namespace) ?? [];
  namespaceSources.set(namespace, [...sources, source]);
}

const duplicateNamespaces = [...namespaceSources]
  .filter(([, sources]) => sources.length > 1)
  .map(([namespace, sources]) => `${namespace} (${sources.join(', ')})`);
const fileNamespaces = new Set(namespaceSources.keys());
const configuredNamespaces = new Set(config.ns);
const unlistedNamespaces = [...fileNamespaces].filter(
  (namespace) => !configuredNamespaces.has(namespace),
);
const missingNamespaces = [...configuredNamespaces].filter(
  (namespace) => !fileNamespaces.has(namespace),
);

if (duplicateNamespaces.length > 0) {
  fail('Translation namespaces must have one source:', duplicateNamespaces);
}
if (unlistedNamespaces.length > 0) {
  fail(
    'Translation namespaces missing from next-i18next config:',
    unlistedNamespaces,
  );
}
if (missingNamespaces.length > 0) {
  fail('Configured namespaces without translation files:', missingNamespaces);
}

// A namespace file added under the shared locale root but left out of
// SHARED_NAMESPACES passes every check above and then resolves at runtime to
// the app's own public/locales, where no such file exists.
const unsharedNamespaces = translationFiles
  .filter(
    ({ source, namespace }) =>
      source === 'shared components' && !SHARED_NAMESPACES.includes(namespace),
  )
  .map(({ namespace }) => namespace);
if (unsharedNamespaces.length > 0) {
  fail(
    `Shared locale namespaces missing from SHARED_NAMESPACES (${SHARED_NAMESPACES.join(', ')}):`,
    unsharedNamespaces,
  );
}
const pageFiles = getPageFiles(pagesDirectory).map((filePath) => ({
  filePath,
  relativePath: path.relative(appRoot, filePath),
  contents: fs.readFileSync(filePath, 'utf8'),
}));

const directPageImports = pageFiles
  .filter(({ contents }) => directServerTranslationsImport.test(contents))
  .map(({ relativePath }) => relativePath);
if (directPageImports.length > 0) {
  fail('Pages must use the app getPageTranslations helper:', directPageImports);
}

// The helper's implicit namespaces are invisible at each call site, so a drift
// between it and DEFAULT_PAGE_NAMESPACES would silently change what pages
// hydrate.
const helperMatch = helperDefaultNamespaces.exec(
  fs.readFileSync(helperPath, 'utf8'),
);
if (!helperMatch) {
  console.error(`Expected a defaultNamespaces array in ${helperPath}`);
  process.exit(1);
}
const helperNamespaces = parseNamespaceList(helperMatch[1]);
if (helperNamespaces.join() !== DEFAULT_PAGE_NAMESPACES.join()) {
  fail(
    `getPageTranslations defaults must match DEFAULT_PAGE_NAMESPACES (${DEFAULT_PAGE_NAMESPACES.join(', ')}), found:`,
    helperNamespaces,
  );
}

const unknownRequestedNamespaces = pageFiles.flatMap(
  ({ relativePath, contents }) =>
    [...contents.matchAll(pageTranslationsCall)]
      .flatMap(([, list]) => parseNamespaceList(list))
      .filter((namespace) => !fileNamespaces.has(namespace))
      .map((namespace) => `${namespace} (${relativePath})`),
);
if (unknownRequestedNamespaces.length > 0) {
  fail(
    'Pages request namespaces without translation files:',
    unknownRequestedNamespaces,
  );
}
const sharedComponentTranslationViolations =
  getSharedComponentTranslationViolations();
if (sharedComponentTranslationViolations.length > 0) {
  fail(
    'Shared components must resolve literal translation keys from sharedComponents:',
    sharedComponentTranslationViolations,
  );
}

// Narrowing these to individual files ships a module without the siblings it
// requires, which only surfaces as MODULE_NOT_FOUND in the running container.
const dockerfile = fs.readFileSync(dockerfilePath, 'utf8');
const copyInstructions = getCopyInstructions(dockerfile);
const uncopiedImageDirectories = requiredImageDirectories.filter(
  (directory) => !copiesDirectory(copyInstructions, directory),
);
if (uncopiedImageDirectories.length > 0) {
  fail(
    `Dockerfile must copy these directories whole (${path.relative(appRoot, dockerfilePath)}):`,
    uncopiedImageDirectories,
  );
}
if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log(`Validated ${configuredNamespaces.size} translation namespaces.`);
