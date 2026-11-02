// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Toast, toastQueue } from '@heroui/react';

export const SystemToastContainer = () => {
  return <Toast.Provider placement="top end" queue={toastQueue} width={460} />;
};

export default SystemToastContainer;
