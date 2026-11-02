// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, fireEvent } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { vi } from 'vitest';

import { FormPasswordInput } from '@amdenterpriseai/components';

// FormPasswordInput → PasswordInput composes the local Input/Button adapters
// (not the raw HeroUI primitives); stub those to isolate the form wiring.
vi.mock('../../../src/Input/InputPrimitive', () => ({
  Input: ({ type, endContent, startContent, ...props }: any) => (
    <div data-testid="input-wrapper">
      {startContent && <div data-testid="start-content">{startContent}</div>}
      <input data-testid="form-password-input" type={type} {...props} />
      {endContent && <div data-testid="end-content">{endContent}</div>}
    </div>
  ),
}));

vi.mock('../../../src/Buttons/Button', () => ({
  Button: ({ children, onPress, tabIndex, ...props }: any) => (
    <button
      data-testid="password-toggle-button"
      onClick={onPress}
      tabIndex={tabIndex}
      {...props}
    >
      {children}
    </button>
  ),
}));

vi.mock('@tabler/icons-react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tabler/icons-react')>();
  return {
    ...actual,
    IconEye: (props: any) => (
      <svg data-testid="icon-eye" aria-label="Show password" {...props}>
        <title>Show password</title>
      </svg>
    ),
    IconEyeOff: (props: any) => (
      <svg data-testid="icon-eye-off" aria-label="Hide password" {...props}>
        <title>Hide password</title>
      </svg>
    ),
  };
});

