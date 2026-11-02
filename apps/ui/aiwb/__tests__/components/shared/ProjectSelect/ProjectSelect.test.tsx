// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { ProjectSelect } from '@/components/shared/ProjectSelect/ProjectSelect';

// Mock next-i18next
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const mockSetActiveProject = vi.fn();

// Mock useProject context
vi.mock('@/contexts/ProjectContext', () => ({
  useProject: vi.fn(() => ({
    activeProject: 'project-1',
    projects: [
      { id: 'project-1', name: 'Project 1' },
      { id: 'project-2', name: 'Project 2' },
      { id: 'project-3', name: 'Project 3' },
    ],
    setActiveProject: mockSetActiveProject,
  })),
}));

vi.mock('@amdenterpriseai/components', () => ({
  Tooltip: ({ children, content, isDisabled }: any) => (
    <div
      data-testid="tooltip"
      data-content={content}
      data-disabled={isDisabled}
    >
      {children}
    </div>
  ),
  Select: ({
    children,
    onChange,
    selectedKeys,
    isDisabled,
    disallowEmptySelection: _disallowEmptySelection,
    startContent,
    className,
    ...props
  }: any) => (
    <div
      className={className}
      data-disabled={isDisabled}
      data-selected={selectedKeys?.[0] || ''}
      {...props}
    >
      <div data-testid="select-start-content">{startContent}</div>
      <select
        data-testid="select-element"
        onChange={onChange}
        disabled={isDisabled}
        value={selectedKeys?.[0] || ''}
      >
        {children}
      </select>
    </div>
  ),
  SelectItem: ({ children, ...props }: any) => (
    <option {...props} value={props['aria-label']}>
      {children}
    </option>
  ),
}));

// Mock the ProjectSelect icon while preserving icons imported by shared components.
vi.mock('@tabler/icons-react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tabler/icons-react')>();

  return {
    ...actual,
    IconCheckupList: (props: any) => (
      <div data-testid="checkup-list-icon" {...props}>
        Checkup List Icon
      </div>
    ),
  };
});

describe('ProjectSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component', () => {
    render(<ProjectSelect />);

    expect(screen.getByTestId('project-select')).toBeInTheDocument();
  });

  it('should render with tooltip enabled by default', () => {
    render(<ProjectSelect />);

    const tooltip = screen.getByTestId('tooltip');
    expect(tooltip).toBeInTheDocument();
    expect(tooltip).toHaveAttribute('data-disabled', 'false');
  });

  it('should render with tooltip disabled when showTooltip is false', () => {
    render(<ProjectSelect showTooltip={false} />);

    const tooltip = screen.getByTestId('tooltip');
    expect(tooltip).toHaveAttribute('data-disabled', 'true');
  });

  it('should render all projects', () => {
    render(<ProjectSelect />);

    expect(screen.getByText('Project 1')).toBeInTheDocument();
    expect(screen.getByText('Project 2')).toBeInTheDocument();
    expect(screen.getByText('Project 3')).toBeInTheDocument();
  });

  it('should display the active project', () => {
    render(<ProjectSelect />);

    const select = screen.getByTestId('project-select');
    expect(select).toHaveAttribute('data-selected', 'project-1');
  });

  it('should call setActiveProject when selection changes', () => {
    render(<ProjectSelect />);

    const selectElement = screen.getByTestId('select-element');
    fireEvent.change(selectElement, { target: { value: 'project-2' } });

    expect(mockSetActiveProject).toHaveBeenCalledWith('project-2');
  });

  it('should render with default icon', () => {
    render(<ProjectSelect />);

    expect(screen.getByTestId('checkup-list-icon')).toBeInTheDocument();
  });

  it('should render with custom startContent', () => {
    render(
      <ProjectSelect
        startContent={<div data-testid="custom-icon">Custom</div>}
      />,
    );

    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
    expect(screen.queryByTestId('checkup-list-icon')).not.toBeInTheDocument();
  });

  it('should be disabled when disabled prop is true', () => {
    render(<ProjectSelect disabled={true} />);

    const select = screen.getByTestId('project-select');
    expect(select).toHaveAttribute('data-disabled', 'true');
  });

  it('should use correct translation keys', () => {
    render(<ProjectSelect />);

    const select = screen.getByTestId('project-select');
    expect(select).toHaveAttribute('aria-label', 'projectSelection.label');
    expect(select).toHaveAttribute(
      'placeholder',
      'projectSelection.placeholder',
    );

    const tooltip = screen.getByTestId('tooltip');
    expect(tooltip).toHaveAttribute('data-content', 'projectSelection.tooltip');
  });
});
