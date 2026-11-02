// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { TFunction } from 'next-i18next';

import { PageFrameSize } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';

import { BaseDataTable } from '@amdenterpriseai/components';

const generateRandomData = (numEntries: number) => {
  const names = [
    'Alice',
    'Bob',
    'Charlie',
    'David',
    'Eve',
    'Frank',
    'Grace',
    'Hank',
    'Ivy',
    'Jack',
  ];
  const data = [];
  for (let i = 0; i < numEntries; i++) {
    const id = i + 1;
    const name = names[Math.floor(Math.random() * names.length)];
    const age = Math.floor(Math.random() * 60) + 20; // Random age between 20 and 80
    data.push({ id, name, age });
  }
  return data;
};

describe('BaseDataTable', () => {
  const mockData = [
    { id: 1, name: 'Alice', age: 30 },
    { id: 2, name: 'Bob', age: 45 },
    { id: 3, name: 'Charlie', age: 35 },
  ];

  const mockColumns = [{ key: 'name' }, { key: 'age', sortable: true }];

  const mockTranslation = ((a: any) => a) as TFunction;

  const mockCallbacks = {
    onSortChange: vi.fn(),
    onFrameSizeChange: vi.fn(),
    onPageChange: vi.fn(),
  };

  it('should set render sort button if sortable is set true on field', () => {
    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const ageColumnHeader = screen.getByText('list.headers.age.title');

    expect(ageColumnHeader).toBeTruthy();
    expect(ageColumnHeader.parentElement?.parentElement).toHaveAttribute(
      'aria-sort',
      'none',
    );
  });

  it('should not render sort button if sortable is set to false on field', () => {
    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const nameColumnHeader = screen.getByText('list.headers.name.title');
    expect(nameColumnHeader).toBeInTheDocument();
    expect(nameColumnHeader.parentElement?.parentElement).not.toHaveAttribute(
      'aria-sort',
    );
  });

  it('should display empty state message when data is empty', () => {
    act(() => {
      render(
        <BaseDataTable
          data={[]}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={0}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const emptyStateMessage = screen.getByText('list.empty.description');
    expect(emptyStateMessage).toBeInTheDocument();
  });

  it('should render cell data correctly', () => {
    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    // Check that the cell data is rendered correctly
    const aliceNameCell = screen.getByText('Alice');
    const bobNameCell = screen.getByText('Bob');
    const charlieNameCell = screen.getByText('Charlie');
    const aliceAgeCell = screen.getByText('30');
    const bobAgeCell = screen.getByText('45');
    const charlieAgeCell = screen.getByText('35');

    expect(aliceNameCell).toBeInTheDocument();
    expect(bobNameCell).toBeInTheDocument();
    expect(charlieNameCell).toBeInTheDocument();
    expect(aliceAgeCell).toBeInTheDocument();
    expect(bobAgeCell).toBeInTheDocument();
    expect(charlieAgeCell).toBeInTheDocument();
  });

  it('should not render the pagination component if the number of rows is less than the minimum page size ', () => {
    const mockData = generateRandomData(PageFrameSize.SMALL - 1);

    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const pagination = screen.queryByLabelText(
      'list.pagination.pageSize.label',
    );
    expect(pagination).toBeFalsy();
  });

  it('should call onFrameSizeChange with correct number of rows per when frame size changed that fits all the rows', async () => {
    const mockData = generateRandomData(30);

    await act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const user = userEvent.setup();
    const selectTrigger = document.querySelector(
      'button[data-slot="select-trigger"]',
    ) as HTMLElement;
    await user.click(selectTrigger);

    const options = await screen.findAllByRole('option');
    const largePageSize = options.find(
      (option) => option.textContent === PageFrameSize.LARGE.toString(),
    );
    await user.click(largePageSize as HTMLElement);

    await waitFor(() => {
      expect(mockCallbacks.onFrameSizeChange).toHaveBeenCalledWith(
        PageFrameSize.LARGE,
      );
    });
  });

  it('should call onPageChange with the correct page in pagination', () => {
    const mockData = generateRandomData(35);

    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const paginationButton = screen.getAllByLabelText('pagination item 3');
    fireEvent.click(paginationButton[0]);

    expect(mockCallbacks.onPageChange).toHaveBeenCalledWith(3);
  });

  it('should call onSortChange correctly', () => {
    act(() => {
      render(
        <BaseDataTable
          data={[]}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const sortButton = screen.getByText('list.headers.age.title');
    fireEvent.click(sortButton);

    expect(mockCallbacks.onSortChange).toHaveBeenCalledWith({
      column: 'age',
      direction: SortDirection.ASC,
    });
  });

  it('should call onSortChange correctly with opposite direction', () => {
    act(() => {
      render(
        <BaseDataTable
          data={[]}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const sortButton = screen.getByText('list.headers.age.title');

    // click twice to reverse
    fireEvent.click(sortButton);
    fireEvent.click(sortButton);

    expect(mockCallbacks.onSortChange).toHaveBeenCalledWith({
      column: 'age',
      direction: SortDirection.DESC,
    });
  });

  it('should call onRowPressed when a row is clicked', () => {
    const mockOnRowPressed = vi.fn();

    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
          onRowPressed={mockOnRowPressed}
        />,
      );
    });

    act(() => {
      const aliceRow = screen.getByText('Alice').closest('tr');
      if (aliceRow) {
        fireEvent.click(aliceRow);
      }
    });

    expect(mockOnRowPressed).toHaveBeenCalledWith('1');
  });

  it('should call the corresponding action handler when an action is clicked', () => {
    const mockDeleteAction = vi.fn();

    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          rowActions={[
            {
              key: 'delete',
              onPress: mockDeleteAction,
              label: 'Delete',
            },
            {
              key: 'copy',
              onPress: () => {},
              label: 'copy',
            },
          ]}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={0}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    act(() => {
      const aliceRow = screen.getByText('Bob').closest('tr');
      expect(aliceRow).toBeTruthy();
      const dropDown = within(aliceRow!).getByLabelText('Actions');
      fireEvent.click(dropDown);
    });

    act(() => {
      fireEvent.click(screen.getByText('Delete'));
    });

    expect(mockDeleteAction).toHaveBeenCalledWith({
      id: 2,
      name: 'Bob',
      age: 45,
    });
  });

  it('re-enables row action trigger when isRowDisabled flips without data reference change', async () => {
    const rowActions = [
      {
        key: 'delete',
        onPress: vi.fn(),
        label: 'Delete',
      },
    ];

    const TableWithToggle = () => {
      const [allRowsDisabled, setAllRowsDisabled] = useState(true);
      return (
        <div>
          <button type="button" onClick={() => setAllRowsDisabled(false)}>
            enable-rows
          </button>
          <BaseDataTable
            data={mockData}
            columns={mockColumns}
            rowActions={rowActions}
            defaultSortByField="name"
            translation={mockTranslation}
            idKey="id"
            total={mockData.length}
            onSortChange={mockCallbacks.onSortChange}
            onFrameSizeChange={mockCallbacks.onFrameSizeChange}
            onPageChange={mockCallbacks.onPageChange}
            isRowDisabled={() => allRowsDisabled}
          />
        </div>
      );
    };

    render(<TableWithToggle />);

    const aliceRow = screen.getByText('Alice').closest('tr');
    expect(aliceRow).toBeTruthy();
    const dropDownBefore = within(aliceRow!).getByLabelText('Actions');
    expect(dropDownBefore).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: 'enable-rows' }));

    await waitFor(() => {
      const aliceRowAfter = screen.getByText('Alice').closest('tr');
      expect(aliceRowAfter).toBeTruthy();
      const dropDownAfter = within(aliceRowAfter!).getByLabelText('Actions');
      expect(dropDownAfter).not.toBeDisabled();
    });
  });

  it('should render the description if a column needs it', () => {
    const columns = [
      { key: 'name' },
      { key: 'age', sortable: true, hasDescription: true },
    ];
    act(() => {
      render(
        <BaseDataTable
          data={[]}
          columns={columns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={0}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const emptyStateMessage = screen.getByText('list.headers.age.description');
    expect(emptyStateMessage).toBeInTheDocument();
  });

  it('should render selection checkboxes when isSelectable is true', () => {
    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          isSelectable
          selectedKeys={new Set()}
          onSelectionChange={vi.fn()}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    expect(screen.getByLabelText('Select all')).toBeInTheDocument();
    expect(screen.getByLabelText('Select row 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Select row 2')).toBeInTheDocument();
    expect(screen.getByLabelText('Select row 3')).toBeInTheDocument();
  });

  it('should not render selection checkboxes when isSelectable is not set', () => {
    act(() => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    expect(screen.queryByLabelText('Select all')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Select row 1')).not.toBeInTheDocument();
  });

  it('should call onSelectionChange when a row checkbox is clicked', async () => {
    const onSelectionChange = vi.fn();

    await act(async () => {
      render(
        <BaseDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
          isSelectable
          selectedKeys={new Set()}
          onSelectionChange={onSelectionChange}
          onSortChange={mockCallbacks.onSortChange}
          onFrameSizeChange={mockCallbacks.onFrameSizeChange}
          onPageChange={mockCallbacks.onPageChange}
        />,
      );
    });

    const user = userEvent.setup();
    await user.click(screen.getByLabelText('Select row 1'));

    await waitFor(() => {
      expect(onSelectionChange).toHaveBeenCalled();
    });
  });
});
