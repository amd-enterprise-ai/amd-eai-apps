# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from loguru import logger


class ClusterAuthService:
    """
    Service layer for cluster-auth operations with in-memory storage.

    This service implements the same logic as MockClusterAuthClient but
    as a standalone service that can be accessed via HTTP.
    """

    def __init__(self):
        """Initialize the service with empty storage."""
        self._api_keys: dict[str, dict[str, Any]] = {}
        self._groups: dict[str, dict[str, Any]] = {}
        logger.info("Initialized mock cluster-auth service")

    def _generate_api_key(self) -> str:
        """Generate a realistic-looking API key."""
        random_part = secrets.token_hex(16)
        return f"amd_aim_api_key_{random_part}"

    def _generate_key_id(self) -> str:
        """Generate a key ID (accessor)."""
        return str(uuid4())

    def _parse_ttl(self, ttl: str) -> int:
        """
        Parse TTL string to seconds.

        Args:
            ttl: TTL string like "1h", "24h", "30d", or "0" for never expires

        Returns:
            Duration in seconds, or 0 for never expires
        """
        if not ttl:
            return 0  # Default to never expires

        ttl = ttl.strip().lower()

        # Special case: "0" means never expires
        if ttl == "0":
            return 0

        if ttl.endswith("h"):
            return int(ttl[:-1]) * 3600
        elif ttl.endswith("d"):
            return int(ttl[:-1]) * 86400
        elif ttl.endswith("m"):
            return int(ttl[:-1]) * 60
        elif ttl.endswith("s"):
            return int(ttl[:-1])
        else:
            # Assume seconds if no unit
            return int(ttl)

    async def create_api_key(
        self,
        ttl: str = "0",
        num_uses: int = 0,
        meta: dict | None = None,
        period: str = "",
        renewable: bool = True,
        explicit_max_ttl: str = "",
    ) -> dict:
        """
        Create an API key.

        Args:
            ttl: Time to live (e.g., "1h", "24h", "0" for never)
            num_uses: Number of uses allowed (0 = unlimited)
            meta: Metadata dictionary
            period: Renewal period
            renewable: Whether the key can be renewed
            explicit_max_ttl: Maximum TTL

        Returns:
            dict with api_key, key_id, and other metadata
        """
        api_key = self._generate_api_key()
        key_id = self._generate_key_id()
        entity_id = str(uuid4())

        ttl_seconds = self._parse_ttl(ttl)
        creation_time = datetime.now(UTC)

        # If ttl_seconds is 0, the key never expires
        if ttl_seconds == 0:
            expires_at = None  # Never expires
        else:
            expires_at = creation_time + timedelta(seconds=ttl_seconds)

        key_data = {
            "api_key": api_key,
            "key_id": key_id,
            "entity_id": entity_id,
            "ttl": ttl,
            "ttl_seconds": ttl_seconds,
            "num_uses": num_uses,
            "meta": meta or {},
            "period": period,
            "renewable": renewable,
            "explicit_max_ttl": explicit_max_ttl,
            "creation_time": creation_time,
            "expires_at": expires_at,
            "groups": [],
            "revoked": False,
        }

        self._api_keys[key_id] = key_data

        logger.debug(f"Created API key with key_id={key_id}")

        return {
            "api_key": api_key,
            "key_id": key_id,
            "entity_id": entity_id,
            "ttl": ttl,
            "lease_duration": ttl_seconds,
            "renewable": renewable,
            "num_uses": num_uses,
            "creation_time": creation_time.isoformat(),
            "expire_time": expires_at.isoformat() if expires_at else None,
        }

    async def revoke_api_key(self, key_id: str) -> None:
        """
        Revoke an API key.

        Args:
            key_id: The accessor/key_id of the API key to revoke

        Raises:
            KeyError: If the key_id doesn't exist
        """
        if key_id not in self._api_keys:
            raise KeyError(f"API key {key_id} not found")

        self._api_keys[key_id]["revoked"] = True
        logger.debug(f"Revoked API key with key_id={key_id}")

    async def renew_api_key(self, key_id: str, increment: str | None = None) -> dict:
        """
        Renew an API key's lease.

        Args:
            key_id: The accessor/key_id of the API key to renew
            increment: Optional TTL increment

        Returns:
            dict with lease_duration

        Raises:
            KeyError: If the key_id doesn't exist
            ValueError: If the key is not renewable or is revoked
        """
        if key_id not in self._api_keys:
            raise KeyError(f"API key {key_id} not found")

        key_data = self._api_keys[key_id]

        if key_data["revoked"]:
            raise ValueError("Cannot renew a revoked key")

        if not key_data["renewable"]:
            raise ValueError(f"API key {key_id} is not renewable")

        # Use increment if provided, otherwise use original TTL
        ttl_to_use = increment if increment else key_data["ttl"]
        ttl_seconds = self._parse_ttl(ttl_to_use)

        # Update expiration time
        if ttl_seconds == 0:
            new_expires_at = None  # Never expires
        else:
            new_expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        key_data["expires_at"] = new_expires_at
        key_data["ttl_seconds"] = ttl_seconds

        logger.debug(f"Renewed API key with key_id={key_id}, new ttl={ttl_seconds}s")

        return {
            "lease_duration": ttl_seconds,
            "renewable": key_data["renewable"],
            "expire_time": new_expires_at.isoformat() if new_expires_at else None,
        }

    async def lookup_api_key(self, key_id: str) -> dict:
        """
        Get API key metadata.

        Args:
            key_id: The accessor/key_id of the API key

        Returns:
            dict with key metadata including groups

        Raises:
            KeyError: If the key_id doesn't exist
        """
        if key_id not in self._api_keys:
            raise KeyError(f"API key {key_id} not found")

        key_data = self._api_keys[key_id]

        logger.debug(f"Looked up API key with key_id={key_id}")

        return {
            "key_id": key_id,
            "entity_id": key_data["entity_id"],
            "ttl": key_data["ttl"],  # Return original TTL string format like "1h", "24h", "0"
            "num_uses": key_data["num_uses"],
            "renewable": key_data["renewable"],
            "meta": key_data["meta"],
            "groups": key_data["groups"],
            "creation_time": key_data["creation_time"].isoformat(),
            "expire_time": key_data["expires_at"].isoformat() if key_data["expires_at"] else None,
            "revoked": key_data["revoked"],
        }

    async def create_group(self, name: str | None = None, group_id: str | None = None) -> dict:
        """
        Create a group.

        Args:
            name: Name of the group
            group_id: Optional group ID (generated if not provided)

        Returns:
            dict with id and name
        """
        if not group_id:
            group_id = f"group-{uuid4()}"

        # If name is not provided, default to group_id
        if name is None:
            name = group_id

        group_data: dict[str, str | list[str]] = {"id": group_id, "name": name, "members": []}

        self._groups[group_id] = group_data

        logger.debug(f"Created group with id={group_id}, name={name}")

        return {"id": group_id, "name": name}

    async def delete_group(self, group_id: str) -> None:
        """
        Delete a group.

        Args:
            group_id: The ID of the group to delete

        Raises:
            KeyError: If the group_id doesn't exist
        """
        if group_id not in self._groups:
            raise KeyError(f"Group {group_id} not found")

        # Remove this group from all API keys
        for key_data in self._api_keys.values():
            if group_id in key_data["groups"]:
                key_data["groups"].remove(group_id)

        del self._groups[group_id]
        logger.debug(f"Deleted group with id={group_id}")

    async def bind_api_key_to_group(self, key_id: str, group_id: str) -> dict:
        """
        Bind an API key to a group.

        Args:
            key_id: The accessor/key_id of the API key
            group_id: The ID of the group

        Returns:
            dict with updated groups list

        Raises:
            KeyError: If the key_id or group_id doesn't exist
        """
        if key_id not in self._api_keys:
            raise KeyError(f"API key {key_id} not found")
        if group_id not in self._groups:
            raise KeyError(f"Group {group_id} not found")

        key_data = self._api_keys[key_id]
        if group_id not in key_data["groups"]:
            key_data["groups"].append(group_id)

        group_data = self._groups[group_id]
        entity_id = key_data["entity_id"]
        if entity_id not in group_data["members"]:
            group_data["members"].append(entity_id)

        logger.debug(f"Bound API key {key_id} to group {group_id}")

        return {"groups": key_data["groups"]}

    async def unbind_api_key_from_group(self, key_id: str, group_id: str) -> dict:
        """
        Unbind an API key from a group.

        Args:
            key_id: The accessor/key_id of the API key
            group_id: The ID of the group

        Returns:
            dict with updated groups list

        Raises:
            KeyError: If the key_id or group_id doesn't exist
        """
        if key_id not in self._api_keys:
            raise KeyError(f"API key {key_id} not found")
        if group_id not in self._groups:
            raise KeyError(f"Group {group_id} not found")

        key_data = self._api_keys[key_id]
        if group_id in key_data["groups"]:
            key_data["groups"].remove(group_id)

        group_data = self._groups[group_id]
        entity_id = key_data["entity_id"]
        if entity_id in group_data["members"]:
            group_data["members"].remove(entity_id)

        logger.debug(f"Unbound API key {key_id} from group {group_id}")

        return {"groups": key_data["groups"]}
