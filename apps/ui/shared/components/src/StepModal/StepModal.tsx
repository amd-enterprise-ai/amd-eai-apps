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
import { useCallback, useState } from 'react';
import { forwardRef, useImperativeHandle } from 'react';

import { useTranslation } from 'next-i18next';

import { StepModalHandle, StepModalStep } from '@amdenterpriseai/types';
import { ActionButton } from '../Buttons';
import Stepper from '../Stepper/Stepper';

interface Props {
  initialStep: number;
  steps: StepModalStep[];
  allowPrevious?: boolean;
  onOpenChange: (isOpen: boolean) => void;
  isOpen: boolean;
  onCancel?: () => void;
  isActioning?: boolean;
  resetOnClose?: boolean;
  title?: string;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'full' | 'cover';
}

export const StepModal = forwardRef<StepModalHandle, Props>(
  (
    {
      allowPrevious,
      initialStep = 0,
      steps,
      isOpen,
      onOpenChange,
      onCancel,
      size,
      isActioning,
      title,
      resetOnClose = true,
    },
    ref,
  ) => {
    const { t } = useTranslation('sharedComponents');
    const [currentStep, setCurrentStep] = useState<number>(initialStep || 0);

    useImperativeHandle(
      ref,
      () => ({
        incrementStep: () => {
          setCurrentStep((prev) =>
            prev + 1 > steps.length - 1 ? steps.length - 1 : prev + 1,
          );
        },
        setStep: (step: number) => {
          setCurrentStep(step);
        },
      }),
      [steps.length],
    );

    const handleNext = useCallback(() => {
      if (steps) {
        const step = steps[currentStep];
        if (step.onStepChange) {
          step.onStepChange(currentStep + 1);
          return;
        }
      }
      setCurrentStep((prev) => prev + 1);
    }, [currentStep, steps]);

    const handlePrev = useCallback(() => {
      if (steps) {
        const step = steps[currentStep];
        if (step.onStepChange) {
          step.onStepChange(currentStep - 1);
          return;
        }
      }
      setCurrentStep((prev) => prev - 1);
    }, [currentStep, steps]);

    const handleClose = useCallback(() => {
      if (resetOnClose) {
        setCurrentStep(0);
      }
      if (onCancel) {
        onCancel();
      }
    }, [resetOnClose, onCancel]);

    const step = steps[currentStep];
    const showPrev = currentStep > 0 && allowPrevious && !step?.hidePrev;
    const showNext = currentStep < steps.length - 1 && !step?.hideNext;

    const defaultFooterRowClass =
      showPrev && showNext
        ? 'flex w-full min-w-0 items-center justify-between gap-2'
        : 'flex w-full min-w-0 items-center justify-end gap-2';

    return (
      <ModalPrimitive
        isOpen={isOpen}
        size={size}
        onOpenChange={onOpenChange}
        onClose={handleClose}
        isDismissable={
          !isActioning &&
          (typeof step?.canCloseByOverlayPress === 'undefined' ||
            step?.canCloseByOverlayPress)
        }
      >
        <ModalPrimitiveContent hideCloseButton={isActioning}>
          <ModalPrimitiveHeader>
            {title ?? steps?.[currentStep].label}
          </ModalPrimitiveHeader>
          <ModalPrimitiveBody>
            <div className="mx-auto w-5/6">
              <Stepper
                step={currentStep}
                steps={steps.map((s) => ({ label: s.label }))}
              />
            </div>
            {steps?.[currentStep].content}
          </ModalPrimitiveBody>
          <ModalPrimitiveFooter>
            {step?.customActions ? (
              step.customActions
            ) : (
              <div className={defaultFooterRowClass}>
                {showPrev ? (
                  <ActionButton
                    secondary
                    aria-label={
                      step?.backActionLabel || t('actions.previous') || ''
                    }
                    onPress={handlePrev}
                  >
                    {step?.backActionLabel || t('actions.previous')}
                  </ActionButton>
                ) : null}
                {showNext ? (
                  <ActionButton
                    primary
                    isLoading={isActioning}
                    aria-label={step.nextActionLabel || t('actions.next') || ''}
                    type="submit"
                    onPress={handleNext}
                  >
                    {step.nextActionLabel || t('actions.next')}
                  </ActionButton>
                ) : null}
              </div>
            )}
          </ModalPrimitiveFooter>
        </ModalPrimitiveContent>
      </ModalPrimitive>
    );
  },
);

StepModal.displayName = 'StepModal';

export default StepModal;
