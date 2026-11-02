// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { StoragesFilter } from '@/components/features/storages';

describe('StoragesListFilter', () => {
  it('renders StoragesListFilter with correct filters', () => {
    const onFilterChange = vi.fn();
    render(
      <StoragesFilter onFilterChange={onFilterChange} onRefresh={() => {}} />,
    );
    expect(
      screen.getByPlaceholderText('list.filter.search.placeholder'),
    ).toBeInTheDocument();

    expect(
      screen.getByRole('button', { name: 'actions.clearFilters.title' }),
    ).toBeInTheDocument();
  });

  it('can clear filters', async () => {
    const onFilterChange = vi.fn();
    render(
      <StoragesFilter onFilterChange={onFilterChange} onRefresh={() => {}} />,
    );

    // Then change search input
    const searchInput = screen.getByPlaceholderText(
      'list.filter.search.placeholder',
    );
    fireEvent.change(searchInput, { target: { value: 'searchValue' } });

    await waitFor(() => {
      expect(onFilterChange).toHaveBeenCalledWith({
        search: ['searchValue'],
      });
    });

    fireEvent.click(screen.getByText('actions.clearFilters.title'));

    await waitFor(() => {
      expect(onFilterChange).toHaveBeenCalledWith({});
    });
  });

  it('if in project scope do not show scope filter', async () => {
    const onFilterChange = vi.fn();
    render(
      <StoragesFilter
        onFilterChange={onFilterChange}
        isInProjects
        onRefresh={() => {}}
      />,
    );

    const searchInput = screen.getByPlaceholderText(
      'list.filter.search.placeholder',
    );
    await fireEvent.change(searchInput, { target: { value: 'searchValue' } });

    const scopeButton = screen.queryByRole('button', {
      name: 'list.filter.scope.label',
    });
    expect(scopeButton).not.toBeInTheDocument();
  });

  it('calls onRefresh when refresh button is clicked', async () => {
    const onRefresh = vi.fn();
    render(
      <StoragesFilter
        onFilterChange={() => {}}
        isInProjects
        onRefresh={onRefresh}
      />,
    );

    const refreshButton = screen.getByRole('button', {
      name: 'actions.refresh.title',
    });
    await fireEvent.click(refreshButton);

    expect(onRefresh).toHaveBeenCalled();
  });
});
