// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  useOverlayState as useOverlayStateBase,
  type UseOverlayStateProps,
} from '@heroui/react';
import { useMemo } from 'react';

/**
 * Manages open/close state for overlays (modals, drawers, popovers).
 *
 * HeroUI v3 replaced the v2 `useDisclosure` hook with `useOverlayState`, whose
 * surface (`open`/`close`/`toggle`/`setOpen`) differs from the v2 callbacks
 * (`onOpen`/`onClose`/`onOpenChange`) that the entire app still consumes. This
 * adapter wraps the v3 hook and re-exposes the v2-compatible callbacks so no
 * consumer has to change, while also forwarding the new v3 methods for future
 * use.
 */
export interface OverlayState {
  readonly isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  setOpen: (isOpen: boolean) => void;
  // v2-compatible aliases preserved for existing consumers.
  onOpen: () => void;
  onClose: () => void;
  // v2 typed this as a zero-arg toggle, which is what lets call sites hand it
  // directly to `onPress`/`onClick`. The runtime implementation still accepts
  // the optional next-open-state that HeroUI overlays pass.
  onOpenChange: () => void;
}

export const useOverlayState = (props?: UseOverlayStateProps): OverlayState => {
  const state = useOverlayStateBase(props);

  return useMemo<OverlayState>(
    () => ({
      isOpen: state.isOpen,
      open: state.open,
      close: state.close,
      toggle: state.toggle,
      setOpen: state.setOpen,
      onOpen: state.open,
      onClose: state.close,
      // v2 `onOpenChange` toggles when called without a boolean (e.g. wired to
      // `onPress`, which passes a PressEvent). HeroUI overlays invoke it with
      // the next open state as a boolean.
      onOpenChange: (isOpen?: boolean) =>
        typeof isOpen === 'boolean' ? state.setOpen(isOpen) : state.toggle(),
    }),
    [state],
  );
};
