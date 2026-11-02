// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconCheckupList } from '@tabler/icons-react';

import { useTranslation } from 'next-i18next';

import { UserListEntry } from '@amdenterpriseai/components';

interface Props {
  name: string;
  description: string;
  icon?: React.ComponentType<{ size?: number }>;
  onPress?: () => void;
}

export const ProjectAndRoleEntry: React.FC<Props> = ({
  name,
  description,
  onPress,
  icon = IconCheckupList,
}) => {
  const { t } = useTranslation('users');
  const IconComponent = icon;
  return (
    <UserListEntry
      name={name}
      description={description}
      userIcon={<IconComponent size={32} />}
      onPress={onPress}
      buttonLabel={t('detail.projectsAndRoles.projects.actions.delete.title')}
    />
  );
};

export default ProjectAndRoleEntry;
