// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { cn } from '@heroui/react';
import { forwardRef, useCallback, useImperativeHandle, useState } from 'react';
import { useTranslation } from 'next-i18next';

import { StepPageHandle, StepPageStep } from '@amdenterpriseai/types';
import { ActionButton } from '../Buttons';
import Stepper from '../Stepper/Stepper';

interface Props {
  className?: string;
  /** Step index to start on. Defaults to 0. */
  initialStep?: number;
  steps: StepPageStep[];
  /** When true, the Previous button renders on every step after the first. */
  allowPrevious?: boolean;
  /** Drives the loading state of the Next button (e.g. during async submit). */
  isActioning?: boolean;
  /** Wrapper around the stepper. Use to constrain width on wide pages. */
  stepperClassName?: string;
  /**
   * Wrapper around the step content and its actions footer. Use to constrain
   * the form to a narrower column than the page so dense input layouts stay
   * readable on wide viewports.
   */
  contentClassName?: string;
}

/**
 * Full-page multi-step wizard. Mirrors the API of `StepModal` but renders
 * inline so it can be embedded in a Next.js page (with breadcrumbs, app
 * chrome, etc.) instead of inside a modal overlay.
 *
 * Step transitions are owned by this component; callers can override per
 * step via `onStepChange` or take imperative control via the `ref`.
 */
export const StepPage = forwardRef<StepPageHandle, Props>(
  (
    {
      className,
      initialStep = 0,
      steps,
      allowPrevious = true,
      isActioning,
      stepperClassName,
      contentClassName,
    },
    ref,
  ) => {
    const { t } = useTranslation('sharedComponents');
    const [currentStep, setCurrentStep] = useState<number>(initialStep);

    const clampStep = useCallback(
      (step: number) => Math.max(0, Math.min(step, steps.length - 1)),
      [steps.length],
    );

    useImperativeHandle(
      ref,
      () => ({
        incrementStep: () => {
          setCurrentStep((prev) => clampStep(prev + 1));
        },
        setStep: (step: number) => {
          setCurrentStep(clampStep(step));
        },
      }),
      [clampStep],
    );

    const handleNext = useCallback(() => {
      const step = steps[currentStep];
      if (step?.onStepChange) {
        step.onStepChange(currentStep + 1);
        return;
      }
      setCurrentStep((prev) => clampStep(prev + 1));
    }, [clampStep, currentStep, steps]);

    const handlePrev = useCallback(() => {
      const step = steps[currentStep];
      if (step?.onStepChange) {
        step.onStepChange(currentStep - 1);
        return;
      }
      setCurrentStep((prev) => clampStep(prev - 1));
    }, [clampStep, currentStep, steps]);

    const active = steps[currentStep];
    const isLast = currentStep === steps.length - 1;
    const showPrev = currentStep > 0 && allowPrevious && !active?.hidePrev;
    const showNext = !isLast && !active?.hideNext;

    return (
      <div className={cn('flex flex-col gap-6 w-full', className)}>
        <div className={cn('mx-auto w-full max-w-2xl', stepperClassName)}>
          <Stepper
            step={currentStep}
            steps={steps.map((step) => ({ label: step.label }))}
          />
        </div>

        <div className={cn('flex w-full flex-col gap-6', contentClassName)}>
          <div className="flex flex-col gap-4">{active?.content}</div>

          <div className="flex items-center justify-end gap-2">
            {active?.customActions ?? (
              <>
                {showPrev ? (
                  <ActionButton
                    secondary
                    aria-label={
                      active?.backActionLabel || t('actions.previous') || ''
                    }
                    onPress={handlePrev}
                  >
                    {active?.backActionLabel || t('actions.previous')}
                  </ActionButton>
                ) : null}
                {showNext ? (
                  <ActionButton
                    primary
                    isLoading={isActioning}
                    aria-label={
                      active?.nextActionLabel || t('actions.next') || ''
                    }
                    type="submit"
                    onPress={handleNext}
                  >
                    {active?.nextActionLabel || t('actions.next')}
                  </ActionButton>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
    );
  },
);

StepPage.displayName = 'StepPage';

export default StepPage;
