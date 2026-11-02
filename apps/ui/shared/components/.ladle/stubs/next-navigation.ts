// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Stub for next/navigation in Ladle environment.

export const usePathname = () => '/';
export const useRouter = () => ({
  push: () => {},
  replace: () => {},
  back: () => {},
  forward: () => {},
  refresh: () => {},
  prefetch: () => {},
});
export const useSearchParams = () => new URLSearchParams();
export const useParams = () => ({});
