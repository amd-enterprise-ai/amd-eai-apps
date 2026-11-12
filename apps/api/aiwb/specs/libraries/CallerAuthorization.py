# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Authorization for requests made with a caller's own token instead of the run's admin token."""

from typing import Any

from robot.libraries.BuiltIn import BuiltIn


class CallerAuthorization:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def request_options_for_token(self, access_token: str | None = None) -> dict[str, Any]:
        """Keyword arguments that make a Safe HTTP request authenticate with the given token.

        Without a token they are empty, so the request keeps the session's admin token. The token
        travels with the one request; the shared session is never switched to another identity.
        """
        if access_token is None:
            return {}
        return {"headers": self.bearer_headers(access_token)}

    def bearer_headers(self, access_token: str | None = None) -> dict[str, str]:
        """Authorization header for the given token, or for the run's admin token when none is given."""
        if access_token is None:
            access_token = BuiltIn().run_keyword("Authorization Token")
        return {"Authorization": f"Bearer {access_token}"}
