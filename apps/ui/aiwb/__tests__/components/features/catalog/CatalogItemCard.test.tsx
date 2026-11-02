// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';

import { WorkspaceCatalogTableItem } from '@/types/workspaces';

import { CatalogItemCard } from '@/components/features/catalog/CatalogItemCard';

const makeWorkload = (
  status: 'Pending' | 'Running' | 'Failed',
  id = `${status.toLowerCase()}-workload`,
) =>
  ({
    id,
    type: 'WORKSPACE',
    name: 'test-workload',
    displayName: 'test-workload',
    createdBy: 'user-1',
    updatedBy: null,
    namespace: 'project1',
    endpoints: {},
    status,
    createdAt: '2023-01-01T00:00:00Z',
    updatedAt: '2023-01-01T00:00:00Z',
  }) as NonNullable<WorkspaceCatalogTableItem['workloads']>[number];

vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const components =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...components,
    ActionButton: ({
      'aria-label': ariaLabel,
      children,
      color,
      isDisabled,
      onPress,
    }: any) => (
      <button
        type="button"
        aria-label={ariaLabel}
        data-color={color}
        disabled={isDisabled}
        onClick={onPress}
      >
        {children}
      </button>
    ),
    ActionsDropdown: ({ children, actions }: any) => (
      <div data-testid="nested-dropdown">
        {children}
        <div data-testid="dropdown-content">
          {actions?.map((action: any) => (
            <button
              key={action.key}
              type="button"
              disabled={action.isDisabled}
              onClick={() => action.onPress?.()}
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
    ),
  };
});

