# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Robot Framework library that exposes OIDC credentials for browser-based login.

Admin credentials come from KubeconfigAuth (kubeconfig OIDC config).
Team-member credentials and provisioning detection delegate to the shared
TeamMemberCredentials library so the same logic powers both API and UI
RBAC suites.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_from_testing(name: str) -> ModuleType:
    """Import a module from the shared testing/libraries by absolute path.

    The shared libraries are on Robot's pythonpath but are shadowed by the
    local libraries/ package, so a normal import would resolve incorrectly.
    """
    testing_lib = Path(__file__).resolve().parents[5] / "testing" / "libraries"
    module_path = testing_lib / f"{name}.py"
    if not module_path.exists():
        raise ImportError(f"{name} not found at expected path: {module_path}")
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create module spec from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


KubeconfigAuth = _load_from_testing("KubeconfigAuth").KubeconfigAuth
TeamMemberCredentials = _load_from_testing("TeamMemberCredentials").TeamMemberCredentials


class UICredentials:
    """Provides UI login credentials for multiple user roles.

    Admin credentials are extracted from kubeconfig OIDC configuration.
    Team-member credentials follow the shared convention encapsulated in
    TeamMemberCredentials (env vars or derived from admin).
    """

    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self):
        self._auth = KubeconfigAuth()
        self._team_member = TeamMemberCredentials()

    def _get_admin_credentials(self) -> dict[str, str]:
        """Get admin credentials from environment or kubeconfig.

        Uses KubeconfigAuth private methods directly because it has no public
        API for raw credential extraction (its public methods return RF variables).
        Coupled to KubeconfigAuth internals -- update if that class is refactored.
        """
        creds = self._auth._get_credentials_from_env()
        if not creds:
            creds = self._auth._get_credentials_from_kubeconfig()
        return creds

    def get_ui_username(self) -> str:
        """Get the admin OIDC username for browser login."""
        username = self._get_admin_credentials().get("username")
        if not username:
            raise ValueError("No username found in credentials")
        return username

    def get_ui_password(self) -> str:
        """Get the admin OIDC password for browser login."""
        password = self._get_admin_credentials().get("password")
        if not password:
            raise ValueError("No password found in credentials")
        return password

    def get_team_member_username(self) -> str:
        """Get the team-member username for browser login."""
        return self._team_member.get_username()

    def get_team_member_password(self) -> str:
        """Get the team-member password for browser login."""
        return self._team_member.get_password()

    def team_member_is_applicable(self) -> bool:
        """Return True if this run can authenticate as a team member at all."""
        return self._team_member.is_applicable()

    def team_member_not_applicable_reason(self) -> str:
        """Human-readable reason this run cannot carry a team-member password."""
        return self._team_member.not_applicable_reason()

    def team_member_is_provisioned(self) -> bool:
        """Return True if the team-member account exists on the target environment."""
        return self._team_member.is_provisioned()

    def team_member_unavailable_reason(self) -> str:
        """Human-readable reason naming the account the suite cannot authenticate as."""
        return self._team_member.not_provisioned_reason()
