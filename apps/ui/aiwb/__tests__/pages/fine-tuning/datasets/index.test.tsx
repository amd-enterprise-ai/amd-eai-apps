// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { mockDatasets } from '@/__mocks__/services/app/datasets.data';
import {
  deleteDatasets,
  downloadDatasetById,
  listDatasets,
} from '@/lib/app/datasets';

import DatasetsPage, {
  getServerSideProps,
} from '@/pages/[project]/fine-tuning/datasets';

import wrapper from '@/__tests__/ProviderWrapper';
import type { GetServerSidePropsContext } from 'next';
import { serverSideTranslations } from 'next-i18next/serverSideTranslations';
import { Mock, vi } from 'vitest';

// Mock Tabler icons
vi.mock('@tabler/icons-react', async (importOriginal) => {
  const original = (await importOriginal()) ?? {};
  return {
    ...original,
    IconDotsVertical: ({ className }: any) => (
      <span className={className}>action-dot-icon</span>
    ),
  };
});

vi.mock('@/lib/app/datasets', () => ({
  downloadDatasetById: vi.fn(),
  deleteDatasets: vi.fn(),
  listDatasets: vi.fn(),
  getDatasetTypeVariants: vi.fn(() => ({})),
}));

vi.mock('next-i18next/serverSideTranslations', () => ({
  serverSideTranslations: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(serverSideTranslations).mockResolvedValue({
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
      initialLocale: 'en',
      ns: ['common'],
      userConfig: null,
    },
  });
});

describe('Datasets Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listDatasets as Mock).mockResolvedValue({
      data: mockDatasets,
      pagination: { page: 1, pageSize: 10, total: mockDatasets.length },
    });
    (deleteDatasets as Mock).mockResolvedValue({
      succeededIds: ['1'],
      failed: [],
    });
  });

  it('renders the datasets page', async () => {
    await act(async () => {
      render(<DatasetsPage />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('dataset-1')).toBeInTheDocument();
      expect(screen.getByText('dataset-2')).toBeInTheDocument();
    });
  });

  it('requests datasets from the server on initial load', async () => {
    await act(async () => {
      render(<DatasetsPage />, { wrapper });
    });

    // The page must drive its data via the paginated server-side helper.
    // We assert the call shape here; filter wiring is verified separately
    // through the FilterValueMap unit test in the DataFilter component.
    await waitFor(() => {
      expect(listDatasets).toHaveBeenCalledWith(
        'project1',
        expect.objectContaining({
          page: expect.any(Number),
          pageSize: expect.any(Number),
        }),
      );
    });
  });

  it('allows downloading a dataset', async () => {
    await act(async () => {
      render(<DatasetsPage />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('dataset-1')).toBeInTheDocument();
    });

    const actionButtons = await screen.findAllByText('action-dot-icon');
    await act(async () => {
      fireEvent.click(actionButtons[0]);
    });

    const downloadOption = await screen.findByTestId('download');
    await act(async () => {
      fireEvent.click(downloadOption);
    });

    await waitFor(() => {
      // downloadDatasetById(id, activeProject)
      expect(downloadDatasetById).toHaveBeenCalledWith('1', 'project1');
    });
  });

  it('allows deleting a dataset', async () => {
    await act(async () => {
      render(<DatasetsPage />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('dataset-1')).toBeInTheDocument();
    });

    const actionButtons = await screen.findAllByText('action-dot-icon');
    await act(async () => {
      fireEvent.click(actionButtons[0]);
    });

    const deleteOption = await screen.findByTestId('delete');
    await act(async () => {
      fireEvent.click(deleteOption);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    const confirmButton = screen.getByRole('button', {
      name: /confirm/i,
    });
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    await waitFor(() => {
      // deleteDatasets(ids, activeProject)
      expect(deleteDatasets).toHaveBeenCalledWith(['1'], 'project1');
    });
  });
});

describe('getServerSideProps', () => {
  it('returns the Fine-tuning and Datasets breadcrumbs', async () => {
    const result = await getServerSideProps({
      locale: 'en',
    } as GetServerSidePropsContext);

    expect(result).toMatchObject({
      props: {
        pageBreadcrumb: [{ title: 'Fine-tuning' }, { title: 'Datasets' }],
      },
    });
  });
});
