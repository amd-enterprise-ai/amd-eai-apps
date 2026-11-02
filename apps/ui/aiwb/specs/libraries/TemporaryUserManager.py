# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Robot Framework library for creating and cleaning up temporary AIRM users in E2E tests.

Handles all logic for multi-user testing: credential generation, AIRM API calls,
and suite-scoped tracking for teardown cleanup.
"""

import importlib.util
import os
import sys
import uuid
from pathlib import Path

import requests
from loguru import logger

# KubeconfigAuth lives in the shared testing libraries — import directly,
# same pattern as UICredentials.py.
_testing = Path(__file__).resolve().parents[5] / "testing"
_kca_path = _testing / "libraries" / "KubeconfigAuth.py"
if not _kca_path.exists():
    raise ImportError(f"KubeconfigAuth not found at expected path: {_kca_path}")
_spec = importlib.util.spec_from_file_location("KubeconfigAuth", _kca_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Failed to create module spec from {_kca_path}")
_module = importlib.util.module_from_spec(_spec)
sys.modules["KubeconfigAuth"] = _module
_spec.loader.exec_module(_module)
KubeconfigAuth = _module.KubeconfigAuth


class TemporaryUserManager:
    """Creates and cleans up temporary AIRM users for multi-user E2E tests."""

    ROBOT_LIBRARY_SCOPE = "SUITE"

    def __init__(self):
        self._auth = KubeconfigAuth()
        self._created_user_ids: list[str] = []
        # Match the shared VERIFY_SSL convention.
        # Dev/test clusters use self-signed certs, so default to disabled.
        self._verify_ssl = os.environ.get("VERIFY_SSL", "false").lower() in ("true", "1", "yes")

    def _auth_headers(self) -> dict[str, str]:
        token = self._auth.get_authorization_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def create_temporary_airm_user(
        self, users_endpoint: str, project_id: str | None = None
    ) -> tuple[str, str, str]:
        """Create a temporary test user via the AIRM API.

        Generates unique credentials, registers the user in both Keycloak and the AIRM
        database, and optionally assigns them to the given project. Tracks the user ID
        for cleanup.

        Args:
            users_endpoint: Full URL of the AIRM /v1/users endpoint.
            project_id: Optional UUID of the project to assign the user to. When omitted,
                the user is registered without project membership — useful for tests that
                need to verify authorization rejections.

        Returns:
            Tuple of (email, password, user_id).
        """
        suffix = uuid.uuid4().hex[:8]
        email = f"temp-user-{suffix}@test.local"
        password = f"TempPassword123!{suffix}"

        project_ids = [project_id] if project_id else []
        user_data = {
            "email": email,
            "roles": [],
            "projectIds": project_ids,
            "temporaryPassword": password,
        }

        response = requests.post(
            users_endpoint,
            json=user_data,
            headers=self._auth_headers(),
            timeout=30,
            verify=self._verify_ssl,
        )
        response.raise_for_status()

        user_id = response.json()["id"]
        self._created_user_ids.append(user_id)
        logger.info(f"Created temporary AIRM user: {email} (id: {user_id})")
        return email, password, user_id

    def clean_up_temporary_airm_users(self, users_endpoint: str) -> None:
        """Delete all temporary users created during this suite.

        Tolerates individual failures (e.g., user already deleted by a prior cleanup).
        Successfully deleted users are removed from tracking; failed deletions remain
        for retry or diagnostic purposes.
        """
        failed_deletions = []
        for user_id in list(self._created_user_ids):
            try:
                response = requests.delete(
                    f"{users_endpoint}/{user_id}",
                    headers=self._auth_headers(),
                    timeout=30,
                    verify=self._verify_ssl,
                )
                if response.ok:
                    logger.info(f"Deleted temporary user {user_id}")
                    self._created_user_ids.remove(user_id)
                else:
                    logger.warning(f"Failed to delete temporary user {user_id}: HTTP {response.status_code}")
                    failed_deletions.append(user_id)
            except requests.RequestException as e:
                logger.warning(f"Error deleting temporary user {user_id}: {e}")
                failed_deletions.append(user_id)

        if failed_deletions:
            logger.error(
                f"Failed to clean up {len(failed_deletions)} temporary users: {failed_deletions}. "
                f"These may need manual cleanup or can be re-attempted."
            )
