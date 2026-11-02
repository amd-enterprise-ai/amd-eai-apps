// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { FormInput, ManagedForm, Wizard } from '@amdenterpriseai/components';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState, type ComponentProps } from 'react';
import { z } from 'zod';

// Resolves keys the way i18next does, so a wrong namespace or a dropped
// keyPrefix changes the rendered text instead of passing silently.
vi.mock('next-i18next', () => ({
  useTranslation: (ns: string, options?: { keyPrefix?: string }) => ({
    t: (key: string) => [ns, options?.keyPrefix, key].filter(Boolean).join('.'),
  }),
}));

const schema = z.object({
  name: z.string().min(1),
  owner: z.string().min(1),
});
const nameSchema = schema.pick({ name: true });
const ownerSchema = schema.pick({ owner: true });

type Values = z.infer<typeof schema>;

const Harness = ({
  onComplete,
  isReviewReady = true,
  onReviewNext,
}: {
  onComplete: (values: Values) => void;
  isReviewReady?: boolean;
  onReviewNext?: ComponentProps<typeof Wizard.Step>['onNext'];
}) => (
  <ManagedForm<Values>
    validationSchema={schema}
    defaultValues={{ name: '', owner: '' }}
    onFormSuccess={onComplete}
    renderFields={(form) => {
      const values = {
        name: form.watch('name') ?? '',
        owner: form.watch('owner') ?? '',
      };
      return (
        <Wizard
          title="Wizard"
          onClose={vi.fn()}
          onComplete={async () => {
            let isValid = true;
            await form.handleSubmit(onComplete, () => {
              isValid = false;
            })();
            return isValid;
          }}
        >
          <Wizard.Step
            id="details"
            title="Details"
            canProceed={nameSchema.safeParse(values).success}
            renderSummary={() => (
              <Wizard.SummaryRow label="Name" value={values.name} />
            )}
          >
            <FormInput form={form} name="name" label="Name" />
          </Wizard.Step>
          <Wizard.Step
            id="access"
            title="Access"
            canProceed={ownerSchema.safeParse(values).success}
          >
            <FormInput form={form} name="owner" label="Owner" />
          </Wizard.Step>
          <Wizard.Step
            id="review"
            title="Review"
            canProceed={isReviewReady}
            onNext={onReviewNext}
          >
            <span>Review the details</span>
          </Wizard.Step>
        </Wizard>
      );
    }}
  />
);

const noteSchema = z.object({
  name: z.string().min(1),
  note: z.string().optional(),
});

/** A first step whose only field satisfies the whole schema on its own. */
const SingleInputHarness = ({
  onComplete,
}: {
  onComplete: (values: z.infer<typeof noteSchema>) => void;
}) => (
  <ManagedForm<z.infer<typeof noteSchema>>
    validationSchema={noteSchema}
    defaultValues={{ name: '', note: '' }}
    onFormSuccess={onComplete}
    renderFields={(form) => (
      <Wizard
        onClose={vi.fn()}
        onComplete={async () => {
          let isValid = true;
          await form.handleSubmit(onComplete, () => {
            isValid = false;
          })();
          return isValid;
        }}
      >
        <Wizard.Step id="details" title="Details">
          <FormInput form={form} name="name" label="Name" />
        </Wizard.Step>
        <Wizard.Step id="note" title="Note">
          <FormInput form={form} name="note" label="Note" />
        </Wizard.Step>
      </Wizard>
    )}
  />
);

const ConditionalStepHarness = () => {
  const [showFirstStep, setShowFirstStep] = useState(true);

  return (
    <Wizard onClose={vi.fn()} onComplete={vi.fn()}>
      {showFirstStep ? (
        <Wizard.Step id="first" title="First">
          <span>First content</span>
        </Wizard.Step>
      ) : null}
      <Wizard.Step id="second" title="Second">
        <span>Second content</span>
        <button type="button" onClick={() => setShowFirstStep(false)}>
          Remove first step
        </button>
      </Wizard.Step>
      <Wizard.Step id="third" title="Third">
        <span>Third content</span>
      </Wizard.Step>
    </Wizard>
  );
};

