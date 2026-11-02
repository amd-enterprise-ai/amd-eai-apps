// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import BaseDataTable from '@/src/DataTable/BaseDataTable';
import { SortDirection } from '@amdenterpriseai/types';

type Row = { id: string; name: string; score: number };

const columns = [
  { key: 'name' as const, sortable: true },
  { key: 'score' as const, sortable: true },
];

const rows: Row[] = [
  { id: '1', name: 'Alpha', score: 10 },
  { id: '2', name: 'Beta', score: 20 },
];

function translation(key: string): string {
  if (key.includes('.headers.name.title')) return 'Name';
  if (key.includes('.headers.score.title')) return 'Score';
  if (key.includes('.table.ariaLabel')) return 'Test table';
  if (key.includes('.empty.description')) return 'No data';
  return key;
}

describe('BaseDataTable', () => {
  it('renders rows and sortable column header reflects sort descriptor', async () => {
    const onSortChange = vi.fn();
    const onFrameSizeChange = vi.fn();
    const onPageChange = vi.fn();

    await act(() => {
      render(
        <BaseDataTable<Row, 'name' | 'score'>
          data={rows}
          total={2}
          columns={columns}
          idKey="id"
          defaultSortByField="score"
          defaultSortDirection={SortDirection.DESC}
          translation={translation}
          onSortChange={onSortChange}
          onFrameSizeChange={onFrameSizeChange}
          onPageChange={onPageChange}
        />,
      );
    });

    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();

    const scoreHeader = screen.getByRole('columnheader', { name: 'Score' });
    expect(scoreHeader).toHaveAttribute('aria-sort', 'descending');
  });
});
