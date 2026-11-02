// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { isValidElement, type ReactNode } from 'react';

/**
 * HeroUI v3 trigger primitives (`Tooltip.Trigger`, `Dropdown.Trigger`, …) render
 * their own focusable element — a `<div role="button">` (Tooltip) or a `<Button>`
 * (Dropdown) — and place the consumer's content *inside* it. v2 call sites,
 * however, pass an already-interactive element (our `Button`/`ActionButton`, a
 * `Link`, or a raw `<button>`/`<a>`) as the trigger, which would nest two
 * focusable/button-role elements (duplicate `role="button"`, invalid a11y).
 *
 * The underlying react-aria `MenuTrigger`/`TooltipTrigger` attach their trigger
 * behaviour through context (`PressResponder`/`FocusableProvider`), so an
 * interactive child can be rendered *directly* as the trigger without the extra
 * wrapper. This predicate identifies such children so the adapters can skip the
 * wrapper for them and only wrap genuinely non-interactive content
 * (spans, icons, badges) in the v3 trigger primitive.
 */
export const isInteractiveTriggerChild = (node: ReactNode): boolean => {
  if (!isValidElement(node)) return false;
  const type = node.type;

  if (type === 'button' || type === 'a' || type === 'input') {
    return true;
  }
  if (typeof type === 'string') return false;

  const component = type as {
    displayName?: string;
    name?: string;
    render?: { displayName?: string; name?: string };
    type?: { displayName?: string; name?: string };
  };
  const name =
    component.displayName ??
    component.name ??
    component.render?.displayName ??
    component.render?.name ??
    component.type?.displayName ??
    component.type?.name ??
    '';
  return /button|link|input|select|dropdown/i.test(name);
};
