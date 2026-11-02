// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * Builds the key a resolved profile is stored and looked up under.
 *
 * A profile name is unique only within a scope, so one name can belong to both
 * a project-scoped profile and a cluster-wide one serving different weights.
 * aim-engine chose between them when it deployed the service and said which in
 * `status.resolvedProfile`, so the key carries the scope and a namesake in the
 * other scope cannot be mistaken for it.
 *
 * `Cluster` and `Namespace` are the two scopes that identify a single object.
 * `Merged`, `Unknown` and an absent scope identify none, so they share a bare
 * key — matching the bare-name fallback the API resolves them with.
 */
export const profileKey = (
  scope: string | null | undefined,
  name: string,
): string =>
  scope === 'Cluster' || scope === 'Namespace'
    ? `${scope}:${name}`
    : `bare:${name}`;
