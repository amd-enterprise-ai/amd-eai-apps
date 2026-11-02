// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ModalPrimitive,
  ModalPrimitiveBody,
  ModalPrimitiveContent,
  ModalPrimitiveFooter,
  ModalPrimitiveHeader,
} from './ModalPrimitive';
import React from 'react';

interface ModalProps {
  children: React.ReactNode;
  onClose: () => void;
  footer?: React.ReactNode;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'full' | 'cover';
  title?: string;
  subTitle?: string;
  isDismissible?: boolean;
}

export const Modal: React.FC<ModalProps> = ({
  children,
  footer,
  onClose,
  size,
  title,
  subTitle,
  isDismissible,
}) => {
  return (
    <ModalPrimitive
      isOpen={true}
      onOpenChange={onClose}
      isDismissable={isDismissible}
      size={size || 'lg'}
    >
      <ModalPrimitiveContent>
        <ModalPrimitiveHeader>
          <div className="flex flex-col gap-1">
            <h2>{title || ''}</h2>
            {subTitle ? (
              <p className="dark:text-muted text-foreground font-medium">
                {subTitle}
              </p>
            ) : null}
          </div>
        </ModalPrimitiveHeader>
        <ModalPrimitiveBody>{children}</ModalPrimitiveBody>
        {footer ? <ModalPrimitiveFooter>{footer}</ModalPrimitiveFooter> : null}
      </ModalPrimitiveContent>
    </ModalPrimitive>
  );
};
