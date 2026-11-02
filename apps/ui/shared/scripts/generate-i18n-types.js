#!/usr/bin/env node
// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

const fs = require('fs');
const path = require('path');
const { getLocaleDirectories, getTranslationFiles } = require('./i18n-locales');

// Use the calling app's working directory as the root.
// When run via `pnpm i18n:types` from an app directory, process.cwd() is that app's root.
const appRoot = process.cwd();
const outputFile = path.resolve(appRoot, 'types/react-i18next.d.ts');

console.log('🔍 Scanning translation files...');

let translationFiles;
try {
  translationFiles = getTranslationFiles(getLocaleDirectories(appRoot));
} catch (error) {
  console.error('❌', error instanceof Error ? error.message : error);
  console.error(
    '   Run this script from the app root directory (e.g., apps/ui/aiwb).',
  );
  process.exit(1);
}
if (translationFiles.length === 0) {
  console.error('❌ No translation files found.');
  process.exit(1);
}

// Helper function to convert namespace to valid TypeScript identifier.
// Prefixes with '_' when the name starts with a digit (e.g. "2fa" → "_2fa").
function toIdentifier(namespace) {
  const base = namespace.replace(/[^a-zA-Z0-9_]/g, '_');
  return /^[0-9]/.test(base) ? `_${base}` : base;
}

function loadJsonFile(filePath, file) {
  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf-8');
  } catch (err) {
    console.error('❌ Failed to read translation file:', filePath);
    console.error('   Original error:', err?.message ? err.message : err);
    process.exit(1);
  }
  try {
    return JSON.parse(raw);
  } catch (err) {
    console.error('❌ Failed to parse translation file:', filePath);
    console.error('   File name:', file);
    console.error(
      '   Ensure the JSON is valid. Original error:',
      err?.message ? err.message : err,
    );
    process.exit(1);
  }
}

// Recursively extract all leaf key paths as dot-separated strings.
// e.g. { a: { b: 'v' } } → ['a.b']
function extractKeys(obj, prefix = '') {
  const keys = [];
  for (const [k, v] of Object.entries(obj)) {
    const keyPath = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      keys.push(...extractKeys(v, keyPath));
    } else {
      keys.push(keyPath);
    }
  }
  return keys;
}

// Generate a nested TypeScript object type literal from JSON.
// e.g. { a: { b: 'v' } } → "a: {\n  b: string;\n};"
// This preserves the JSON structure so i18next's KeysBuilderWithoutReturnObjects
// can recursively compute dot-separated key paths during constraint checking.
//
// WHY NESTED TYPE, NOT Record<nsKeys, string>:
// i18next's TFunctionStrict evaluates ParseKeys<Ns, TOpt, KPrefix> where TOpt is
// a generic type variable. TypeScript uses the constraint bound (Keys extends
// $Dictionary = {[key:string]:unknown}) for indexed access, so Keys[Ns] resolves
// to unknown when the Keys default cannot be statically computed. A nested concrete
// type avoids this: Resources['chat'] is a specific object type, not unknown.
function generateNestedType(obj, indent) {
  const lines = [];
  for (const [k, v] of Object.entries(obj)) {
    const needsQuotes = /[^a-zA-Z0-9_$]/.test(k) || /^[0-9]/.test(k);
    const tsKey = needsQuotes
      ? `'${k.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`
      : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      lines.push(`${indent}${tsKey}: {`);
      lines.push(generateNestedType(v, indent + '  '));
      lines.push(`${indent}};`);
    } else {
      lines.push(`${indent}${tsKey}: string;`);
    }
  }
  return lines.join('\n');
}

const namespaceData = translationFiles.map(({ file, filePath, namespace }) => {
  const content = loadJsonFile(filePath, file);
  const keys = extractKeys(content);
  console.log(`   ✓ ${file} (${keys.length} keys)`);
  return { namespace, keys, content };
});

// One flat string union type per namespace.
//
// WHY FLAT UNION, NOT typeof json:
// Using `typeof json` crashes TypeScript for large/deep namespaces due to
// microsoft/TypeScript#63195. A flat union of all valid key paths is O(n) for
// TypeScript to resolve — no deep JSON inference, no instantiation limit risk.
const typeAliases = namespaceData
  .map(({ namespace, keys }) => {
    const typeName = `${toIdentifier(namespace)}Keys`;
    const literals = keys
      .map((k) => `  | '${k.replace(/'/g, "\\'")}'`)
      .join('\n');
    return `export type ${typeName} =\n${literals};\n`;
  })
  .join('\n');

