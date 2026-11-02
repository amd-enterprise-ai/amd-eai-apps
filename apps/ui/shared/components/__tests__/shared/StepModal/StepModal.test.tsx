// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen } from '@testing-library/react';
import { createRef } from 'react';

import { StepModalHandle, StepModalStep } from '@amdenterpriseai/types';

import { StepModal } from '@/src/StepModal/StepModal';

describe('StepModal', () => {
  const steps: StepModalStep[] = [
    {
      label: 'Step 1',
      content: <div>Step 1 Content</div>,
      nextActionLabel: 'Next 1',
    },
    {
      label: 'Step 2',
      content: <div>Step 2 Content</div>,
      nextActionLabel: 'Next 2',
    },
    { label: 'Step 3', content: <div>Step 3 Content</div>, hideNext: true },
  ];

  const onOpenChange = vi.fn();
  const onCancel = vi.fn();

  const renderComponent = (props = {}) => {
    return render(
      <StepModal
        initialStep={0}
        steps={steps}
        isOpen={true}
        onOpenChange={onOpenChange}
        onCancel={onCancel}
        {...props}
      />,
    );
  };

  it('renders the StepModal component', async () => {
    await act(() => {
      renderComponent();
    });

    expect(screen.getAllByText('Step 1').length).toBeGreaterThan(0);
    expect(screen.getByText('Step 1 Content')).toBeInTheDocument();
  });

  it('navigates to the next step', async () => {
    await act(() => {
      renderComponent();
    });

    expect(screen.getAllByText('Step 1').length).toBeGreaterThan(0);
    expect(screen.getByText('Step 1 Content')).toBeInTheDocument();

    await fireEvent.click(screen.getByLabelText('Next 1'));

    expect(screen.getByText('Step 2 Content')).toBeInTheDocument();

    await fireEvent.click(screen.getByLabelText('Next 2'));

    expect(screen.getByText('Step 3 Content')).toBeInTheDocument();
  });

  it('navigates to the previous step', async () => {
    await act(() => {
      renderComponent({ initialStep: 1, allowPrevious: true });
    });

    expect(screen.getByText('Step 2 Content')).toBeInTheDocument();

    await fireEvent.click(screen.getByLabelText('Previous'));

    expect(screen.getByText('Step 1 Content')).toBeInTheDocument();
  });

  it('calls onOpenChange when modal is closed', async () => {
    await act(() => {
      renderComponent();
    });

    await fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('calls onCancel when modal is closed', async () => {
    await act(() => {
      renderComponent();
    });
    await fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it('resets to initial step on close if resetOnClose is true', async () => {
    await act(() => {
      renderComponent({ initialStep: 1, resetOnClose: true });
    });

    await fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.getByText('Step 1 Content')).toBeInTheDocument();
  });

  it('does not show previous button if allowPrevious is false', () => {
    renderComponent({ initialStep: 1, allowPrevious: false });
    expect(screen.queryByLabelText('Back')).not.toBeInTheDocument();
  });

  it('does not show next button if on the last step', () => {
    renderComponent({ initialStep: 1 });
    expect(screen.queryByLabelText('Next')).not.toBeInTheDocument();
  });

  it('calls the imperative handlers correctly', async () => {
    const ref = createRef<StepModalHandle>();

    await act(() => {
      renderComponent({ ref });
    });

    expect(screen.getByText('Step 1 Content')).toBeInTheDocument();

    await act(() => {
      ref?.current?.incrementStep();
    });
    expect(screen.getByText('Step 2 Content')).toBeInTheDocument();

    await act(() => {
      ref?.current?.setStep(2);
    });

    expect(screen.getByText('Step 3 Content')).toBeInTheDocument();
  });

  it('calls onStepChange when step changes', async () => {
    const ref = createRef<StepModalHandle>();
    const testSteps: StepModalStep[] = [
      {
        label: 'Step 1',
        content: <div>Step 1 Content</div>,
        nextActionLabel: 'Next 1',
        onStepChange: vi.fn(),
      },
      {
        label: 'Step 2',
        content: <div>Step 2 Content</div>,
        nextActionLabel: 'Next 2',
        onStepChange: vi.fn(),
      },
      { label: 'Step 3', content: <div>Step 3 Content</div>, hideNext: true },
    ];

    await act(() => {
      render(
        <StepModal
          ref={ref}
          initialStep={0}
          steps={testSteps}
          isOpen={true}
          onOpenChange={vi.fn()}
          onCancel={vi.fn()}
        />,
      );
    });

    fireEvent.click(screen.getByLabelText('Next 1'));
    expect(testSteps[0].onStepChange).toHaveBeenCalledWith(1);

    // handleNext returns early when onStepChange is set, so manually advance
    await act(async () => {
      ref.current?.incrementStep();
    });

    const nextButton = await screen.findByLabelText('Next 2');
    fireEvent.click(nextButton);
    expect(testSteps[1].onStepChange).toHaveBeenCalledWith(2);
  });

  it('hides the previous button if hidePrev is true', async () => {
    const stepsWithHidePrev: StepModalStep[] = [
      {
        label: 'Step 1',
        content: <div>Step 1 Content</div>,
        nextActionLabel: 'Next 1',
      },
      {
        label: 'Step 2',
        content: <div>Step 2 Content</div>,
        nextActionLabel: 'Next 2',
        hidePrev: true,
      },
    ];

    await act(() => {
      renderComponent({
        steps: stepsWithHidePrev,
        initialStep: 1,
        allowPrevious: true,
      });
    });

    expect(screen.queryByLabelText('Previous')).not.toBeInTheDocument();
  });

  it('hides the next button if hideNext is true', async () => {
    const stepsWithHideNext: StepModalStep[] = [
      {
        label: 'Step 1',
        content: <div>Step 1 Content</div>,
        nextActionLabel: 'Next 1',
        hideNext: true,
      },
      {
        label: 'Step 2',
        content: <div>Step 2 Content</div>,
        nextActionLabel: 'Next 2',
      },
    ];

    await act(() => {
      renderComponent({ steps: stepsWithHideNext, initialStep: 0 });
    });

    expect(screen.queryByLabelText('Next 1')).not.toBeInTheDocument();
  });
});
