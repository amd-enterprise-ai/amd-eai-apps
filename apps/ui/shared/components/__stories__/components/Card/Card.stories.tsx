// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';
import { Card, CardBody, CardHeader, CardFooter } from '../../../src/Card';

export default {
  title: 'Components/Card',
} satisfies StoryDefault;

// ============================================================================
// Compound API — the adapter exposes both flat parts and Card.* subcomponents
// ============================================================================

export const FlatImports: Story = () => (
  <div className="w-full max-w-sm p-4">
    <Card>
      <CardHeader>
        <h3 className="text-lg font-semibold">Flat import usage</h3>
      </CardHeader>
      <CardBody>
        <p>Body rendered with the flat CardBody import.</p>
      </CardBody>
      <CardFooter>
        <p className="text-sm text-muted">Footer</p>
      </CardFooter>
    </Card>
  </div>
);

export const CompoundSyntax: Story = () => (
  <div className="w-full max-w-sm p-4">
    <Card>
      <Card.Header>
        <h3 className="text-lg font-semibold">Compound syntax usage</h3>
      </Card.Header>
      <Card.Body>
        <p>Body rendered with the Card.Body compound subcomponent.</p>
      </Card.Body>
      <Card.Footer>
        <p className="text-sm text-muted">Footer</p>
      </Card.Footer>
    </Card>
  </div>
);

export const HeaderBodyFooter: Story = () => (
  <div className="w-full max-w-sm p-4">
    <Card>
      <Card.Header className="flex flex-col items-start gap-1">
        <h3 className="text-lg font-semibold">Workload summary</h3>
        <span className="text-xs text-muted">Updated just now</span>
      </Card.Header>
      <Card.Body className="gap-2">
        <div className="flex justify-between text-sm">
          <span className="text-muted">Status</span>
          <span className="font-medium">Running</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted">Replicas</span>
          <span className="font-medium">3 / 3</span>
        </div>
      </Card.Body>
      <Card.Footer className="justify-end">
        <span className="text-xs text-muted">View details</span>
      </Card.Footer>
    </Card>
  </div>
);

// ============================================================================
// Interactive Playground
// ============================================================================

type PlaygroundArgs = {
  showHeader: boolean;
  showFooter: boolean;
};

export const Playground: Story<PlaygroundArgs> = ({
  showHeader = true,
  showFooter = true,
}) => (
  <div className="w-full max-w-sm p-4">
    <Card>
      {showHeader && (
        <Card.Header>
          <h3 className="text-base font-semibold">Playground</h3>
        </Card.Header>
      )}
      <Card.Body>
        <p className="text-sm text-muted">
          Toggle the controls to explore the Card layout.
        </p>
      </Card.Body>
      {showFooter && (
        <Card.Footer>
          <span className="text-xs text-muted">Footer</span>
        </Card.Footer>
      )}
    </Card>
  </div>
);

Playground.args = {
  showHeader: true,
  showFooter: true,
};

Playground.argTypes = {
  showHeader: {
    control: { type: 'boolean' },
    defaultValue: true,
  },
  showFooter: {
    control: { type: 'boolean' },
    defaultValue: true,
  },
};
