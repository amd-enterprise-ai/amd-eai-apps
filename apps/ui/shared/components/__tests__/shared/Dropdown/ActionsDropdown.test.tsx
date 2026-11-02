// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ActionFieldHintType } from '@amdenterpriseai/types';

import { ActionsDropdown } from '@amdenterpriseai/components';

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

vi.mock('../../../src/Tooltip', () => ({
  Tooltip: ({ children, content }: any) => (
    <div data-testid="mock-tooltip">
      {children}
      {content && <div data-testid="tooltip-content">{content}</div>}
    </div>
  ),
}));

const openMenu = async () => {
  fireEvent.click(screen.getByText('action-dot-icon'));
};

describe('ActionsDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders the default trigger', () => {
      render(
        <ActionsDropdown
          actions={[{ key: 'edit', label: 'Edit', onPress: vi.fn() }]}
        />,
      );

      expect(screen.getByText('action-dot-icon')).toBeInTheDocument();
    });

    it('returns null when actions array is empty', () => {
      const { container } = render(<ActionsDropdown actions={[]} />);

      expect(container.firstChild).toBeNull();
    });

    it('renders a custom trigger child', () => {
      render(
        <ActionsDropdown
          actions={[{ key: 'edit', label: 'Edit', onPress: vi.fn() }]}
        >
          <button type="button">custom-trigger</button>
        </ActionsDropdown>,
      );

      expect(screen.getByText('custom-trigger')).toBeInTheDocument();
    });
  });

  describe('Items', () => {
    it('renders all actions when opened', async () => {
      render(
        <ActionsDropdown
          actions={[
            { key: 'edit', label: 'Edit', onPress: vi.fn() },
            { key: 'delete', label: 'Delete', onPress: vi.fn() },
          ]}
        />,
      );
      await openMenu();

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument();
        expect(screen.getByText('Delete')).toBeInTheDocument();
      });
    });

    it('applies danger variant', async () => {
      render(
        <ActionsDropdown
          actions={[
            {
              key: 'danger',
              label: 'Danger',
              color: 'danger',
              onPress: vi.fn(),
            },
          ]}
        />,
      );
      await openMenu();

      await waitFor(() => {
        expect(screen.getByTestId('danger')).toHaveClass('menu-item--danger');
      });
    });

    it('forwards aria-label, testid, and description', async () => {
      render(
        <ActionsDropdown
          actions={[
            {
              key: 'edit',
              label: 'Edit',
              description: 'Edit the thing',
              onPress: vi.fn(),
            },
          ]}
        />,
      );
      await openMenu();

      await waitFor(() => {
        expect(screen.getByTestId('edit')).toHaveAttribute(
          'aria-label',
          'Edit',
        );
        expect(screen.getByText('Edit the thing')).toBeInTheDocument();
      });
    });
  });

  describe('Action handling', () => {
    it('calls the leaf onPress', async () => {
      const editPress = vi.fn();
      const deletePress = vi.fn();
      render(
        <ActionsDropdown
          actions={[
            { key: 'edit', label: 'Edit', onPress: editPress },
            { key: 'delete', label: 'Delete', onPress: deletePress },
          ]}
        />,
      );
      await openMenu();
      await waitFor(() => expect(screen.getByText('Edit')).toBeInTheDocument());

      fireEvent.click(screen.getByText('Edit'));

      expect(editPress).toHaveBeenCalledTimes(1);
      expect(deletePress).not.toHaveBeenCalled();
    });

    it('does not call onPress for disabled items', async () => {
      const disabledPress = vi.fn();
      render(
        <ActionsDropdown
          actions={[
            {
              key: 'disabled',
              label: 'Disabled',
              isDisabled: true,
              onPress: disabledPress,
            },
          ]}
        />,
      );
      await openMenu();
      await waitFor(() =>
        expect(screen.getByText('Disabled')).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByText('Disabled'));

      expect(disabledPress).not.toHaveBeenCalled();
    });
  });

  describe('Sections', () => {
    it('renders a section header and its items', async () => {
      render(
        <ActionsDropdown
          actions={[
            {
              key: 'group',
              label: 'Group',
              isSection: true,
              onPress: vi.fn(),
              actions: [{ key: 'item1', label: 'Item 1', onPress: vi.fn() }],
            },
          ]}
        />,
      );
      await openMenu();

      await waitFor(() => {
        expect(screen.getByText('Group')).toBeInTheDocument();
        expect(screen.getByText('Item 1')).toBeInTheDocument();
      });
    });
  });

  describe('Submenus', () => {
    it('renders a submenu parent with the submenu affordance', async () => {
      render(
        <ActionsDropdown
          actions={[
            {
              key: 'parent',
              label: 'Parent',
              onPress: vi.fn(),
              actions: [{ key: 'child', label: 'Child', onPress: vi.fn() }],
            },
          ]}
        />,
      );
      await openMenu();

      await waitFor(() => {
        const parent = screen.getByTestId('parent');
        expect(parent).toBeInTheDocument();
        expect(parent).toHaveAttribute('data-has-submenu', 'true');
      });
    });

    it('treats an empty actions array as a regular item', async () => {
      const onPress = vi.fn();
      render(
        <ActionsDropdown
          actions={[{ key: 'leaf', label: 'Leaf', onPress, actions: [] }]}
        />,
      );
      await openMenu();
      await waitFor(() => expect(screen.getByText('Leaf')).toBeInTheDocument());

      expect(screen.getByTestId('leaf')).not.toHaveAttribute(
        'data-has-submenu',
      );
      fireEvent.click(screen.getByText('Leaf'));
      expect(onPress).toHaveBeenCalledTimes(1);
    });
  });

  describe('Hints', () => {
    it('renders top-level hints in a tooltip', async () => {
      render(
        <ActionsDropdown
          actions={[
            {
              key: 'edit',
              label: 'Edit',
              onPress: vi.fn(),
              hint: [
                { message: 'info hint', type: ActionFieldHintType.INFO },
                { message: 'warning hint', type: ActionFieldHintType.WARNING },
              ],
            },
          ]}
        />,
      );
      await openMenu();

      await waitFor(() => {
        expect(screen.getByText('info hint')).toBeInTheDocument();
        expect(screen.getByText('warning hint')).toBeInTheDocument();
        expect(screen.getByText('info hint').previousSibling).toHaveClass(
          'text-info',
        );
        expect(screen.getByText('warning hint').previousSibling).toHaveClass(
          'text-warning',
        );
      });
    });
  });
});
