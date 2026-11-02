// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useTranslation } from 'next-i18next';

import { displayTimestamp } from '@amdenterpriseai/utils/app';

import RefreshButton from '../Filters/RefreshButton';

interface Props {
  onRefresh: () => void;
  lastFetchedTimestamp?: Date;
  isRefreshing?: boolean;
  compact?: boolean;
  reversed?: boolean;
}

export const DataRefresher: React.FC<Props> = ({
  onRefresh,
  lastFetchedTimestamp,
  isRefreshing = false,
  compact = false,
  reversed = false,
}) => {
  const { t } = useTranslation('sharedComponents');

  return (
    <div
      className={`flex min-w-0 items-center ${reversed ? 'flex-row-reverse' : ''}`}
    >
      {lastFetchedTimestamp ? (
        <span className="min-w-0 text-sm text-muted dark:text-muted mx-4">
          {t(`data.lastUpdated`, {
            timestamp: displayTimestamp(lastFetchedTimestamp),
          })}
        </span>
      ) : null}

      <div className="shrink-0">
        <RefreshButton
          compact={compact}
          isLoading={isRefreshing}
          onPress={onRefresh}
        />
      </div>
    </div>
  );
};

export default DataRefresher;
