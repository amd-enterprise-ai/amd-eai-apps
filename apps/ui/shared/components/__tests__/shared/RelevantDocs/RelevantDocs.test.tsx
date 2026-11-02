// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { RelevantDocs } from '@amdenterpriseai/components';
import type { DocEntry } from '@amdenterpriseai/components';

const mockSetStoredKeys = vi.fn();

const testDocs: DocEntry[] = [
  {
    title: 'Chat',
    description: 'Test deployments and inspect debug output.',
    url: 'https://example.com/chat',
  },
  {
    title: 'Compare Models',
    description: 'Compare responses across models.',
    url: 'https://example.com/compare',
  },
  {
    title: 'Deploy a Model',
    description: 'Deploy a model and run inference.',
    url: 'https://example.com/deploy',
  },
];

vi.mock('next-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: {} }),
}));

vi.mock('@amdenterpriseai/hooks', () => {
  const React = require('react') as typeof import('react');
  return {
    useLocalStorage: (_key: string, initialValue: string[]) => {
      const [keys, setKeys] = React.useState<string[]>(initialValue);
      return [
        keys,
        (value: string[] | ((prev: string[]) => string[])) => {
          const next = typeof value === 'function' ? value(keys) : value;
          setKeys(next);
          mockSetStoredKeys(next);
        },
      ];
    },
  };
});

// RelevantDocs consumes the v2 Accordion surface (`selectedKeys` /
// `onSelectionChange`) from the local adapter, so mock the adapter module
// directly. (Mocking `@heroui/react` would break the v3 adapter, which relies on
// the compound `Accordion.Item`/`.Heading`/`.Panel` subcomponents.)
type AccordionSelection = 'all' | Set<string>;
vi.mock('@/src/Accordion/Accordion', () => ({
  Accordion: ({
    children,
    selectedKeys,
    onSelectionChange,
  }: {
    children: React.ReactNode;
    selectedKeys: AccordionSelection;
    onSelectionChange: (keys: Set<string>) => void;
  }) => (
    <div data-testid="accordion" data-selected={String(selectedKeys)}>
      <button
        data-testid="accordion-toggle"
        onClick={() => {
          const isCurrentlyOpen =
            selectedKeys === 'all' ||
            (selectedKeys instanceof Set &&
              selectedKeys.has('relevantDocsAccordion'));
          onSelectionChange(
            isCurrentlyOpen
              ? new Set<string>()
              : new Set(['relevantDocsAccordion']),
          );
        }}
      >
        Toggle
      </button>
      {children}
    </div>
  ),
  AccordionItem: ({
    title,
    children,
  }: {
    title: string;
    children: React.ReactNode;
  }) => (
    <div data-testid="accordion-item">
      <span data-testid="accordion-item-title">{title}</span>
      {children}
    </div>
  ),
}));

describe('RelevantDocs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns null when docs is empty', () => {
    const { container } = render(<RelevantDocs docs={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders accordion with Documentation title and doc cards for page with entries', () => {
    render(<RelevantDocs docs={testDocs} />);
    expect(screen.getByTestId('accordion')).toBeTruthy();
    expect(screen.getByTestId('accordion-item-title').textContent).toBe(
      'title',
    );
    expect(screen.getByText('Chat')).toBeTruthy();
  });

  it('persists collapsed state when accordion is toggled closed', async () => {
    const user = userEvent.setup();
    render(<RelevantDocs docs={testDocs} />);
    await user.click(screen.getByTestId('accordion-toggle'));
    expect(mockSetStoredKeys).toHaveBeenCalledWith([]);
  });

  it('persists expanded state when accordion is toggled open', async () => {
    const user = userEvent.setup();
    render(<RelevantDocs docs={testDocs} />);
    await user.click(screen.getByTestId('accordion-toggle'));
    expect(mockSetStoredKeys).toHaveBeenCalledWith([]);
    mockSetStoredKeys.mockClear();
    await user.click(screen.getByTestId('accordion-toggle'));
    expect(mockSetStoredKeys).toHaveBeenCalledWith(['relevantDocsAccordion']);
  });
});
