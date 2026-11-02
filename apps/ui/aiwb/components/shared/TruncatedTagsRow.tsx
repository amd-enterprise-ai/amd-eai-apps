// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Chip, Tooltip } from '@amdenterpriseai/components';
import { useState, useRef, useEffect, useLayoutEffect, useMemo } from 'react';

const DEFAULT_MAX_VISIBLE = 3;

interface Props {
  tags: string[];
  /** e.g. (count) => t('card.tagsMoreCount', { count }) */
  formatMoreCount: (count: number) => string;
  maxVisible?: number;
  className?: string;
}

export const TruncatedTagsRow = ({
  tags,
  formatMoreCount,
  maxVisible = DEFAULT_MAX_VISIBLE,
  className = '',
}: Props) => {
  const [visibleTagCount, setVisibleTagCount] = useState(() =>
    Math.min(maxVisible, tags.length),
  );
  const [containerWidth, setContainerWidth] = useState(0);
  const tagsRowRef = useRef<HTMLDivElement>(null);

  const visibleTags = useMemo(
    () => tags.slice(0, visibleTagCount),
    [tags, visibleTagCount],
  );
  const remainingCount = tags.length - visibleTagCount;
  const remainingTags = useMemo(
    () => (remainingCount > 0 ? tags.slice(visibleTagCount) : []),
    [tags, visibleTagCount, remainingCount],
  );

  useEffect(() => {
    setVisibleTagCount(Math.min(maxVisible, tags.length));
  }, [tags.length, maxVisible]);

  useEffect(() => {
    const el = tagsRowRef.current?.parentElement;
    if (!el) return;
    let rafId: number | null = null;
    const ro = new ResizeObserver((entries) => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      const nextWidth = entries[0]?.contentRect.width ?? 0;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setContainerWidth((w) => (w === nextWidth ? w : nextWidth));
        setVisibleTagCount((c) => {
          const next = Math.min(maxVisible, tags.length);
          return next === c ? c : next;
        });
      });
    });
    ro.observe(el);
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      ro.disconnect();
    };
  }, [tags.length, maxVisible]);

  useLayoutEffect(() => {
    const row = tagsRowRef.current;
    if (!row || tags.length === 0) return;
    const overflow = row.scrollWidth > row.clientWidth;
    if (overflow && visibleTagCount > 0) {
      setVisibleTagCount((c) => c - 1);
    }
  }, [containerWidth, visibleTagCount, tags.length]);

  if (tags.length === 0) return null;

  return (
    <div
      ref={tagsRowRef}
      className={`flex flex-nowrap gap-1 overflow-hidden min-w-0 ${className}`.trim()}
    >
      {visibleTags.map((tag) => (
        <Chip key={tag} variant="flat" size="sm" className="flex-shrink-0">
          {tag}
        </Chip>
      ))}
      {remainingCount > 0 && (
        <Tooltip
          content={
            <div className="flex flex-wrap gap-1 py-1">
              {remainingTags.map((tag) => (
                <Chip key={tag} variant="flat" size="sm">
                  {tag}
                </Chip>
              ))}
            </div>
          }
        >
          <Chip variant="tertiary" size="sm" className="cursor-help shrink-0">
            {formatMoreCount(remainingCount)}
          </Chip>
        </Tooltip>
      )}
    </div>
  );
};

TruncatedTagsRow.displayName = 'TruncatedTagsRow';
