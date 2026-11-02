// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { renderHook } from '@testing-library/react';
import type { Mock } from 'vitest';

import { useDeletedWorkloadsOptIn } from '@/hooks/useDeletedWorkloadsOptIn';

const { routerQuery } = vi.hoisted(() => ({
  routerQuery: {} as Record<string, string | string[] | undefined>,
}));

vi.mock('next/router', () => ({
  useRouter: () => ({ query: routerQuery }),
}));

const STORAGE_KEY = 'showDeletedWorkloads';

const storePersistedOptIn = (value: boolean) => {
  (window.localStorage.getItem as Mock).mockImplementation((key: string) =>
    key === STORAGE_KEY ? JSON.stringify(value) : null,
  );
};

describe('useDeletedWorkloadsOptIn', () => {
  beforeEach(() => {
    delete routerQuery.deleted;
  });

  it('is off without the URL param and without a stored choice', () => {
    const { result } = renderHook(() => useDeletedWorkloadsOptIn());

    expect(result.current).toBe(false);
  });

  it('opts in and persists the choice when the URL asks for it', () => {
    routerQuery.deleted = '1';

    const { result } = renderHook(() => useDeletedWorkloadsOptIn());

    expect(result.current).toBe(true);
    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      STORAGE_KEY,
      JSON.stringify(true),
    );
  });

  it('stays opted in on a later visit without the URL param', () => {
    storePersistedOptIn(true);

    const { result } = renderHook(() => useDeletedWorkloadsOptIn());

    expect(result.current).toBe(true);
  });

  it('clears a persisted opt-in when the URL revokes it', () => {
    storePersistedOptIn(true);
    routerQuery.deleted = '0';

    const { result } = renderHook(() => useDeletedWorkloadsOptIn());

    expect(result.current).toBe(false);
    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      STORAGE_KEY,
      JSON.stringify(false),
    );
  });
});
