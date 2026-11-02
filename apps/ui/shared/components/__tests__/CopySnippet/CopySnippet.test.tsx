// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CopySnippet } from '@amdenterpriseai/components';

describe('CopySnippet adapter', () => {
  let writeText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    writeText = vi.fn();
    writeText.mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
  });

  it('renders single-line children in a read-only input', () => {
    render(<CopySnippet>hello-world</CopySnippet>);
    expect(screen.getByDisplayValue('hello-world')).toBeInTheDocument();
  });

  it('renders the text passed via the value prop', () => {
    render(<CopySnippet value="from-value" />);
    expect(screen.getByDisplayValue('from-value')).toBeInTheDocument();
  });

  it('renders multiline content in a read-only textarea', () => {
    render(<CopySnippet value={'line one\nline two'} />);
    const textarea = screen.getByRole('textbox');
    expect(textarea.tagName).toBe('TEXTAREA');
    expect(textarea).toHaveValue('line one\nline two');
    expect(screen.queryByDisplayValue('line one')).not.toBeInTheDocument();
  });

  it('places the multiline copy button inside the input group suffix', () => {
    render(<CopySnippet value={'line one\nline two'} />);
    const copyButton = screen.getByRole('button', { name: 'Copy' });
    const textarea = screen.getByRole('textbox');
    expect(textarea.closest('.input-group')).toContainElement(copyButton);
  });

  it('renders the label when provided', () => {
    render(<CopySnippet label="API key" value="secret" />);
    expect(screen.getByText('API key')).toBeInTheDocument();
  });

  it('renders the description when provided', () => {
    render(
      <CopySnippet
        label="API key"
        description="Copy this key now — it will not be shown again."
        value="secret"
      />,
    );
    expect(
      screen.getByText('Copy this key now — it will not be shown again.'),
    ).toBeInTheDocument();
  });

  it('forwards aria-label to the read-only field', () => {
    render(
      <CopySnippet aria-label="API endpoint" value="https://example.com" />,
    );
    expect(screen.getByLabelText('API endpoint')).toHaveValue(
      'https://example.com',
    );
  });

  it('writes the value to the clipboard when the copy button is clicked', async () => {
    render(<CopySnippet>copy-me</CopySnippet>);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('copy-me');
    });
  });

  it('extracts text from element children for clipboard copy', async () => {
    render(
      <CopySnippet>
        <span>nested-value</span>
      </CopySnippet>,
    );
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('nested-value');
    });
  });

  it('hides the copy button when hideCopyButton is set', () => {
    render(<CopySnippet hideCopyButton>no-copy</CopySnippet>);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('forwards copyButtonAriaLabel to the copy button', () => {
    render(
      <CopySnippet copyButtonAriaLabel="Copy API key">secret</CopySnippet>,
    );
    expect(
      screen.getByRole('button', { name: 'Copy API key' }),
    ).toBeInTheDocument();
  });

  it('renders only the copy button in button-only mode', async () => {
    render(<CopySnippet buttonOnly value="copy-me" />);

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('copy-me');
    });
  });

  it('calls onCopySuccess and shows a success check icon after copy', async () => {
    const onCopySuccess = vi.fn();
    const { container } = render(
      <CopySnippet onCopySuccess={onCopySuccess}>copy-me</CopySnippet>,
    );
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('copy-me');
      expect(onCopySuccess).toHaveBeenCalledTimes(1);
      expect(container.querySelector('.text-success')).toBeInTheDocument();
    });
  });

  it('calls onCopyError when clipboard write fails', async () => {
    const onCopyError = vi.fn();
    writeText.mockRejectedValue(new Error('denied'));
    render(<CopySnippet onCopyError={onCopyError}>copy-me</CopySnippet>);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(onCopyError).toHaveBeenCalledTimes(1);
    });
  });
});
