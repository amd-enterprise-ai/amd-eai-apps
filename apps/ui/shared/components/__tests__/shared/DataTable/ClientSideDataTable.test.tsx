// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TFunction } from 'next-i18next';

// v3 Select opens its option list via a react-aria overlay; `userEvent` drives
// the trigger press, and the option list mounts in a portal. Helper centralises
// the open-and-pick flow used by the frame-size selector tests.
const selectFrameSize = async (size: PageFrameSize) => {
  const user = userEvent.setup();
  const selectTrigger = document.querySelector(
    'button[data-slot="select-trigger"]',
  ) as HTMLElement;
  await user.click(selectTrigger);
  const options = await screen.findAllByRole('option');
  const target = options.find(
    (option) => option.textContent === size.toString(),
  );
  await user.click(target as HTMLElement);
};

import { PageFrameSize } from '@amdenterpriseai/types';

import { ClientSideDataTable } from '@amdenterpriseai/components';

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

describe('ClientSideDataTable', () => {
  const mockData = [
    { id: 1, name: 'Alice', age: 30 },
    { id: 2, name: 'Bob', age: 45 },
    { id: 3, name: 'Charlie', age: 35 },
  ];

  const mockColumns = [{ key: 'name' }, { key: 'age', sortable: true }];

  const mockTranslation = ((a: any) => a) as TFunction;

  it('should set render sort button if sortable is set true on field', () => {
    act(() => {
      render(
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
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
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
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
        <ClientSideDataTable
          data={[]}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    const emptyStateMessage = screen.getByText('list.empty.description');
    expect(emptyStateMessage).toBeInTheDocument();
  });

  it('should render cell data correctly', () => {
    act(() => {
      render(
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
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
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    const pagination = screen.queryByLabelText(
      'list.pagination.pageSize.label',
    );
    expect(pagination).toBeFalsy();
  });

  it('should render the correct number of rows per when frame size changed', async () => {
    const mockData = generateRandomData(30);

    act(() => {
      render(
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    await selectFrameSize(PageFrameSize.MEDIUM);

    const rows25 = screen.getAllByRole('row');
    expect(rows25).toHaveLength(PageFrameSize.MEDIUM + 1); // +1 for the header row
  });

  it('should render the correct number of rows per when frame size changed that fits all the rows', async () => {
    const mockData = generateRandomData(30);

    act(() => {
      render(
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    await selectFrameSize(PageFrameSize.LARGE);

    const rows100 = screen.getAllByRole('row');
    expect(rows100).toHaveLength(31); // +1 for the header row
  });

  it('should render the correct number of rows in pagination', () => {
    const mockData = generateRandomData(35);

    act(() => {
      render(
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    const paginationButton = screen.getAllByLabelText('pagination item 2');
    fireEvent.click(paginationButton[0]);

    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(PageFrameSize.SMALL + 1); // +1 for the header row
  });

  it('should render the correct number of rows in pagination on the last frame', () => {
    const mockData = generateRandomData(35);

    act(() => {
      render(
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    const paginationButton = screen.getAllByLabelText('pagination item 4');
    fireEvent.click(paginationButton[0]);

    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(6); // +1 for the header row
  });

  it('should render the correct number of rows in pagination with selected frame size', async () => {
    const mockData = generateRandomData(76);

    await act(() => {
      render(
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    act(() => {
      const paginationButton = screen.getAllByLabelText('pagination item 2');
      fireEvent.click(paginationButton[0]);
    });

    await selectFrameSize(PageFrameSize.MEDIUM);

    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(PageFrameSize.MEDIUM + 1); // +1 for the header row
  });

  it('should call onRowPressed when a row is clicked', () => {
    const mockOnRowPressed = vi.fn();

    act(() => {
      render(
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
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
        <ClientSideDataTable
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
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

  it('should show correct data and page number after deleting the last item on a non-first page', () => {
    // 11 items sorted ascending by age: pages 1..10 on page 1, item 11 (age 30) on page 2
    const initialData = Array.from({ length: 11 }, (_, i) => ({
      id: i + 1,
      name: `Item ${i + 1}`,
      age: i + 20,
    }));

    let currentData = [...initialData];
    const { rerender } = render(
      <ClientSideDataTable
        data={currentData}
        columns={mockColumns}
        defaultSortByField="age"
        translation={mockTranslation}
        idKey="id"
      />,
    );

    // Navigate to page 2
    act(() => {
      const page2Button = screen.getAllByLabelText('pagination item 2');
      fireEvent.click(page2Button[0]);
    });

    // Verify we're on page 2 — only 1 row visible (age 30), plus header
    expect(screen.getAllByRole('row')).toHaveLength(2);
    expect(screen.getByText('30')).toBeInTheDocument();

    // Delete the item on page 2 — data shrinks to 10 items (fits on 1 page)
    currentData = currentData.slice(0, 10);
    act(() => {
      rerender(
        <ClientSideDataTable
          data={currentData}
          columns={mockColumns}
          defaultSortByField="age"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    // Page should have been clamped back to 1: 10 rows + header
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(PageFrameSize.SMALL + 1);

    // Page 1 items must be visible
    expect(screen.getByText('20')).toBeInTheDocument();
    // Page 2's item (age 30) must no longer exist in data, and page 1 ends at age 29
    expect(screen.queryByText('30')).not.toBeInTheDocument();

    // With exactly PageFrameSize.SMALL items the pagination bar is hidden
    expect(
      screen.queryByLabelText('list.pagination.pageSize.label'),
    ).not.toBeInTheDocument();
  });

  it('should render the description if a column needs it', () => {
    const columns = [
      { key: 'name' },
      { key: 'age', sortable: true, hasDescription: true },
    ];
    act(() => {
      render(
        <ClientSideDataTable
          data={[]}
          columns={columns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
        />,
      );
    });

    const emptyStateMessage = screen.getByText('list.headers.age.description');
    expect(emptyStateMessage).toBeInTheDocument();
  });
});
