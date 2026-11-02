// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { cn } from '@heroui/react';
import { useTranslation } from 'next-i18next';

import { ActionButton } from '../Buttons';
import { Chip } from '../Chip';

import { useWizardStepContext } from './WizardContext';

export type WizardStepProps = {
  /** Identifies the step across renders, so a conditional step cannot shift another's state. */
  id: string;
  title: string;
  description?: string;
  /** Marks the step as optional; advancement remains controlled by `canProceed`. */
  isOptional?: boolean;
  /** Whether the user can advance from this step. */
  canProceed?: boolean;
  /** Runs before advancing; return `false` after handling an expected failure. */
  onNext?: () => boolean | void | Promise<boolean> | Promise<void>;
  /** Called only while the step is collapsed, so it can read the caller's live values. */
  renderSummary?: () => React.ReactNode;
  children?: React.ReactNode;
};

/**
 * One step of a Wizard. A step is just a titled section: it shows its children
 * while active and its summary once passed.
 */
export const WizardStep = ({
  id,
  title,
  description,
  isOptional,
  renderSummary,
  children,
}: WizardStepProps): React.ReactElement | null => {
  const { t: tShared } = useTranslation('sharedComponents');
  const { t: tWizard } = useTranslation('sharedComponents', {
    keyPrefix: 'wizard',
  });
  const { state, onEdit } = useWizardStepContext();

  if (state === 'unreached') {
    return null;
  }

  const isCollapsed = state === 'collapsed';

  return (
    <section
      hidden={state === 'ahead'}
      data-testid={`wizard-step-${id}`}
      className="box-border mx-auto w-full max-w-[980px] rounded-xl border border-divider"
    >
      <div className="flex flex-col gap-4 p-8">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3
                className="text-lg font-semibold outline-none"
                tabIndex={state === 'active' ? -1 : undefined}
              >
                {title}
              </h3>
              {isOptional ? (
                <Chip size="sm" variant="flat">
                  {tWizard('optional')}
                </Chip>
              ) : null}
            </div>
            {!isCollapsed && description ? (
              <p className="text-sm text-muted">{description}</p>
            ) : null}
          </div>
          {isCollapsed ? (
            <ActionButton secondary size="sm" onPress={onEdit}>
              {tShared('actions.edit.title')}
            </ActionButton>
          ) : null}
        </div>

        {isCollapsed ? (
          // Summary rows subgrid onto this label column so labels stay aligned
          // across steps; anything else spans the full width.
          <div className="grid grid-cols-[13.75rem_1fr] gap-x-4 gap-y-2 text-sm [&>*]:col-span-2">
            {renderSummary?.()}
          </div>
        ) : null}

        {/* Hidden rather than unmounted: the wizard's form drops the value of
            any field that leaves the DOM, and a passed step still owns its. */}
        <div
          hidden={state !== 'active'}
          className={cn(state === 'active' && 'flex flex-col gap-4')}
        >
          {children}
        </div>
      </div>
    </section>
  );
};

WizardStep.displayName = 'Wizard.Step';

/** Must be rendered inside a Wizard step summary, whose grid supplies the columns. */
export const WizardSummaryRow: React.FC<{
  label: string;
  value: React.ReactNode;
}> = ({ label, value }) => (
  <div className="grid grid-cols-subgrid">
    <span className="text-muted">{label}</span>
    <span className="min-w-0">{value ?? '—'}</span>
  </div>
);
