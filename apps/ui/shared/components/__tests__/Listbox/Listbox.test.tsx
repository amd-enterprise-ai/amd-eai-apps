// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import {
  Listbox,
  ListboxItem,
  ListboxSection,
} from '@amdenterpriseai/components';

describe('Listbox adapter', () => {
  it('exposes Item and Section as static properties', () => {
    expect(Listbox.Item).toBe(ListboxItem);
    expect(Listbox.Section).toBe(ListboxSection);
  });

  it('renders flat item syntax', () => {
    render(
      <Listbox aria-label="Fruit" selectedKeys={['apple']}>
        <ListboxItem key="apple">Apple</ListboxItem>
      </Listbox>,
    );
    expect(screen.getByRole('listbox', { name: 'Fruit' })).toBeInTheDocument();
  });

  it('accepts onSelectionChange', () => {
    const onSelectionChange = vi.fn();
    render(
      <Listbox aria-label="Color" onSelectionChange={onSelectionChange}>
        <ListboxItem key="red">Red</ListboxItem>
      </Listbox>,
    );
    expect(screen.getByRole('listbox', { name: 'Color' })).toBeInTheDocument();
  });

  it('renders compound syntax with section', () => {
    render(
      <Listbox aria-label="Tokens" selectedKeys={['a']}>
        <Listbox.Section title="Existing">
          <Listbox.Item key="a">Alpha</Listbox.Item>
        </Listbox.Section>
      </Listbox>,
    );
    expect(screen.getByRole('listbox', { name: 'Tokens' })).toBeInTheDocument();
  });

  it('renders item description with text-muted by default', () => {
    const { container } = render(
      <Listbox aria-label="Models" selectedKeys={['a']}>
        <ListboxItem key="a" description="1.0.0 · Throughput">
          Inference Running
        </ListboxItem>
      </Listbox>,
    );
    const description = container.querySelector('[data-slot="description"]');
    expect(description).toHaveTextContent('1.0.0 · Throughput');
    expect(description).toHaveClass('text-muted');
  });

  it('applies indicatorClassName to the selection indicator', () => {
    const { container } = render(
      <Listbox aria-label="Color" selectedKeys={['red']}>
        <ListboxItem key="red" indicatorClassName="opacity-30">
          Red
        </ListboxItem>
      </Listbox>,
    );
    expect(container.querySelector('.opacity-30')).not.toBeNull();
  });
});