const DynamicStepHarness = () => {
  const [replicas, setReplicas] = useState('1');

  return (
    <Wizard onClose={vi.fn()} onComplete={vi.fn()}>
      <Wizard.Step id="name" title="Workload">
        <span>Workload</span>
      </Wizard.Step>
      <Wizard.Step id="capacity" title="Capacity">
        <input
          aria-label="Replicas"
          value={replicas}
          onChange={(event) => setReplicas(event.target.value)}
        />
      </Wizard.Step>
      {Number(replicas) > 1 && (
        <Wizard.Step id="rollout" title="Rollout">
          <span>Rollout strategy</span>
        </Wizard.Step>
      )}
    </Wizard>
  );
};

const nextButton = () =>
  screen.getByRole('button', { name: 'sharedComponents.actions.next' });

const advance = async (user: ReturnType<typeof userEvent.setup>) => {
  await waitFor(() => expect(nextButton()).toBeEnabled());
  await user.click(nextButton());
};

describe('Wizard', () => {
  it('renders a fullscreen modal with its close trigger in the dialog', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Wizard title="Wizard" onClose={onClose} onComplete={vi.fn()}>
        <Wizard.Step id="details" title="Details">
          <span>Content</span>
        </Wizard.Step>
      </Wizard>,
    );

    const dialog = screen.getByRole('dialog');
    const closeButton = screen.getByRole('button', { name: /close/i });

    expect(closeButton.parentElement).toBe(dialog);
    expect(dialog.closest('[data-slot="modal-container"]')).toHaveClass(
      'modal__container--full',
    );

    await user.click(closeButton);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('gates Next on the fields a step owns and collapses passed steps', async () => {
    const user = userEvent.setup();
    render(<Harness onComplete={vi.fn()} />);

    expect(nextButton()).toBeDisabled();
    expect(screen.queryByLabelText('Owner')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Name'), 'gpu-pool');
    await advance(user);

    expect(screen.getByLabelText('Owner')).toBeVisible();
    expect(screen.getByText('gpu-pool')).toBeVisible();
    expect(screen.getByLabelText('Name')).not.toBeVisible();
  });

  it('blocks a step that reports itself invalid', async () => {
    const user = userEvent.setup();
    render(<Harness onComplete={vi.fn()} isReviewReady={false} />);

    await user.type(screen.getByLabelText('Name'), 'gpu-pool');
    await advance(user);
    await user.type(screen.getByLabelText('Owner'), 'platform-team');
    await advance(user);

    expect(screen.getByText('Review the details')).toBeVisible();
    expect(nextButton()).toBeDisabled();
  });

  it('keeps the user on a step when onNext returns false', async () => {
    const user = userEvent.setup();
    const onReviewNext = vi.fn(() => false);
    render(<Harness onComplete={vi.fn()} onReviewNext={onReviewNext} />);

    await user.type(screen.getByLabelText('Name'), 'gpu-pool');
    await advance(user);
    await user.type(screen.getByLabelText('Owner'), 'platform-team');
    await advance(user);
    await user.click(nextButton());

    expect(onReviewNext).toHaveBeenCalledOnce();
    expect(screen.getByText('Review the details')).toBeVisible();
    expect(
      screen.queryByRole('button', {
        name: 'sharedComponents.actions.submit.title',
      }),
    ).not.toBeInTheDocument();
  });

  it('keeps the values of steps the user is not looking at', async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<Harness onComplete={onComplete} />);

    await user.type(screen.getByLabelText('Name'), 'gpu-pool');
    await advance(user);
    await user.type(screen.getByLabelText('Owner'), 'platform-team');

    // Jumping back leaves the step ahead out of sight but still holding its value.
    await user.click(
      screen.getByRole('button', {
        name: 'sharedComponents.actions.edit.title',
      }),
    );
    expect(screen.getByLabelText('Owner')).not.toBeVisible();

    await advance(user);
    await advance(user);
    await advance(user);
    await user.click(
      screen.getByRole('button', {
        name: 'sharedComponents.actions.submit.title',
      }),
    );

    await waitFor(() =>
      expect(onComplete.mock.calls[0]?.[0]).toEqual({
        name: 'gpu-pool',
        owner: 'platform-team',
      }),
    );
  });

  // A step holding a single input is what the browser submits a buttonless form
  // on, which would hand the caller a payload from the middle of the flow.
  it('does not submit the surrounding form when Enter is pressed in a step', async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<SingleInputHarness onComplete={onComplete} />);

    await user.type(screen.getByLabelText('Name'), 'gpu-pool{Enter}');

    expect(onComplete).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Name')).toBeVisible();
  });

  it('keeps the active step when an earlier conditional step disappears', async () => {
    const user = userEvent.setup();
    render(<ConditionalStepHarness />);

    await advance(user);
    await user.click(screen.getByRole('button', { name: 'Remove first step' }));

    expect(screen.getByText('Second content')).toBeVisible();
    expect(screen.queryByText('Third content')).not.toBeInTheDocument();
  });

  it('inserts a conditional step before Check and renumbers the flow', async () => {
    const user = userEvent.setup();
    render(<DynamicStepHarness />);

    expect(screen.getByText('1 / 3')).toBeVisible();

    await user.click(nextButton());
    await user.clear(screen.getByLabelText('Replicas'));
    await user.type(screen.getByLabelText('Replicas'), '3');

    expect(screen.getByText('2 / 4')).toBeVisible();

    await user.click(nextButton());
    expect(screen.getByText('Rollout strategy')).toBeVisible();
    expect(screen.getByText('3 / 4')).toBeVisible();

    await user.click(nextButton());
    expect(screen.getByText('4 / 4')).toBeVisible();
    expect(
      screen.getByRole('button', {
        name: 'sharedComponents.actions.submit.title',
      }),
    ).toBeVisible();
  });

  it('removes a conditional step without stranding the user', async () => {
    const user = userEvent.setup();
    render(<DynamicStepHarness />);

    await user.click(nextButton());
    await user.clear(screen.getByLabelText('Replicas'));
    await user.type(screen.getByLabelText('Replicas'), '3');
    await user.click(nextButton());

    await user.click(
      screen.getAllByRole('button', {
        name: 'sharedComponents.actions.back.title',
      })[0],
    );
    await user.clear(screen.getByLabelText('Replicas'));
    await user.type(screen.getByLabelText('Replicas'), '1');

    expect(screen.getByText('2 / 3')).toBeVisible();
    expect(screen.queryByText('Rollout strategy')).not.toBeInTheDocument();

    await user.click(nextButton());
    expect(screen.getByText('3 / 3')).toBeVisible();
    expect(
      screen.getByRole('button', {
        name: 'sharedComponents.actions.submit.title',
      }),
    ).toBeVisible();
  });

  it('treats isOptional as a label rather than a validation bypass', () => {
    render(
      <Wizard onClose={vi.fn()} onComplete={vi.fn()}>
        <Wizard.Step
          id="optional"
          title="Optional details"
          isOptional
          canProceed={false}
        >
          <span>Optional content</span>
        </Wizard.Step>
      </Wizard>,
    );

    expect(screen.getByText('sharedComponents.wizard.optional')).toBeVisible();
    expect(nextButton()).toBeDisabled();
  });

  it('preserves zero values and falls back only for nullish summaries', async () => {
    const user = userEvent.setup();
    render(
      <Wizard onClose={vi.fn()} onComplete={vi.fn()}>
        <Wizard.Step
          id="values"
          title="Values"
          renderSummary={() => (
            <>
              <Wizard.SummaryRow label="Count" value={0} />
              <Wizard.SummaryRow label="Note" value={null} />
            </>
          )}
        />
      </Wizard>,
    );

    await user.click(nextButton());

    expect(screen.getByText('0')).toBeVisible();
    expect(screen.getByText('—')).toBeVisible();
  });

  it('announces the active step for screen readers', async () => {
    const user = userEvent.setup();
    render(
      <Wizard onClose={vi.fn()} onComplete={vi.fn()}>
        <Wizard.Step id="details" title="Details">
          <span>Details content</span>
        </Wizard.Step>
        <Wizard.Step id="review" title="Review">
          <span>Review content</span>
        </Wizard.Step>
      </Wizard>,
    );

    expect(
      screen.getByText('sharedComponents.wizard.stepAnnouncement'),
    ).toBeInTheDocument();

    await advance(user);
    expect(
      screen.getByText('sharedComponents.wizard.stepAnnouncement'),
    ).toBeInTheDocument();
  });

  it('marks the current step in the stepper', async () => {
    const user = userEvent.setup();
    render(
      <Wizard onClose={vi.fn()} onComplete={vi.fn()}>
        <Wizard.Step id="details" title="Details">
          <span>Details content</span>
        </Wizard.Step>
        <Wizard.Step id="review" title="Review">
          <span>Review content</span>
        </Wizard.Step>
      </Wizard>,
    );

    expect(document.querySelector('[aria-current="step"]')).toBeTruthy();

    await advance(user);
    expect(document.querySelector('[aria-current="step"]')).toBeTruthy();
  });

  it('returns to the first blocked step when onComplete reports failure', async () => {
    const user = userEvent.setup();
    const SubmitFailureHarness = () => {
      const [blocked, setBlocked] = useState(false);
      return (
        <Wizard
          onClose={vi.fn()}
          onComplete={() => {
            setBlocked(true);
            return false;
          }}
        >
          <Wizard.Step id="details" title="Details" canProceed={!blocked}>
            <span>Details content</span>
          </Wizard.Step>
        </Wizard>
      );
    };

    render(<SubmitFailureHarness />);
    await advance(user);
    await user.click(
      screen.getByRole('button', {
        name: 'sharedComponents.actions.submit.title',
      }),
    );

    await waitFor(() =>
      expect(screen.getByText('Details content')).toBeVisible(),
    );
  });

  it('stays on the check step when onComplete reports failure and every step can proceed', async () => {
    const user = userEvent.setup();
    render(
      <Wizard onClose={vi.fn()} onComplete={() => false}>
        <Wizard.Step id="details" title="Details">
          <span>Details content</span>
        </Wizard.Step>
      </Wizard>,
    );

    await advance(user);
    await user.click(
      screen.getByRole('button', {
        name: 'sharedComponents.actions.submit.title',
      }),
    );

    expect(
      screen.getByRole('button', {
        name: 'sharedComponents.actions.submit.title',
      }),
    ).toBeVisible();
    expect(screen.queryByText('Details content')).not.toBeVisible();
  });

  it('accepts steps in fragments and rejects unsupported children', () => {
    const { unmount } = render(
      <Wizard onClose={vi.fn()} onComplete={vi.fn()}>
        {/* biome-ignore lint/complexity/noUselessFragments: verifies fragment flattening */}
        <>
          <Wizard.Step id="details" title="Details">
            <span>Content</span>
          </Wizard.Step>
          <Wizard.Step id="review" title="Review">
            <span>Review</span>
          </Wizard.Step>
        </>
      </Wizard>,
    );

    expect(screen.getByText('Content')).toBeVisible();
    unmount();

    expect(() =>
      render(
        <Wizard onClose={vi.fn()} onComplete={vi.fn()}>
          <div>Not a step</div>
        </Wizard>,
      ),
    ).toThrow('Wizard only accepts Wizard.Step as children');
  });
});
