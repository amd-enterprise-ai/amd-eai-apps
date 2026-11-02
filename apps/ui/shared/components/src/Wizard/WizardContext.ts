// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { createContext, useContext } from 'react';

/**
 * Passed steps are `collapsed` to their summary. A step the user has jumped back
 * past is `ahead`: out of sight, but still rendered so its fields keep their
 * values. A step never reached yet is `unreached` and renders nothing.
 */
export type WizardStepState = 'active' | 'collapsed' | 'ahead' | 'unreached';

type WizardStepContextValue = {
  state: WizardStepState;
  onEdit: () => void;
};

export const WizardStepContext = createContext<WizardStepContextValue | null>(
  null,
);

export const useWizardStepContext = (): WizardStepContextValue => {
  const context = useContext(WizardStepContext);
  if (!context) {
    throw new Error('Wizard.Step must be rendered inside a Wizard');
  }
  return context;
};
