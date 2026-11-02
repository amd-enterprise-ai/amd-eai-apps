// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import { GetServerSidePropsContext } from 'next';

import ApiKeysPage, {
  getServerSideProps,
} from '@/pages/[project]/api-keys/index';

import wrapper from '@/__tests__/ProviderWrapper';

// Mock serverSideTranslations
vi.mock('next-i18next/serverSideTranslations', () => ({
  serverSideTranslations: vi.fn().mockResolvedValue({}),
}));

const { mockUseProject } = vi.hoisted(() => ({
  mockUseProject: vi.fn(),
}));

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => mockUseProject(),
}));

const defaultProjectContext = {
  activeProject: 'project1',
  apiKeysManagementEnabled: true,
  projects: [{ id: 'project1', name: 'Project 1' }],
  isLoading: false,
  setActiveProject: vi.fn(),
};

// Mock the API keys components
vi.mock('@/components/features/api-keys/ApiKeysTable', () => ({
  default: ({ createButton }: { createButton: React.ReactNode }) => (
    <div data-testid="api-keys-table">
      API Keys Table
      {createButton}
    </div>
  ),
}));

vi.mock('@/components/features/api-keys/CreateApiKey', () => ({
  default: ({ isOpen }: { isOpen: boolean }) => (
    <div data-testid="create-api-key" data-open={isOpen}>
      Create API Key Modal
    </div>
  ),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockUseProject.mockReturnValue(defaultProjectContext);
});

describe('ApiKeysPage', () => {
  describe('with active project', () => {
    it('renders API keys table with active project', () => {
      render(<ApiKeysPage />, { wrapper });

      expect(screen.getByTestId('api-keys-table')).toBeInTheDocument();
      expect(screen.getByText('list.actions.create.title')).toBeInTheDocument();
      expect(screen.getByTestId('create-api-key')).toBeInTheDocument();
    });

    it('renders create button correctly', () => {
      render(<ApiKeysPage />, { wrapper });

      const createButton = screen.getByText('list.actions.create.title');
      expect(createButton).toBeInTheDocument();
      expect(createButton.tagName).toBe('BUTTON');
    });

    it('modal is closed by default', () => {
      render(<ApiKeysPage />, { wrapper });

      const modal = screen.getByTestId('create-api-key');
      expect(modal).toHaveAttribute('data-open', 'false');
    });
  });

  describe('with API-key management disabled', () => {
    it('shows the disabled notice instead of the table', () => {
      mockUseProject.mockReturnValue({
        ...defaultProjectContext,
        apiKeysManagementEnabled: false,
      });

      render(<ApiKeysPage />, { wrapper });

      expect(screen.getByText('list.apiKeysDisabled')).toBeInTheDocument();
      expect(screen.queryByTestId('api-keys-table')).not.toBeInTheDocument();
      expect(screen.queryByTestId('create-api-key')).not.toBeInTheDocument();
    });
  });
});

describe('getServerSideProps', () => {
  const mockContext = {
    locale: 'en',
  } as GetServerSidePropsContext;

  it('returns props with translations', async () => {
    const result = await getServerSideProps(mockContext);

    expect(result).toEqual({
      props: {},
    });
  });

  it('handles different locales', async () => {
    const contextWithDifferentLocale = {
      ...mockContext,
      locale: 'fr',
    };

    await getServerSideProps(contextWithDifferentLocale);
  });

  it('handles missing locale', async () => {
    const contextWithoutLocale = {
      ...mockContext,
      locale: undefined,
    };

    const result = await getServerSideProps(contextWithoutLocale);

    expect(result).toHaveProperty('props');
  });
});

describe('API Keys Page Integration', () => {
  it('integrates table and modal correctly', () => {
    render(<ApiKeysPage />, { wrapper });

    // Both components should be present
    expect(screen.getByTestId('api-keys-table')).toBeInTheDocument();
    expect(screen.getByTestId('create-api-key')).toBeInTheDocument();

    // Create button should be passed to table
    expect(screen.getByText('list.actions.create.title')).toBeInTheDocument();
  });

  it('passes correct props to components', () => {
    render(<ApiKeysPage />, { wrapper });

    const table = screen.getByTestId('api-keys-table');
    const modal = screen.getByTestId('create-api-key');

    // Verify components are rendered (props are tested in component tests)
    expect(table).toBeInTheDocument();
    expect(modal).toBeInTheDocument();
  });
});
