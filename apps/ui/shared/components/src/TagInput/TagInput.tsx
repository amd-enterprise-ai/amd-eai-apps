// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'next-i18next';
import { IconX } from '@tabler/icons-react';

import { Chip } from '../Chip';
import { Input } from '../Input/InputPrimitive';

export interface TagInputProps {
  /** Controlled list of current tags. */
  value: string[];
  /** Fired whenever the tag list changes. */
  onChange: (tags: string[]) => void;
  /** Minimum length of a single tag. Defaults to 1. */
  minTagLength?: number;
  /** Maximum length of a single tag. Defaults to 50. */
  maxTagLength?: number;
  /**
   * Regex that every tag must fully match.
   * Defaults to alphanumerics, hyphens, underscores and dots.
   */
  allowedPattern?: RegExp;
  label?: string;
  placeholder?: string;
  /** Helper text rendered below the field. */
  description?: string;
  isDisabled?: boolean;
  isRequired?: boolean;
  /**
   * Marks the field invalid and shows `errorMessage`, taking precedence over
   * the component's own tag-level validation. Lets a form layer (e.g. RHF+Zod)
   * surface schema-level rules the component cannot know about.
   */
  isInvalid?: boolean;
  errorMessage?: string;
  /**
   * Called when the text field loses focus, after any pending tag has been
   * committed. Lets a form layer mark the field touched / trigger validation.
   */
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void;
  className?: string;
  /** Test handle for the root element. */
  'data-testid'?: string;
}

const DEFAULT_MIN = 1;
const DEFAULT_MAX = 50;
const DEFAULT_PATTERN = /^[\w.-]+$/;
// Characters that separate tags in batch (typed-comma / pasted) input. Includes
// tab and CR so spreadsheet cells and Windows-clipboard pastes tokenize too.
const DELIMITER_PATTERN = /[,\t\r\n]/;

/**
 * Tests a tag against a pattern requiring a full-string match. Rebuilds the
 * regex anchored and without `g`/`y`/`m` flags so callers can pass un-anchored,
 * stateful or multiline patterns without partial matches, `lastIndex`-driven
 * flakiness, or `^`/`$` matching interior line boundaries.
 */
const matchesFully = (pattern: RegExp, tag: string): boolean => {
  const flags = pattern.flags.replace(/[gym]/g, '');
  return new RegExp(`^(?:${pattern.source})$`, flags).test(tag);
};

/**
 * Validates a candidate tag and returns an error message, or null when valid.
 */
const validateTag = (
  tag: string,
  existing: string[],
  min: number,
  max: number,
  pattern: RegExp,
  t: (key: string, options?: Record<string, unknown>) => string,
): string | null => {
  if (tag.length < min) return t('errorMinLength', { min, tag });
  if (tag.length > max) return t('errorMaxLength', { max, tag });
  if (!matchesFully(pattern, tag)) return t('errorDisallowedChars', { tag });
  if (existing.includes(tag)) return t('errorDuplicate', { tag });
  return null;
};

