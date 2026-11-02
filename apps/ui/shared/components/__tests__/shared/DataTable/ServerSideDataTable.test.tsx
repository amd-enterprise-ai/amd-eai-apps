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

import { TFunction } from 'next-i18next';

import { PageFrameSize } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';

import { ServerSideDataTable } from '@amdenterpriseai/components';

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

describe('ServerSideDataTable', () => {
  const mockData = [
    { id: 1, name: 'Alice', age: 30 },
    { id: 2, name: 'Bob', age: 45 },
    { id: 3, name: 'Charlie', age: 35 },
  ];

  const mockColumns = [{ key: 'name' }, { key: 'age', sortable: true }];

  const mockCallbacks = {
    handleDataRequest: vi.fn(),
  };
  const mockTranslation = ((a: any) => a) as TFunction;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should set render sort button if sortable is set true on field', () => {
    act(() => {
      render(
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
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
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
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
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={[]}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={0}
        />,
      );
    });

    const emptyStateMessage = screen.getByText('list.empty.description');
    expect(emptyStateMessage).toBeInTheDocument();
  });

  it('should render cell data correctly', () => {
    act(() => {
      render(
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
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
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
        />,
      );
    });

    const pagination = screen.queryByLabelText(
      'list.pagination.pageSize.label',
    );
    expect(pagination).toBeFalsy();
  });

  it('should call handleRequest with correct frame size change', async () => {
    const mockData = generateRandomData(11);

    await act(() => {
      render(
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
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
      expect(mockCallbacks.handleDataRequest).toHaveBeenCalledWith({
        page: 1,
        pageSize: PageFrameSize.LARGE,
        sort: [
          {
            direction: SortDirection.ASC,
            field: 'name',
          },
        ],
      });
    });
  });

  it('should call onPageChange with the correct page in pagination', () => {
    const mockData = generateRandomData(35);

    act(() => {
      render(
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
        />,
      );
    });

    const paginationButton = screen.getAllByLabelText('pagination item 3');
    fireEvent.click(paginationButton[0]);

    expect(mockCallbacks.handleDataRequest).toHaveBeenCalledWith({
      page: 3,
      pageSize: 10,
      sort: [
        {
          direction: SortDirection.ASC,
          field: 'name',
        },
      ],
    });
  });

  it('should call onSortChange correctly', () => {
    act(() => {
      render(
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
        />,
      );
    });

    const sortButton = screen.getByText('list.headers.age.title');
    fireEvent.click(sortButton);

    expect(mockCallbacks.handleDataRequest).toHaveBeenCalledWith({
      page: 1,
      pageSize: 10,
      sort: [
        {
          direction: SortDirection.ASC,
          field: 'age',
        },
      ],
    });
  });

  it('should call onSortChange correctly with opposite direction', () => {
    act(() => {
      render(
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
        />,
      );
    });

    const sortButton = screen.getByText('list.headers.age.title');

    // click twice to reverse
    fireEvent.click(sortButton);
    fireEvent.click(sortButton);

    expect(mockCallbacks.handleDataRequest).toHaveBeenCalledWith({
      page: 1,
      pageSize: 10,
      sort: [
        {
          direction: SortDirection.DESC,
          field: 'age',
        },
      ],
    });
  });

  it('should call onRowPressed when a row is clicked', () => {
    const mockOnRowPressed = vi.fn();

    act(() => {
      render(
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
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
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={mockColumns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
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

  it('should render the description if a column needs it', () => {
    const columns = [
      { key: 'name' },
      { key: 'age', sortable: true, hasDescription: true },
    ];
    act(() => {
      render(
        <ServerSideDataTable
          handleDataRequest={mockCallbacks.handleDataRequest}
          data={mockData}
          columns={columns}
          defaultSortByField="name"
          translation={mockTranslation}
          idKey="id"
          total={mockData.length}
        />,
      );
    });

    const emptyStateMessage = screen.getByText('list.headers.age.description');
    expect(emptyStateMessage).toBeInTheDocument();
  });
});
