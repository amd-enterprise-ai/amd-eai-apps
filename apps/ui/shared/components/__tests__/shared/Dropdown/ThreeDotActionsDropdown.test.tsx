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

import { ActionItem } from '@amdenterpriseai/types';
import { ActionFieldHintType } from '@amdenterpriseai/types';

import { ThreeDotActionsDropdown } from '@amdenterpriseai/components';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'list.actions.label': 'Actions',
      };
      return translations[key] ?? key;
    },
  }),
}));

vi.mock('@tabler/icons-react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tabler/icons-react')>();
  return {
    ...actual,
    IconDotsVertical: ({ className }: any) => (
      <span className={className}>action-dot-icon</span>
    ),
    IconInfoCircle: ({ className }: any) => (
      <span className={className}>info-icon</span>
    ),
    IconAlertTriangle: ({ className }: any) => (
      <span className={className}>alert-icon</span>
    ),
  };
});

// Mock HeroUI Tooltip to render content directly
vi.mock('@heroui/react', async () => {
  const actual = await vi.importActual('@heroui/react');
  return {
    ...actual,
  };
});
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    Tooltip: ({ children, content }: any) => (
      <div data-testid="mock-tooltip">
        {children}
        {content && <div data-testid="tooltip-content">{content}</div>}
      </div>
    ),
  };
});

interface TestItem {
  id: string;
  name: string;
}

vi.mock('../../../src/Tooltip', () => ({
  Tooltip: ({ children, content }: any) => (
    <div data-testid="mock-tooltip">
      {children}
      {content && <div data-testid="tooltip-content">{content}</div>}
    </div>
  ),
}));

