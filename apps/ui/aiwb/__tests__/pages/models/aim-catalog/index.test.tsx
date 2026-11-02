// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import type { GetServerSidePropsContext } from 'next';
import { serverSideTranslations } from 'next-i18next/serverSideTranslations';

import AIMCatalogPage, {
  getServerSideProps,
} from '@/pages/[project]/models/aim-catalog';

vi.mock('@/components/features/models/AIMCatalog', () => ({
  default: () => <div data-testid="aim-catalog" />,
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

describe('AIM Catalog page', () => {
  beforeEach(() => {
    vi.mocked(serverSideTranslations).mockResolvedValue({
      // biome-ignore lint/style/useNamingConvention: next-i18next owns this key.
      _nextI18Next: {
        initialI18nStore: {
          en: {
            common: {
              pages: {
                models: { title: 'Models' },
                aimCatalog: { title: 'AIM Catalog' },
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

  it('renders the AIM Catalog and relevant documentation', () => {
    render(<AIMCatalogPage />);

    expect(screen.getByTestId('aim-catalog')).toBeInTheDocument();
    expect(screen.getByTestId('relevant-docs')).toBeInTheDocument();
  });

  it('returns the Models and AIM Catalog breadcrumbs', async () => {
    const result = await getServerSideProps({
      locale: 'en',
    } as GetServerSidePropsContext);

    expect(result).toMatchObject({
      props: {
        pageBreadcrumb: [{ title: 'Models' }, { title: 'AIM Catalog' }],
      },
    });
  });

  it('requests the loras namespace so the deploy wizard can render adapter selection', async () => {
    await getServerSideProps({
      locale: 'en',
    } as GetServerSidePropsContext);

    expect(serverSideTranslations).toHaveBeenCalledWith(
      'en',
      expect.arrayContaining(['loras']),
    );
  });
});
