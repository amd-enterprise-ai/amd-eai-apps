// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';
import { forwardRef, useState } from 'react';
import { vi } from 'vitest';

import { TagInput } from '@amdenterpriseai/components';

// Mock next-i18next
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        placeholder: 'Add a tag\u2026',
        ariaLabel: 'Tag input',
      };
      if (key === 'errorDisallowedChars')
        return `Tag "${options?.tag}" contains disallowed characters.`;
      if (key === 'errorMinLength')
        return `Tag "${options?.tag}" must be at least ${options?.min} character(s).`;
      if (key === 'errorMaxLength')
        return `Tag "${options?.tag}" must be at most ${options?.max} characters.`;
      if (key === 'errorDuplicate')
        return `"${options?.tag}" is already added.`;
      if (key === 'removeTag') return `Remove tag ${options?.tag}`;
      if (key === 'tagAdded') return `Tag ${options?.tag} added`;
      if (key === 'tagsAdded') return `${options?.count} tags added`;
      if (key === 'tagRemoved') return `Tag ${options?.tag} removed`;
      return map[key] ?? key;
    },
  }),
}));

// ---------------------------------------------------------------------------
// Shared wrapper stubs — TagInput composes the shared `Input` and `Chip`
// wrappers, so stub those directly (not raw HeroUI). This keeps the tests fast,
// deterministic, and independent of the underlying HeroUI version.
// ---------------------------------------------------------------------------
vi.mock('../../../src/Input/InputPrimitive', () => ({
  Input: forwardRef(
    (
      {
        label,
        description,
        placeholder,
        value,
        isDisabled,
        isRequired,
        isInvalid,
        errorMessage,
        onChange,
        onKeyDown,
        onPaste,
        ...rest
      }: any,
      ref: any,
    ) => (
      <div>
        {label && <label htmlFor="tag-input">{label}</label>}
        <input
          ref={ref}
          id="tag-input"
          placeholder={placeholder}
          value={value}
          disabled={isDisabled}
          aria-required={isRequired || undefined}
          aria-invalid={isInvalid}
          onChange={onChange}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          {...rest}
        />
        {description && (
          <span data-testid="tag-input-description">{description}</span>
        )}
        {isInvalid && errorMessage && (
          <span data-testid="tag-input-error">{errorMessage}</span>
        )}
      </div>
    ),
  ),
}));

vi.mock('../../../src/Chip', () => ({
  Chip: ({ children, endContent, ...rest }: any) => (
    <span data-testid={`chip-${children}`} {...rest}>
      {children}
      {endContent}
    </span>
  ),
}));

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

