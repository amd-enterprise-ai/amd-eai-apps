// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

import FineTuningModelsPage, {
  getServerSideProps,
} from '@/pages/[project]/fine-tuning/models';
import type { GetServerSidePropsContext } from 'next';
import { serverSideTranslations } from 'next-i18next/serverSideTranslations';

vi.mock('@/components/features/models/FineTuneModels', () => ({
  default: () => <div data-testid="fine-tune-models" />,
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

describe('Fine-tuning models page', () => {
  beforeEach(() => {
    vi.mocked(serverSideTranslations).mockResolvedValue({
      // biome-ignore lint/style/useNamingConvention: next-i18next owns this key.
      _nextI18Next: {
        initialI18nStore: {
          en: {
            common: {
              pages: {
                fineTuning: { title: 'Fine-tuning' },
                fineTuneModels: { title: 'Fine-tune models' },
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

  it('renders fine-tuned models and relevant documentation', () => {
    render(<FineTuningModelsPage />);

    expect(screen.getByTestId('fine-tune-models')).toBeInTheDocument();
    expect(screen.getByTestId('relevant-docs')).toBeInTheDocument();
  });

  it('returns the Fine-tuning and Fine-tune models breadcrumbs', async () => {
    const result = await getServerSideProps({
      locale: 'en',
    } as GetServerSidePropsContext);

    expect(result).toMatchObject({
      props: {
        pageBreadcrumb: [
          { title: 'Fine-tuning' },
          { title: 'Fine-tune models' },
        ],
      },
    });
  });
});
