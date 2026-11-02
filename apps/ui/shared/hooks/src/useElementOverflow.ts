// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useCallback, useEffect, useState } from 'react';

/**
 * Tracks overflow when UI behavior depends on resize-sensitive truncation or clamping.
 */
export const useElementOverflow = <T extends HTMLElement>(
  measureOverflow: (element: T) => boolean,
) => {
  const [element, setElement] = useState<T | null>(null);
  const [isOverflowing, setIsOverflowing] = useState(false);
  const elementRef = useCallback((nextElement: T | null) => {
    setElement(nextElement);
    if (!nextElement) setIsOverflowing(false);
  }, []);

  useEffect(() => {
    if (!element) return;

    const measure = () => setIsOverflowing(measureOverflow(element));
    const frameId = requestAnimationFrame(measure);
    const resizeObserver = new ResizeObserver(measure);
    resizeObserver.observe(element);

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
    };
  }, [element, measureOverflow]);

  return { elementRef, isOverflowing };
};
