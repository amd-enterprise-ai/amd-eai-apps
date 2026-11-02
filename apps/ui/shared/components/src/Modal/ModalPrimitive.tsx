// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Modal as HeroUIModal } from '@heroui/react';
import React from 'react';

type ModalSize = 'xs' | 'sm' | 'md' | 'lg' | 'full' | 'cover';

interface ModalPrimitiveProps {
  children: React.ReactNode;
  isOpen?: boolean;
  onOpenChange?: (isOpen: boolean) => void;
  onClose?: () => void;
  isDismissable?: boolean;
  size?: ModalSize;
  backdrop?: 'opaque' | 'blur' | 'transparent';
  [key: `data-${string}`]: unknown;
}

export const ModalPrimitive: React.FC<ModalPrimitiveProps> = ({
  children,
  isOpen,
  onOpenChange,
  onClose,
  isDismissable = true,
  size,
  backdrop = 'blur',
  ...rest
}) => {
  const handleOpenChange = (open: boolean) => {
    onOpenChange?.(open);
    if (!open) {
      onClose?.();
    }
  };

  return (
    <HeroUIModal isOpen={isOpen} onOpenChange={handleOpenChange}>
      <HeroUIModal.Backdrop isDismissable={isDismissable} variant={backdrop}>
        <HeroUIModal.Container size={size} {...rest}>
          {children}
        </HeroUIModal.Container>
      </HeroUIModal.Backdrop>
    </HeroUIModal>
  );
};

interface SlotProps {
  children: React.ReactNode;
}

interface ModalPrimitiveContentProps extends SlotProps {
  hideCloseButton?: boolean;
}

export const ModalPrimitiveContent: React.FC<ModalPrimitiveContentProps> = ({
  children,
  hideCloseButton = false,
}) => (
  <HeroUIModal.Dialog>
    {!hideCloseButton ? <HeroUIModal.CloseTrigger /> : null}
    {children}
  </HeroUIModal.Dialog>
);

export const ModalPrimitiveHeader: React.FC<SlotProps> = ({ children }) => (
  <HeroUIModal.Header>
    <HeroUIModal.Heading>{children}</HeroUIModal.Heading>
  </HeroUIModal.Header>
);

export const ModalPrimitiveBody: React.FC<SlotProps> = ({ children }) => (
  <HeroUIModal.Body>{children}</HeroUIModal.Body>
);

export const ModalPrimitiveFooter: React.FC<SlotProps> = ({ children }) => (
  <HeroUIModal.Footer>{children}</HeroUIModal.Footer>
);

export const ModalPrimitiveObject = Object.assign(ModalPrimitive, {
  Body: ModalPrimitiveBody,
  Content: ModalPrimitiveContent,
  Footer: ModalPrimitiveFooter,
  Header: ModalPrimitiveHeader,
});
