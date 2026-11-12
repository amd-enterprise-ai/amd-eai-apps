# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Per-request caller tokens the RBAC scenarios use to act as a team member without switching sessions."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from CallerAuthorization import CallerAuthorization  # noqa: E402


def test_no_token_leaves_the_request_on_the_session_identity() -> None:
    assert CallerAuthorization().request_options_for_token(None) == {}


def test_a_token_is_sent_as_the_request_authorization_header() -> None:
    options = CallerAuthorization().request_options_for_token("member-token")

    assert options == {"headers": {"Authorization": "Bearer member-token"}}


def test_bearer_headers_use_the_given_token_without_fetching_the_admin_token() -> None:
    with patch("CallerAuthorization.BuiltIn") as builtin:
        headers = CallerAuthorization().bearer_headers("member-token")

    assert headers == {"Authorization": "Bearer member-token"}
    builtin.assert_not_called()


def test_bearer_headers_fall_back_to_the_run_admin_token() -> None:
    with patch("CallerAuthorization.BuiltIn") as builtin:
        builtin.return_value.run_keyword.return_value = "admin-token"
        headers = CallerAuthorization().bearer_headers(None)

    assert headers == {"Authorization": "Bearer admin-token"}
    builtin.return_value.run_keyword.assert_called_once_with("Authorization Token")
