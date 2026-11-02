# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import httpx
from loguru import logger

from .config import (
    OPENBAO_ADDR,
    OPENBAO_API_KEY_PATH_PREFIX,
    OPENBAO_KV_MOUNT,
    OPENBAO_TOKEN,
)


class OpenBaoClient:
    """Client for OpenBao KV v2 — the source of truth for API-key tokens.

    AIWB writes each key's token here on create; External Secrets Operator (read-only) then
    materializes the per-backend Kubernetes Secrets from it. AIWB never writes those Secrets.

    Expiry is native: ``delete_version_after`` on the KV metadata makes OpenBao drop the version
    after the requested TTL, and the next ESO sync removes it from the materialized Secret — so
    there is no bespoke reaper.
    """

    def __init__(
        self,
        addr: str,
        token: str,
        kv_mount: str = OPENBAO_KV_MOUNT,
        path_prefix: str = OPENBAO_API_KEY_PATH_PREFIX,
    ):
        """Initialize the OpenBao KV client for the API-key token path."""
        self.addr = addr.rstrip("/")
        self.kv_mount = kv_mount.strip("/")
        self.path_prefix = path_prefix.strip("/")
        self.client = httpx.AsyncClient(
            base_url=f"{self.addr}/v1",
            headers={"X-Vault-Token": token},
            timeout=30.0,
        )

    def _data_path(self, key_id: str) -> str:
        """KV v2 data endpoint for a key (read/write the token value)."""
        return f"/{self.kv_mount}/data/{self.path_prefix}/{key_id}"

    def _metadata_path(self, key_id: str) -> str:
        """KV v2 metadata endpoint for a key (delete_version_after / delete-all-versions)."""
        return f"/{self.kv_mount}/metadata/{self.path_prefix}/{key_id}"

    async def put_token(
        self,
        key_id: str,
        token: str,
        namespace: str,
        client_id: str,
        ttl: str | None = None,
    ) -> None:
        """Store an API-key token at ``<mount>/apikeys/<key_id>``.

        ``client_id`` (the ``x-api-key-id``) is stored for ESO's secretKey. ``ttl`` is a Vault-style
        duration (``None``/``""``/``"0"``/``"0s"`` = never) written as ``delete_version_after``
        *before* the value, so version 1 is covered by native expiry.
        """
        # Set native expiry first so version 1 is covered. Omit for "never".
        if ttl and ttl not in ("0", "0s"):
            resp = await self.client.post(self._metadata_path(key_id), json={"delete_version_after": ttl})
            resp.raise_for_status()

        resp = await self.client.post(
            self._data_path(key_id),
            json={"data": {"token": token, "namespace": namespace, "client_id": client_id}},
        )
        resp.raise_for_status()
        logger.info(f"Stored API-key token in OpenBao at '{self.path_prefix}/{key_id}'")

    async def get_token(self, key_id: str) -> str | None:
        """Read a stored token back, or ``None`` if it's absent/expired (404)."""
        resp = await self.client.get(self._data_path(key_id))
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("data", {}).get("data", {}).get("token")

    async def delete_token(self, key_id: str) -> None:
        """Delete a key's entry and all its versions. Idempotent (404 tolerated)."""
        resp = await self.client.delete(self._metadata_path(key_id))
        if resp.status_code == 404:
            logger.warning(f"OpenBao entry '{self.path_prefix}/{key_id}' not found, nothing to delete")
            return
        resp.raise_for_status()
        logger.info(f"Deleted API-key token from OpenBao at '{self.path_prefix}/{key_id}'")

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


def init_openbao_client() -> OpenBaoClient:
    """Build the OpenBao client from env config at startup; raises ``ValueError`` if OPENBAO_ADDR or OPENBAO_TOKEN is unset."""
    if not OPENBAO_ADDR or not OPENBAO_TOKEN:
        logger.error("OpenBao client not fully configured. Missing OPENBAO_ADDR or OPENBAO_TOKEN.")
        raise ValueError("OpenBao client not fully configured. Missing OPENBAO_ADDR or OPENBAO_TOKEN.")

    client = OpenBaoClient(addr=OPENBAO_ADDR, token=OPENBAO_TOKEN)
    logger.info(
        f"Connected to OpenBao at {OPENBAO_ADDR} (mount '{OPENBAO_KV_MOUNT}', prefix '{OPENBAO_API_KEY_PATH_PREFIX}')"
    )
    return client
