// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';

import { SearchInput } from '@amdenterpriseai/components';

import { vi } from 'vitest';

// Mock debounce to execute immediately for testing purposes
vi.mock('lodash', async () => {
  const actual = await vi.importActual('lodash');
  return {
    ...(actual as object),
    debounce: (fn: Function) => fn,
  };
});

describe('SearchInput Component', () => {
  it('renders correctly with default props', () => {
    render(<SearchInput />);
    const inputElement = screen.getByRole('searchbox');
    expect(inputElement).toBeInTheDocument();
  });

  it('renders with the correct placeholder', () => {
    const placeholder = 'Search items...';
    render(<SearchInput placeholder={placeholder} />);
    const inputElement = screen.getByPlaceholderText(placeholder);
    expect(inputElement).toBeInTheDocument();
  });

  it('applies the correct size class', () => {
    const { container } = render(<SearchInput size="sm" />);
    const inputWrapper = container.querySelector('.w-54');
    expect(inputWrapper).toBeInTheDocument();
  });

  it('initializes with the default value', () => {
    const defaultValue = 'initial search';
    render(<SearchInput defaultValue={defaultValue} />);
    const inputElement = screen.getByRole('searchbox') as HTMLInputElement;
    expect(inputElement.value).toBe(defaultValue);
  });

  it('updates internal value when the input changes', () => {
    render(<SearchInput />);
    const inputElement = screen.getByRole('searchbox') as HTMLInputElement;

    fireEvent.change(inputElement, { target: { value: 'new search' } });

    expect(inputElement.value).toBe('new search');
  });

  it('calls onValueChange when the input changes', () => {
    const onValueChangeMock = vi.fn();
    render(<SearchInput onValueChange={onValueChangeMock} />);
    const inputElement = screen.getByRole('searchbox');

    fireEvent.change(inputElement, { target: { value: 'test search' } });

    expect(onValueChangeMock).toHaveBeenCalledWith('test search');
  });

  it('updates value when defaultValue prop changes', () => {
    const { rerender } = render(<SearchInput defaultValue="initial" />);
    const inputElement = screen.getByRole('searchbox') as HTMLInputElement;
    expect(inputElement.value).toBe('initial');

    rerender(<SearchInput defaultValue="updated" />);
    expect(inputElement.value).toBe('updated');
  });

  it('uses debounced function when disableDebounce is false', () => {
    const onValueChangeMock = vi.fn();

    render(
      <SearchInput
        onValueChange={onValueChangeMock}
        disableDebounce={false}
        delay={300}
      />,
    );

    const inputElement = screen.getByRole('searchbox');
    fireEvent.change(inputElement, { target: { value: 'debounced search' } });

    expect(onValueChangeMock).toHaveBeenCalledWith('debounced search');
  });

  it('shows clear button after typing in a narrow container', () => {
    render(
      <div className="w-48">
        <SearchInput
          className="w-full max-w-48"
          aria-label="Search"
          placeholder="Search..."
        />
      </div>,
    );
    const inputElement = screen.getByRole('searchbox') as HTMLInputElement;

    fireEvent.change(inputElement, { target: { value: 'hello' } });

    expect(screen.getByRole('button', { name: 'Close' })).toBeVisible();
  });

  it('clears the input when the clear button is clicked', () => {
    render(<SearchInput defaultValue="test value" />);
    const inputElement = screen.getByRole('searchbox') as HTMLInputElement;
    expect(inputElement.value).toBe('test value');

    const clearButton = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(clearButton);

    expect(inputElement.value).toBe('');
  });
});
