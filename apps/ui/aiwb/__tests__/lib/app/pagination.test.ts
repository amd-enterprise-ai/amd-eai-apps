// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fetchAllPages } from '@/lib/app/pagination';

type Item = { id: string };

const makePage = (
  items: Item[],
  page: number,
  pageSize: number,
  total: number,
) => ({
  data: items,
  pagination: { page, pageSize, total },
});

describe('fetchAllPages', () => {
  it('returns the first page directly when total fits in one page', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(
        makePage([{ id: 'a' }, { id: 'b' }, { id: 'c' }], 1, 100, 3),
      );

    const result = await fetchAllPages(fetchPage);

    expect(result).toEqual([{ id: 'a' }, { id: 'b' }, { id: 'c' }]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(fetchPage).toHaveBeenCalledWith(1, 100);
  });

  it('walks every page when total exceeds one page', async () => {
    // total=12, pageSize=5 → 3 pages
    const pageOne = Array.from({ length: 5 }, (_, i) => ({ id: `${i}` }));
    const pageTwo = Array.from({ length: 5 }, (_, i) => ({ id: `${5 + i}` }));
    const pageThree = Array.from({ length: 2 }, (_, i) => ({
      id: `${10 + i}`,
    }));
    const fetchPage = vi.fn().mockImplementation((page: number) => {
      const data = page === 1 ? pageOne : page === 2 ? pageTwo : pageThree;
      return Promise.resolve(makePage(data, page, 5, 12));
    });

    const result = await fetchAllPages<Item>(fetchPage, {
      pageSize: 5,
      delayMs: 0,
    });

    expect(result).toHaveLength(12);
    expect(result.map((r) => r.id)).toEqual([
      '0',
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
      '7',
      '8',
      '9',
      '10',
      '11',
    ]);
    expect(fetchPage).toHaveBeenCalledTimes(3);
  });

  it('respects the concurrency bound when issuing batches', async () => {
    // total=51, pageSize=10 → 6 pages, concurrency=2:
    //   page 1 fetched alone, then pages 2..6 in batches of 2.
    // Page 1 has already settled before any batch starts, so the in-flight
    // count is bounded purely by `concurrency`.
    let inFlight = 0;
    let peakInFlight = 0;
    const fetchPage = vi.fn().mockImplementation(async (page: number) => {
      inFlight += 1;
      peakInFlight = Math.max(peakInFlight, inFlight);
      await new Promise((r) => setTimeout(r, 5));
      inFlight -= 1;
      const data = Array.from({ length: 10 }, (_, i) => ({
        id: `${(page - 1) * 10 + i}`,
      }));
      return makePage(data, page, 10, 51);
    });

    await fetchAllPages(fetchPage, {
      pageSize: 10,
      concurrency: 2,
      delayMs: 0,
    });

    expect(fetchPage).toHaveBeenCalledTimes(6);
    // Peak concurrency must not exceed the configured bound.
    expect(peakInFlight).toBeLessThanOrEqual(2);
  });

  it('staggers in-flight requests when delayMs is positive', async () => {
    // total=4, pageSize=1, concurrency=3, delayMs=20.
    // Page 1 fetched alone; then pages 2, 3, 4 form one batch with the
    // kickoffs staggered: page 2 at t=0, page 3 at t=delayMs, page 4 at
    // t=2*delayMs.
    //
    // Uses fake timers so the assertion validates scheduled order rather
    // than measuring wall-clock — eliminates CI-flake risk from timer
    // scheduling jitter.
    vi.useFakeTimers();
    try {
      const fetchPage = vi
        .fn()
        .mockImplementation(async (page: number) =>
          makePage([{ id: `${page}` }], page, 1, 4),
        );

      const walkPromise = fetchAllPages(fetchPage, {
        pageSize: 1,
        concurrency: 3,
        delayMs: 20,
      });

      // Flush microtasks: page 1 resolves, then the batch loop kicks off
      // IIFEs 2, 3, 4. IIFE 2 has offset=0 so it calls fetchPage(2)
      // immediately; IIFE 3 and IIFE 4 are blocked on their sleep timers.
      await vi.advanceTimersByTimeAsync(0);
      expect(fetchPage).toHaveBeenCalledTimes(2);
      expect(fetchPage).toHaveBeenLastCalledWith(2, 1);

      // After delayMs, IIFE 3's sleep wakes and it calls fetchPage(3).
      await vi.advanceTimersByTimeAsync(20);
      expect(fetchPage).toHaveBeenCalledTimes(3);
      expect(fetchPage).toHaveBeenLastCalledWith(3, 1);

      // After another delayMs (2*delayMs from batch start), IIFE 4 wakes.
      await vi.advanceTimersByTimeAsync(20);
      expect(fetchPage).toHaveBeenCalledTimes(4);
      expect(fetchPage).toHaveBeenLastCalledWith(4, 1);

      // Let the outer Promise settle so vitest doesn't see a hanging promise.
      await walkPromise;
    } finally {
      vi.useRealTimers();
    }
  });

  it('handles an empty result set', async () => {
    const fetchPage = vi.fn().mockResolvedValueOnce(makePage([], 1, 100, 0));

    const result = await fetchAllPages(fetchPage);

    expect(result).toEqual([]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it('propagates errors from page fetches', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(makePage([{ id: 'a' }], 1, 1, 3))
      .mockRejectedValueOnce(new Error('page 2 failed'));

    await expect(
      fetchAllPages(fetchPage, { pageSize: 1, delayMs: 0 }),
    ).rejects.toThrow('page 2 failed');
  });
});
