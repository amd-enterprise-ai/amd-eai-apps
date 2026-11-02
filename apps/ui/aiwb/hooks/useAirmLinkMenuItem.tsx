// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { DropdownItem, DropdownSection } from '@amdenterpriseai/components';
import { IconExternalLink } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';

import { useProject } from '@/contexts/ProjectContext';

export const useAirmLinkMenuItem = () => {
  const { isStandaloneMode, airmAppUrl } = useProject();
  const { t } = useTranslation('common');

  if (isStandaloneMode || !airmAppUrl) {
    return undefined;
  }

  return (
    <DropdownSection showDivider key="switch-app-section">
      <DropdownItem
        href={airmAppUrl}
        target="_blank"
        rel="noopener noreferrer"
        startContent={<IconExternalLink size={16} stroke={2} />}
        key="menu-switch-app"
      >
        {t('userMenu.airmAppLabel')}
      </DropdownItem>
    </DropdownSection>
  );
};
