# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the backend-origin assertion used by the multipart AI Gateway scenario.

The scenario it guards runs only on a GPU cluster, so this is the only place the judgment
can be exercised on demand. Each case below is a response the gateway or a model really
produces on the header-less inference path.
"""

import pytest
import requests
from GatewayAssertions import response_should_come_from_the_model


def _response(status: int, body: str) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = body.encode()
    return response


def test_a_chat_model_refusing_an_audio_path_is_a_model_answer():
    """vLLM answers an unsupported endpoint with its error model, which FastAPI serialises at 200."""
    response_should_come_from_the_model(
        _response(
            200,
            '{"error":{"message":"The model does not support Transcriptions API",'
            '"type":"BadRequestError","param":null,"code":400}}',
        )
    )


def test_a_transcription_result_is_a_model_answer():
    response_should_come_from_the_model(_response(200, '{"text":"hello"}'))


def test_a_model_error_at_400_is_a_model_answer():
    response_should_come_from_the_model(_response(400, '{"error":{"message":"bad audio"}}'))


def test_a_model_404_carrying_an_error_object_is_a_model_answer():
    response_should_come_from_the_model(_response(404, '{"error":{"message":"not found"}}'))


def test_an_empty_routing_failure_is_rejected():
    """A request that matched no route returns an empty body — nothing answered it."""
    with pytest.raises(AssertionError, match="not JSON"):
        response_should_come_from_the_model(_response(404, ""))


def test_the_body_aware_authorizer_refusal_is_rejected():
    with pytest.raises(AssertionError, match="not JSON"):
        response_should_come_from_the_model(_response(400, "invalid json body"))


def test_the_endpoint_picker_refusal_is_rejected():
    with pytest.raises(AssertionError, match="not JSON"):
        response_should_come_from_the_model(
            _response(400, "inference error: BadRequest - error unmarshaling request bodyMap")
        )


@pytest.mark.parametrize("status", [401, 403])
def test_an_ext_authz_denial_is_rejected_despite_a_json_body(status):
    """The denial is OpenAI-shaped, so only the status separates it from a model answer.

    Both statuses, because the module excludes both and a tuple widened to admit either would
    otherwise pass: an ext_authz denial answers 401 for a missing or unparseable key and 403 for
    a key that parsed but is not authorized, and this guard has to refuse both as model answers.
    """
    with pytest.raises(AssertionError, match="no model produces"):
        response_should_come_from_the_model(_response(status, '{"error":{"message":"denied"}}'))


def test_a_gateway_5xx_is_rejected_despite_a_json_body():
    with pytest.raises(AssertionError, match="no model produces"):
        response_should_come_from_the_model(_response(503, '{"error":{"message":"no healthy upstream"}}'))


def test_a_json_body_that_is_not_an_openai_reply_is_rejected():
    with pytest.raises(AssertionError, match="not an OpenAI-shaped reply"):
        response_should_come_from_the_model(_response(200, '{"ok":true}'))


def test_an_error_field_that_is_not_an_object_is_rejected():
    """A bare string `error` is not the OpenAI envelope and must not be read as one."""
    with pytest.raises(AssertionError, match="not an OpenAI-shaped reply"):
        response_should_come_from_the_model(_response(200, '{"error":"boom"}'))


def test_a_json_list_is_rejected():
    with pytest.raises(AssertionError, match="not an OpenAI-shaped reply"):
        response_should_come_from_the_model(_response(200, "[]"))


def test_an_error_object_without_a_message_is_rejected():
    """An `error` with no message is not the OpenAI envelope.

    Pins the second half of the shape check: a bare `{"error": {}}` carries no statement of what
    went wrong, and accepting it would let any JSON object with an `error` key read as a model
    answer.
    """
    with pytest.raises(AssertionError, match="not an OpenAI-shaped reply"):
        response_should_come_from_the_model(_response(400, '{"error":{"code":400}}'))


def test_the_gateway_catch_all_is_rejected():
    """The catch-all answers in plain text, so the shape check refuses it on its own.

    The scenario also matches the catch-all's wording explicitly, to name the component in the
    failure message — but that wording belongs to Envoy AI Gateway and can change, so the origin
    judgement must not depend on it.
    """
    with pytest.raises(AssertionError, match="not JSON"):
        response_should_come_from_the_model(_response(404, "No matching route found"))