// Build i18next module augmentation using nested object types per namespace.
//
// WHY NESTED OBJECT TYPE, NOT Record<nsKeys, string>:
// i18next's TFunctionStrict evaluates ParseKeys<Ns, TOpt, KPrefix> in constraint
// position where TOpt is a generic type variable. TypeScript distributes the
// conditional in KeysByTOptions<TOpt> over TOpt's constraint, producing a union
// of ResourceKeys<true> | ResourceKeys. Accessing this union with Keys[Ns] causes
// TypeScript to use the $Dictionary constraint bound for indexed access, resolving
// to unknown. A nested concrete type avoids this: Resources['chat'] is a specific
// object type, so Keys['chat'] correctly resolves to the nested structure, allowing
// KeysBuilderWithoutReturnObjects to compute the valid dot-separated key paths.
//
// WHY NOT typeof json:
// Using `typeof json` (imported JSON) results in the same nested structure at
// type-check time but requires an import in each component. Generating the nested
// type literal inline keeps types self-contained in the .d.ts file.
//
// WHY NOT TFunction props in shared components:
// When CustomTypeOptions.resources is defined, i18next brands TFunction with its
// namespace ($TFunctionBrand). TFunction<'chat'> becomes incompatible with
// TFunction<'models'>. Shared components that accept TFunction as a prop from
// any namespace use a plain callable type instead:
//   (key: string, options?: Record<string, unknown>) => string
const hasCommonNs = namespaceData.some(
  ({ namespace }) => namespace === 'common',
);
const defaultNsLine = hasCommonNs ? "\n    defaultNS: 'common';" : '';
const strictKeyChecksLine = '\n    strictKeyChecks: true;';

const resourceEntries = namespaceData
  .map(({ namespace, content }) => {
    const needsQuotes = /[^a-zA-Z0-9_]/.test(namespace);
    const nsKey = needsQuotes ? `'${namespace}'` : namespace;
    const nestedType = generateNestedType(content, '        ');
    return `      ${nsKey}: {\n${nestedType}\n      };`;
  })
  .join('\n');

const augmentation = `declare module 'i18next' {
  interface CustomTypeOptions {${defaultNsLine}${strictKeyChecksLine}
    resources: {
${resourceEntries}
    };
  }
}
`;

const combinedContent = `// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
//
// This file is auto-generated. Do not edit manually.
// Run 'pnpm i18n:types' to regenerate.

// ============================================================================
// i18next Key Type Enforcement — Flat Key Unions + Module Augmentation
// ============================================================================
// Flat key union types document all valid translation key paths per namespace.
// Use them for IDE autocomplete or typed wrapper functions (opt-in).
//
// The i18next module augmentation enables compile-time key validation via
// nested object types for each namespace. Passing an unknown key to t() is a
// TypeScript error. Nested types (not Record<flat, string>) are required so
// i18next's ParseKeys<Ns, TOpt> can resolve Keys[Ns] to the concrete structure
// rather than unknown when TOpt is a generic type variable in TFunctionStrict.
//
// Shared components that accept TFunction as a prop use a plain callable type
// to avoid $TFunctionBrand incompatibility across namespaces:
//   translation: (key: string, options?: Record<string, unknown>) => string
//
// WHY export {}:
// TypeScript distinguishes between script files (no imports/exports) and module
// files. In a script file, 'declare module "i18next"' is an ambient module
// declaration (declares a new module), NOT a module augmentation (adds to an
// existing module). Only module files produce proper augmentations. Adding
// 'export {}' makes this file a module, so the 'declare module "i18next"' block
// correctly augments the i18next package's CustomTypeOptions interface.
// ============================================================================

// Required to make this a module file so 'declare module "i18next"' below is
// a module augmentation (not an ambient module declaration).
export {};

// Flat key unions — one per namespace (for documentation and wrapper functions)
${typeAliases}
${augmentation}`;

const typesDir = path.dirname(outputFile);
if (!fs.existsSync(typesDir)) {
  fs.mkdirSync(typesDir, { recursive: true });
}

fs.writeFileSync(outputFile, combinedContent);

console.log('\n✅ i18n types generated successfully:');
console.log(`   - ${path.relative(appRoot, outputFile)}`);
console.log(
  '   Key unions + i18next module augmentation for compile-time key validation.\n',
);
