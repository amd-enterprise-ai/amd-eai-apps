// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { cn } from '@heroui/react';
import { IconCheck } from '@tabler/icons-react';
import { Fragment } from 'react';

type StepperStep = {
  label: string;
  onPress?: (step: number) => void;
};

interface Props {
  className?: string;
  step: number;
  steps: StepperStep[];
}

const Stepper: React.FC<Props> = ({ step, steps, className }) => {
  const stepCount = steps.length;

  return (
    <div className={cn('w-full relative', className)}>
      {stepCount > 1 && (
        <div
          className="absolute z-0 top-0 left-0 right-0 grid h-8 lg:h-10 pointer-events-none"
          style={{
            gridTemplateColumns: `repeat(${stepCount * 2}, minmax(0, 1fr))`,
          }}
          aria-hidden
        >
          <div></div>
          {steps.slice(0, -1).map((_, i) => (
            <Fragment key={`stepper-connector-${i}`}>
              <div className="flex flex-row items-center justify-center h-full w-full pl-8">
                <div
                  className={cn('h-0.5 w-full rounded-l-full', {
                    'bg-accent': i < step,
                    'bg-foreground/50': i >= step,
                  })}
                />
              </div>
              <div className="flex flex-row items-center justify-center h-full w-full pr-8">
                <div
                  className={cn('h-0.5 w-full rounded-r-full', {
                    'bg-accent': i < step,
                    'bg-foreground/50': i >= step,
                  })}
                />
              </div>
            </Fragment>
          ))}
          <div></div>
        </div>
      )}

      <div
        className="relative z-10 grid w-full"
        style={{
          gridTemplateColumns: `repeat(${stepCount}, minmax(0, 1fr))`,
        }}
      >
        {steps.map((_step, idx) => {
          const isCurrentStep = idx === step;
          const isCompletedStep = idx < step;
          const isPendingStep = idx > step;

          return (
            <div
              key={`stepper-${idx}`}
              aria-current={isCurrentStep ? 'step' : undefined}
              className="flex min-w-0 flex-col items-center"
            >
              <div
                className="flex w-full flex-col items-center gap-3"
                onClick={() => {
                  if (_step.onPress) {
                    _step.onPress(idx);
                  }
                }}
              >
                <span
                  className={cn(
                    'flex size-8 items-center justify-center rounded-full border-2 text-sm lg:size-10',
                    {
                      'border-transparent bg-accent text-background dark:text-foreground':
                        isCompletedStep,
                      'border-accent text-accent': isCurrentStep,
                      'border-foreground/50 text-foreground/50': isPendingStep,
                    },
                  )}
                >
                  {isCompletedStep ? (
                    <IconCheck className="size-4 lg:size-5" stroke={2.5} />
                  ) : (
                    idx + 1
                  )}
                </span>
                <div
                  className={cn('w-full px-1 text-center text-xs text-wrap', {
                    'font-medium': isCurrentStep,
                    'text-muted': isPendingStep,
                  })}
                >
                  {_step.label}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Stepper;
