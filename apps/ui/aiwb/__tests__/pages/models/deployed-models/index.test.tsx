// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import type { GetServerSidePropsContext } from 'next';
import { serverSideTranslations } from 'next-i18next/serverSideTranslations';

import DeployedModelsPage, {
  getServerSideProps,
} from '@/pages/[project]/models/deployed-models';

vi.mock('@/components/features/models/DeployedModels', () => ({
  default: () => <div data-testid="deployed-models" />,
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

describe('Deployed Models page', () => {
  beforeEach(() => {
    vi.mocked(serverSideTranslations).mockResolvedValue({
      // biome-ignore lint/style/useNamingConvention: next-i18next owns this key.
      _nextI18Next: {
        initialI18nStore: {
          en: {
            common: {
              pages: {
                models: { title: 'Models' },
                deployedModels: { title: 'Deployed Models' },
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

  it('renders Deployed Models and relevant documentation', () => {
    render(<DeployedModelsPage />);

    expect(screen.getByTestId('deployed-models')).toBeInTheDocument();
    expect(screen.getByTestId('relevant-docs')).toBeInTheDocument();
  });

  it('returns the Models and Deployed Models breadcrumbs', async () => {
    const result = await getServerSideProps({
      locale: 'en',
    } as GetServerSidePropsContext);

    expect(result).toMatchObject({
      props: {
        pageBreadcrumb: [{ title: 'Models' }, { title: 'Deployed Models' }],
      },
    });
  });
});