describe('ThreeDotActionsDropdown', () => {
  const mockItem: TestItem = {
    id: '1',
    name: 'Test Item',
  };

  const createMockActions = (
    overrides: Partial<ActionItem<TestItem>[][0]>[] = [],
  ): ActionItem<TestItem>[] => [
    {
      key: 'edit',
      label: 'Edit',
      onPress: vi.fn(),
      ...overrides[0],
    },
    {
      key: 'delete',
      label: 'Delete',
      color: 'danger',
      onPress: vi.fn(),
      ...overrides[1],
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders correctly with actions', () => {
      const actions = createMockActions();

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Check for the trigger button
      expect(screen.getByText('action-dot-icon')).toBeInTheDocument();
    });

    it('returns null when actions array is empty', () => {
      const { container } = render(
        <ThreeDotActionsDropdown actions={[]} item={mockItem} />,
      );

      expect(container.firstChild).toBeNull();
    });

    it('renders the correct button properties', () => {
      const actions = createMockActions();

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      const button = screen.getByText('action-dot-icon');
      expect(button.parentElement).toHaveAttribute('aria-label', 'Actions');
      expect(button.parentElement).toHaveClass('h-auto w-6 min-w-6');
    });

    it('renders the dots vertical icon with correct styling', () => {
      const actions = createMockActions();

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      const icon = screen.getByText('action-dot-icon');
      expect(icon).toHaveClass('text-muted');
    });
  });

  describe('Actions rendering', () => {
    it('renders all actions as dropdown items when dropdown is opened', async () => {
      const actions = createMockActions();

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Click the trigger button to open the dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for dropdown items to appear
      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument();
        expect(screen.getByText('Delete')).toBeInTheDocument();
      });
    });

    it('applies custom className to dropdown items', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'custom',
          label: 'Custom Action',
          className: 'custom-class',
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for dropdown item to appear and check class
      await waitFor(() => {
        const customItem = screen.getByTestId('custom');
        expect(customItem).toHaveClass('custom-class');
      });
    });

    it('applies danger variant to dropdown items', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'danger-action',
          label: 'Danger Action',
          color: 'danger',
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for dropdown item to appear and check class
      await waitFor(() => {
        const dangerItem = screen.getByTestId('danger-action');
        expect(dangerItem).toHaveClass('menu-item--danger');
      });
    });

    it('does not apply color class for default color', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'default-action',
          label: 'Default Action',
          color: 'default',
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for dropdown item to appear and check class
      await waitFor(() => {
        const defaultItem = screen.getByTestId('default-action');
        expect(defaultItem).not.toHaveClass('text-default');
      });
    });

    it('renders startContent when provided', async () => {
      const startContentTestId = 'start-content';
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'with-icon',
          label: 'With Icon',
          startContent: <span data-testid={startContentTestId}>Icon</span>,
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for dropdown item to appear
      await waitFor(() => {
        expect(screen.getByTestId(startContentTestId)).toBeInTheDocument();
      });
    });

    it('sets correct aria-label for dropdown items', async () => {
      const actions = createMockActions();

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for dropdown items to appear
      await waitFor(() => {
        expect(screen.getByTestId('edit')).toHaveAttribute(
          'aria-label',
          'Edit',
        );
        expect(screen.getByTestId('delete')).toHaveAttribute(
          'aria-label',
          'Delete',
        );
      });
    });

    it('renders description when provided', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'with-description',
          label: 'Action with Description',
          description: 'This is a helpful description',
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for dropdown item and description to appear
      await waitFor(() => {
        expect(
          screen.getByText('This is a helpful description'),
        ).toBeInTheDocument();
      });
    });

    it('renders showDivider when provided', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'with-divider',
          label: 'Action with Divider',
          showDivider: true,
          onPress: vi.fn(),
        },
        {
          key: 'after-divider',
          label: 'Action after Divider',
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for dropdown items to appear
      await waitFor(() => {
        expect(screen.getByTestId('with-divider')).toBeInTheDocument();
        expect(screen.getByTestId('after-divider')).toBeInTheDocument();
      });
    });
  });

  describe('Disabled actions', () => {
    it('handles disabled actions correctly', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'enabled',
          label: 'Enabled Action',
          onPress: vi.fn(),
        },
        {
          key: 'disabled',
          label: 'Disabled Action',
          isDisabled: true,
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Check that both actions are rendered
      await waitFor(() => {
        expect(screen.getByText('Enabled Action')).toBeInTheDocument();
        expect(screen.getByText('Disabled Action')).toBeInTheDocument();
      });
    });

    it('handles multiple disabled actions', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'disabled1',
          label: 'Disabled 1',
          isDisabled: true,
          onPress: vi.fn(),
        },
        {
          key: 'disabled2',
          label: 'Disabled 2',
          isDisabled: true,
          onPress: vi.fn(),
        },
        {
          key: 'enabled',
          label: 'Enabled',
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Check that all actions are rendered
      await waitFor(() => {
        expect(screen.getByText('Disabled 1')).toBeInTheDocument();
        expect(screen.getByText('Disabled 2')).toBeInTheDocument();
        expect(screen.getByText('Enabled')).toBeInTheDocument();
      });
    });

    it('handles actions with undefined isDisabled property', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'undefined-disabled',
          label: 'Undefined Disabled',
          onPress: vi.fn(),
          // isDisabled is undefined
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Action should be rendered and not disabled
      await waitFor(() => {
        expect(screen.getByText('Undefined Disabled')).toBeInTheDocument();
      });
    });

    it('handles actions with isDisabled being a callback function', async () => {
      const mockOnPress1 = vi.fn();
      const mockOnPress2 = vi.fn();

      const actions: ActionItem<TestItem>[] = [
        {
          key: 'action1',
          label: 'Action 1',
          onPress: mockOnPress1,
          isDisabled: (item: TestItem) => !!item,
        },
        {
          key: 'action2',
          label: 'Action 2',
          onPress: mockOnPress2,
          isDisabled: (item: TestItem) => !item,
        },
      ];

      act(() => {
        render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);
      });

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      const action1 = screen.getByText('Action 1');
      const action2 = screen.getByText('Action 2');

      // Wait for actions to appear
      await waitFor(() => {
        expect(action1).toBeInTheDocument();
        expect(action2).toBeInTheDocument();
      });

      await fireEvent.click(action1);
      await fireEvent.click(action2);

      // Action should be rendered and not disabled
      await waitFor(() => {
        expect(mockOnPress1).not.toBeCalled();
        expect(mockOnPress2).toBeCalled();
      });
    });
  });

  describe('Action handling', () => {
    it('calls the correct action onPress when an action is triggered', async () => {
      const editAction = vi.fn();
      const deleteAction = vi.fn();
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'edit',
          label: 'Edit',
          onPress: editAction,
        },
        {
          key: 'delete',
          label: 'Delete',
          onPress: deleteAction,
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Click on the edit action
      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument();
      });

      const editItem = screen.getByText('Edit');
      await fireEvent.click(editItem);

      expect(editAction).toHaveBeenCalledWith(mockItem);
      expect(deleteAction).not.toHaveBeenCalled();
    });

    it('passes the correct item to the action handler', async () => {
      const actionHandler = vi.fn();
      const customItem = { id: '2', name: 'Custom Item', customProp: 'value' };
      const actions: ActionItem<typeof customItem>[] = [
        {
          key: 'test-action',
          label: 'Test Action',
          onPress: actionHandler,
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={customItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Click on the action
      await waitFor(() => {
        expect(screen.getByText('Test Action')).toBeInTheDocument();
      });

      const actionItem = screen.getByText('Test Action');
      await fireEvent.click(actionItem);

      expect(actionHandler).toHaveBeenCalledWith(customItem);
    });

    it('does not trigger action when clicking disabled items', async () => {
      const enabledAction = vi.fn();
      const disabledAction = vi.fn();
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'enabled-action',
          label: 'Enabled Action',
          onPress: enabledAction,
        },
        {
          key: 'disabled-action',
          label: 'Disabled Action',
          isDisabled: true,
          onPress: disabledAction,
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for items to appear
      await waitFor(() => {
        expect(screen.getByText('Enabled Action')).toBeInTheDocument();
        expect(screen.getByText('Disabled Action')).toBeInTheDocument();
      });

      // Try to click disabled action - it should not trigger
      const disabledItem = screen.getByText('Disabled Action');
      await fireEvent.click(disabledItem);

      expect(disabledAction).not.toHaveBeenCalled();
      expect(enabledAction).not.toHaveBeenCalled();
    });
  });

  describe('Edge cases', () => {
    it('handles actions with undefined isDisabled property', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'undefined-disabled',
          label: 'Undefined Disabled',
          onPress: vi.fn(),
          // isDisabled is undefined
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Action should be rendered and not disabled
      await waitFor(() => {
        expect(screen.getByText('Undefined Disabled')).toBeInTheDocument();
      });
    });

    it('handles empty action label', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'empty-label',
          label: '',
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Action should be rendered even with empty label
      await waitFor(() => {
        const actionItem = screen.getByTestId('empty-label');
        expect(actionItem).toBeInTheDocument();
        expect(actionItem).toHaveTextContent('');
      });
    });

    it('handles complex className combinations', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'complex-class',
          label: 'Complex Class',
          className: 'custom-class another-class',
          color: 'warning',
          onPress: vi.fn(),
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Check combined classes
      await waitFor(() => {
        const actionItem = screen.getByTestId('complex-class');
        expect(actionItem).toHaveClass('custom-class another-class');
      });
    });
  });

  describe('Container structure', () => {
    it('renders the correct container structure', () => {
      const actions = createMockActions();
      const { container } = render(
        <ThreeDotActionsDropdown actions={actions} item={mockItem} />,
      );

      const outerDiv = container.firstChild as HTMLElement;
      expect(outerDiv).toHaveClass(
        'relative flex justify-center items-center gap-2',
      );
    });
  });

  describe('Hint rendering', () => {
    it('renders hints when provided and conditions are met', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'action-with-hint',
          label: 'Action with Hint',
          onPress: vi.fn(),
          hint: [
            {
              message: 'This is an info hint',
              type: ActionFieldHintType.INFO,
              showHint: (item: TestItem) => item.id === '1',
            },
            {
              message: 'This is a warning hint',
              type: ActionFieldHintType.WARNING,
              showHint: (item: TestItem) => item.id === '1',
            },
          ],
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Wait for hints to appear (they're rendered immediately with the mock)
      await waitFor(() => {
        expect(screen.getByText('This is an info hint')).toBeInTheDocument();
        expect(screen.getByText('This is a warning hint')).toBeInTheDocument();
        expect(
          screen.getByText('This is an info hint').previousSibling,
        ).toHaveClass('text-info');
        expect(
          screen.getByText('This is a warning hint').previousSibling,
        ).toHaveClass('text-warning');
      });
    });

    it('does not render hints when conditions are not met', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'action-with-hint',
          label: 'Action with Hint',
          onPress: vi.fn(),
          hint: [
            {
              message: 'This hint should not show',
              type: ActionFieldHintType.INFO,
              showHint: (item: TestItem) => item.id === '999',
            },
          ],
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Ensure hint does not appear
      await waitFor(() => {
        expect(
          screen.queryByText('This hint should not show'),
        ).not.toBeInTheDocument();
      });
    });

    it('handles multiple hints with mixed conditions', async () => {
      const actions: ActionItem<TestItem>[] = [
        {
          key: 'action-with-mixed-hints',
          label: 'Action with Mixed Hints',
          onPress: vi.fn(),
          hint: [
            {
              message: 'Visible Hint',
              type: ActionFieldHintType.INFO,
              showHint: (item: TestItem) => item.id === '1',
            },
            {
              message: 'Hidden    Hint', // Extra spaces to ensure distinct text
              type: ActionFieldHintType.WARNING,
              showHint: (item: TestItem) => item.id === '999',
            },
          ],
        },
      ];

      render(<ThreeDotActionsDropdown actions={actions} item={mockItem} />);

      // Open dropdown
      const triggerButton = screen.getByText('action-dot-icon');
      await fireEvent.click(triggerButton);

      // Check that only the visible hint appears
      await waitFor(() => {
        expect(screen.getByText('Visible Hint')).toBeInTheDocument();
        expect(screen.queryByText('Hidden    Hint')).not.toBeInTheDocument();
      });
    });
  });
});
