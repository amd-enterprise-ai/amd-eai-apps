// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

type PaginatedList<T> = {
  data: T[];
  pagination: components['schemas']['PaginationMetadata'];
};

/**
 * Function that fetches a single page of a paginated list endpoint.
 *
 * Implementations issue exactly one HTTP request and return the raw
 * paginated envelope so {@link fetchAllPages} can read `pagination.total`.
 */
type PageFetcher<T> = (
  page: number,
  pageSize: number,
) => Promise<PaginatedList<T>>;

interface FetchAllPagesOptions {
  /**
   * Items per request. Backend caps at 100; using the max minimizes round-trips.
   */
  pageSize?: number;
  /**
   * Maximum number of concurrent requests after page 1. The loader fetches
   * page 1 alone (to learn `total`), then issues remaining pages in batches
   * of this size. Lower values are gentler on the backend; higher values
   * finish faster on large result sets.
   */
  concurrency?: number;
  /**
   * Milliseconds to wait between request kickoffs within a batch. Staggers
   * the burst so the backend doesn't see N concurrent connections land in
   * the same tick. Set to 0 to disable.
   */
  delayMs?: number;
}

const DEFAULT_PAGE_SIZE = 100;
const DEFAULT_CONCURRENCY = 4;
const DEFAULT_DELAY_MS = 50;

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Walks every page of a paginated list endpoint and returns the concatenated
 * items.
 *
 * The loader fetches page 1 first to learn `pagination.total`, computes
 * `totalPages = ceil(total / pageSize)`, then fetches pages 2..N in
 * bounded-concurrency batches with a small inter-request delay so the
 * backend isn't hit with N simultaneous connections.
 *
 * Prefer this utility over hand-rolled `Promise.all` walkers.
 *
 * @example
 * const all = await fetchAllPages<Dataset>((page, pageSize) =>
 *   listDatasetsPage(projectId, { page, pageSize, type }),
 * );
 *
 * @param fetchPage - Function that fetches one page; called multiple times.
 * @param options - Pagination + throttling controls; all optional.
 * @returns Concatenated `data` from every page.
 */
export const fetchAllPages = async <T>(
  fetchPage: PageFetcher<T>,
  options: FetchAllPagesOptions = {},
): Promise<T[]> => {
  // Clamp shared-utility defaults so a malformed caller (or a misbehaving
  // backend reporting pageSize=0) can't deadlock the walker. A pageSize of
  // 0 would make totalPages = Infinity; a concurrency of 0 would freeze
  // the batch loop.
  const pageSize = Math.max(1, options.pageSize ?? DEFAULT_PAGE_SIZE);
  const concurrency = Math.max(1, options.concurrency ?? DEFAULT_CONCURRENCY);
  const delayMs = options.delayMs ?? DEFAULT_DELAY_MS;

  const firstPage = await fetchPage(1, pageSize);
  const firstData = firstPage.data ?? [];
  const total = firstPage.pagination?.total ?? firstData.length;
  const effectivePageSize = Math.max(
    1,
    firstPage.pagination?.pageSize || pageSize,
  );
  const totalPages = Math.max(1, Math.ceil(total / effectivePageSize));

  if (totalPages <= 1) {
    return firstData;
  }

  const allData: T[] = [...firstData];
  for (
    let batchStart = 2;
    batchStart <= totalPages;
    batchStart += concurrency
  ) {
    const batchEnd = Math.min(batchStart + concurrency - 1, totalPages);
    // Build all batch promises synchronously and stagger fetch kickoffs via
    // an internal sleep on each IIFE. The kickoffs are spaced by delayMs so
    // the backend never sees N simultaneous connections from a single client.
    const batchPromises: Promise<PaginatedList<T>>[] = [];
    for (let p = batchStart; p <= batchEnd; p++) {
      const offsetMs = delayMs > 0 ? (p - batchStart) * delayMs : 0;
      batchPromises.push(
        (async () => {
          if (offsetMs > 0) await sleep(offsetMs);
          // Use effectivePageSize (server's reported pageSize) so subsequent
          // page requests stay aligned with the totalPages math above. If
          // the backend clamps an oversize request, we don't keep asking
          // for the wrong size.
          return fetchPage(p, effectivePageSize);
        })(),
      );
    }
    // Promise.allSettled (not Promise.all) so every batch promise resolves
    // or rejects before we move on — otherwise a fast-failing page would
    // cause the outer await to return while later IIFEs are still sleeping,
    // and their delayed fetch calls would leak into the next caller (or, in
    // tests, the next test's mocked fetch).
    const settled = await Promise.allSettled(batchPromises);
    const rejected = settled.find((s) => s.status === 'rejected');
    if (rejected && rejected.status === 'rejected') {
      throw rejected.reason;
    }
    for (const r of settled) {
      if (r.status === 'fulfilled') {
        allData.push(...(r.value.data ?? []));
      }
    }
  }

  return allData;
};
