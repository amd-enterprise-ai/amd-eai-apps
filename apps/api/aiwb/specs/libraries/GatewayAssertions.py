# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Behavioral assertions about who answered an AI Gateway request.

Kept in Python rather than a Robot ``Evaluate`` one-liner because this is real logic and
because the judgment is worth regression-testing directly: the scenarios that use it are
GPU-cluster tests that cannot be run on demand, so a silent weakening here would only be
discovered on a cluster, rounds later.

The contract:

  - A request that the gateway refused and a request the model answered must be
    distinguishable from the response alone, with no routing headers to help.
  - Envoy's own ``x-envoy-upstream-service-time`` cannot carry that distinction. Envoy
    Gateway suppresses Envoy-generated headers unless ``ClientTrafficPolicy``
    ``enableEnvoyHeaders`` is set, which no chart here sets, so the header is absent even
    on a request the model served.
  - The discriminator is therefore the body, because every gateway-side refusal on this path
    is plain text or empty ("invalid json body" from the body-aware authorizer, "error
    unmarshaling request bodyMap" from the endpoint picker, an empty body from a routing
    failure), while a model server answers in the OpenAI envelope — a result object, or an
    ``error`` object carrying a message — including when refusing the request itself.
  - Status alone cannot carry it either. A chat model asked for an audio endpoint may answer
    404, or 200/400 carrying an OpenAI error object (vLLM returns its error model, which
    FastAPI serialises at 200). So the status set is deliberately wide and the body shape does
    the discriminating.
  - **The limit, stated plainly:** this is status ∧ shape, not proof of origin. A gateway that
    chose to emit an OpenAI-shaped ``error`` body at 200, 400 or 404 would pass. No component
    on this path does today — the two named regressions and a routing failure are all excluded
    by shape, and an ext_authz denial by status — but the assertion cannot rule it out in
    principle, and no header can restore that (see above). Read it as "nothing we know of
    inside the gateway produced this", not "the model certainly did".
"""

import json
from typing import Any

# Statuses a model server can produce for an endpoint it may or may not serve. Anything
# outside this set — notably 401/403 from an ext_authz denial and 5xx from the gateway —
# did not come from the model, whatever the body looks like.
_BACKEND_STATUSES = (200, 400, 404)


def _openai_envelope(payload: Any) -> bool:
    """True when ``payload`` is the OpenAI reply shape: a result, or an error with a message."""
    if not isinstance(payload, dict):
        return False
    if "text" in payload:
        return True
    error = payload.get("error")
    return isinstance(error, dict) and "message" in error


def response_should_come_from_the_model(response: Any) -> None:
    """Fail unless a model server, not the gateway, wrote this response.

    ``response`` is a ``requests`` response. Raises ``AssertionError`` naming what was seen,
    so a regression reports the component that produced the answer rather than only a status.
    """
    body = response.text
    status = response.status_code

    if status not in _BACKEND_STATUSES:
        raise AssertionError(
            f"Expected a response from the backend but got {status}, which no model produces for this path: {body}"
        )

    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        raise AssertionError(
            f"Response body is not JSON, so it did not come from the model — the request was "
            f"refused inside the gateway. Status {status}: {body}"
        ) from None

    if not _openai_envelope(payload):
        raise AssertionError(
            f"Response is not an OpenAI-shaped reply from the model (no result content, no error object): {body}"
        )
