// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button, Tooltip } from '@amdenterpriseai/components';

const TestIcon = () => <svg aria-hidden />;

/**
 * Tooltips are opened from the keyboard because jsdom does not deliver the hover
 * events react-aria listens for.
 *
 * The overlay positions itself against the element the trigger context publishes,
 * and jsdom has no layout to measure. The description link is the observable side
 * of that same wiring: when it is missing, the overlay has no anchor and renders
 * at the viewport origin.
 */
const expectAnchoredTooltipOnFocus = async (
  trigger: Element | null,
  text: string,
) => {
  await userEvent.tab();
  expect(trigger).toHaveFocus();
  const tooltip = await screen.findByRole('tooltip');
  expect(tooltip).toHaveTextContent(text);
  expect(trigger).toHaveAttribute('aria-describedby', tooltip.id);
};

describe('Tooltip adapter', () => {
  it('renders trigger content', () => {
    render(
      <Tooltip content="Help text">
        <button type="button">Trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole('button', { name: 'Trigger' })).toBeInTheDocument();
  });

  it('anchors the tooltip to an interactive child', async () => {
    render(
      <Tooltip content="Help text">
        <Button>Action</Button>
      </Tooltip>,
    );
    await expectAnchoredTooltipOnFocus(
      screen.getByRole('button', { name: 'Action' }),
      'Help text',
    );
  });

  it('anchors the tooltip to a focusable wrapper around a component child', async () => {
    render(
      <Tooltip content="Help text">
        <TestIcon />
      </Tooltip>,
    );
    const trigger = screen.getByRole('button');
    expect(trigger).toHaveClass('cursor-help');
    await expectAnchoredTooltipOnFocus(trigger, 'Help text');
  });

  it('anchors the tooltip to a plain element child without wrapping it', async () => {
    const { container } = render(
      <Tooltip content="Help text">
        <span>Truncated value</span>
      </Tooltip>,
    );
    const trigger = container.querySelector('span');
    expect(trigger).not.toHaveAttribute('role');
    await expectAnchoredTooltipOnFocus(trigger, 'Help text');
  });

  it('preserves the role an element child declares', async () => {
    const { container } = render(
      <Tooltip content="Help text">
        <span role="img" aria-label="Healthy">
          ●
        </span>
      </Tooltip>,
    );
    const trigger = container.querySelector('span');
    expect(trigger).toHaveAttribute('role', 'img');
    await expectAnchoredTooltipOnFocus(trigger, 'Help text');
  });

  it('anchors the tooltip to a wrapper around a bare string child', async () => {
    render(<Tooltip content="Help text">Plain text trigger</Tooltip>);
    await expectAnchoredTooltipOnFocus(screen.getByRole('button'), 'Help text');
  });

  it('keeps a wrapper around a control free of a second button role', async () => {
    const { container } = render(
      <Tooltip content="Unavailable">
        <span>
          <Button isDisabled>Action</Button>
        </span>
      </Tooltip>,
    );
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(container.querySelector('span')).not.toHaveAttribute('role');
    await expectAnchoredTooltipOnFocus(
      container.querySelector('span'),
      'Unavailable',
    );
  });
});
