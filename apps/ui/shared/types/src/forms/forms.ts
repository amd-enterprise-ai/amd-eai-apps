// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export type FormField<T> = {
  name: keyof T;
  label: string | null;
  placeholder?: string | null;
  description?: string | null;
  isRequired?: boolean;
  isInvalid?: boolean;
  isReadOnly?: boolean;
  secondaryAction?: {
    label: string;
    callback: () => void;
  };
  component?: React.ComponentType<any>;
  icon?: React.ComponentType<any>;
  props?: Record<string, any>;
};
