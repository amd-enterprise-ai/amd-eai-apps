// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconCheck, IconCopy } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import React, { useCallback, useEffect, useRef, useState } from 'react';

import { ActionButton } from '../Buttons/ActionButton';
import { Input, type InputProps } from '../Input/InputPrimitive';
import type { FormFieldVariant } from '../internal/formFieldVariant';
import { Textarea } from '../Textarea/Textarea';

export interface CopySnippetProps {
  children?: React.ReactNode;
  value?: string;
  label?: React.ReactNode;
  description?: React.ReactNode;
  hideCopyButton?: boolean;
  buttonOnly?: boolean;
  /** Accessible label for the copy button. */
  copyButtonAriaLabel?: string;
  /** Called after a successful clipboard write. */
  onCopySuccess?: () => void;
  /** Called when clipboard write fails. */
  onCopyError?: () => void;
  variant?: FormFieldVariant;
  className?: string;
  'aria-label'?: string;
}

const COPIED_RESET_MS = 2000;
const MIN_TEXTAREA_ROWS = 3;
const MAX_TEXTAREA_ROWS = 12;
const MONO_INPUT_CLASS = 'font-mono text-sm';

const extractText = (children: React.ReactNode, value?: string): string => {
  if (value !== undefined) {
    return value;
  }
  if (typeof children === 'string' || typeof children === 'number') {
    return String(children);
  }
  if (Array.isArray(children)) {
    return children.map((child) => extractText(child)).join('');
  }
  if (React.isValidElement(children)) {
    return extractText(
      (children.props as { children?: React.ReactNode }).children,
    );
  }
  return '';
};

const computeMinRows = (text: string): number =>
  Math.min(
    Math.max(text.split('\n').length, MIN_TEXTAREA_ROWS),
    MAX_TEXTAREA_ROWS,
  );

// HeroUI v3 removes both `Snippet` and the `useClipboard` hook, so this
// reimplements the copy-to-clipboard affordance with read-only Input/Textarea
// shells.
export const CopySnippet = ({
  children,
  value,
  label,
  description,
  hideCopyButton = false,
  buttonOnly = false,
  copyButtonAriaLabel,
  onCopySuccess,
  onCopyError,
  variant,
  className,
  'aria-label': ariaLabel,
}: CopySnippetProps): React.JSX.Element => {
  const { t } = useTranslation('sharedComponents');
  const [copied, setCopied] = useState(false);
  const copiedResetRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const text = extractText(children, value);
  const copyButtonLabel = copyButtonAriaLabel ?? t('actions.copy.title');
  const isMultiline = text.includes('\n');

  const clearCopiedReset = useCallback(() => {
    if (copiedResetRef.current !== null) {
      clearTimeout(copiedResetRef.current);
      copiedResetRef.current = null;
    }
  }, []);

  useEffect(() => clearCopiedReset, [clearCopiedReset]);

  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(text).then(
      () => {
        clearCopiedReset();
        setCopied(true);
        copiedResetRef.current = setTimeout(() => {
          setCopied(false);
          copiedResetRef.current = null;
        }, COPIED_RESET_MS);
        onCopySuccess?.();
      },
      () => {
        onCopyError?.();
      },
    );
  }, [text, onCopySuccess, onCopyError, clearCopiedReset]);

  const copyButtonIcon = copied ? (
    <IconCheck size={16} className="text-success" />
  ) : (
    <IconCopy size={16} />
  );

  const copyButton = hideCopyButton ? null : (
    <ActionButton
      tertiary
      size="sm"
      aria-label={copyButtonLabel}
      icon={
        <span className="transition-colors duration-200">{copyButtonIcon}</span>
      }
      onPress={handleCopy}
      className={buttonOnly ? className : undefined}
    />
  );

  if (buttonOnly) {
    return <>{copyButton}</>;
  }

  if (isMultiline) {
    return (
      <Textarea
        label={label}
        description={description}
        value={text}
        isReadOnly
        variant={variant}
        minRows={computeMinRows(text)}
        endContent={copyButton}
        className={className}
        classNames={{ input: MONO_INPUT_CLASS }}
        aria-label={ariaLabel}
      />
    );
  }

  return (
    <Input
      label={label}
      description={description}
      value={text}
      isReadOnly
      variant={variant}
      endContent={copyButton}
      className={className}
      classNames={{ input: MONO_INPUT_CLASS }}
      aria-label={ariaLabel}
    />
  );
};
