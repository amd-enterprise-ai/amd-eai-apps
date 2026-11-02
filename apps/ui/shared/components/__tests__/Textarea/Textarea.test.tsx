// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Textarea } from '@amdenterpriseai/components';
describe('Textarea adapter', () => {
  it('renders default textarea', () => {
    render(
      <Textarea
        aria-label="Description"
        data-testid="textarea"
        placeholder="Enter text"
      />,
    );
    expect(screen.getByTestId('textarea')).toBeInTheDocument();
  });
  it('supports value updates', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Textarea
        aria-label="Description"
        defaultValue="hello"
        onChange={onChange}
      />,
    );
    await user.type(screen.getByRole('textbox'), '!');
    expect(onChange).toHaveBeenCalled();
  });
  it('respects isDisabled', () => {
    render(<Textarea aria-label="Description" isDisabled value="locked" />);
    expect(screen.getByRole('textbox')).toBeDisabled();
  });
  it('renders endContent inside the input group', () => {
    render(
      <Textarea
        aria-label="Description"
        endContent={<button type="button">Copy</button>}
        value="multiline"
      />,
    );
    const copyButton = screen.getByRole('button', { name: 'Copy' });
    const textarea = screen.getByRole('textbox');
    expect(copyButton).toBeInTheDocument();
    expect(textarea.closest('.input-group')).toContainElement(copyButton);
  });
  it('defaults to secondary variant on InputGroup', () => {
    const { container } = render(
      <Textarea aria-label="Description" data-testid="textarea" />,
    );
    expect(
      container.querySelector('.input-group--secondary'),
    ).toBeInTheDocument();
  });
  it('applies primary variant when requested', () => {
    const { container } = render(
      <Textarea aria-label="Description" variant="primary" />,
    );
    expect(
      container.querySelector('.input-group--primary'),
    ).toBeInTheDocument();
  });
});
