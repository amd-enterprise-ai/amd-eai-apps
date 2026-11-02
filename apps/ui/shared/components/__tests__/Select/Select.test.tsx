// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { Select, SelectItem } from '@amdenterpriseai/components';

describe('Select adapter', () => {
  it('exposes Item as a static property', () => {
    expect(Select.Item).toBe(SelectItem);
  });

  it('renders single-select with selectedKeys', () => {
    render(
      <Select label="Fruit" selectedKeys={['apple']} aria-label="Fruit">
        <SelectItem key="apple">Apple</SelectItem>
      </Select>,
    );
    expect(screen.getByRole('button', { name: /Fruit/ })).toBeInTheDocument();
  });

  it('accepts onSelectionChange', () => {
    const onSelectionChange = vi.fn();
    render(
      <Select
        label="Color"
        onSelectionChange={onSelectionChange}
        aria-label="Color"
      >
        <SelectItem key="red">Red</SelectItem>
      </Select>,
    );
    expect(screen.getByRole('button', { name: /Color/ })).toBeInTheDocument();
  });

  it('renders multi-select', () => {
    render(
      <Select
        label="Tags"
        selectionMode="multiple"
        selectedKeys={['a']}
        aria-label="Tags"
      >
        <SelectItem key="a">Alpha</SelectItem>
      </Select>,
    );
    expect(screen.getByRole('button', { name: /Tags/ })).toBeInTheDocument();
  });

  it('renders compound syntax', () => {
    render(
      <Select label="Size" selectedKeys={['md']} aria-label="Size">
        <Select.Item key="md">Medium</Select.Item>
      </Select>,
    );
    expect(screen.getByRole('button', { name: /Size/ })).toBeInTheDocument();
  });

  it('shows the label tooltip on focus', async () => {
    const user = userEvent.setup();
    render(
      <Select label="Fruit" tooltipContent="Choose your favorite fruit">
        <SelectItem key="apple">Apple</SelectItem>
      </Select>,
    );
    const trigger = screen.getByRole('button', {
      name: 'Choose your favorite fruit',
    });
    await user.tab();
    expect(trigger).toHaveFocus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Choose your favorite fruit',
    );
  });

  it('wraps startContent and endContent in a clip-safe span', () => {
    const { container } = render(
      <Select
        aria-label="Wrapped"
        startContent={<svg data-testid="start-icon" />}
        endContent={<svg data-testid="end-icon" />}
      >
        <SelectItem key="a">A</SelectItem>
      </Select>,
    );
    const startIcon = container.querySelector('[data-testid="start-icon"]');
    const endIcon = container.querySelector('[data-testid="end-icon"]');
    expect(startIcon?.closest('span.shrink-0')).not.toBeNull();
    expect(endIcon?.closest('span.shrink-0')).not.toBeNull();
  });

  it('renders startContent with a falsy-but-valid ReactNode value of 0', () => {
    const { container } = render(
      <Select aria-label="Zero" startContent={0}>
        <SelectItem key="a">A</SelectItem>
      </Select>,
    );
    // The wrapper span should be present even when startContent is 0
    const trigger = container.querySelector('button');
    expect(trigger?.querySelector('span.shrink-0')).not.toBeNull();
  });

  it('shows placeholder and select-value slot when renderValue is set but nothing is selected', () => {
    const { container } = render(
      <Select
        aria-label="Select model"
        placeholder="Select model"
        selectedKeys={[]}
        renderValue={(items) => items.map((item) => <span key={item.key} />)}
      >
        <SelectItem key="a">Alpha</SelectItem>
      </Select>,
    );
    expect(screen.getByText('Select model')).toBeInTheDocument();
    expect(
      container.querySelector('[data-slot="select-value"]'),
    ).toBeInTheDocument();
  });

  it('opens listbox when renderValue is set but nothing is selected', async () => {
    const user = userEvent.setup();
    render(
      <Select
        aria-label="Select model"
        placeholder="Select model"
        selectedKeys={[]}
        renderValue={(items) => items.map((item) => <span key={item.key} />)}
      >
        <SelectItem key="a">Alpha</SelectItem>
        <SelectItem key="b">Beta</SelectItem>
      </Select>,
    );
    await user.click(screen.getByRole('button', { name: /Select model/ }));
    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });
  });

  it('hides SelectItem description in trigger by default when selected', () => {
    const { container } = render(
      <Select aria-label="Model" selectedKeys={['a']}>
        <SelectItem key="a" description="1.0.0 · Throughput">
          Inference Running
        </SelectItem>
      </Select>,
    );
    const trigger = container.querySelector('[data-slot="select-trigger"]');
    expect(trigger).toHaveTextContent('Inference Running');
    expect(trigger).not.toHaveTextContent('1.0.0 · Throughput');
  });

  it('shows SelectItem description in trigger when showDescriptionInTrigger is set', () => {
    const { container } = render(
      <Select aria-label="Model" selectedKeys={['a']} showDescriptionInTrigger>
        <SelectItem key="a" description="1.0.0 · Throughput">
          Inference Running
        </SelectItem>
      </Select>,
    );
    const trigger = container.querySelector('[data-slot="select-trigger"]');
    expect(trigger).toHaveTextContent('Inference Running');
    expect(trigger).toHaveTextContent('1.0.0 · Throughput');
  });

  it('shows comma-separated labels only in multi-select trigger when descriptions are set', () => {
    const { container } = render(
      <Select
        aria-label="Models"
        selectionMode="multiple"
        selectedKeys={['a', 'b']}
      >
        <SelectItem key="a" description="1.0.0">
          Alpha
        </SelectItem>
        <SelectItem key="b" description="2.0.0">
          Beta
        </SelectItem>
      </Select>,
    );
    const trigger = container.querySelector('[data-slot="select-trigger"]');
    expect(trigger).toHaveTextContent('Alpha, Beta');
    expect(trigger).not.toHaveTextContent('1.0.0');
    expect(trigger).not.toHaveTextContent('2.0.0');
  });

  it('uses renderValue for selected items when provided', () => {
    render(
      <Select
        aria-label="Model"
        selectedKeys={['a']}
        renderValue={(items) => <span>Custom {String(items[0]?.key)}</span>}
      >
        <SelectItem key="a">Alpha</SelectItem>
      </Select>,
    );
    expect(screen.getByText('Custom a')).toBeInTheDocument();
  });

  it('defaults to secondary variant on the root', () => {
    const { container } = render(
      <Select aria-label="Fruit">
        <SelectItem key="apple">Apple</SelectItem>
      </Select>,
    );
    expect(container.querySelector('.select--secondary')).toBeInTheDocument();
  });

  it('applies primary variant when requested', () => {
    const { container } = render(
      <Select aria-label="Fruit" variant="primary">
        <SelectItem key="apple">Apple</SelectItem>
      </Select>,
    );
    expect(container.querySelector('.select--primary')).toBeInTheDocument();
  });

  it('derives listbox aria-label from string label', async () => {
    const user = userEvent.setup();
    render(
      <Select label="Fruit">
        <SelectItem key="apple">Apple</SelectItem>
      </Select>,
    );
    await user.click(screen.getByRole('button', { name: /Fruit/ }));
    const listbox = await screen.findByRole('listbox');
    expect(listbox).toHaveAttribute('aria-label', 'Fruit');
  });
});
