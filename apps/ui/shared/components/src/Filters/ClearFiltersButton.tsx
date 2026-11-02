// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ActionButton } from '../Buttons';
import { useTranslation } from 'next-i18next';

interface ClearFiltersButtonProps {
  isDisabled: boolean;
  onPress: () => void;
}

const ClearFiltersButton: React.FC<ClearFiltersButtonProps> = ({
  isDisabled,
  onPress,
}) => {
  const { t } = useTranslation('sharedComponents');

  return (
    <ActionButton
      tertiary
      aria-label={t('actions.clearFilters.title')}
      type="button"
      role="button"
      isDisabled={isDisabled}
      onPress={onPress}
      data-testid="clear-filters-button"
      className="min-w-[fit-content] ml-auto"
    >
      {t('actions.clearFilters.title')}
    </ActionButton>
  );
};

export default ClearFiltersButton;
