// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

const fs = require('fs');
const path = require('path');

function getLocaleDirectories(appRoot, locale = 'en') {
  return [
    {
      source: 'application',
      directory: path.resolve(appRoot, 'public/locales', locale),
    },
    {
      source: 'shared components',
      directory: path.resolve(__dirname, '../components/locales', locale),
    },
  ];
}

function getTranslationFiles(localeDirectories) {
  return localeDirectories
    .flatMap(({ source, directory }) => {
      if (!fs.existsSync(directory)) {
        throw new Error(`${source} locales directory not found: ${directory}`);
      }
      return fs
        .readdirSync(directory)
        .filter((file) => file.endsWith('.json'))
        .map((file) => ({
          source,
          file,
          filePath: path.join(directory, file),
          namespace: file.slice(0, -'.json'.length),
        }));
    })
    .sort(({ namespace: left }, { namespace: right }) =>
      left.localeCompare(right),
    );
}

module.exports = {
  getLocaleDirectories,
  getTranslationFiles,
};
