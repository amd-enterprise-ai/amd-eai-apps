// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import React from 'react';

import { ClientSideDataTable } from '../../../src/DataTable/ClientSideDataTable';
import type { TFunction } from 'next-i18next';

import { SortDirection, TableColumns } from '@amdenterpriseai/types';
import type { CustomComparatorConfig } from '@amdenterpriseai/types';

// ---------------------------------------------------------------------------
// Shared data & helpers
// ---------------------------------------------------------------------------

type WorkloadRow = {
  id: string;
  name: string;
  status: 'Pending' | 'Running' | 'Complete' | 'Failed';
  memoryBytes: number;
  createdAt: string;
  projectId: string;
  projectName: string;
};

enum WorkloadColumn {
  NAME = 'name',
  STATUS = 'status',
  MEMORY = 'memoryBytes',
  CREATED_AT = 'createdAt',
  PROJECT = 'projectName',
}

const rows: WorkloadRow[] = [
  {
    id: 'w1',
    name: 'Fraud classifier',
    status: 'Complete',
    memoryBytes: 8_589_934_592,
    createdAt: '2025-02-01T10:00:00Z',
    projectId: 'p1',
    projectName: 'Risk ML',
  },
  {
    id: 'w2',
    name: 'Tokenization',
    status: 'Running',
    memoryBytes: 2_147_483_648,
    createdAt: '2026-01-12T08:30:00Z',
    projectId: 'p2',
    projectName: 'NLP Pipeline',
  },
  {
    id: 'w3',
    name: 'Document parser',
    status: 'Pending',
    memoryBytes: 17_179_869_184,
    createdAt: '2024-12-07T14:15:00Z',
    projectId: 'p1',
    projectName: 'Risk ML',
  },
  {
    id: 'w4',
    name: 'Embedding index',
    status: 'Failed',
    memoryBytes: 4_294_967_296,
    createdAt: '2025-04-19T22:45:00Z',
    projectId: 'p3',
    projectName: 'Search',
  },
];

const columns: TableColumns<WorkloadColumn> = [
  { key: WorkloadColumn.NAME, sortable: true },
  { key: WorkloadColumn.STATUS, sortable: true },
  { key: WorkloadColumn.MEMORY, hasDescription: true, sortable: true },
  { key: WorkloadColumn.CREATED_AT, sortable: true },
];

const baseTranslation = (key: string): string => {
  const keyMap: Record<string, string> = {
    'list.table.ariaLabel': 'Workloads table',
    'list.empty.description': 'No workloads',
    'list.headers.name.title': 'Name',
    'list.headers.status.title': 'Status',
    'list.headers.memoryBytes.title': 'Memory',
    'list.headers.memoryBytes.description': 'Memory in bytes',
    'list.headers.createdAt.title': 'Created At',
    'list.headers.projectName.title': 'Project',
    'list.headers.actions.title': '',
  };
  return keyMap[key] ?? key;
};

const t = baseTranslation as unknown as TFunction;

const statusLabel: Record<WorkloadRow['status'], string> = {
  Pending: 'Queued',
  Running: 'In progress',
  Complete: 'Completed',
  Failed: 'Errored',
};

const statusRank: Record<WorkloadRow['status'], number> = {
  Pending: 0,
  Running: 1,
  Complete: 2,
  Failed: 3,
};

