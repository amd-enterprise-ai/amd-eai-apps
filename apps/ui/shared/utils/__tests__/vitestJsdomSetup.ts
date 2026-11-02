// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { vi } from 'vitest';

import { installElementScrollToPolyfill } from './installElementScrollToPolyfill';

const unsupportedCssShimMarker = Symbol.for(
  'amdenterpriseai.test.unsupportedCssShimInstalled',
);

function unwrapUnsupportedLayerCss(cssText: string): string {
  const trimmedCssText = cssText.trim();
  const layerPrefix = '@layer {';

  if (
    !trimmedCssText.startsWith(layerPrefix) ||
    !trimmedCssText.endsWith('}')
  ) {
    return cssText;
  }

  return trimmedCssText.slice(layerPrefix.length, -1).trim();
}

function sanitizeStyleNodeForJsdom(node: unknown): void {
  if (
    !node ||
    typeof node !== 'object' ||
    !('nodeType' in node) ||
    !('nodeName' in node)
  ) {
    return;
  }

  const possibleStyleNode = node as {
    nodeType: number;
    nodeName: string;
    textContent: string | null;
  };

  if (
    possibleStyleNode.nodeType !== 1 ||
    possibleStyleNode.nodeName !== 'STYLE'
  ) {
    return;
  }

  if (!possibleStyleNode.textContent?.includes('@layer')) {
    return;
  }

  possibleStyleNode.textContent = unwrapUnsupportedLayerCss(
    possibleStyleNode.textContent,
  );
}

// HeroUI emits @layer rules that jsdom rejects with a CSSStyleSheet parse error.
// This shim intercepts STYLE nodes being prepended to <head> and unwraps any
// anonymous `@layer { ... }` wrapper (i.e. the literal prefix "@layer {") so
// jsdom can parse the inner rules safely. Named layers like `@layer base { ... }`
// are not handled here and pass through unchanged.
export function installUnsupportedCssRuleShim(): void {
  const headPrototype = HTMLHeadElement.prototype as HTMLHeadElement & {
    [unsupportedCssShimMarker]?: boolean;
  };

  if (headPrototype[unsupportedCssShimMarker]) {
    return;
  }

  const originalPrepend = HTMLHeadElement.prototype.prepend;

  HTMLHeadElement.prototype.prepend = function (
    ...nodes: Array<Node | string>
  ) {
    for (const node of nodes) {
      sanitizeStyleNodeForJsdom(node);
    }

    return originalPrepend.apply(this, nodes);
  };

  headPrototype[unsupportedCssShimMarker] = true;
}

export const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
  length: 0,
  key: vi.fn(),
};

export function stubAuthEnv(): void {
  vi.stubEnv('NEXTAUTH_SECRET', 'secret');
  vi.stubEnv('OIDC_CLIENT_ID', 'oidc_client_id');
  vi.stubEnv('OIDC_CLIENT_SECRET', 'oidc_client_secret');
  vi.stubEnv('OIDC_ISSUER', 'https://auth.example.com/');
  vi.stubEnv('OIDC_ISSUER_INTERNAL_URL', 'http://dex.dex.svc:5556');
  vi.stubEnv('DEBUG_PRINT_LIMIT', '10');
}

export function shimNodeGlobalAsWindow(): void {
  if (typeof global === 'undefined') {
    window.global = window;
  }
}

export function installResizeObserverMock(): void {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// react-aria-components' SharedElementTransition (used by Tabs, Select, Modal,
// Drawer, Popover, …) calls `element.getAnimations()`, which jsdom does not
// implement. Without this, overlay/transition tests throw an uncaught
// "element.getAnimations is not a function" and fail the whole file.
export function installWebAnimationsMock(): void {
  if (typeof Element === 'undefined') {
    return;
  }
  if (typeof Element.prototype.getAnimations !== 'function') {
    Element.prototype.getAnimations = function getAnimations() {
      return [];
    };
  }
  if (typeof Element.prototype.animate !== 'function') {
    Element.prototype.animate = function animate() {
      return {
        cancel() {},
        finish() {},
        play() {},
        pause() {},
        finished: Promise.resolve(),
        addEventListener() {},
        removeEventListener() {},
      } as unknown as Animation;
    };
  }
  if (
    typeof document !== 'undefined' &&
    typeof (document as Document & { getAnimations?: unknown })
      .getAnimations !== 'function'
  ) {
    (
      document as Document & { getAnimations: () => Animation[] }
    ).getAnimations = () => [];
  }
}

// react-aria's press/overlay interactions (used by Select, Dropdown, Modal, …)
// rely on Pointer Events and the pointer-capture DOM methods, none of which
// jsdom implements. Without them `userEvent`/react-aria can't drive a trigger
// to open its overlay, so option lists never mount in tests. Provide a minimal
// PointerEvent (extending MouseEvent) plus no-op capture methods.
export function installPointerEventMock(): void {
  if (typeof window === 'undefined') {
    return;
  }
  if (typeof window.PointerEvent === 'undefined') {
    class PointerEventMock extends MouseEvent {
      pointerId: number;
      pointerType: string;
      width: number;
      height: number;
      isPrimary: boolean;

      constructor(type: string, params: PointerEventInit = {}) {
        super(type, params);
        this.pointerId = params.pointerId ?? 1;
        this.pointerType = params.pointerType ?? 'mouse';
        this.width = params.width ?? 1;
        this.height = params.height ?? 1;
        this.isPrimary = params.isPrimary ?? true;
      }
    }
    window.PointerEvent = PointerEventMock as unknown as typeof PointerEvent;
    (global as { PointerEvent?: typeof PointerEvent }).PointerEvent =
      window.PointerEvent;
  }

  if (typeof Element !== 'undefined') {
    Element.prototype.hasPointerCapture ??= () => false;
    Element.prototype.setPointerCapture ??= () => {};
    Element.prototype.releasePointerCapture ??= () => {};
  }
}

/** DataTransfer, localStorage, location.reload, scrollIntoView, Element.scrollTo polyfill */
export function installHeavyJsdomMocks(): void {
  (global as any).DataTransfer = class MockDataTransfer {
    files: FileList;
    items: DataTransferItemList;
    types: string[];

    constructor() {
      this.files = [] as any;
      this.items = {
        length: 0,
        add: vi.fn(),
        remove: vi.fn(),
        clear: vi.fn(),
        [Symbol.iterator]: function* () {},
      } as any;
      this.types = [];
    }
  };

  Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
    writable: true,
  });

  Object.defineProperty(window, 'location', {
    value: {
      ...window.location,
      reload: vi.fn(),
    },
    writable: true,
  });

  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    value: vi.fn(),
    writable: true,
  });

  installElementScrollToPolyfill();
}

/** Use in app + shared component/utils setups that run React tree tests with forms, overlays, and tables. */
export function installPackageTestJsdom(): void {
  stubAuthEnv();
  shimNodeGlobalAsWindow();
  installResizeObserverMock();
  installWebAnimationsMock();
  installPointerEventMock();
  installUnsupportedCssRuleShim();
  installHeavyJsdomMocks();
}

/** Hooks-only: env + globals + ResizeObserver (avoid overriding JSDOM localStorage). */
export function installHooksTestJsdom(): void {
  stubAuthEnv();
  shimNodeGlobalAsWindow();
  installResizeObserverMock();
}

export function resetActiveProjectLocalStorage(): void {
  localStorageMock.getItem.mockImplementation((key: string) => {
    if (key === 'activeProject') {
      return JSON.stringify('project1');
    }
    return null;
  });
}