const renderTagInput = (
  overrides: Partial<Parameters<typeof TagInput>[0]> = {},
) => {
  const onChange = vi.fn();
  const { rerender } = render(
    <TagInput value={[]} onChange={onChange} {...overrides} />,
  );
  return {
    onChange,
    input: () => screen.getByRole('textbox'),
    rerender,
  };
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TagInput', () => {
  describe('adding tags', () => {
    it('adds a tag on Enter and clears the input', () => {
      const { onChange, input } = renderTagInput();
      fireEvent.change(input(), { target: { value: 'react' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).toHaveBeenCalledWith(['react']);
      expect(input()).toHaveValue('');
    });

    it('prevents the default Enter action when a tag is pending', () => {
      const { input } = renderTagInput();
      fireEvent.change(input(), { target: { value: 'react' } });
      const prevented = !fireEvent.keyDown(input(), { key: 'Enter' });
      expect(prevented).toBe(true);
    });

    it('does not prevent the default Enter action when the input is empty', () => {
      const { input } = renderTagInput();
      const prevented = !fireEvent.keyDown(input(), { key: 'Enter' });
      expect(prevented).toBe(false);
    });

    it('prevents the default Enter action for whitespace-only input', () => {
      // Whitespace commits no tag, but Enter must still not submit a
      // surrounding form while the user is interacting with the field.
      const { input } = renderTagInput();
      fireEvent.change(input(), { target: { value: '   ' } });
      const prevented = !fireEvent.keyDown(input(), { key: 'Enter' });
      expect(prevented).toBe(true);
    });

    it('commits a pending tag when tabbing out of the field', () => {
      const { onChange, input } = renderTagInput();
      fireEvent.change(input(), { target: { value: 'vue' } });
      // Tab advances focus, firing blur — the single commit-on-focus-loss path.
      fireEvent.blur(input());
      expect(onChange).toHaveBeenCalledWith(['vue']);
    });

    it('does not prevent default on Tab so focus can still advance', () => {
      const { input } = renderTagInput();
      fireEvent.change(input(), { target: { value: 'vue' } });
      const prevented = !fireEvent.keyDown(input(), { key: 'Tab' });
      expect(prevented).toBe(false);
    });

    it('adds a tag when a trailing comma is typed', () => {
      const { onChange, input } = renderTagInput();
      fireEvent.change(input(), { target: { value: 'svelte,' } });
      expect(onChange).toHaveBeenCalledWith(['svelte']);
    });

    it('commits interior comma-delimited tokens and keeps the trailing partial', () => {
      const { onChange, input } = renderTagInput();
      // A single change event may deliver multiple commas (autofill, IME); every
      // complete token commits and the unterminated remainder stays in the field.
      fireEvent.change(input(), { target: { value: 'a,b,c' } });
      expect(onChange).toHaveBeenCalledWith(['a', 'b']);
      expect(input()).toHaveValue('c');
    });

    it('trims whitespace from the candidate before adding', () => {
      const { onChange, input } = renderTagInput();
      fireEvent.change(input(), { target: { value: '  angular  ' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).toHaveBeenCalledWith(['angular']);
    });

    it('does nothing on Enter when the input is empty', () => {
      const { onChange, input } = renderTagInput();
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).not.toHaveBeenCalled();
    });

    it('appends to an existing list', () => {
      const { onChange, input } = renderTagInput({ value: ['existing'] });
      fireEvent.change(input(), { target: { value: 'new-tag' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).toHaveBeenCalledWith(['existing', 'new-tag']);
    });
  });

  describe('removing tags', () => {
    it('renders a remove button for each chip', () => {
      renderTagInput({ value: ['alpha', 'beta'] });
      expect(screen.getByTestId('tag-input-remove-0')).toBeInTheDocument();
      expect(screen.getByTestId('tag-input-remove-1')).toBeInTheDocument();
    });

    it('gives each remove button a distinguishable accessible name', () => {
      renderTagInput({ value: ['alpha', 'beta'] });
      expect(
        screen.getByRole('button', { name: 'Remove tag alpha' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Remove tag beta' }),
      ).toBeInTheDocument();
    });

    it('calls onChange without the removed tag', () => {
      const onChange = vi.fn();
      render(
        <TagInput value={['alpha', 'beta', 'gamma']} onChange={onChange} />,
      );
      fireEvent.click(screen.getByTestId('tag-input-remove-1'));
      expect(onChange).toHaveBeenCalledWith(['alpha', 'gamma']);
    });

    it('removes the last tag on Backspace when input is empty', () => {
      const onChange = vi.fn();
      render(<TagInput value={['alpha', 'beta']} onChange={onChange} />);
      const input = screen.getByRole('textbox');
      fireEvent.keyDown(input, { key: 'Backspace' });
      expect(onChange).toHaveBeenCalledWith(['alpha']);
    });

    it('does not remove chips when disabled', () => {
      renderTagInput({ value: ['alpha'], isDisabled: true });
      expect(
        screen.queryByTestId('tag-input-remove-0'),
      ).not.toBeInTheDocument();
    });

    it('keeps focus in the component after removing a chip', () => {
      const Wrapper = () => {
        const [tags, setTags] = useState(['alpha', 'beta']);
        return <TagInput value={tags} onChange={setTags} />;
      };
      render(<Wrapper />);
      const removeAlpha = screen.getByTestId('tag-input-remove-0');
      removeAlpha.focus();
      fireEvent.click(removeAlpha);
      // Focus shifts to the remove button that moved into the vacated slot
      // rather than falling back to <body>.
      expect(document.activeElement).toBe(
        screen.getByTestId('tag-input-remove-0'),
      );
    });

    it('removes only the clicked duplicate when value contains duplicates', () => {
      const onChange = vi.fn();
      render(
        <TagInput value={['alpha', 'alpha', 'beta']} onChange={onChange} />,
      );
      // Position-based test ids stay unique even for duplicate values, so the
      // first copy can be targeted directly; removal is by index, not equality.
      fireEvent.click(screen.getByTestId('tag-input-remove-0'));
      expect(onChange).toHaveBeenCalledWith(['alpha', 'beta']);
    });

    it('clears a stale error and pending text when the offending tag is removed', () => {
      const Wrapper = () => {
        const [tags, setTags] = useState(['a', 'b']);
        return <TagInput value={tags} onChange={setTags} />;
      };
      render(<Wrapper />);
      const input = screen.getByRole('textbox');
      // Typing a duplicate leaves a rejection error and the pending text behind.
      fireEvent.change(input, { target: { value: 'a' } });
      fireEvent.keyDown(input, { key: 'Enter' });
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        '"a" is already added.',
      );
      // Removing the offending chip clears the now-stale error and pending text…
      fireEvent.click(screen.getByTestId('tag-input-remove-0'));
      expect(screen.queryByTestId('tag-input-error')).not.toBeInTheDocument();
      expect(input).toHaveValue('');
      // …and a subsequent blur must not silently re-add the removed tag.
      fireEvent.blur(input);
      expect(screen.queryByTestId('chip-a')).not.toBeInTheDocument();
      expect(screen.getByTestId('chip-b')).toBeInTheDocument();
    });

    it('moves focus to the last remaining button when the final chip is removed', () => {
      const Wrapper = () => {
        const [tags, setTags] = useState(['alpha', 'beta']);
        return <TagInput value={tags} onChange={setTags} />;
      };
      render(<Wrapper />);
      const removeBeta = screen.getByTestId('tag-input-remove-1');
      removeBeta.focus();
      fireEvent.click(removeBeta);
      // No button occupies the vacated last slot, so focus falls back to the
      // last remaining remove button rather than <body>.
      expect(document.activeElement).toBe(
        screen.getByTestId('tag-input-remove-0'),
      );
    });

    it('moves focus to the input when the only chip is removed', () => {
      const Wrapper = () => {
        const [tags, setTags] = useState(['solo']);
        return <TagInput value={tags} onChange={setTags} />;
      };
      render(<Wrapper />);
      const removeSolo = screen.getByTestId('tag-input-remove-0');
      removeSolo.focus();
      fireEvent.click(removeSolo);
      // No remove buttons remain, so focus falls back to the text input.
      expect(document.activeElement).toBe(screen.getByRole('textbox'));
    });

    it('marks chips as disabled when the field is disabled', () => {
      renderTagInput({ value: ['alpha'], isDisabled: true });
      expect(screen.getByTestId('chip-alpha')).toHaveAttribute(
        'aria-disabled',
        'true',
      );
    });
  });

  describe('paste handling', () => {
    const paste = (input: HTMLElement, text: string) => {
      fireEvent.paste(input, {
        clipboardData: { getData: () => text },
      });
    };

    it('splits a comma-separated paste into multiple chips', () => {
      const { onChange, input } = renderTagInput();
      paste(input(), 'foo,bar,baz');
      expect(onChange).toHaveBeenCalledWith(['foo', 'bar', 'baz']);
    });

    it('splits a newline-separated paste into multiple chips', () => {
      const { onChange, input } = renderTagInput();
      paste(input(), 'foo\nbar\nbaz');
      expect(onChange).toHaveBeenCalledWith(['foo', 'bar', 'baz']);
    });

    it('skips empty tokens in a paste', () => {
      const { onChange, input } = renderTagInput();
      paste(input(), 'foo,,bar,');
      expect(onChange).toHaveBeenCalledWith(['foo', 'bar']);
    });

    it('appends pasted tags to the existing list', () => {
      const { onChange, input } = renderTagInput({ value: ['existing'] });
      paste(input(), 'new1,new2');
      expect(onChange).toHaveBeenCalledWith(['existing', 'new1', 'new2']);
    });

    it('skips duplicate tokens but still adds new ones when pasting', () => {
      const { onChange, input } = renderTagInput({ value: ['alpha'] });
      paste(input(), 'alpha,beta');
      expect(onChange).toHaveBeenCalledWith(['alpha', 'beta']);
      expect(screen.getByTestId('tag-input-error')).toBeInTheDocument();
    });

    it('announces both the addition and the rejection on a mixed paste', () => {
      const { input } = renderTagInput({ value: ['alpha'] });
      paste(input(), 'alpha,beta');
      // Screen-reader users must learn that some tokens were rejected even when
      // others were added, since the visible error alone is not announced.
      const live = screen.getByTestId('tag-input-live');
      expect(live).toHaveTextContent('Tag beta added');
      expect(live).toHaveTextContent('"alpha" is already added.');
    });

    it('merges already-typed text into the paste instead of discarding it', () => {
      const { onChange, input } = renderTagInput();
      const el = input();
      fireEvent.change(el, { target: { value: 'post' } });
      el.setSelectionRange(4, 4);
      paste(el, 'urgent,bug');
      expect(onChange).toHaveBeenCalledWith(['posturgent', 'bug']);
    });

    it('keeps rejected tokens in the field on an all-invalid paste', () => {
      const { onChange, input } = renderTagInput();
      paste(input(), 'bad!,worse!');
      // Nothing is added, but the pasted text stays editable instead of vanishing.
      // Rejected tokens are space-joined so the field holds no re-parseable comma.
      expect(onChange).not.toHaveBeenCalled();
      expect(input()).toHaveValue('bad! worse!');
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        'Tag "worse!" contains disallowed characters.',
      );
    });

    it('does not re-parse rejected tokens written back into the field', () => {
      const { onChange, input } = renderTagInput();
      paste(input(), 'bad!,worse!');
      // The write-back contains no comma, so typing does not re-tokenize or
      // accumulate separators — the field simply reflects the new text.
      fireEvent.change(input(), { target: { value: 'bad! worse!z' } });
      expect(input()).toHaveValue('bad! worse!z');
      expect(onChange).not.toHaveBeenCalled();
    });

    it('tokenizes a tab-separated (spreadsheet) paste', () => {
      const { onChange, input } = renderTagInput();
      paste(input(), 'foo\tbar\tbaz');
      expect(onChange).toHaveBeenCalledWith(['foo', 'bar', 'baz']);
    });

    it('keeps the rejected token editable on a mixed paste', () => {
      const { onChange, input } = renderTagInput();
      paste(input(), 'ok,bad!');
      // The accepted token is committed; the rejected one remains for editing.
      expect(onChange).toHaveBeenCalledWith(['ok']);
      expect(input()).toHaveValue('bad!');
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        'Tag "bad!" contains disallowed characters.',
      );
    });

    it('announces the plural count when several tags are added at once', () => {
      const { input } = renderTagInput();
      paste(input(), 'foo,bar,baz');
      expect(screen.getByTestId('tag-input-live')).toHaveTextContent(
        '3 tags added',
      );
    });

    it('does not call onChange when a paste adds no new tags', () => {
      const { onChange, input } = renderTagInput({ value: ['alpha'] });
      paste(input(), 'alpha,alpha');
      expect(onChange).not.toHaveBeenCalled();
    });

    it('falls through to default paste for plain text without delimiters', () => {
      const { onChange, input } = renderTagInput();
      paste(input(), 'justonetoken');
      // No delimiter → onChange not called, default paste allowed
      expect(onChange).not.toHaveBeenCalled();
    });
  });

  describe('parent-controlled validation', () => {
    it('surfaces a parent-supplied error over internal validation', () => {
      renderTagInput({
        isInvalid: true,
        errorMessage: 'At least 2 tags are required',
      });
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        'At least 2 tags are required',
      );
    });

    it('renders a parent-supplied description', () => {
      renderTagInput({ description: 'Press Enter to add each tag' });
      expect(screen.getByTestId('tag-input-description')).toHaveTextContent(
        'Press Enter to add each tag',
      );
    });

    it('still surfaces internal validation when the parent passes isInvalid={false}', () => {
      // Binding isInvalid to form state (false) must not suppress the
      // component's own tag-level validation.
      const { input } = renderTagInput({ isInvalid: false });
      fireEvent.change(input(), { target: { value: 'bad!' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        'Tag "bad!" contains disallowed characters.',
      );
    });
  });

  describe('blur handling', () => {
    it('commits a pending tag when the field loses focus', () => {
      const { onChange, input } = renderTagInput();
      fireEvent.change(input(), { target: { value: 'backend' } });
      fireEvent.blur(input());
      // Clicking away without pressing Enter/Tab/comma must not lose the tag.
      expect(onChange).toHaveBeenCalledWith(['backend']);
      expect(input()).toHaveValue('');
    });

    it('does not commit on blur when the field is empty', () => {
      const { onChange, input } = renderTagInput();
      fireEvent.blur(input());
      expect(onChange).not.toHaveBeenCalled();
    });

    it('invokes a parent onBlur after committing', () => {
      const onBlur = vi.fn();
      const { onChange, input } = renderTagInput({ onBlur });
      fireEvent.change(input(), { target: { value: 'backend' } });
      fireEvent.blur(input());
      expect(onChange).toHaveBeenCalledWith(['backend']);
      expect(onBlur).toHaveBeenCalledTimes(1);
    });
  });

  describe('ref forwarding', () => {
    it('forwards a ref to the underlying text input', () => {
      const ref = { current: null as HTMLInputElement | null };
      render(<TagInput value={[]} onChange={vi.fn()} ref={ref} />);
      expect(ref.current).toBe(screen.getByRole('textbox'));
    });
  });

  describe('validation', () => {
    it('does not add a whitespace-only tag', () => {
      const { onChange, input } = renderTagInput({ minTagLength: 1 });
      fireEvent.change(input(), { target: { value: '   ' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).not.toHaveBeenCalled();
      // Stray whitespace is dropped so the field state matches "no tag added".
      expect(input()).toHaveValue('');
    });

    it('shows an error for a tag that exceeds maxTagLength', () => {
      const { onChange, input } = renderTagInput({ maxTagLength: 5 });
      fireEvent.change(input(), { target: { value: 'toolongtag' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).not.toHaveBeenCalled();
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        'Tag "toolongtag" must be at most 5 characters.',
      );
    });

    it('shows an error for a tag shorter than minTagLength', () => {
      const { onChange, input } = renderTagInput({ minTagLength: 3 });
      fireEvent.change(input(), { target: { value: 'ab' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).not.toHaveBeenCalled();
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        'Tag "ab" must be at least 3 character(s).',
      );
    });

    it('shows an error for disallowed characters', () => {
      const { onChange, input } = renderTagInput();
      fireEvent.change(input(), { target: { value: 'tag with spaces' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).not.toHaveBeenCalled();
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        'Tag "tag with spaces" contains disallowed characters.',
      );
    });

    it('accepts a custom allowedPattern', () => {
      const { onChange, input } = renderTagInput({
        allowedPattern: /^[a-z]+$/,
      });
      fireEvent.change(input(), { target: { value: 'lowercase' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).toHaveBeenCalledWith(['lowercase']);
    });

    it('requires an un-anchored allowedPattern to match the whole tag', () => {
      const { onChange, input } = renderTagInput({
        allowedPattern: /[a-z]+/,
      });
      fireEvent.change(input(), { target: { value: 'abc123' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).not.toHaveBeenCalled();
      expect(screen.getByTestId('tag-input-error')).toBeInTheDocument();
    });

    it('does not flicker validation across calls for a stateful allowedPattern', () => {
      const { onChange, input } = renderTagInput({
        allowedPattern: /[a-z]+/g,
      });
      fireEvent.change(input(), { target: { value: 'alpha' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      fireEvent.change(input(), { target: { value: 'beta' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).toHaveBeenCalledTimes(2);
      expect(onChange).toHaveBeenNthCalledWith(1, ['alpha']);
      expect(onChange).toHaveBeenNthCalledWith(2, ['beta']);
    });

    it('shows an error for a duplicate tag', () => {
      const { onChange, input } = renderTagInput({ value: ['react'] });
      fireEvent.change(input(), { target: { value: 'react' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(onChange).not.toHaveBeenCalled();
      expect(screen.getByTestId('tag-input-error')).toHaveTextContent(
        '"react" is already added.',
      );
    });

    it('clears the validation error when the user edits the input', () => {
      const { input } = renderTagInput({ maxTagLength: 5 });
      // Trigger an error
      fireEvent.change(input(), { target: { value: 'toolongtag' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(screen.getByTestId('tag-input-error')).toBeInTheDocument();
      // Edit the input — error should disappear
      fireEvent.change(input(), { target: { value: 'ok' } });
      expect(screen.queryByTestId('tag-input-error')).not.toBeInTheDocument();
    });
  });

  describe('controllable binding', () => {
    it('renders the supplied tags as chips', () => {
      renderTagInput({ value: ['alpha', 'beta'] });
      expect(screen.getByTestId('chip-alpha')).toBeInTheDocument();
      expect(screen.getByTestId('chip-beta')).toBeInTheDocument();
    });

    it('reflects a value update from the parent', () => {
      const onChange = vi.fn();
      const { rerender } = render(
        <TagInput value={['alpha']} onChange={onChange} />,
      );
      expect(screen.getByTestId('chip-alpha')).toBeInTheDocument();
      expect(screen.queryByTestId('chip-beta')).not.toBeInTheDocument();

      rerender(<TagInput value={['alpha', 'beta']} onChange={onChange} />);
      expect(screen.getByTestId('chip-beta')).toBeInTheDocument();
    });

    it('passes the data-testid attribute to the root element', () => {
      renderTagInput({ 'data-testid': 'my-tag-input' });
      expect(screen.getByTestId('my-tag-input')).toBeInTheDocument();
    });
  });

  describe('disabled state', () => {
    it('disables the underlying input', () => {
      const { input } = renderTagInput({ isDisabled: true });
      expect(input()).toBeDisabled();
    });
  });

  describe('screen-reader announcements', () => {
    it('announces when a tag is added', () => {
      const { input } = renderTagInput();
      fireEvent.change(input(), { target: { value: 'react' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(screen.getByTestId('tag-input-live')).toHaveTextContent(
        'Tag react added',
      );
    });

    it('announces when a tag is removed', () => {
      const Wrapper = () => {
        const [tags, setTags] = useState(['alpha']);
        return <TagInput value={tags} onChange={setTags} />;
      };
      render(<Wrapper />);
      fireEvent.click(screen.getByTestId('tag-input-remove-0'));
      expect(screen.getByTestId('tag-input-live')).toHaveTextContent(
        'Tag alpha removed',
      );
    });

    it('re-announces an identical validation error on a repeated attempt', () => {
      const { input } = renderTagInput({ value: ['react'] });
      fireEvent.change(input(), { target: { value: 'react' } });
      fireEvent.keyDown(input(), { key: 'Enter' });
      const live = screen.getByTestId('tag-input-live');
      const first = live.textContent;
      fireEvent.keyDown(input(), { key: 'Enter' });
      // The toggled zero-width prefix guarantees the text node changes so an
      // identical message is still re-read by assistive technology.
      expect(live.textContent).not.toBe(first);
      expect(live).toHaveTextContent('"react" is already added.');
    });
  });
});
