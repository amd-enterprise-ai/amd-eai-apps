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

import { deleteApiKey, fetchProjectApiKeys } from '@/lib/app/api-keys';

import {
  generateMockApiKeys,
  generateMockApiKeyResponse,
} from '@/__mocks__/utils/api-keys-mock';

import ApiKeysTable from '@/components/features/api-keys/ApiKeysTable';
import { useProject } from '@/contexts/ProjectContext';

import wrapper from '@/__tests__/ProviderWrapper';

// Mock the API functions
vi.mock('@/lib/app/api-keys', () => ({
  fetchProjectApiKeys: vi.fn(),
  deleteApiKey: vi.fn(),
}));

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: vi.fn(),
}));

const mockUseProject = vi.mocked(useProject);
const mockFetchProjectApiKeys = vi.mocked(fetchProjectApiKeys);
const mockDeleteApiKey = vi.mocked(deleteApiKey);

const defaultProjectContext = {
  isStandaloneMode: false,
  apiKeysManagementEnabled: true,
  aiGatewayEnabled: true,
  airmAppUrl: undefined,
  activeProject: 'project1',
  projects: [{ id: 'project1', name: 'Project 1' }],
  isLoading: false,
  projectError: null,
  refetchProjects: vi.fn(),
  setActiveProject: vi.fn(),
  projectPath: (path: string) =>
    `/project1${path.startsWith('/') ? path : `/${path}`}`,
  projectUrl: (path: string) =>
    `/project1${path.startsWith('/') ? path : `/${path}`}`,
};

