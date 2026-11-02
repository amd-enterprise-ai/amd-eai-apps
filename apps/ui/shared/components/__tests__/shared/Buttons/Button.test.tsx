// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';
import { Button, ButtonGroup } from '@amdenterpriseai/components';

describe('Button adapter', () => {
  it('renders with children', () => {
    render(<Button data-testid="btn">Click me</Button>);
    expect(screen.getByTestId('btn')).toHaveTextContent('Click me');
  });

  it('passes color prop', () => {
    render(
      <Button color="primary" data-testid="btn">
        Primary
      </Button>,
    );
    expect(screen.getByTestId('btn')).toBeInTheDocument();
  });

  it('passes variant prop', () => {
    render(
      <Button variant="flat" data-testid="btn">
        Flat
      </Button>,
    );
    expect(screen.getByTestId('btn')).toBeInTheDocument();
  });

  it('passes isDisabled prop', () => {
    render(
      <Button isDisabled data-testid="btn">
        Disabled
      </Button>,
    );
    expect(screen.getByTestId('btn')).toBeDisabled();
  });

  it('accepts onPress prop without error', () => {
    const handlePress = vi.fn();
    const { unmount } = render(
      <Button onPress={handlePress} data-testid="btn">
        Press me
      </Button>,
    );
    expect(screen.getByTestId('btn')).toBeInTheDocument();
    unmount();
  });

  it('renders as an anchor when href is provided', () => {
    render(
      <Button href="/docs" data-testid="btn">
        Documentation
      </Button>,
    );

    const link = screen.getByTestId('btn');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/docs');
  });

  it('opens external links in a new tab when isExternal is set', () => {
    render(
      <Button href="https://example.com/docs" isExternal data-testid="btn">
        Documentation
      </Button>,
    );

    const link = screen.getByTestId('btn');
    expect(link).toHaveAttribute('href', 'https://example.com/docs');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('respects a caller-supplied render prop over href default', () => {
    render(
      <Button
        href="/docs"
        render={(props) => <span {...props} data-testid="custom-render" />}
      >
        Documentation
      </Button>,
    );

    expect(screen.getByTestId('custom-render').tagName).toBe('SPAN');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders as a button when href is not provided', () => {
    render(<Button data-testid="btn">Click me</Button>);

    expect(screen.getByTestId('btn').tagName).toBe('BUTTON');
  });
});

describe('ButtonGroup adapter', () => {
  it('renders children buttons', () => {
    render(
      <ButtonGroup>
        <Button data-testid="btn-a">A</Button>
        <Button data-testid="btn-b">B</Button>
      </ButtonGroup>,
    );
    expect(screen.getByTestId('btn-a')).toBeInTheDocument();
    expect(screen.getByTestId('btn-b')).toBeInTheDocument();
  });
});
