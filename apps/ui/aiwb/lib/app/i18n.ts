// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * Creates a lookup function that maps a value to its translation key.
 *
 * Returns a function that, given a value:
 *  - returns the mapped translation key when the value is a key of `map`
 *  - otherwise returns the translation key for `defaultKey` (when provided),
 *    or undefined when no default is given
 *
 * Usage with a default fallback:
 *   const getMetricTranslationKey = translationKeyGenerator(PERFORMANCE_METRIC_KEYS, 'default');
 *   t(getMetricTranslationKey(metric));
 *
 * Usage without a default (returns undefined for unknown values):
 *   const getErrorTitleTranslationKey = translationKeyGenerator(ERROR_TITLE_KEYS);
 *   const titleKey = getErrorTitleTranslationKey(code);
 */
export function translationKeyGenerator<M extends Record<string, string>>(
  map: M,
  defaultKey: keyof M,
): (key: string | null | undefined) => M[keyof M];
export function translationKeyGenerator<M extends Record<string, string>>(
  map: M,
): (key: string | null | undefined) => M[keyof M] | undefined;
export function translationKeyGenerator<M extends Record<string, string>>(
  map: M,
  defaultKey?: keyof M,
) {
  return (key: string | null | undefined): M[keyof M] | undefined => {
    if (key != null && key in map) return map[key as keyof M];
    return defaultKey != null ? map[defaultKey] : undefined;
  };
}
