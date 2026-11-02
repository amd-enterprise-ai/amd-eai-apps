# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Slugging of names that become storage path segments.

Object storage is keyed by the slug of a namespace name, and one bucket is shared by every
project, so the slug is a tenancy boundary: two names that slug alike address the same tree.
`slugify` is deliberately lossy — it folds runs of separators and maps every non-alphanumeric
character to a hyphen — so it cannot be made injective. `is_slug_stable` is how callers keep
the boundary sound instead: a name that already equals its own slug is a fixed point of
`slugify`, and over a set of such names distinct names necessarily have distinct slugs.
"""

import re


def slugify(name: str) -> str:
    """
    Convert a name to a path-safe slug.
    - Convert to lowercase
    - Replace spaces and special characters with hyphens
    - Remove consecutive hyphens
    - Remove leading and trailing hyphens
    - Preserve letters and digits from any language
    """
    # Convert to lowercase
    slug = name.lower()
    # Replace non-alphanumeric characters with hyphens, but preserve Unicode letters and digits
    slug = re.sub(r"[^\w\d]+", "-", slug, flags=re.UNICODE)
    # Remove consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Remove leading and trailing hyphens
    slug = slug.strip("-")

    return slug


def is_slug_stable(name: str) -> bool:
    """Whether the name survives slugging unchanged, and so cannot collide with another such name."""
    return slugify(name) == name
