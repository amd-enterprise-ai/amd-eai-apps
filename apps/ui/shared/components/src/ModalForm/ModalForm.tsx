// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ModalPrimitive,
  ModalPrimitiveBody,
  ModalPrimitiveContent,
  ModalPrimitiveFooter,
  ModalPrimitiveHeader,
} from '../Modal/ModalPrimitive';
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

  title: string;
  confirmText: string;
  cancelText: string;

  children?: React.ReactNode;
  onOpenChange?: () => void;
  onCancel?: () => void;
  onFormSuccess?: (data: T) => void;
  onFormFailure?: (errors: FieldErrors<T>, data: T) => void;
  renderFields: (form: UseFormReturn<T>) => React.ReactNode;
  defaultValues?: DefaultValues<T>;
  validationSchema: ZodType<T, ZodTypeDef, unknown>;
  resolver?: (schema: ZodType<T, ZodTypeDef, unknown>) => Resolver<T>;
}

export const ModalForm = <T extends FieldValues>({
  isOpen,
  isActioning,
  onOpenChange,
  cancelText,
  confirmText,
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

  const handleFormSubmit = useCallback(() => {
    formRef?.current?.requestSubmit();
  }, [formRef]);

  const handleCancel = useCallback(() => {
    if (onCancel) {
      onCancel();
    } else {
      onOpenChange?.();
    }
  }, [onCancel, onOpenChange]);

  const handleFormSuccess = useCallback(
    (data: T) => {
      if (onFormSuccess) {
        onFormSuccess(data as T);
      }
    },
    [onFormSuccess],
  );

  const handleFormFailure = useCallback(
    (errors: FieldErrors<T>, data: T) => {
      if (onFormFailure) {
        onFormFailure(errors, data);
      }
    },
    [onFormFailure],
  );

  return (
    <ModalPrimitive
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      onClose={() => {
        if (onCancel) {
          onCancel();
        }
      }}
      isDismissable={!isActioning}
    >
      <ModalPrimitiveContent hideCloseButton={isActioning}>
        <ModalPrimitiveHeader>{title}</ModalPrimitiveHeader>
        <ModalPrimitiveBody>
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
        </ModalPrimitiveBody>
        <ModalPrimitiveFooter>
          <ActionButton
            secondary
            data-testid="modal-cancel"
            aria-label={cancelText}
            type="reset"
            onPress={handleCancel}
          >
            {cancelText}
          </ActionButton>
          <ActionButton
            primary
            data-testid="modal-confirm"
            aria-label={confirmText}
            isLoading={isActioning}
            type="submit"
            onPress={handleFormSubmit}
          >
            {confirmText}
          </ActionButton>
        </ModalPrimitiveFooter>
      </ModalPrimitiveContent>
    </ModalPrimitive>
  );
};

export default ModalForm;