describe('FormPasswordInput', () => {
  const TestWrapper = ({ children }: any) => {
    const form = useForm({ defaultValues: { password: '' } });
    return children(form);
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom has no `CSS.supports`; simulate a browser that supports
    // `-webkit-text-security` so the `preventPasswordManagerPrompt` masking
    // path (exercised below) behaves as in Chrome/Safari.
    vi.stubGlobal('CSS', { supports: vi.fn().mockReturnValue(true) });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('Basic rendering', () => {
    it('renders password input with form', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );
      expect(screen.getByTestId('form-password-input')).toBeInTheDocument();
    });

    it('renders with password type by default', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );
      const input = screen.getByTestId('form-password-input');
      expect(input).toHaveAttribute('type', 'password');
    });

    it('renders toggle button', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );
      expect(screen.getByTestId('password-toggle-button')).toBeInTheDocument();
    });

    it('renders eye icon by default', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );
      expect(screen.getByTestId('icon-eye')).toBeInTheDocument();
      expect(screen.queryByTestId('icon-eye-off')).not.toBeInTheDocument();
    });

    it('registers field with provided name', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );
      const input = screen.getByTestId('form-password-input');
      expect(input).toHaveAttribute('name', 'password');
    });
  });

  describe('Password visibility toggle', () => {
    it('changes input type to text when toggle button clicked', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );

      const input = screen.getByTestId('form-password-input');
      const toggleButton = screen.getByTestId('password-toggle-button');

      expect(input).toHaveAttribute('type', 'password');
      fireEvent.click(toggleButton);
      expect(input).toHaveAttribute('type', 'text');
    });

    it('shows eye-off icon when password is revealed', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );

      const toggleButton = screen.getByTestId('password-toggle-button');
      fireEvent.click(toggleButton);

      expect(screen.getByTestId('icon-eye-off')).toBeInTheDocument();
      expect(screen.queryByTestId('icon-eye')).not.toBeInTheDocument();
    });

    it('toggles back to password type and eye icon', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );

      const input = screen.getByTestId('form-password-input');
      const toggleButton = screen.getByTestId('password-toggle-button');

      // Toggle twice
      fireEvent.click(toggleButton);
      fireEvent.click(toggleButton);

      expect(input).toHaveAttribute('type', 'password');
      expect(screen.getByTestId('icon-eye')).toBeInTheDocument();
      expect(screen.queryByTestId('icon-eye-off')).not.toBeInTheDocument();
    });

    it('input name remains registered after toggling', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );

      const input = screen.getByTestId('form-password-input');
      const toggleButton = screen.getByTestId('password-toggle-button');

      expect(input).toHaveAttribute('name', 'password');

      // Toggle visibility
      fireEvent.click(toggleButton);
      expect(input).toHaveAttribute('name', 'password');

      // Toggle back
      fireEvent.click(toggleButton);
      expect(input).toHaveAttribute('name', 'password');
    });
  });

  describe('Props support', () => {
    it('renders with label prop', () => {
      render(
        <TestWrapper>
          {(form: any) => (
            <FormPasswordInput form={form} name="password" label="Password" />
          )}
        </TestWrapper>,
      );
      expect(screen.getByTestId('form-password-input')).toBeInTheDocument();
    });

    it('renders with placeholder prop', () => {
      render(
        <TestWrapper>
          {(form: any) => (
            <FormPasswordInput
              form={form}
              name="password"
              placeholder="Enter your password"
            />
          )}
        </TestWrapper>,
      );
      expect(screen.getByTestId('form-password-input')).toBeInTheDocument();
    });

    it('renders with isRequired prop', () => {
      render(
        <TestWrapper>
          {(form: any) => (
            <FormPasswordInput form={form} name="password" isRequired />
          )}
        </TestWrapper>,
      );
      expect(screen.getByTestId('form-password-input')).toBeInTheDocument();
    });

    it('renders with isReadOnly prop', () => {
      render(
        <TestWrapper>
          {(form: any) => (
            <FormPasswordInput form={form} name="password" isReadOnly />
          )}
        </TestWrapper>,
      );
      expect(screen.getByTestId('form-password-input')).toBeInTheDocument();
    });
  });

  describe('Button behavior', () => {
    it('button has tabIndex -1', () => {
      render(
        <TestWrapper>
          {(form: any) => <FormPasswordInput form={form} name="password" />}
        </TestWrapper>,
      );

      const button = screen.getByTestId('password-toggle-button');
      expect(button).toHaveAttribute('tabIndex', '-1');
    });
  });

  describe('preventPasswordManagerPrompt', () => {
    it('renders type="text" instead of "password" when enabled', () => {
      render(
        <TestWrapper>
          {(form: any) => (
            <FormPasswordInput
              form={form}
              name="password"
              preventPasswordManagerPrompt
            />
          )}
        </TestWrapper>,
      );
      const input = screen.getByTestId('form-password-input');
      expect(input).toHaveAttribute('type', 'text');
    });

    it('keeps type="text" after toggling reveal', () => {
      render(
        <TestWrapper>
          {(form: any) => (
            <FormPasswordInput
              form={form}
              name="password"
              preventPasswordManagerPrompt
            />
          )}
        </TestWrapper>,
      );
      const input = screen.getByTestId('form-password-input');
      const toggleButton = screen.getByTestId('password-toggle-button');

      fireEvent.click(toggleButton);
      expect(input).toHaveAttribute('type', 'text');
    });
  });

  describe('Custom icon support', () => {
    it('renders custom icon in startContent when provided', () => {
      const CustomIcon = ({ className }: any) => (
        <svg
          data-testid="custom-icon"
          className={className}
          aria-label="Custom icon"
        >
          <title>Custom icon</title>
          Custom
        </svg>
      );

      render(
        <TestWrapper>
          {(form: any) => (
            <FormPasswordInput form={form} name="password" icon={CustomIcon} />
          )}
        </TestWrapper>,
      );

      expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
    });
  });

  describe('Multiple instances', () => {
    it('renders multiple password inputs with independent toggle states', () => {
      const TestComponent = () => {
        const form = useForm({
          defaultValues: { password: '', confirmPassword: '' },
        });

        return (
          <div>
            <FormPasswordInput form={form} name="password" />
            <FormPasswordInput form={form} name="confirmPassword" />
          </div>
        );
      };

      render(<TestComponent />);

      const inputs = screen.getAllByTestId('form-password-input');
      const toggleButtons = screen.getAllByTestId('password-toggle-button');

      expect(inputs).toHaveLength(2);
      expect(inputs[0]).toHaveAttribute('name', 'password');
      expect(inputs[1]).toHaveAttribute('name', 'confirmPassword');

      // Both start as password type
      expect(inputs[0]).toHaveAttribute('type', 'password');
      expect(inputs[1]).toHaveAttribute('type', 'password');

      // Toggle first input
      fireEvent.click(toggleButtons[0]);
      expect(inputs[0]).toHaveAttribute('type', 'text');
      expect(inputs[1]).toHaveAttribute('type', 'password'); // Second unchanged

      // Toggle second input
      fireEvent.click(toggleButtons[1]);
      expect(inputs[0]).toHaveAttribute('type', 'text');
      expect(inputs[1]).toHaveAttribute('type', 'text');
    });
  });
});
