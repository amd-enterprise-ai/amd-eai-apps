// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { renderHook } from '@testing-library/react';
import { toast } from '@heroui/react';

import { useSystemToast } from '@amdenterpriseai/hooks';

import { APIRequestError } from '@amdenterpriseai/utils/app';

vi.mock('@heroui/react', () => {
  const _toast = vi.fn() as any;
  _toast.danger = vi.fn();
  _toast.info = vi.fn();
  _toast.warning = vi.fn();
  _toast.success = vi.fn();
  _toast.close = vi.fn();

  return {
    toast: _toast,
  };
});

describe('useSystemToast', () => {
  it('should call toast with correct content and options', () => {
    const { result } = renderHook(() => useSystemToast());
    const toastContent = 'Test Toast';
    const toastOptions = { description: 'Details' };

    result.current.toast(toastContent, toastOptions);

    expect(toast).toHaveBeenCalledWith(toastContent, {
      timeout: 5000,
      ...toastOptions,
    });
  });

  it('should call toast.danger with correct content', () => {
    const { result } = renderHook(() => useSystemToast());
    const toastContent = 'Error Toast';

    result.current.toast.error(toastContent);

    expect(toast.danger).toHaveBeenCalledWith(
      expect.objectContaining({
        props: expect.objectContaining({
          content: toastContent,
          copyText: toastContent,
        }),
      }),
      expect.objectContaining({ timeout: 5000 }),
    );
  });

  it('should make a string error message copyable', () => {
    const { result } = renderHook(() => useSystemToast());
    const toastContent = 'Error Toast';

    result.current.toast.error(toastContent);

    expect(toast.danger).toHaveBeenCalledWith(
      expect.objectContaining({
        props: expect.objectContaining({ copyText: toastContent }),
      }),
      expect.anything(),
    );
  });

  it('should not provide copy text for non-string content', () => {
    const { result } = renderHook(() => useSystemToast());

    result.current.toast.error(<span>Rich error</span>);

    expect(toast.danger).toHaveBeenCalledWith(
      expect.objectContaining({
        props: expect.objectContaining({ copyText: undefined }),
      }),
      expect.anything(),
    );
  });

  it('should call toast.danger with error message when APIRequestError is provided', () => {
    const { result } = renderHook(() => useSystemToast());
    const toastContent = 'Generic error Toast';

    const apiError = new APIRequestError(
      'Failed to get resource: Error message from API',
      400,
    );

    result.current.toast.error(toastContent, apiError);

    expect(toast.danger).toHaveBeenCalledWith(
      expect.objectContaining({
        props: expect.objectContaining({
          content: 'Failed to get resource: Error message from API',
          copyText: 'Failed to get resource: Error message from API',
        }),
      }),
      expect.anything(),
    );
  });

  it('should call toast.danger with error message for any status code', () => {
    const { result } = renderHook(() => useSystemToast());
    const apiError = new APIRequestError(
      'Failed to process request: Server error',
      500,
    );
    const toastContent = 'Generic error Toast';

    result.current.toast.error(toastContent, apiError);

    expect(toast.danger).toHaveBeenCalledWith(
      expect.objectContaining({
        props: expect.objectContaining({
          content: 'Failed to process request: Server error',
        }),
      }),
      expect.anything(),
    );
  });

  it('should call toast.info with correct content', () => {
    const { result } = renderHook(() => useSystemToast());
    const toastContent = 'Info Toast';

    result.current.toast.info(toastContent);

    expect(toast.info).toHaveBeenCalledWith(toastContent, {
      timeout: 5000,
    });
  });

  it('should call toast.warning with correct content', () => {
    const { result } = renderHook(() => useSystemToast());
    const toastContent = 'Warning Toast';

    result.current.toast.warning(toastContent);

    expect(toast.warning).toHaveBeenCalledWith(toastContent, {
      timeout: 5000,
    });
  });

  it('should call toast.success with correct content', () => {
    const { result } = renderHook(() => useSystemToast());
    const toastContent = 'Success Toast';

    result.current.toast.success(toastContent);

    expect(toast.success).toHaveBeenCalledWith(toastContent, {
      timeout: 5000,
    });
  });

  it('should call toast.close with the toast key', () => {
    const { result } = renderHook(() => useSystemToast());
    const toastKey = 'toast-key-1';

    result.current.toast.close(toastKey);

    expect(toast.close).toHaveBeenCalledWith(toastKey);
  });
});
