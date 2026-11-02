// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconCheck, IconCopy } from '@tabler/icons-react';
import { ReactNode, useEffect, useRef, useState } from 'react';

import { useTranslation } from 'next-i18next';

interface ErrorToastProps {
  /** Rendered as the toast body. */
  content: ReactNode;
  /** Plain text written to the clipboard. The copy affordance is hidden when absent. */
  copyText?: string;
}

export const ErrorToast = ({ content, copyText }: ErrorToastProps) => {
  const { t } = useTranslation('sharedComponents');
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );

  useEffect(() => () => clearTimeout(resetTimer.current), []);

  const handleCopy = (event: React.MouseEvent) => {
    // The toast container closes on click; keep the toast open while copying.
    event.stopPropagation();

    if (!copyText || !navigator.clipboard?.writeText) return;

    navigator.clipboard.writeText(copyText).then(() => {
      setCopied(true);
      // Restart the window on every click so rapid copies don't let an earlier
      // timer clear the feedback prematurely.
      clearTimeout(resetTimer.current);
      resetTimer.current = setTimeout(() => setCopied(false), 2000);
    });
  };

  const label = copied ? t('actions.copy.copied') : t('actions.copy.title');

  return (
    <div className="flex items-start gap-2">
      <div className="flex-1">{content}</div>
      {copyText && (
        <button
          type="button"
          onClick={handleCopy}
          aria-label={label}
          title={label}
          className="mt-0.5 shrink-0 hover:opacity-70"
        >
          {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
        </button>
      )}
    </div>
  );
};

ErrorToast.displayName = 'ErrorToast';

export default ErrorToast;
