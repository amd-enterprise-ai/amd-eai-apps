// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';

import { Tab, Tabs } from '@amdenterpriseai/components';

describe('Tabs adapter', () => {
  it('re-exports HeroUI Tabs and Tab', () => {
    expect(Tabs).toBeDefined();
    expect(Tab).toBeDefined();
  });

  it('exposes Tabs.Tab compound sub-component', () => {
    expect(Tabs.Tab).toBe(Tab);
  });

  it('renders tabs and switches selection via selectedKey', async () => {
    const TabsFixture = () => {
      const [selectedKey, setSelectedKey] = useState('one');
      return (
        <Tabs selectedKey={selectedKey} onSelectionChange={setSelectedKey}>
          <Tab key="one" title="One">
            Panel one
          </Tab>
          <Tab key="two" title="Two">
            Panel two
          </Tab>
        </Tabs>
      );
    };

    await act(() => {
      render(<TabsFixture />);
    });

    expect(screen.getByText('Panel one')).toBeInTheDocument();
    expect(screen.queryByText('Panel two')).not.toBeInTheDocument();

    const twoTab = screen.getByRole('tab', { name: 'Two' });
    await act(() => {
      fireEvent.click(twoTab);
    });

    expect(screen.getByText('Panel two')).toBeInTheDocument();
    expect(screen.queryByText('Panel one')).not.toBeInTheDocument();
  });

  it('supports compound Tabs.Tab syntax', async () => {
    await act(() => {
      render(
        <Tabs selectedKey="alpha">
          <Tabs.Tab key="alpha" title="Alpha">
            Alpha panel
          </Tabs.Tab>
        </Tabs>,
      );
    });

    expect(screen.getByText('Alpha panel')).toBeInTheDocument();
  });

  it('defaults to fit-content tab list width', () => {
    const { container } = render(
      <Tabs selectedKey="one" aria-label="Width test">
        <Tab key="one" title="One" />
        <Tab key="two" title="Two" />
      </Tabs>,
    );

    expect(container.querySelector('.tabs__list')).toHaveClass('w-fit');
    expect(container.querySelector('.tabs__tab')).toHaveClass('w-fit');
  });

  it('renders full-width tab list when fullWidth is true', () => {
    const { container } = render(
      <Tabs selectedKey="one" fullWidth aria-label="Width test">
        <Tab key="one" title="One" />
        <Tab key="two" title="Two" />
      </Tabs>,
    );

    expect(container.querySelector('.tabs__list')).toHaveClass('w-full');
    expect(container.querySelector('.tabs__tab')).toHaveClass('w-full');
  });

  it('renders full-width secondary strip with fit-content tabs', () => {
    const { container } = render(
      <Tabs
        selectedKey="one"
        variant="secondary"
        aria-label="Secondary width test"
      >
        <Tab key="one" title="One" />
        <Tab key="two" title="Two" />
      </Tabs>,
    );

    expect(container.querySelector('.tabs__list-container')).toHaveClass(
      'w-full',
    );
    expect(container.querySelector('.tabs__list')).toHaveClass('w-full');
    expect(container.querySelector('.tabs__tab')).toHaveClass('w-fit');
  });
});