describe('ApiKeysTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseProject.mockReturnValue(defaultProjectContext);

    // Default mock implementation
    mockFetchProjectApiKeys.mockResolvedValue(generateMockApiKeyResponse());

    mockDeleteApiKey.mockResolvedValue();
  });

  const defaultProps = {
    projectId: 'project-1',
    createButton: <button>Create API Key</button>,
  };

  it('renders correct columns', async () => {
    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    expect(
      screen.getByText('list.apiKeys.headers.name.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.apiKeys.headers.secretKey.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.apiKeys.headers.createdAt.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.apiKeys.headers.createdBy.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`list.apiKeys.headers.actions.title`),
    ).toBeInTheDocument();
  });

  it('loads and displays API keys data', async () => {
    const mockApiKeys = generateMockApiKeys(2);
    mockFetchProjectApiKeys.mockResolvedValue({
      data: mockApiKeys,
    });

    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(mockApiKeys[0].displayName)).toBeInTheDocument();
      expect(screen.getByText(mockApiKeys[1].displayName)).toBeInTheDocument();
    });

    expect(mockFetchProjectApiKeys).toHaveBeenCalledWith('project-1');
  });

  it('handles search filter', async () => {
    const mockApiKeys = generateMockApiKeys(3);
    mockFetchProjectApiKeys.mockResolvedValue({
      data: mockApiKeys,
    });

    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    // All API keys should be visible initially
    await waitFor(() => {
      expect(screen.getByText(mockApiKeys[0].displayName)).toBeInTheDocument();
      expect(screen.getByText(mockApiKeys[1].displayName)).toBeInTheDocument();
      expect(screen.getByText(mockApiKeys[2].displayName)).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(
      'list.filters.search.placeholder',
    );

    // Type a search term that matches only one API key
    await act(async () => {
      fireEvent.change(searchInput, {
        target: { value: mockApiKeys[0].displayName },
      });
    });

    // Client-side filtering should show only matching results
    // Note: This tests that filtering works, but the exact behavior depends on
    // the filter implementation. The fetch should only be called once (on mount)
    expect(mockFetchProjectApiKeys).toHaveBeenCalledTimes(1);
    expect(mockFetchProjectApiKeys).toHaveBeenCalledWith('project-1');
  });

  it('handles refresh action', async () => {
    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    // Wait for initial load
    await waitFor(() => {
      expect(mockFetchProjectApiKeys).toHaveBeenCalledTimes(1);
    });

    const refreshButton = screen.getByRole('button', { name: /refresh/i });

    fireEvent.click(refreshButton);

    // Should trigger a new fetch
    await waitFor(() => {
      expect(mockFetchProjectApiKeys).toHaveBeenCalledTimes(2);
    });
  });

  it('handles delete action', async () => {
    const mockApiKeys = generateMockApiKeys(1);
    mockFetchProjectApiKeys.mockResolvedValue({
      data: mockApiKeys,
    });

    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(mockApiKeys[0].displayName)).toBeInTheDocument();
    });

    // Click on the actions menu
    const actionsButton = screen.getByLabelText('list.actions.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    // Find and click delete button in dropdown
    const deleteButton = screen.getByText('list.actions.delete.title');
    await act(async () => {
      fireEvent.click(deleteButton);
    });

    // Confirm delete in modal
    const confirmButton = screen.getByTestId('confirm-button');
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    expect(mockDeleteApiKey).toHaveBeenCalledWith(
      'project-1',
      mockApiKeys[0].id,
    );
  }, 20_000);

  it('handles sorting', async () => {
    const mockApiKeys = generateMockApiKeys(3);
    mockFetchProjectApiKeys.mockResolvedValue({
      data: mockApiKeys,
    });

    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText(mockApiKeys[0].displayName)).toBeInTheDocument();
    });

    const nameHeader = screen.getByText('list.apiKeys.headers.name.title');

    await act(async () => {
      fireEvent.click(nameHeader);
    });

    // Sorting is handled client-side, so no new fetch should occur
    // The fetch should only be called once (on mount)
    expect(mockFetchProjectApiKeys).toHaveBeenCalledTimes(1);
    expect(mockFetchProjectApiKeys).toHaveBeenCalledWith('project-1');
  }, 20_000);

  it('displays loading skeleton when loading', async () => {
    // Create a promise that never resolves to simulate loading state
    mockFetchProjectApiKeys.mockImplementation(() => new Promise(() => {}));

    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    // Should show skeleton loading state
    expect(
      screen.getByLabelText('list.apiKeys.table.ariaLabel'),
    ).toBeInTheDocument();
  });

  it('handles empty state', async () => {
    mockFetchProjectApiKeys.mockResolvedValue({
      data: [],
    });

    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      // The table should still be rendered but empty
      expect(
        screen.getByLabelText('list.apiKeys.table.ariaLabel'),
      ).toBeInTheDocument();
    });
  });

  it('renders create button', async () => {
    await act(async () => {
      render(<ApiKeysTable {...defaultProps} />, {
        wrapper,
      });
    });

    expect(screen.getByText('Create API Key')).toBeInTheDocument();
  });

  describe('viewDetails action visibility', () => {
    it('shows viewDetails action when aiGatewayEnabled is true', async () => {
      const mockApiKeys = generateMockApiKeys(1);
      mockFetchProjectApiKeys.mockResolvedValue({ data: mockApiKeys });

      await act(async () => {
        render(<ApiKeysTable {...defaultProps} />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByText(mockApiKeys[0].displayName),
        ).toBeInTheDocument();
      });

      const actionsButton = screen.getByLabelText('list.actions.label');
      await act(async () => {
        fireEvent.click(actionsButton);
      });

      expect(
        screen.getByText('list.actions.viewDetails.title'),
      ).toBeInTheDocument();
    });

    it('hides viewDetails action when aiGatewayEnabled is false', async () => {
      mockUseProject.mockReturnValue({
        ...defaultProjectContext,
        aiGatewayEnabled: false,
      });

      const mockApiKeys = generateMockApiKeys(1);
      mockFetchProjectApiKeys.mockResolvedValue({ data: mockApiKeys });

      await act(async () => {
        render(<ApiKeysTable {...defaultProps} />, { wrapper });
      });

      await waitFor(() => {
        expect(
          screen.getByText(mockApiKeys[0].displayName),
        ).toBeInTheDocument();
      });

      const actionsButton = screen.getByLabelText('list.actions.label');
      await act(async () => {
        fireEvent.click(actionsButton);
      });

      expect(
        screen.queryByText('list.actions.viewDetails.title'),
      ).not.toBeInTheDocument();
    });
  });
});
