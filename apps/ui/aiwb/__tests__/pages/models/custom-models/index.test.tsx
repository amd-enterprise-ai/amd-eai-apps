// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import type { GetServerSidePropsContext } from 'next';
import { serverSideTranslations } from 'next-i18next/serverSideTranslations';

import CustomModelsPage, {
  getServerSideProps,
} from '@/pages/[project]/models/custom-models';

vi.mock('@/components/features/models/CustomModels', () => ({
  default: () => <div data-testid="custom-models" />,
}));

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    RelevantDocs: () => <div data-testid="relevant-docs" />,
  };
});

vi.mock('next-i18next/serverSideTranslations', () => ({
  serverSideTranslations: vi.fn(),
}));

describe('Custom Models page', () => {
  beforeEach(() => {
    vi.mocked(serverSideTranslations).mockResolvedValue({
      // biome-ignore lint/style/useNamingConvention: next-i18next owns this key.
      _nextI18Next: {
        initialI18nStore: {
          en: {
            common: {
              pages: {
                models: { title: 'Models' },
                customModels: { title: 'Custom Models' },
              },
            },
          },
        },
        initialLocale: 'en',
        ns: ['common'],
        userConfig: null,
      },
    });
  });

  it('renders Custom Models and relevant documentation', () => {
    render(<CustomModelsPage />);

    expect(screen.getByTestId('custom-models')).toBeInTheDocument();
    expect(screen.getByTestId('relevant-docs')).toBeInTheDocument();
  });

  it('returns the Models and Custom Models breadcrumbs', async () => {
    const result = await getServerSideProps({
      locale: 'en',
    } as GetServerSidePropsContext);

    expect(result).toMatchObject({
      props: {
        pageBreadcrumb: [{ title: 'Models' }, { title: 'Custom Models' }],
      },
    });
  });
});
