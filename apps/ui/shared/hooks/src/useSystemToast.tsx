// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { toast as heroToast } from '@heroui/react';
import { ReactNode } from 'react';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { ErrorToast } from './ErrorToast';

const TOAST_TIMEOUT_MS = 5000;

type SystemToastOptions = Parameters<typeof heroToast>[1];

export const useSystemToast = () => {
  const toast = (
    toastContent: ReactNode | string,
    toastOptions?: SystemToastOptions,
  ) => {
    return heroToast(toastContent, {
      timeout: TOAST_TIMEOUT_MS,
      ...toastOptions,
    });
  };

  toast.close = (key: string) => {
    heroToast.close(key);
  };

  toast.error = (
    toastContent: ReactNode | string,
    error?: APIRequestError | Error,
  ) => {
    const message =
      error instanceof APIRequestError ? error.message : toastContent;

    // Only a plain-text message can be placed on the clipboard; richer content
    // (e.g. a LinkToast) is shown without a copy affordance.
    const copyText = typeof message === 'string' ? message : undefined;

    heroToast.danger(<ErrorToast content={message} copyText={copyText} />, {
      timeout: TOAST_TIMEOUT_MS,
    });
  };

  toast.info = (toastContent: ReactNode | string) => {
    heroToast.info(toastContent, { timeout: TOAST_TIMEOUT_MS });
  };

  toast.warning = (toastContent: ReactNode | string) => {
    heroToast.warning(toastContent, { timeout: TOAST_TIMEOUT_MS });
  };

  toast.success = (
    toastContent: ReactNode | string,
    toastOptions?: Omit<SystemToastOptions, 'variant'>,
  ) => {
    heroToast.success(toastContent, {
      timeout: TOAST_TIMEOUT_MS,
      ...toastOptions,
    });
  };

  return {
    toast,
  };
};

export default useSystemToast;
