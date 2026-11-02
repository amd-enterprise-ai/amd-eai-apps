// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Wire shape for paginated list endpoints.
// `totalPages` is intentionally omitted; clients derive it as
// `Math.ceil(total / pageSize)` when needed.

export type PaginationMetadata = {
  page: number;
  pageSize: number;
  total: number;
};

export type PaginatedList<T> = {
  data: T[];
  pagination: PaginationMetadata;
};
