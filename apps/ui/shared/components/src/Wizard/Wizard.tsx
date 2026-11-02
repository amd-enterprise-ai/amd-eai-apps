// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Modal as HeroUIModal, useScrollShadow } from '@heroui/react';
import {
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
} from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import {
  Children,
  Fragment,
  isValidElement,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from 'react';

import { ActionButton } from '../Buttons';
import Stepper from '../Stepper/Stepper';

import { WizardStepContext, type WizardStepState } from './WizardContext';
import {
  WizardStep,
  WizardSummaryRow,
  type WizardStepProps,
} from './WizardStep';

type WizardStepElement = React.ReactElement<WizardStepProps>;

/**
 * The steps in the order the user walks them. Fragments are flattened away, so
 * steps can be grouped however the caller finds readable, and blank children are
 * dropped, so a conditional step can be left out with `{condition && <Step/>}`.
 */
const toStepElements = (children: React.ReactNode): WizardStepElement[] =>
  Children.toArray(children).flatMap((child) => {
    if (isValidElement(child) && child.type === Fragment) {
      return toStepElements(
        (child.props as { children?: React.ReactNode }).children,
      );
    }
    if (!isValidElement(child) || child.type !== WizardStep) {
      throw new Error('Wizard only accepts Wizard.Step as children');
    }
    return [child as WizardStepElement];
  });

const stepState = (
  id: string,
  index: number,
  currentStepIndex: number,
  reachedStepIds: ReadonlySet<string>,
): WizardStepState => {
  if (index === currentStepIndex) {
    return 'active';
  }
  if (!reachedStepIds.has(id)) {
    return 'unreached';
  }
  return index < currentStepIndex ? 'collapsed' : 'ahead';
};

const resolveCurrentStepIndex = (
  steps: readonly WizardStepProps[],
  requestedStepId: string | null,
  reachedStepIds: ReadonlySet<string>,
): number => {
  const requestedStepIndex =
    requestedStepId === null
      ? steps.length
      : steps.findIndex((step) => step.id === requestedStepId);

  // Visit any newly inserted step before the requested one. If the requested
  // step disappeared, continue with the first step not reached yet.
  const firstUnreachedStepIndex = steps.findIndex(
    (step, index) =>
      (requestedStepIndex === -1 || index <= requestedStepIndex) &&
      !reachedStepIds.has(step.id),
  );

  if (firstUnreachedStepIndex !== -1) {
    return firstUnreachedStepIndex;
  }
  return requestedStepIndex === -1 ? steps.length : requestedStepIndex;
};

/**
 * The flow usually sits in a form whose only buttons are the wizard's own, and a
 * browser submits such a form as soon as Enter is pressed in a step that happens
 * to hold a single input — handing the caller a half-filled payload from the
 * middle of the flow.
 */
const blockImplicitSubmit = (event: React.KeyboardEvent) => {
  if (event.key === 'Enter' && event.target instanceof HTMLInputElement) {
    event.preventDefault();
  }
};

type WizardProps = {
  /**
   * The steps, in the order the user walks them. Only `Wizard.Step` children count
   * as steps; a conditional one can be left out with
   * `{condition && <Wizard.Step … />}`.
   */
  children: React.ReactNode;
  title?: string;
  description?: string;
  completeLabel?: string;
  /**
   * Runs on the Check step. Return `false` when submission was rejected so the
   * wizard can return the user to the first step reporting `canProceed={false}`.
   */
  onComplete: () => boolean | void | Promise<boolean> | Promise<void>;
  onClose: () => void;
};

const WizardRoot = ({
  children,
  title,
  description,
  completeLabel,
  onClose,
  onComplete,
}: WizardProps) => {
  const stepElements = toStepElements(children);
  const steps = stepElements.map((element) => element.props);
  const stepsRef = useRef(steps);
  stepsRef.current = steps;

  const { t: tShared } = useTranslation('sharedComponents');
  const { t: tWizard } = useTranslation('sharedComponents', {
    keyPrefix: 'wizard',
  });
  const scrollRef = useRef<HTMLDivElement>(null);
  // HeroUI exposes the remaining scroll directions as data attributes, which
  // let the bottom fade update without a React render on every scroll.
  useScrollShadow({
    containerRef: scrollRef as RefObject<HTMLElement>,
    orientation: 'vertical',
    offset: 0,
    visibility: 'auto',
    isEnabled: true,
  });

  const [requestedStepId, setRequestedStepId] = useState<string | null>(
    () => steps[0]?.id ?? null,
  );
  const [isPending, setIsPending] = useState(false);
  const [reachedStepIds, setReachedStepIds] = useState<ReadonlySet<string>>(
    () => new Set(steps[0] ? [steps[0].id] : []),
  );

  if (steps.length === 0) {
    throw new Error('Wizard requires at least one Wizard.Step');
  }
  if (new Set(steps.map((step) => step.id)).size !== steps.length) {
    throw new Error('Wizard.Step ids must be unique');
  }

  const currentStepIndex = resolveCurrentStepIndex(
    steps,
    requestedStepId,
    reachedStepIds,
  );
  const isCheckStep = currentStepIndex === steps.length;
  const isNextEnabled =
    isCheckStep || steps[currentStepIndex].canProceed !== false;
  const activeStep = isCheckStep ? null : steps[currentStepIndex];
  const activeStepId = activeStep?.id ?? null;
  const stepAnnouncement = activeStep
    ? tWizard('stepAnnouncement', {
        current: currentStepIndex + 1,
        total: steps.length,
        title: activeStep.title,
      })
    : tWizard('check');

  useEffect(() => {
    if (!activeStepId) {
      return;
    }
    const stepHeading = scrollRef.current?.querySelector<HTMLElement>(
      `[data-testid="wizard-step-${activeStepId}"] h3`,
    );
    stepHeading?.focus();
  }, [activeStepId]);

  const goToStep = (index: number) => {
    const nextIndex = Math.max(0, Math.min(index, steps.length));
    const nextStep = steps[nextIndex];
    setRequestedStepId(nextStep?.id ?? null);
    if (nextStep) {
      setReachedStepIds((previous) => {
        if (previous.has(nextStep.id)) {
          return previous;
        }
        return new Set(previous).add(nextStep.id);
      });
    }
  };

  const runAction = async (
    action: () => boolean | void | Promise<boolean> | Promise<void>,
  ): Promise<boolean> => {
    setIsPending(true);
    try {
      return (await action()) !== false;
    } finally {
      setIsPending(false);
    }
  };

  const goNext = async () => {
    if (isCheckStep) {
      if (!(await runAction(onComplete))) {
        // Validation failures update step gates on the next render; defer so
        // callers using react-hook-form see the post-submit canProceed values.
        queueMicrotask(() => {
          const blockedIndex = stepsRef.current.findIndex(
            (step) => step.canProceed === false,
          );
          if (blockedIndex !== -1) {
            goToStep(blockedIndex);
          }
        });
      }
      return;
    }
    const onNext = steps[currentStepIndex].onNext;
    if (!onNext || (await runAction(onNext))) {
      goToStep(currentStepIndex + 1);
    }
  };

  const nextLabel = isCheckStep
    ? (completeLabel ?? tShared('actions.submit.title'))
    : tShared('actions.next');
  const backLabel = tShared('actions.back.title');
  const cancelLabel = tShared('actions.cancel.title');

  const stepperSteps = [
    ...steps.map((step, index) => ({
      label: step.title,
      onPress: index <= currentStepIndex ? () => goToStep(index) : undefined,
    })),
    { label: tWizard('check') },
  ];

  const backButton =
    currentStepIndex === 0 ? (
      <ActionButton secondary isDisabled={isPending} onPress={onClose}>
        {cancelLabel}
      </ActionButton>
    ) : (
      <ActionButton
        secondary
        data-testid="wizard-back"
        isDisabled={isPending}
        onPress={() => goToStep(currentStepIndex - 1)}
        startContent={<IconChevronLeft className="size-4" stroke={2} />}
      >
        {backLabel}
      </ActionButton>
    );

  return (
    <HeroUIModal
      isOpen
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <HeroUIModal.Backdrop isDismissable={false} isKeyboardDismissDisabled>
        <HeroUIModal.Container size="full">
          <HeroUIModal.Dialog className="@container p-0!">
            {!isPending ? <HeroUIModal.CloseTrigger /> : null}

            {title || description ? (
              <HeroUIModal.Header className="w-full border-b border-divider px-6 py-6 @4xl:px-10">
                <HeroUIModal.Heading>
                  <div className="flex flex-col gap-1">
                    {title ? (
                      <span className="text-xl font-semibold">{title}</span>
                    ) : null}
                    {description ? (
                      <span className="text-sm text-muted">{description}</span>
                    ) : null}
                  </div>
                </HeroUIModal.Heading>
              </HeroUIModal.Header>
            ) : null}

            <HeroUIModal.Body
              ref={scrollRef}
              className="group relative m-0! p-0!"
              onKeyDown={blockImplicitSubmit}
            >
              <div aria-live="polite" aria-atomic="true" className="sr-only">
                {stepAnnouncement}
              </div>
              <div className="mx-auto flex w-full flex-col gap-6 px-6 py-6">
                {stepElements.map((element, index) => (
                  <WizardStepContext.Provider
                    key={element.props.id}
                    value={{
                      state: stepState(
                        element.props.id,
                        index,
                        currentStepIndex,
                        reachedStepIds,
                      ),
                      onEdit: () => goToStep(index),
                    }}
                  >
                    {element}
                  </WizardStepContext.Provider>
                ))}
              </div>
              <div
                aria-hidden="true"
                className="pointer-events-none sticky bottom-0 z-10 hidden h-6 items-center justify-center bg-linear-to-b from-transparent to-overlay group-data-[bottom-scroll=true]:flex group-data-[top-bottom-scroll=true]:flex"
              >
                <IconChevronDown className="size-4 text-divider" stroke={2} />
              </div>
            </HeroUIModal.Body>

            <HeroUIModal.Footer>
              <div className="grid w-full grid-cols-[1fr_minmax(0,3fr)_1fr] items-center gap-4 border-t border-divider px-6 py-6 @4xl:px-10">
                <div className="flex justify-start">{backButton}</div>

                <div className="min-w-0 px-4">
                  {/* The labelled indicator needs room the flow does not always
                      have, so narrow containers get the position on its own. */}
                  <div className="hidden @4xl:block">
                    <Stepper step={currentStepIndex} steps={stepperSteps} />
                  </div>
                  <p className="text-center text-sm text-muted @4xl:hidden">
                    {currentStepIndex + 1} / {stepperSteps.length}
                  </p>
                </div>

                <div className="flex justify-end">
                  <ActionButton
                    primary
                    data-testid="wizard-next"
                    isDisabled={!isNextEnabled || isPending}
                    isLoading={isPending}
                    onPress={() => {
                      void goNext();
                    }}
                    endContent={
                      !isCheckStep ? (
                        <IconChevronRight className="size-4" stroke={2} />
                      ) : undefined
                    }
                  >
                    {nextLabel}
                  </ActionButton>
                </div>
              </div>
            </HeroUIModal.Footer>
          </HeroUIModal.Dialog>
        </HeroUIModal.Container>
      </HeroUIModal.Backdrop>
    </HeroUIModal>
  );
};

WizardRoot.displayName = 'Wizard';

/**
 * A fullscreen, state-management-agnostic multi-step flow.
 *
 * The caller owns values, validation, and submission using React state, a form
 * library, an external store, or no state at all. Wizard owns navigation and
 * summaries.
 *
 * @example ManagedForm
 * ```tsx
 * <ManagedForm
 *   validationSchema={schema}
 *   onFormSuccess={save}
 *   renderFields={(form) => {
 *     const name = form.watch('name');
 *     return (
 *       <Wizard
 *         onClose={close}
 *         onComplete={async () => {
 *           let isValid = true;
 *           await form.handleSubmit(save, () => {
 *             isValid = false;
 *           })();
 *           return isValid;
 *         }}
 *       >
 *         <Wizard.Step id="name" title="Name" canProceed={Boolean(name)}>
 *           <FormInput form={form} name="name" />
 *         </Wizard.Step>
 *       </Wizard>
 *     );
 *   }}
 * />
 * ```
 *
 * @example useState
 * ```tsx
 * const [name, setName] = useState('');
 *
 * <Wizard onClose={close} onComplete={() => save(name)}>
 *   <Wizard.Step id="name" title="Name" canProceed={Boolean(name)}>
 *     <Input value={name} onValueChange={setName} />
 *   </Wizard.Step>
 * </Wizard>
 * ```
 */
export const Wizard = Object.assign(WizardRoot, {
  Step: WizardStep,
  SummaryRow: WizardSummaryRow,
});
