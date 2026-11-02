// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import type { ReactNode } from 'react';
import { useState } from 'react';

import type { SortDescriptor } from '@heroui/react';
import {
  Table,
  TableBody,
  TableCell,
  TableCollection,
  TableColumn,
  TableRow,
} from '@heroui/react';

export default {
  title: 'Components/Table',
} satisfies StoryDefault;

type Row = { id: string; name: string; role: string };

const columns = [
  { id: 'name', label: 'Name', isRowHeader: true },
  { id: 'role', label: 'Role' },
];

const rows: Row[] = [
  { id: '1', name: 'Ada Lovelace', role: 'Engineer' },
  { id: '2', name: 'Grace Hopper', role: 'Admiral' },
  { id: '3', name: 'Katherine Johnson', role: 'Mathematician' },
];

export const FlatAliases: Story = () => {
  const [sortDescriptor, setSortDescriptor] = useState<SortDescriptor>({
    column: 'name',
    direction: 'ascending',
  });

  return (
    <Table.Root>
      <Table.ScrollContainer>
        <Table.Content
          aria-label="Team members"
          onSortChange={setSortDescriptor}
          sortDescriptor={sortDescriptor}
        >
          <Table.Header columns={columns}>
            {(column) => (
              <TableColumn
                allowsSorting
                id={column.id}
                isRowHeader={column.isRowHeader}
              >
                {column.label}
              </TableColumn>
            )}
          </Table.Header>
          <TableBody items={rows}>
            {(item) => (
              <TableRow id={item.id}>
                <TableCollection items={columns}>
                  {(column) => (
                    <TableCell>
                      {(item as Record<string, ReactNode>)[column.id]}
                    </TableCell>
                  )}
                </TableCollection>
              </TableRow>
            )}
          </TableBody>
        </Table.Content>
      </Table.ScrollContainer>
    </Table.Root>
  );
};

export const CompoundAPI: Story = () => (
  <Table.Root>
    <Table.ScrollContainer>
      <Table.Content aria-label="Team members (compound API)">
        <Table.Header columns={columns}>
          {(column) => (
            <Table.Column id={column.id} isRowHeader={column.isRowHeader}>
              {column.label}
            </Table.Column>
          )}
        </Table.Header>
        <Table.Body items={rows}>
          {(item) => (
            <Table.Row id={item.id}>
              <Table.Collection items={columns}>
                {(column) => (
                  <Table.Cell>
                    {(item as Record<string, ReactNode>)[column.id]}
                  </Table.Cell>
                )}
              </Table.Collection>
            </Table.Row>
          )}
        </Table.Body>
      </Table.Content>
    </Table.ScrollContainer>
  </Table.Root>
);
