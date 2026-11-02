# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Secret response lookups for Robot Framework E2E keywords."""

from typing import Any

from robot.api.deco import keyword


@keyword("Find Secret By Name")
def find_secret_by_name(response: Any, secret_name: str) -> dict[str, Any] | None:
    """Return the matching secret item from either supported API response shape."""
    body = response.json()
    if not isinstance(body, dict):
        return None
    items = body.get("data")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get("secret") or {}).get("name") or item.get("name")
        if name == secret_name:
            return item
    return None
