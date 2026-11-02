# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Robot Framework library for multi-user API authentication.

Thin wrapper around the shared TeamMemberCredentials library so the
team-member derivation, token exchange, and provisioning detection
live in one place. This file only adapts the API to Robot's keyword
naming conventions.
"""

import importlib.util
import sys
from pathlib import Path

# TeamMemberCredentials lives in the shared testing libraries directory,
# which is on the Robot pythonpath but shadowed by the local libraries/
# package. Import it by absolute path the same way the rest of the file
# tree does for KubeconfigAuth.
_testing = Path(__file__).resolve().parents[5] / "testing"
_tmc_path = _testing / "libraries" / "TeamMemberCredentials.py"
if not _tmc_path.exists():
    raise ImportError(f"TeamMemberCredentials not found at expected path: {_tmc_path}")
_spec = importlib.util.spec_from_file_location("TeamMemberCredentials", _tmc_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Failed to create module spec from {_tmc_path}")
_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("TeamMemberCredentials", _module)
_spec.loader.exec_module(_module)
TeamMemberCredentials = _module.TeamMemberCredentials


class APICredentials:
    """Provides API tokens for the team-member user role.

    Admin tokens come from the standard KubeconfigAuth flow used by other
    test libraries; this class only exposes the team-member side, which
    requires a separate password-grant against Keycloak.
    """

    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self):
        self._creds = TeamMemberCredentials()

    def get_team_member_api_token(self) -> str:
        """Get a fresh API access token for the team-member user."""
        return self._creds.get_api_token()

    def get_team_member_username(self) -> str:
        """Get the team-member username (for logging and verification)."""
        return self._creds.get_username()

    def team_member_is_applicable(self) -> bool:
        """Return True if this run can authenticate as a team member at all."""
        return self._creds.is_applicable()

    def team_member_not_applicable_reason(self) -> str:
        """Human-readable reason this run cannot carry a team-member password."""
        return self._creds.not_applicable_reason()

    def team_member_is_provisioned(self) -> bool:
        """Return True if the team-member account exists on the target environment."""
        return self._creds.is_provisioned()

    def team_member_unavailable_reason(self) -> str:
        """Human-readable reason naming the account the suite cannot authenticate as."""
        return self._creds.not_provisioned_reason()
