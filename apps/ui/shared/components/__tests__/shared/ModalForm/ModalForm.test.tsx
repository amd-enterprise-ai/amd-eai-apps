// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { FormFieldComponent } from '@amdenterpriseai/components';
import { ModalForm } from '@amdenterpriseai/components';

import '@testing-library/jest-dom';
import { ZodType, z } from 'zod';

type SampleFormData = {
  username: string;
};

const sampleFormSchema: ZodType<SampleFormData> = z.object({
  username: z.string().trim().nonempty('Username is required'),
});

describe('ModalForm', () => {
  it('renders the modal with form elements', () => {
    act(() => {
      render(
        <ModalForm<SampleFormData>
          isOpen={true}
          isActioning={false}
          validationSchema={sampleFormSchema}
          title="Add User"
          cancelText={'cancel'}
          confirmText={'confirm'}
          renderFields={(form) => (
            <>
              <FormFieldComponent<SampleFormData>
                formField={{
                  name: 'username',
                  label: 'Username',
                  placeholder: 'Enter username',
                  isRequired: true,
                }}
                errorMessage={form.formState.errors.username?.message}
                register={form.register}
                defaultValue={form.getValues('username')}
              />
              <span>Extra Content</span>
            </>
          )}
        />,
      );
    });

    expect(screen.getByText('Add User')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter username')).toBeInTheDocument();
    expect(screen.getByText('Extra Content')).toBeInTheDocument();
  });

  it('validates form fields and shows error messages', async () => {
    act(() => {
      render(
        <ModalForm<SampleFormData>
          isOpen={true}
          isActioning={false}
          validationSchema={sampleFormSchema}
          title="Add User"
          cancelText={'cancel'}
          confirmText={'modal.addUser.actions.confirm'}
          renderFields={(form) => (
            <>
              <FormFieldComponent<SampleFormData>
                formField={{
                  name: 'username',
                  label: 'Username',
                  placeholder: 'Enter username',
                  isRequired: true,
                }}
                errorMessage={form.formState.errors.username?.message}
                register={form.register}
                defaultValue={form.getValues('username')}
              />
              <span>Extra Content</span>
            </>
          )}
        />,
      );
    });

    const actionButton = screen.getByText('modal.addUser.actions.confirm');
    act(() => {
      fireEvent.click(actionButton);
    });
    // react-hook-form focuses the first invalid field after async validation
    // resolves; react-aria's focus management applies it on a later tick.
    await waitFor(() =>
      expect(screen.getByPlaceholderText('Enter username')).toHaveFocus(),
    );
  });

  it('calls onFormSuccess with form data when form is valid', async () => {
    const onFormSuccess = vi.fn();
    await act(() => {
      render(
        <ModalForm<SampleFormData>
          isOpen={true}
          isActioning={false}
          validationSchema={sampleFormSchema}
          title="Add User"
          cancelText={'cancel'}
          confirmText={'modal.addUser.actions.confirm'}
          onFormSuccess={onFormSuccess}
          renderFields={(form) => (
            <>
              <FormFieldComponent<SampleFormData>
                formField={{
                  name: 'username',
                  label: 'Username',
                  placeholder: 'Enter username',
                  isRequired: true,
                }}
                errorMessage={form.formState.errors.username?.message}
                register={form.register}
                defaultValue={form.getValues('username')}
              />
              <span>Extra Content</span>
            </>
          )}
        />,
      );
    });

    await act(() => {
      fireEvent.change(screen.getByPlaceholderText('Enter username'), {
        target: { value: 'testuser' },
      });

      fireEvent.click(
        screen.getByRole('button', { name: 'modal.addUser.actions.confirm' }),
      );
    });

    expect(onFormSuccess).toHaveBeenCalledWith({ username: 'testuser' });
  });
});
