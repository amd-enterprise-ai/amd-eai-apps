// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, renderHook } from '@testing-library/react';

import { useOverlayState } from '@amdenterpriseai/hooks';

describe('useOverlayState', () => {
  it('starts closed by default', () => {
    const { result } = renderHook(() => useOverlayState());
    expect(result.current.isOpen).toBe(false);
  });

  it('opens via onOpen', () => {
    const { result } = renderHook(() => useOverlayState());
    act(() => {
      result.current.onOpen();
    });
    expect(result.current.isOpen).toBe(true);
  });

  it('closes via onClose', () => {
    const { result } = renderHook(() => useOverlayState());
    act(() => {
      result.current.onOpen();
    });
    act(() => {
      result.current.onClose();
    });
    expect(result.current.isOpen).toBe(false);
  });

  it('toggles via onOpenChange', () => {
    const { result } = renderHook(() => useOverlayState());
    act(() => {
      result.current.onOpenChange();
    });
    expect(result.current.isOpen).toBe(true);
    act(() => {
      result.current.onOpenChange();
    });
    expect(result.current.isOpen).toBe(false);
  });

  it('toggles via onOpenChange when invoked with a non-boolean (e.g. PressEvent)', () => {
    const { result } = renderHook(() => useOverlayState());
    act(() => {
      // HeroUI v3 Button passes a PressEvent to onPress handlers wired to onOpenChange.
      result.current.onOpenChange({ type: 'press' } as unknown as boolean);
    });
    expect(result.current.isOpen).toBe(true);
    expect(typeof result.current.isOpen).toBe('boolean');
  });

  it('sets open state when onOpenChange receives a boolean', () => {
    const { result } = renderHook(() => useOverlayState());
    act(() => {
      result.current.onOpenChange(true);
    });
    expect(result.current.isOpen).toBe(true);
    act(() => {
      result.current.onOpenChange(false);
    });
    expect(result.current.isOpen).toBe(false);
  });
});
