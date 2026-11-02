// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  DrawerPrimitive as Drawer,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
} from './DrawerPrimitive';

import { useCallback, useRef } from 'react';
import {
  DefaultValues,
  FieldErrors,
  FieldValues,
  Resolver,
  UseFormReturn,
} from 'react-hook-form';
import { ActionButton } from '../Buttons';
import ManagedForm from '../ManagedForm/ManagedForm';

import { type ZodType, type ZodTypeDef } from 'zod';

interface Props<T extends FieldValues> {
  isOpen?: boolean;
  isActioning?: boolean;
  isDisabled?: boolean;
  hideCloseButton?: boolean;

  title: string;
  confirmText: string;
  cancelText: string;
  /**
   * Optional second submit, rendered before the primary one. It submits the same
   * form; which button was used arrives with `onFormSuccess`, so the caller
   * decides what differs once the submission succeeds.
   */
  secondaryConfirm?: {
    label: string;
    icon?: React.ReactNode;
  };

  onOpenChange?: () => void;
  onCancel?: () => void;
  onFormSuccess?: (data: T, meta: { viaSecondaryConfirm: boolean }) => void;
  onFormFailure?: (errors: FieldErrors<T>, data: T) => void;
  renderFields: (form: UseFormReturn<T>) => React.ReactNode;
  defaultValues?: DefaultValues<T>;
  validationSchema: ZodType<T, ZodTypeDef, unknown>;
  resolver?: (schema: ZodType<T, ZodTypeDef, unknown>) => Resolver<T>;
}

export const DrawerForm = <T extends FieldValues>({
  isOpen,
  isActioning,
  isDisabled,
  hideCloseButton,
  onOpenChange,
  cancelText,
  confirmText,
  secondaryConfirm,
  title,
  onCancel,
  onFormSuccess,
  onFormFailure,
  defaultValues,
  validationSchema,
  resolver,
  renderFields,
}: Props<T>) => {
  const formRef = useRef<HTMLFormElement>(null);
  // Only the secondary button raises this, and the submit it belongs to takes it
  // back down, valid or not. The footer sits outside the form and submits it
  // programmatically, so a submit carries no submitter to read this from, and a
  // secondary submission that failed validation would otherwise still be flying
  // when the user presses Enter or the primary button next.
  const viaSecondaryConfirm = useRef(false);
  const takeViaSecondaryConfirm = useCallback(() => {
    const viaSecondary = viaSecondaryConfirm.current;
    viaSecondaryConfirm.current = false;
    return viaSecondary;
  }, []);

  const handleFormSubmit = useCallback(
    (viaSecondary = false) => {
      viaSecondaryConfirm.current = viaSecondary;
      formRef?.current?.requestSubmit();
    },
    [formRef],
  );

  const handleCancel = useCallback(() => {
    if (onCancel) {
      onCancel();
    } else {
      onOpenChange?.();
    }
  }, [onCancel, onOpenChange]);

  const handleFormSuccess = useCallback(
    (data: T) => {
      const viaSecondaryConfirm = takeViaSecondaryConfirm();
      if (onFormSuccess) {
        onFormSuccess(data as T, { viaSecondaryConfirm });
      }
    },
    [onFormSuccess, takeViaSecondaryConfirm],
  );

  const handleFormFailure = useCallback(
    (errors: FieldErrors<T>, data: T) => {
      takeViaSecondaryConfirm();
      if (onFormFailure) {
        onFormFailure(errors, data);
      }
    },
    [onFormFailure, takeViaSecondaryConfirm],
  );

  return (
    <Drawer
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      onClose={() => {
        if (onCancel) {
          onCancel();
        }
      }}
      isDismissable={
        hideCloseButton !== undefined ? !hideCloseButton : !isActioning
      }
    >
      <DrawerContent
        hideCloseButton={
          hideCloseButton !== undefined ? hideCloseButton : isActioning
        }
      >
        <DrawerHeader>{title}</DrawerHeader>
        <DrawerBody>
          <ManagedForm<T>
            isActioning={isActioning}
            onFormSuccess={handleFormSuccess}
            onFormFailure={handleFormFailure}
            validationSchema={validationSchema}
            resolver={resolver}
            renderFields={renderFields}
            defaultValues={defaultValues}
            formRef={formRef}
          />
        </DrawerBody>
        <DrawerFooter>
          <ActionButton
            tertiary
            aria-label={cancelText}
            type="reset"
            onPress={handleCancel}
          >
            {cancelText}
          </ActionButton>
          {secondaryConfirm && (
            <ActionButton
              secondary
              aria-label={secondaryConfirm.label}
              icon={secondaryConfirm.icon}
              isDisabled={isDisabled || isActioning}
              type="submit"
              onPress={() => handleFormSubmit(true)}
            >
              {secondaryConfirm.label}
            </ActionButton>
          )}
          <ActionButton
            primary
            aria-label={confirmText}
            isLoading={isActioning}
            isDisabled={isDisabled}
            type="submit"
            onPress={() => handleFormSubmit()}
          >
            {confirmText}
          </ActionButton>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
};

export default DrawerForm;
