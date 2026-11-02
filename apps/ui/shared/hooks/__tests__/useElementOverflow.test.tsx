// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useElementOverflow } from '@amdenterpriseai/hooks';

const observe = vi.fn();
const disconnect = vi.fn();
const cancelAnimationFrame = vi.fn();
let animationFrameCallback: FrameRequestCallback;
let resizeCallback: ResizeObserverCallback;

const OverflowProbe = ({
  measureOverflow,
  probeKey = 'probe',
  isVisible = true,
}: {
  measureOverflow: (element: HTMLDivElement) => boolean;
  probeKey?: string;
  isVisible?: boolean;
}) => {
  const { elementRef, isOverflowing } =
    useElementOverflow<HTMLDivElement>(measureOverflow);

  return (
    <>
      <span data-testid="overflow-state">{String(isOverflowing)}</span>
      {isVisible ? (
        <div
          key={probeKey}
          ref={elementRef}
          data-testid="overflow-probe"
          data-overflowing={isOverflowing}
        />
      ) : null}
    </>
  );
};

describe('useElementOverflow', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'requestAnimationFrame',
      vi.fn((callback: FrameRequestCallback) => {
        animationFrameCallback = callback;
        return 1;
      }),
    );
    vi.stubGlobal('cancelAnimationFrame', cancelAnimationFrame);
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: ResizeObserverCallback) {
          resizeCallback = callback;
        }

        observe = observe;
        disconnect = disconnect;
      },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('measures after layout, remeasures on resize, and cleans up', () => {
    const measureOverflow = vi
      .fn()
      .mockReturnValueOnce(false)
      .mockReturnValue(true);
    const { unmount } = render(
      <OverflowProbe measureOverflow={measureOverflow} />,
    );
    const probe = screen.getByTestId('overflow-probe');

    expect(observe).toHaveBeenCalledWith(probe);
    act(() => animationFrameCallback(0));
    expect(probe).toHaveAttribute('data-overflowing', 'false');

    act(() => resizeCallback([], {} as ResizeObserver));
    expect(probe).toHaveAttribute('data-overflowing', 'true');

    unmount();
    expect(cancelAnimationFrame).toHaveBeenCalledWith(1);
    expect(disconnect).toHaveBeenCalledOnce();
  });

  it('observes replacement elements and resets after detachment', () => {
    const measureOverflow = vi
      .fn()
      .mockReturnValueOnce(true)
      .mockReturnValueOnce(false);
    const { rerender } = render(
      <OverflowProbe measureOverflow={measureOverflow} />,
    );
    const firstProbe = screen.getByTestId('overflow-probe');

    act(() => animationFrameCallback(0));
    expect(screen.getByTestId('overflow-state')).toHaveTextContent('true');

    rerender(
      <OverflowProbe
        measureOverflow={measureOverflow}
        probeKey="replacement"
      />,
    );
    const replacementProbe = screen.getByTestId('overflow-probe');

    expect(replacementProbe).not.toBe(firstProbe);
    expect(disconnect).toHaveBeenCalledOnce();
    expect(observe).toHaveBeenLastCalledWith(replacementProbe);

    act(() => animationFrameCallback(0));
    expect(screen.getByTestId('overflow-state')).toHaveTextContent('false');

    rerender(
      <OverflowProbe
        measureOverflow={measureOverflow}
        probeKey="replacement"
        isVisible={false}
      />,
    );

    expect(disconnect).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('overflow-state')).toHaveTextContent('false');
  });
});
