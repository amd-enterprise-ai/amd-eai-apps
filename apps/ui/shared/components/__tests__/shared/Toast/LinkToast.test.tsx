// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';

// Mock Link adapter (LinkToast imports ../Link directly)
vi.mock('../../../src/Link', () => ({
  Link: ({ href, children }: any) => (
    <a href={href} data-testid="toast-link">
      {children}
    </a>
  ),
}));

import { LinkToast } from '../../../src/Toast/LinkToast';

// Mock useTranslation
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'actions.showDetails.title': 'Show Details',
      };
      return translations[key] || key;
    },
  }),
}));

describe('LinkToast', () => {
  const mockHref = '/workloads/workload-123';
  const mockMessage = 'Workload created successfully';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the message', () => {
    render(<LinkToast message={mockMessage} href={mockHref} />);

    expect(
      screen.getByText(/Workload created successfully/),
    ).toBeInTheDocument();
  });

  it('renders the "Show Details" link with correct translation', () => {
    render(<LinkToast message={mockMessage} href={mockHref} />);

    const link = screen.getByTestId('toast-link');
    expect(link).toBeInTheDocument();
    expect(link).toHaveTextContent('Show Details');
  });

  it('renders a custom link label', () => {
    render(
      <LinkToast
        message={mockMessage}
        href={mockHref}
        linkLabel="View models"
      />,
    );

    expect(screen.getByTestId('toast-link')).toHaveTextContent('View models');
  });

  it('renders the link with correct href', () => {
    render(<LinkToast message={mockMessage} href={mockHref} />);

    const link = screen.getByTestId('toast-link');
    expect(link).toHaveAttribute('href', mockHref);
  });

  it('handles different hrefs correctly', () => {
    const differentHref = '/models/model-456';
    render(<LinkToast message={mockMessage} href={differentHref} />);

    const link = screen.getByTestId('toast-link');
    expect(link).toHaveAttribute('href', differentHref);
  });

  it('handles different messages correctly', () => {
    const differentMessage = 'Training job submitted';
    render(<LinkToast message={differentMessage} href={mockHref} />);

    expect(screen.getByText(/Training job submitted/)).toBeInTheDocument();
  });

  it('renders with correct displayName', () => {
    expect(LinkToast.displayName).toBe('LinkToast');
  });
});
