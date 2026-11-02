// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Button } from '../Buttons/Button';
import { IconTrash } from '@tabler/icons-react';
import { ReactNode } from 'react';

interface Props {
  name: string;
  description: string;
  userIcon: ReactNode;
  onPress?: () => void;
  buttonLabel?: string | null;
}

export const UserListEntry: React.FC<Props> = ({
  name,
  description,
  userIcon,
  onPress,
  buttonLabel,
}) => {
  return (
    <div className="flex gap-4 items-center group relative py-2">
      <div>{userIcon}</div>
      <div className="grow overflow-hidden">
        <div
          data-testid="user-name"
          className="text-nowrap overflow-hidden text-ellipsis"
          title={name}
        >
          {name}
        </div>
        <div
          title={description}
          className="text-sm text-muted overflow-hidden text-nowrap text-ellipsis"
        >
          {description}
        </div>
      </div>
      {onPress ? (
        <div>
          <Button
            onPress={onPress}
            aria-label={buttonLabel || ''}
            isIconOnly
            variant="light"
            className="opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <IconTrash className="text-danger" size={18} />
          </Button>
        </div>
      ) : null}
    </div>
  );
};

export default UserListEntry;
