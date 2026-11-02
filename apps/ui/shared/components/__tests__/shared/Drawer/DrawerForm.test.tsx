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

import { DrawerForm } from '@amdenterpriseai/components';
import { FormFieldComponent } from '@amdenterpriseai/components';

import '@testing-library/jest-dom';
import { ZodType, z } from 'zod';

type SampleFormData = {
  username: string;
};

const sampleFormSchema: ZodType<SampleFormData> = z.object({
  username: z.string().trim().nonempty('Username is required'),
});

describe('DrawerForm', () => {
  it('renders the drawer with form elements', () => {
    act(() => {
      render(
        <DrawerForm<SampleFormData>
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
        <DrawerForm<SampleFormData>
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
        <DrawerForm<SampleFormData>
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

    expect(onFormSuccess).toHaveBeenCalledWith(
      { username: 'testuser' },
      { viaSecondaryConfirm: false },
    );
  });

  it('reports which of two confirms submitted the form', async () => {
    const onFormSuccess = vi.fn();
    const renderForm = () =>
      render(
        <DrawerForm<SampleFormData>
          isOpen={true}
          validationSchema={sampleFormSchema}
          title="Add User"
          cancelText={'cancel'}
          confirmText={'save'}
          secondaryConfirm={{ label: 'save and continue' }}
          onFormSuccess={onFormSuccess}
          renderFields={(form) => (
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
          )}
        />,
      );
    await act(() => renderForm());

    await act(() => {
      fireEvent.change(screen.getByPlaceholderText('Enter username'), {
        target: { value: 'testuser' },
      });
      fireEvent.click(
        screen.getByRole('button', { name: 'save and continue' }),
      );
    });

    expect(onFormSuccess).toHaveBeenCalledWith(
      { username: 'testuser' },
      { viaSecondaryConfirm: true },
    );
  });

  it('forgets a second confirm that failed validation', async () => {
    // Pressing Enter submits the form itself, with nothing to say which button
    // was meant, so an abandoned second confirm must not still be standing.
    const onFormSuccess = vi.fn();
    await act(() => {
      render(
        <DrawerForm<SampleFormData>
          isOpen={true}
          validationSchema={sampleFormSchema}
          title="Add User"
          cancelText={'cancel'}
          confirmText={'save'}
          secondaryConfirm={{ label: 'save and continue' }}
          onFormSuccess={onFormSuccess}
          renderFields={(form) => (
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
          )}
        />,
      );
    });
    const field = screen.getByPlaceholderText('Enter username');

    await act(() => {
      fireEvent.click(
        screen.getByRole('button', { name: 'save and continue' }),
      );
    });
    expect(onFormSuccess).not.toHaveBeenCalled();

    await act(() => {
      fireEvent.change(field, { target: { value: 'testuser' } });
      fireEvent.submit(field.closest('form')!);
    });

    expect(onFormSuccess).toHaveBeenCalledWith(
      { username: 'testuser' },
      { viaSecondaryConfirm: false },
    );
  });
});
