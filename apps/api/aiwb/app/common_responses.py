# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Reusable OpenAPI ``responses=`` fragments for FastAPI route decorators.

These dicts describe the documented failure modes raised by common access-check
dependencies and shared service-layer exception paths. The dependencies are
``ensure_access_to_project``, ``ensure_access_to_workbench_namespace`` and
``ensure_platform_administrator``. Compose with the spread operator:

    responses={
        **PROJECT_ACCESS_RESPONSES,
        404: {"description": "AIM deployment not found in the project."},
    }

If the underlying access-check dependency or exception handler ever changes
(e.g. an exception type is remapped to a different status code), update the
matching dict here rather than the individual route decorators.
"""

# Raised by ensure_access_to_project / ensure_access_to_workbench_namespace.
# 403: caller lacks the project group claim (combined mode), the project
#      does not match the standalone default (standalone mode), or the
#      namespace is not a workbench namespace.
# 404: project namespace does not exist in Kubernetes.
PROJECT_ACCESS_RESPONSES: dict[int | str, dict] = {
    403: {"description": "Caller does not have access to the project, or the project is not a workbench namespace."},
    404: {"description": "Project or namespace not found."},
}

# Raised by ensure_platform_administrator on routes that change cluster-wide state.
# Spreading it replaces the AUTH_RESPONSES 403, so it names the missing-email case too.
PLATFORM_ADMINISTRATOR_RESPONSES: dict[int | str, dict] = {
    403: {"description": "Caller does not have the Platform Administrator role, or the token has no email claim."},
}


EXTERNAL_SERVICE_RESPONSES: dict[int | str, dict] = {
    502: {
        "description": (
            "The cluster could not be reached, or refused the request for a reason it did not attribute to the request."
        )
    },
}

# Raised (as UnhealthyException) when a platform dependency is unfit for the operation through no
# fault of the caller. Distinct from the 4xx codes, which all mean "change the request and retry":
# no change to this request can make it succeed until the install is fixed.
UNHEALTHY_PLATFORM_RESPONSES: dict[int | str, dict] = {
    503: {
        "description": (
            "The install is not configured to serve this operation. Retrying the same request, or any variant "
            "of it, cannot help; an administrator has to correct the configuration first."
        )
    },
}

# Raised by ensure_user_logged_in (applied to all secured routes via api_secured_router).
# 401: Authorization header is missing, expired, or JWT validation fails.
# 403: JWT is valid but missing the email claim (misconfigured token / wrong audience).
#      Endpoints that also spread PROJECT_ACCESS_RESPONSES or
#      PLATFORM_ADMINISTRATOR_RESPONSES override this 403 description with their own wording.
AUTH_RESPONSES: dict[int | str, dict] = {
    401: {"description": "Missing or invalid authentication token."},
    403: {"description": "Token is valid but missing required claims (e.g. email)."},
}