describe('CatalogItemCard', () => {
  const mockItem: WorkspaceCatalogTableItem = {
    id: 'item-1',
    name: 'Test Catalog Item',
    displayName: 'Test Catalog Item',
    slug: 'test-catalog-item',
    description: 'Short description',
    longDescription: 'Long description',
    type: 'WORKSPACE',
    category: 'development',
    createdAt: '2023-01-01T00:00:00Z',
    updatedAt: '2023-01-01T00:00:00Z',
    createdBy: null,
    updatedBy: null,
    usageScope: 'user',
    tags: ['tag1', 'tag2'],
    featuredImage: '',
    requiredResources: {
      gpuCount: 1,
      gpuMemory: 8,
      cpuCoreCount: 4,
      systemMemory: 16,
    },
    available: true,
    externalUrl: 'https://example.com',
    workloadsCount: 0,
    workloads: [],
  };

  const primaryAction = {
    key: 'view',
    label: 'View',
    onPress: vi.fn(),
  };
  const secondaryAction = {
    key: 'secondary',
    label: 'Secondary',
    onPress: vi.fn(),
  };

  const readyAction = {
    key: 'ready',
    label: 'Launch',
    onPress: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the card with name, description, and tags', () => {
    render(
      <CatalogItemCard
        item={mockItem}
        primaryAction={primaryAction}
        secondaryAction={secondaryAction}
        readyAction={readyAction}
      />,
    );
    expect(screen.getByText('Test Catalog Item')).toBeInTheDocument();
    expect(screen.getByText('Short description')).toBeInTheDocument();
    expect(screen.getByText('tag1')).toBeInTheDocument();
    expect(screen.getByText('tag2')).toBeInTheDocument();
    expect(screen.getByText('View')).toBeInTheDocument();
    expect(screen.getByText('Secondary')).toBeInTheDocument();
  });

  it('calls primaryActionClick when card header or primary button is clicked', () => {
    render(
      <CatalogItemCard
        item={mockItem}
        primaryAction={primaryAction}
        readyAction={readyAction}
      />,
    );

    // Click on primary action button
    fireEvent.click(screen.getByText('View'));
    expect(primaryAction.onPress).toHaveBeenCalledTimes(1);
  });

  it('calls secondaryActionClick when secondary button is clicked', () => {
    render(
      <CatalogItemCard
        item={mockItem}
        primaryAction={primaryAction}
        secondaryAction={secondaryAction}
        readyAction={readyAction}
      />,
    );
    fireEvent.click(screen.getByText('Secondary'));
    expect(secondaryAction.onPress).toHaveBeenCalledWith(mockItem);
  });

  it('uses danger color for both failed workload action buttons', () => {
    render(
      <CatalogItemCard
        item={mockItem}
        isFailed
        secondaryAction={secondaryAction}
      />,
    );

    expect(screen.getByRole('button', { name: 'Secondary' })).toHaveAttribute(
      'data-color',
      'danger',
    );
    expect(
      screen.getByRole('button', { name: 'card.actionsMenu' }),
    ).toHaveAttribute('data-color', 'danger');
  });

  it('opens external link when external link button is clicked', () => {
    window.open = vi.fn();
    render(
      <CatalogItemCard
        item={mockItem}
        primaryAction={primaryAction}
        readyAction={readyAction}
      />,
    );
    const externalButton = screen.getByRole('button', {
      name: /more information|card\.moreInformation/i,
    });
    fireEvent.click(externalButton);
    expect(window.open).toHaveBeenCalledWith('https://example.com', '_blank');
  });

  it('disables actions and buttons when item is not available', () => {
    render(
      <CatalogItemCard
        item={{ ...mockItem, available: false }}
        primaryAction={primaryAction}
        secondaryAction={secondaryAction}
        readyAction={readyAction}
      />,
    );
    expect(screen.getByText('View')).toBeDisabled();
    expect(screen.getByText('Secondary')).toBeDisabled();
  });

  it('does not render external link when no externalUrl', () => {
    render(
      <CatalogItemCard
        item={{ ...mockItem, externalUrl: '' }}
        primaryAction={primaryAction}
        readyAction={readyAction}
      />,
    );
    expect(
      screen.queryByRole('button', {
        name: /more information|card\.moreInformation/i,
      }),
    ).not.toBeInTheDocument();
  });

  describe('deploying status indicator', () => {
    it('shows deploying status and a disabled launch button', () => {
      render(
        <CatalogItemCard
          item={{ ...mockItem, workloads: [makeWorkload('Pending')] }}
          isPending
          primaryAction={primaryAction}
        />,
      );

      expect(screen.getByText('status.Deploying')).toBeInTheDocument();
      const launchButton = screen.getByText('list.actions.launch');
      expect(launchButton).toBeDisabled();
      expect(screen.queryByText('Pending...')).not.toBeInTheDocument();
      expect(screen.queryByText('View')).not.toBeInTheDocument();
    });

    it.each([
      {
        name: 'without a pending workload',
        workloads: [],
        props: { isPending: true },
        showsFailed: false,
      },
      {
        name: 'after deployment',
        workloads: [makeWorkload('Running')],
        props: { isPending: true, isDeployed: true },
        showsFailed: false,
      },
      {
        name: 'after failure',
        workloads: [makeWorkload('Failed')],
        props: { isPending: true, isFailed: true },
        showsFailed: true,
      },
    ])(
      'does not show deploying status $name',
      ({ workloads, props, showsFailed }) => {
        render(
          <CatalogItemCard item={{ ...mockItem, workloads }} {...props} />,
        );

        expect(screen.queryByText('status.Deploying')).not.toBeInTheDocument();
        if (showsFailed) {
          expect(screen.getByText('status.Failed')).toBeInTheDocument();
        } else {
          expect(screen.queryByText('status.Failed')).not.toBeInTheDocument();
        }
      },
    );
  });

  describe('details action', () => {
    it('opens details for the running workload when multiple workloads exist', () => {
      const onOpenWorkloadDetails = vi.fn();

      render(
        <CatalogItemCard
          item={{
            ...mockItem,
            workloads: [makeWorkload('Pending'), makeWorkload('Running')],
          }}
          isDeployed
          readyAction={readyAction}
          onOpenWorkloadDetails={onOpenWorkloadDetails}
        />,
      );

      fireEvent.click(screen.getByText('list.actions.details'));

      expect(onOpenWorkloadDetails).toHaveBeenCalledWith('running-workload');
    });
  });
});
