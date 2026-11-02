// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Story, StoryDefault } from '@ladle/react';

import { useSystemToast } from '@amdenterpriseai/hooks';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { ActionButton } from '../../src/Buttons/ActionButton';
import { SystemToastContainer } from '../../src/SystemToastContainer';

export default {
  title: 'Hooks/useSystemToast',
} satisfies StoryDefault;

const ToastDemo = () => {
  const { toast } = useSystemToast();

  return (
    <>
      <SystemToastContainer />
      <div className="flex flex-col items-start gap-4 p-6">
        <p className="text-sm text-muted">
          Click a button to trigger a toast. Toasts appear top-right and
          auto-dismiss after 5 seconds.
        </p>
        <div className="flex flex-wrap gap-2">
          <ActionButton
            primary
            onPress={() => toast.success('Operation completed')}
          >
            Success
          </ActionButton>
          <ActionButton
            tertiary
            onPress={() => toast.error('Something went wrong')}
          >
            Error
          </ActionButton>
          <ActionButton
            secondary
            onPress={() => toast.info('New update available')}
          >
            Info
          </ActionButton>
          <ActionButton
            tertiary
            onPress={() => toast.warning('Please check your settings')}
          >
            Warning
          </ActionButton>
          <ActionButton
            tertiary
            onPress={() =>
              toast('Custom toast message', {
                description: 'With optional description',
              })
            }
          >
            Default
          </ActionButton>
        </div>
      </div>
    </>
  );
};

// useSystemToast is a hook, not a renderable component, so the story drives a
// small demo that wires each toast variant to buttons. Reviewers can verify
// placement, styling, and auto-dismiss behavior in Ladle.
export const AllVariants: Story = () => <ToastDemo />;

export const WithAPIRequestError: Story = () => {
  const { toast } = useSystemToast();
  const apiError = new APIRequestError(
    'Failed to get resource: Error message from API',
    400,
  );

  return (
    <>
      <SystemToastContainer />
      <div className="flex flex-col items-start gap-4 p-6">
        <p className="text-sm text-muted">
          When an APIRequestError is passed to toast.error, the API error
          message is shown instead of the fallback content.
        </p>
        <ActionButton
          tertiary
          onPress={() =>
            toast.error('This fallback message is ignored', apiError)
          }
        >
          Show API error toast
        </ActionButton>
      </div>
    </>
  );
};