export const TagInput = forwardRef<HTMLInputElement, TagInputProps>(
  (
    {
      value,
      onChange,
      minTagLength = DEFAULT_MIN,
      maxTagLength = DEFAULT_MAX,
      allowedPattern = DEFAULT_PATTERN,
      label,
      placeholder,
      description,
      isDisabled = false,
      isRequired = false,
      isInvalid,
      errorMessage,
      onBlur,
      className,
      'data-testid': dataTestId,
    },
    ref,
  ) => {
    const { t } = useTranslation('sharedComponents', {
      keyPrefix: 'TagInput',
    });
    const [inputValue, setInputValue] = useState('');
    const [validationError, setValidationError] = useState<string | null>(null);
    const [liveMessage, setLiveMessage] = useState('');

    const containerRef = useRef<HTMLDivElement>(null);
    // Index of the remove button to focus after the next chip removal; consumed
    // by the effect below once the parent re-renders with the shortened list.
    const pendingFocusRef = useRef<number | null>(null);
    // Previous tag count, so the focus effect fires only on an actual removal and
    // not on any `value` change. Guards against a stale focus request stealing
    // focus later if a parent ignores or debounces the removal `onChange`.
    const prevLengthRef = useRef(value.length);
    // Flips each announcement so an identical repeated message (e.g. the same
    // validation error twice) still changes the live region's text node and is
    // therefore re-read by screen readers.
    const announceToggle = useRef(false);

    const announce = useCallback((message: string) => {
      announceToggle.current = !announceToggle.current;
      setLiveMessage(announceToggle.current ? `\u200b${message}` : message);
    }, []);

    useEffect(() => {
      const index = pendingFocusRef.current;
      const decreased = value.length < prevLengthRef.current;
      prevLengthRef.current = value.length;
      if (index === null) return;
      if (!decreased) {
        // The expected removal didn't materialize (parent ignored/debounced the
        // onChange); drop the stale request instead of stealing focus later.
        pendingFocusRef.current = null;
        return;
      }
      pendingFocusRef.current = null;
      const buttons =
        containerRef.current?.querySelectorAll<HTMLButtonElement>(
          '[data-tag-remove]',
        );
      // Prefer the button that shifted into the removed chip's slot; fall back to
      // the last remaining button, then to the text input, so focus never lands
      // on <body>.
      const nextButton = buttons?.[index] ?? buttons?.[buttons.length - 1];
      if (nextButton) {
        nextButton.focus();
      } else {
        containerRef.current?.querySelector('input')?.focus();
      }
    }, [value]);

    const tryAddTag = useCallback(
      (raw: string) => {
        const tag = raw.trim();
        if (!tag) {
          // Nothing to commit — reset any error and drop stray whitespace so the
          // field state matches the "no tag added" outcome.
          setValidationError(null);
          setInputValue('');
          return;
        }
        const error = validateTag(
          tag,
          value,
          minTagLength,
          maxTagLength,
          allowedPattern,
          t,
        );
        if (error) {
          setValidationError(error);
          announce(error);
          return;
        }
        setValidationError(null);
        onChange([...value, tag]);
        setInputValue('');
        announce(t('tagAdded', { tag }));
      },
      [
        value,
        onChange,
        minTagLength,
        maxTagLength,
        allowedPattern,
        t,
        announce,
      ],
    );

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
          // Prevent Enter from submitting a surrounding form whenever the field
          // holds any pending input (including whitespace-only).
          if (inputValue) e.preventDefault();
          tryAddTag(inputValue);
        } else if (e.key === 'Backspace' && !inputValue && value.length > 0) {
          const removed = value[value.length - 1];
          onChange(value.slice(0, -1));
          // A removal invalidates any pending error computed against the old
          // list (see removeTag); clear it so the UI matches the new list.
          setValidationError(null);
          announce(t('tagRemoved', { tag: removed }));
        }
        // Tab intentionally has no branch: focus-loss commit is handled once in
        // handleBlur, which fires on Tab, click-away and programmatic blur alike.
      },
      [inputValue, tryAddTag, value, onChange, t, announce],
    );

    const handleBlur = useCallback(
      (e: React.FocusEvent<HTMLInputElement>) => {
        // Single commit-on-focus-loss path: covers Tab and click-away alike, so
        // pending text is never silently dropped. Committing only here (not also
        // on Tab keydown) avoids announcing a rejection twice per keypress.
        if (inputValue.trim()) tryAddTag(inputValue);
        onBlur?.(e);
      },
      [inputValue, tryAddTag, onBlur],
    );

    // Validate and add a batch of candidate tokens in a single pass, announcing
    // the combined result. Building the next array locally (instead of calling
    // tryAddTag per token) avoids stale-closure batching, where each add would
    // otherwise overwrite the previous one. Returns the accepted and rejected
    // tokens so callers can keep rejected text in the field for editing.
    const commitTokens = useCallback(
      (tokens: string[]): { added: string[]; rejected: string[] } => {
        const next = [...value];
        let lastError: string | null = null;
        const added: string[] = [];
        const rejected: string[] = [];
        for (const token of tokens) {
          const candidate = token.trim();
          if (!candidate) continue;
          const err = validateTag(
            candidate,
            next,
            minTagLength,
            maxTagLength,
            allowedPattern,
            t,
          );
          if (err) {
            lastError = err;
            rejected.push(candidate);
          } else {
            next.push(candidate);
            added.push(candidate);
          }
        }
        if (added.length > 0) {
          onChange(next);
          const addedMessage =
            added.length === 1
              ? t('tagAdded', { tag: added[0] })
              : t('tagsAdded', { count: added.length });
          // Append the error so screen-reader users learn that some tokens were
          // rejected even when others were accepted (the shared Input wrapper does
          // not announce the visible error set below).
          announce(lastError ? `${addedMessage} ${lastError}` : addedMessage);
        } else if (lastError) {
          announce(lastError);
        }
        setValidationError(lastError);
        return { added, rejected };
      },
      [
        value,
        onChange,
        minTagLength,
        maxTagLength,
        allowedPattern,
        t,
        announce,
      ],
    );

    const handleChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        const raw = e.target.value;
        // Commit every complete comma-delimited token and keep any trailing
        // partial in the field. Handles interior commas (autofill, IME,
        // programmatic set), not just a single trailing comma.
        if (raw.includes(',')) {
          const parts = raw.split(',');
          // trimStart the trailing partial so the write-back stays idempotent — a
          // user typing a space after a comma must not accumulate leading spaces.
          const remainder = parts.pop()?.trimStart() ?? '';
          // Join rejected tokens and the remainder with spaces, NOT commas:
          // writing a comma back into the field is indistinguishable from one the
          // user typed and would be re-parsed (and re-announced) every keystroke.
          const { rejected } = commitTokens(parts);
          setInputValue([...rejected, remainder].filter(Boolean).join(' '));
        } else {
          setInputValue(raw);
          // Clear the error as soon as the user edits the input
          if (validationError) setValidationError(null);
        }
      },
      [commitTokens, validationError],
    );

    const handlePaste = useCallback(
      (e: React.ClipboardEvent<HTMLInputElement>) => {
        const text = e.clipboardData.getData('text');
        if (!DELIMITER_PATTERN.test(text)) return;
        e.preventDefault();

        // Splice the clipboard text into the current input at the caret so any
        // already-typed, uncommitted text is committed as part of a token rather
        // than silently discarded.
        const el = e.currentTarget;
        const start = el.selectionStart ?? inputValue.length;
        const end = el.selectionEnd ?? inputValue.length;
        const merged =
          inputValue.slice(0, start) + text + inputValue.slice(end);

        // Keep rejected tokens in the field so the user can see and fix them
        // instead of losing the pasted text; accepted tokens become chips and
        // drop out of the field. Space-join (not comma-join) so the write-back is
        // not re-parsed as fresh delimited input on the next keystroke.
        const { rejected } = commitTokens(merged.split(DELIMITER_PATTERN));
        setInputValue(rejected.join(' '));
      },
      [inputValue, commitTokens],
    );

    const removeTag = useCallback(
      (index: number) => {
        // Remove by position, not value equality: a parent-controlled `value` can
        // contain duplicates, and filtering by value would delete every copy.
        const tag = value[index];
        pendingFocusRef.current = index;
        onChange(value.filter((_, i) => i !== index));
        // A removal changes the list any pending rejection was validated against:
        // the error may name the tag just removed, and re-committing the pending
        // text on the next blur would silently re-add a tag the user deleted.
        // Reset both so the screen, the announced state and `value` agree.
        setValidationError(null);
        setInputValue('');
        announce(t('tagRemoved', { tag }));
      },
      [value, onChange, t, announce],
    );

    return (
      <div ref={containerRef} className={className} data-testid={dataTestId}>
        {/* Chip list */}
        {value.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {value.map((tag, index) => (
              <Chip
                key={`${tag}-${index}`}
                variant="flat"
                size="sm"
                className={isDisabled ? 'opacity-50' : undefined}
                aria-disabled={isDisabled || undefined}
                endContent={
                  isDisabled ? undefined : (
                    <button
                      type="button"
                      data-tag-remove
                      // Position-based, not value-based: `value` may contain
                      // duplicates, and a custom `allowedPattern` can permit tags
                      // with spaces/quotes that make value-derived ids collide or
                      // produce brittle selectors. The accessible name below stays
                      // tag-descriptive for screen readers.
                      data-testid={`tag-input-remove-${index}`}
                      aria-label={t('removeTag', { tag })}
                      onClick={() => removeTag(index)}
                      className="flex size-6 items-center justify-center rounded-full p-1 outline-none focus-visible:ring-2 focus-visible:ring-accent ring-offset-2 ring-offset-background"
                    >
                      <IconX size={14} aria-hidden />
                    </button>
                  )
                }
              >
                {tag}
              </Chip>
            ))}
          </div>
        )}

        {/* Text input */}
        <Input
          ref={ref}
          label={label}
          description={description}
          placeholder={placeholder ?? t('placeholder')}
          value={inputValue}
          isDisabled={isDisabled}
          isRequired={isRequired}
          // A parent-supplied invalid state only ever *adds* to the component's
          // own tag-level validation — it can force the error UI on, but passing
          // isInvalid={false} (common when binding to form state) must not
          // suppress an internal validationError.
          isInvalid={isInvalid || !!validationError}
          errorMessage={errorMessage ?? validationError ?? undefined}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onBlur={handleBlur}
          // Only supply an aria-label when there is no visible label, so the
          // accessible name is not duplicated (and cannot silently diverge).
          aria-label={label ? undefined : t('ariaLabel')}
        />

        {/* Screen-reader status region: announces adds, removals and errors. */}
        <output
          aria-live="polite"
          data-testid="tag-input-live"
          className="sr-only"
        >
          {liveMessage}
        </output>
      </div>
    );
  },
);

TagInput.displayName = 'TagInput';
