// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { buildPageBreadcrumb } from '@/lib/app/breadcrumbs';

describe('buildPageBreadcrumb', () => {
  it('builds breadcrumbs from translated page titles', () => {
    const translations = {
      // biome-ignore lint/style/useNamingConvention: next-i18next owns this key.
      _nextI18Next: {
        initialI18nStore: {
          en: {
            common: {
              pages: {
                fineTuning: { title: 'Fine-tuning' },
                datasets: { title: 'Datasets' },
              },
            },
          },
        },
      },
    } as Parameters<typeof buildPageBreadcrumb>[0];

    expect(
      buildPageBreadcrumb(translations, 'en', 'fineTuning', 'datasets'),
    ).toEqual([{ title: 'Fine-tuning' }, { title: 'Datasets' }]);
  });
});
