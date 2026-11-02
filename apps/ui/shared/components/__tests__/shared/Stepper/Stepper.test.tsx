// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';

import { Stepper } from '@amdenterpriseai/components';

describe('Stepper Component', () => {
  const steps = [{ label: 'Step 1' }, { label: 'Step 2' }, { label: 'Step 3' }];

  it('renders the correct number of steps', () => {
    render(<Stepper step={1} steps={steps} />);
    const stepElements = screen.getAllByText(/Step \d/);
    expect(stepElements).toHaveLength(steps.length);
  });

  it('applies the correct class names based on the current step', () => {
    render(<Stepper step={1} steps={steps} />);
    const stepElements = screen.getAllByText(/Step \d/);

    // Completed step uses bg-accent
    expect(stepElements[0].previousElementSibling?.className).toContain(
      'bg-accent',
    );
    // Active step uses accent border styling
    expect(stepElements[1].previousElementSibling?.className).toContain(
      'border-accent',
    );
    // Future step uses muted foreground styling
    expect(stepElements[2].previousElementSibling?.className).toContain(
      'border-foreground/50',
    );
  });

  it('calls the onPress function when a step is clicked', () => {
    const onPressMock = vi.fn();
    const stepsWithOnPress = [
      { label: 'Step 1', onPress: onPressMock },
      { label: 'Step 2' },
      { label: 'Step 3' },
    ];

    render(<Stepper step={1} steps={stepsWithOnPress} />);
    const stepElement = screen.getByText('Step 1');
    fireEvent.click(stepElement);

    expect(onPressMock).toHaveBeenCalledWith(0);
  });
});
