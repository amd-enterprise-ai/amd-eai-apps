// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  render,
  screen,
  act,
  waitFor,
  fireEvent,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { FilterDropdown, type FilterItem } from '@amdenterpriseai/components';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('FilterDropdown Component', () => {
  const mockItems: FilterItem[] = [
    { key: 'item1', label: 'Item One', description: 'First item description' },
    { key: 'item2', label: 'Item Two', description: 'Second item description' },
    {
      key: 'item3',
      label: 'Item Three',
      description: 'Third item description',
      showDivider: true,
    },
  ];

  const defaultProps = {
    label: 'Test Filter',
    items: mockItems,
  };

  const getTrigger = () => screen.getByRole('button', { name: 'Test Filter' });

  it('renders correctly with default props', () => {
    render(<FilterDropdown {...defaultProps} />);
    const trigger = getTrigger();
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByDisplayValue('Test Filter')).toBeInTheDocument();
  });

  it('reflects external selection in the dropdown menu', async () => {
    const user = userEvent.setup();
    render(<FilterDropdown {...defaultProps} selectedKeys={['item1']} />);
    const triggerButton = getTrigger();
    await user.click(triggerButton);

    const item1 = await screen.findByRole('option', {
      name: 'Item One',
    });
    expect(item1).toHaveAttribute('aria-selected', 'true');
  });

  it('displays multiple selected items in the dropdown menu', async () => {
    render(
      <FilterDropdown {...defaultProps} selectedKeys={['item1', 'item2']} />,
    );
    const triggerButton = getTrigger();
    await fireEvent.click(triggerButton);

    const item1 = await screen.findByRole('option', {
      name: 'Item One',
    });
    const item2 = await screen.findByRole('option', {
      name: 'Item Two',
    });
    expect(item1).toHaveAttribute('aria-selected', 'true');
    expect(item2).toHaveAttribute('aria-selected', 'true');
  });

  it('selects all items by default when no selection is provided', async () => {
    render(<FilterDropdown {...defaultProps} />);
    // No badge or reset button should be visible initially
    expect(screen.queryByRole('badge')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Reset filter' }),
    ).not.toBeInTheDocument();

    const triggerButton = getTrigger();
    await fireEvent.click(triggerButton);

    const menu = await screen.findByRole('listbox');
    const selectedItems = menu.querySelectorAll('[aria-selected="true"]');
    expect(selectedItems.length).toBe(3);
  });

  it('selects no items when defaultSelectedKeys is an empty array', async () => {
    render(<FilterDropdown {...defaultProps} defaultSelectedKeys={[]} />);
    const triggerButton = getTrigger();
    await fireEvent.click(triggerButton);

    const menu = await screen.findByRole('listbox');
    const selectedItems = menu.querySelectorAll('[aria-selected="true"]');
    expect(selectedItems.length).toBe(0);
  });

  it('shows reset button and active state after user interaction', async () => {
    render(<FilterDropdown {...defaultProps} />);
    const triggerButton = getTrigger();
    await fireEvent.click(triggerButton);
    await screen.findByRole('option', { name: 'Item One' });
    await userEvent.keyboard('[ArrowDown]');
    await userEvent.keyboard('[Space]');
    await fireEvent.click(triggerButton);

    await waitFor(() => {
      const badge = screen.getByText('1');
      expect(badge).toBeInTheDocument();
    });

    await waitFor(() => {
      const resetButton = screen.getByLabelText('actions.clear.title');
      expect(resetButton).toBeInTheDocument();
    });
  });

  it('calls onSelectionChange and updates badge', async () => {
    const onSelectionChangeMock = vi.fn();
    render(
      <FilterDropdown
        {...defaultProps}
        onSelectionChange={onSelectionChangeMock}
      />,
    );
    const triggerButton = getTrigger();
    triggerButton.focus();
    await userEvent.keyboard('[Space]');
    await screen.findByRole('option', { name: 'Item One' });
    await userEvent.keyboard('[ArrowDown]');
    await userEvent.keyboard('[Space]');

    await waitFor(() => {
      expect(onSelectionChangeMock).toHaveBeenCalled();
    });

    const selection = onSelectionChangeMock.mock.calls[0][0] as Set<string>;
    expect(selection.size).toBe(1);
    expect(['item1', 'item2', 'item3']).toContain([...selection][0]);

    const badge = await screen.findByText('1');
    expect(badge).toBeInTheDocument();
  });

  it('renders all provided items', async () => {
    render(<FilterDropdown {...defaultProps} />);
    const triggerButton = getTrigger();
    await fireEvent.click(triggerButton);

    for (const item of mockItems) {
      const itemElement = await screen.findByText(item.label);
      expect(itemElement).toBeInTheDocument();
    }
  });

  it('applies showDivider property to dropdown items', async () => {
    render(<FilterDropdown {...defaultProps} />);
    const triggerButton = getTrigger();
    await fireEvent.click(triggerButton);

    await screen.findByRole('listbox');
    expect(screen.getAllByRole('separator')).toHaveLength(1);
  });

  it('supports external control via defaultSelectedKeys', async () => {
    render(
      <FilterDropdown {...defaultProps} defaultSelectedKeys={['item2']} />,
    );
    const triggerButton = getTrigger();
    await fireEvent.click(triggerButton);

    const item2 = await screen.findByRole('option', {
      name: 'Item Two',
    });
    expect(item2).toHaveAttribute('aria-selected', 'true');

    const item1 = await screen.findByRole('option', {
      name: 'Item One',
    });
    expect(item1).toHaveAttribute('aria-selected', 'false');
  });

  it('handles keyboard interactions - open and close dropdown', async () => {
    render(<FilterDropdown {...defaultProps} />);
    const triggerButton = getTrigger();

    await fireEvent.click(triggerButton);

    const listbox = screen.getByRole('listbox');
    expect(listbox).toBeInTheDocument();

    await fireEvent.click(triggerButton);

    await waitFor(() => {
      expect(screen.queryByRole('option')).not.toBeInTheDocument();
    });
  });

  it('opens dropdown, selects second item, then closes and clear filter', async () => {
    render(<FilterDropdown {...defaultProps} />);
    const triggerButton = getTrigger();

    await fireEvent.click(triggerButton);

    const listbox = screen.getByRole('listbox');
    expect(listbox).toBeInTheDocument();

    await screen.findByRole('option', { name: 'Item One' });
    await userEvent.keyboard('[ArrowDown]');
    await userEvent.keyboard('[Space]');

    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    await fireEvent.click(triggerButton);

    await waitFor(() => {
      expect(screen.queryByRole('option')).not.toBeInTheDocument();
    });

    act(() => {
      triggerButton.focus();
    });
    await userEvent.keyboard('[Tab]');
    await userEvent.keyboard('[Tab]');
    await userEvent.keyboard('[Space]');

    await waitFor(() => {
      expect(screen.queryByRole('badge')).not.toBeInTheDocument();
    });

    expect(
      screen.queryByRole('button', { name: 'Reset filter' }),
    ).not.toBeInTheDocument();
  });

  it('clears active filter state after reset', async () => {
    const user = userEvent.setup();
    render(<FilterDropdown {...defaultProps} />);
    const triggerButton = getTrigger();

    await user.click(triggerButton);
    await user.click(await screen.findByRole('option', { name: 'Item Two' }));

    await waitFor(() => {
      expect(screen.getByLabelText('actions.clear.title')).toBeInTheDocument();
    });

    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('actions.clear.title'));

    await waitFor(() => {
      expect(
        screen.queryByLabelText('actions.clear.title'),
      ).not.toBeInTheDocument();
    });
  });

  it('closes the dropdown when Escape is pressed', async () => {
    render(<FilterDropdown {...defaultProps} />);
    const triggerButton = getTrigger();
    await fireEvent.click(triggerButton);
    const listbox = await screen.findByRole('listbox');
    expect(listbox).toBeInTheDocument();

    act(() => {
      listbox.focus();
    });
    await userEvent.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });
  });

  it('closes on Escape even when a filter option is selected', async () => {
    // The underlying RAC Listbox defaults to escapeKeyBehavior="clearSelection",
    // which swallows the first Escape to clear the selection instead of letting
    // the popover dismiss. The filter opts out so Escape always closes — even
    // when a selection is present.
    const user = userEvent.setup();
    render(<FilterDropdown {...defaultProps} selectedKeys={['item1']} />);
    const triggerButton = getTrigger();
    await user.click(triggerButton);

    const selectedOption = await screen.findByRole('option', {
      name: 'Item One',
    });
    expect(selectedOption).toHaveAttribute('aria-selected', 'true');

    const listbox = screen.getByRole('listbox');
    act(() => {
      listbox.focus();
    });
    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });
  });

  it('stays interactive after dismissal — dropdown can be reopened', async () => {
    const user = userEvent.setup();
    render(<FilterDropdown {...defaultProps} />);
    const triggerButton = getTrigger();

    await user.click(triggerButton);
    const listbox = await screen.findByRole('listbox');
    expect(listbox).toBeInTheDocument();

    act(() => {
      listbox.focus();
    });
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    await user.click(triggerButton);
    expect(await screen.findByRole('listbox')).toBeInTheDocument();
  });

  it('applies muted styling to item descriptions when shown', async () => {
    const user = userEvent.setup();
    render(<FilterDropdown {...defaultProps} showDescription />);
    await user.click(getTrigger());
    await screen.findByRole('listbox');
    const description = await screen.findByText('First item description');
    expect(description.closest('.text-muted')).not.toBeNull();
  });

  it('applies reduced opacity to selection indicators before user interaction', async () => {
    const user = userEvent.setup();
    render(<FilterDropdown {...defaultProps} />);
    await user.click(getTrigger());
    await screen.findByRole('listbox');
    expect(document.querySelector('.opacity-30')).not.toBeNull();
  });
});
