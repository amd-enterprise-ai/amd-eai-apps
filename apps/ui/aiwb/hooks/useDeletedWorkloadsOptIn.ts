// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useEffect } from 'react';

import { useRouter } from 'next/router';

import { useLocalStorage } from '@amdenterpriseai/hooks';

const STORAGE_KEY = 'showDeletedWorkloads';

/**
 * Whether deleted workloads should be listed.
 *
 * Deliberately has no UI control: `?deleted=1` opts in and `?deleted=0` opts
 * back out, so support can hand out a single link rather than talk a user
 * through a hidden toggle. The choice is persisted because the URL param is
 * lost on the next navigation.
 */
export const useDeletedWorkloadsOptIn = (): boolean => {
  const router = useRouter();
  const [persisted, setPersisted] = useLocalStorage<boolean>(
    STORAGE_KEY,
    false,
  );
  const param = router.query.deleted;
  const fromUrl = Array.isArray(param) ? param[0] : param;
  useEffect(() => {
    if (fromUrl === '1' || fromUrl === '0') {
      setPersisted(fromUrl === '1');
    }
  }, [fromUrl, setPersisted]);
  if (fromUrl === '1' || fromUrl === '0') {
    return fromUrl === '1';
  }
  return persisted;
};