function formatBytes(bytes: number): string {
  return `${(bytes / 1_073_741_824).toFixed(1)} GB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default {
  title: 'Components/DataTable/ClientSideDataTable/Examples',
} satisfies StoryDefault;

// ===========================================================================
// ROW NAVIGATION — onRowPressed examples
// ===========================================================================

export const RowNavigation: Story = () => {
  return (
    <div className="flex flex-col gap-3 max-w-4xl">
      <h3 className="text-base font-semibold">
        Row navigation with onRowPressed
      </h3>
      <p className="text-sm text-muted">
        Click any row to trigger an alert with the row ID. In a real app this
        would call router.push. Notice the cursor changes to pointer on hover.
      </p>
      <ClientSideDataTable<WorkloadRow, keyof WorkloadRow, WorkloadColumn>
        data={rows}
        columns={columns}
        translation={t}
        idKey="id"
        defaultSortByField={WorkloadColumn.NAME}
        defaultSortDirection={SortDirection.ASC}
        onRowPressed={(id) => alert(`Navigate to /workloads/${id}`)}
      />
    </div>
  );
};

export const RowNavigationWithOverflowMenu: Story = () => {
  const columnsWithProject: TableColumns<WorkloadColumn> = [
    { key: WorkloadColumn.NAME, sortable: true },
    { key: WorkloadColumn.STATUS, sortable: true },
    { key: WorkloadColumn.PROJECT, sortable: true },
    { key: WorkloadColumn.CREATED_AT, sortable: true },
  ];

  const rowActions = (item: WorkloadRow) => {
    const actions: Array<{
      key: string;
      label: string;
      onPress: () => void;
    }> = [];
    if (item.projectId) {
      actions.push({
        key: 'view-project',
        label: 'View project',
        onPress: () => alert(`Navigate to /projects/${item.projectId}`),
      });
    }
    return actions;
  };

  return (
    <div className="flex flex-col gap-3 max-w-4xl">
      <h3 className="text-base font-semibold">
        Row navigation + secondary navigation via overflow menu
      </h3>
      <p className="text-sm text-muted">
        Clicking the row alerts the workload ID (primary navigation). Use the
        (...) menu for secondary navigation — e.g. &quot;View project&quot; — no
        links in cells.
      </p>
      <ClientSideDataTable<WorkloadRow, keyof WorkloadRow, WorkloadColumn>
        data={rows}
        columns={columnsWithProject}
        translation={t}
        idKey="id"
        defaultSortByField={WorkloadColumn.NAME}
        defaultSortDirection={SortDirection.ASC}
        onRowPressed={(id) => alert(`Navigate to /workloads/${id}`)}
        rowActions={rowActions}
        customRenderers={{
          [WorkloadColumn.CREATED_AT]: (row) => formatDate(row.createdAt),
        }}
      />
    </div>
  );
};

// ===========================================================================
// RENDERERS — presentation only, no effect on sort order
// ===========================================================================

export const CustomRenderers: Story = () => {
  return (
    <div className="flex flex-col gap-3 max-w-4xl">
      <h3 className="text-base font-semibold">customRenderers only</h3>
      <p className="text-sm text-muted">
        Renderers change <strong>what the user sees</strong> but have no effect
        on sorting. Click the column headers — rows sort by the raw field value,
        not the displayed text. Notice how Status sorts alphabetically (Complete
        → Failed → Pending → Running) instead of by lifecycle stage.
      </p>
      <ClientSideDataTable<WorkloadRow, keyof WorkloadRow, WorkloadColumn>
        data={rows}
        columns={columns}
        translation={t}
        idKey="id"
        defaultSortByField={WorkloadColumn.NAME}
        defaultSortDirection={SortDirection.ASC}
        customRenderers={{
          [WorkloadColumn.STATUS]: (row) => statusLabel[row.status],
          [WorkloadColumn.MEMORY]: (row) => formatBytes(row.memoryBytes),
          [WorkloadColumn.CREATED_AT]: (row) => formatDate(row.createdAt),
        }}
      />
    </div>
  );
};

// ===========================================================================
// COMPARATORS — sort order only, no effect on display
// ===========================================================================

export const CustomComparators: Story = () => {
  const customComparator: CustomComparatorConfig<WorkloadRow, WorkloadColumn> =
    {
      [WorkloadColumn.STATUS]: (a: WorkloadRow, b: WorkloadRow): number =>
        statusRank[a.status] - statusRank[b.status],
      [WorkloadColumn.CREATED_AT]: (a: WorkloadRow, b: WorkloadRow): number =>
        new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    };

  return (
    <div className="flex flex-col gap-3 max-w-4xl">
      <h3 className="text-base font-semibold">customComparator only</h3>
      <p className="text-sm text-muted">
        Comparators change <strong>how rows are ordered</strong> but have no
        effect on display. The cells show raw values (ISO dates, enum strings),
        but Status now sorts by lifecycle rank and Created At sorts
        chronologically.
      </p>
      <ClientSideDataTable<WorkloadRow, keyof WorkloadRow, WorkloadColumn>
        data={rows}
        columns={columns}
        translation={t}
        idKey="id"
        defaultSortByField={WorkloadColumn.STATUS}
        defaultSortDirection={SortDirection.ASC}
        customComparator={customComparator}
      />
    </div>
  );
};

// ===========================================================================
// COMBINED — renderers + comparators as independent concerns
// ===========================================================================

export const RenderersAndComparatorsTogether: Story = () => {
  const customComparator: CustomComparatorConfig<WorkloadRow, WorkloadColumn> =
    {
      [WorkloadColumn.STATUS]: (a: WorkloadRow, b: WorkloadRow): number =>
        statusRank[a.status] - statusRank[b.status],
      [WorkloadColumn.CREATED_AT]: (a: WorkloadRow, b: WorkloadRow): number =>
        new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    };

  return (
    <div className="flex flex-col gap-3 max-w-4xl">
      <h3 className="text-base font-semibold">
        customRenderers + customComparator
      </h3>
      <p className="text-sm text-muted">
        Recommended pattern: renderers format the display, comparators control
        sorting. Each concern is defined independently. Status displays friendly
        labels and sorts by lifecycle rank; Memory displays GB and sorts
        numerically; Created At displays locale text and sorts chronologically.
      </p>
      <ClientSideDataTable<WorkloadRow, keyof WorkloadRow, WorkloadColumn>
        data={rows}
        columns={columns}
        translation={t}
        idKey="id"
        defaultSortByField={WorkloadColumn.STATUS}
        defaultSortDirection={SortDirection.ASC}
        customRenderers={{
          [WorkloadColumn.STATUS]: (row) => statusLabel[row.status],
          [WorkloadColumn.MEMORY]: (row) => formatBytes(row.memoryBytes),
          [WorkloadColumn.CREATED_AT]: (row) => formatDate(row.createdAt),
        }}
        customComparator={customComparator}
      />
    </div>
  );
};
