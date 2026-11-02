# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the custom-model gateway helpers — AIMProfile wait & patch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes_asyncio.client import ApiException, CustomObjectsApi

from api_common.exceptions import ExternalServiceError, PreconditionNotMetException
from app.aims.constants import (
    AIM_API_GROUP,
    AIM_API_VERSION,
    AIM_MODEL_LABEL,
    AIM_PROFILE_PLURAL,
    AIM_PROFILE_ROLE_BASE,
    AIM_PROFILE_ROLE_LABEL,
    AIM_PROFILE_SOURCE_MODEL_LABEL,
)
from app.custom_models.constants import (
    AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION,
)
from app.custom_models.gateway import (
    find_aim_profile_for_model,
    list_aim_profiles,
    list_base_role_profiles,
    patch_aim_profile,
    wait_for_aim_profile,
)
from app.dispatch.kube_client import KubernetesClient


def _profile_resource_dict(
    name: str = "llama-3-8b-default",
    namespace: str = "kw-test-project",
    model_name: str = "llama-3-8b",
    annotations: dict[str, str] | None = None,
) -> dict:
    return {
        "apiVersion": f"{AIM_API_GROUP}/{AIM_API_VERSION}",
        "kind": "AIMProfile",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {AIM_MODEL_LABEL: model_name},
            "annotations": annotations or {},
        },
        "spec": {"aimId": model_name, "image": "amdenterpriseai/aim-base:0.11"},
        "status": {},
    }


@pytest.fixture
def kube_client() -> MagicMock:
    """Mock ``KubernetesClient`` with the ``custom_objects`` surface the helpers use.

    Both layers carry ``spec=`` so a typo in either a ``KubernetesClient``
    attribute or a ``CustomObjectsApi`` method name fails the test
    immediately rather than silently auto-creating a mock attribute.
    """
    mock = MagicMock(spec=KubernetesClient)
    mock.custom_objects = MagicMock(spec=CustomObjectsApi)
    mock.custom_objects.list_namespaced_custom_object = AsyncMock(return_value={"items": []})
    mock.custom_objects.patch_namespaced_custom_object = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_find_aim_profile_for_model_uses_label_selector(
    kube_client: MagicMock,
) -> None:
    """Lookup must filter by ``aim.eai.amd.com/model.name`` rather than
    guessing the profile name; aim-engine owns the profile naming convention."""
    profile_dict = _profile_resource_dict()
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [profile_dict]}

    result = await find_aim_profile_for_model(kube_client, "kw-test-project", "llama-3-8b")

    assert result is not None
    assert result.metadata.name == "llama-3-8b-default"
    kube_client.custom_objects.list_namespaced_custom_object.assert_awaited_once_with(
        group=AIM_API_GROUP,
        version=AIM_API_VERSION,
        namespace="kw-test-project",
        plural=AIM_PROFILE_PLURAL,
        label_selector=f"{AIM_MODEL_LABEL}=llama-3-8b",
    )


@pytest.mark.asyncio
async def test_find_aim_profile_for_model_returns_none_when_not_present(
    kube_client: MagicMock,
) -> None:
    """An empty list is the steady-state signal that aim-engine has not yet
    reconciled the AIMModel — the caller's poll loop relies on this."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    result = await find_aim_profile_for_model(kube_client, "ns", "model")

    assert result is None


@pytest.mark.asyncio
async def test_find_aim_profile_for_model_handles_404_as_missing(
    kube_client: MagicMock,
) -> None:
    """A 404 from the API server (e.g. while the CRD is initialising) means
    the profile can't be present yet; treat it like an empty list rather
    than letting the exception abort the poll loop."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(status=404)

    result = await find_aim_profile_for_model(kube_client, "ns", "model")

    assert result is None


@pytest.mark.asyncio
async def test_find_aim_profile_for_model_propagates_non_404_errors(
    kube_client: MagicMock,
) -> None:
    """A 500 from the API server is a real failure; we surface it so the
    caller can react rather than treating it like ``not found yet``."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(status=500)

    with pytest.raises(ApiException):
        await find_aim_profile_for_model(kube_client, "ns", "model")


@pytest.mark.asyncio
async def test_list_aim_profiles_filters_by_model_label_when_provided(
    kube_client: MagicMock,
) -> None:
    """Per-model lookup uses the model label selector aim-engine stamps on derived profiles."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [_profile_resource_dict()]}

    profiles = await list_aim_profiles(kube_client, "ns", model_name="llama-3-8b")

    assert len(profiles) == 1
    kube_client.custom_objects.list_namespaced_custom_object.assert_awaited_once_with(
        group=AIM_API_GROUP,
        version=AIM_API_VERSION,
        namespace="ns",
        plural=AIM_PROFILE_PLURAL,
        label_selector=f"{AIM_MODEL_LABEL}=llama-3-8b",
    )


@pytest.mark.asyncio
async def test_list_aim_profiles_omits_label_selector_for_bulk_listing(
    kube_client: MagicMock,
) -> None:
    """The list endpoint for the project model overview fetches all profiles
    in one call to avoid N+1 lookups; that means no label selector."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    await list_aim_profiles(kube_client, "ns")

    kube_client.custom_objects.list_namespaced_custom_object.assert_awaited_once_with(
        group=AIM_API_GROUP,
        version=AIM_API_VERSION,
        namespace="ns",
        plural=AIM_PROFILE_PLURAL,
        label_selector=None,
    )


@pytest.mark.asyncio
async def test_list_aim_profiles_returns_empty_on_404(
    kube_client: MagicMock,
) -> None:
    """In a cluster where the v1alpha2 CRD isn't installed the API returns
    404; degrade to an empty list so the rest of the onboard view still
    renders rather than 500ing the project models page."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(status=404)

    profiles = await list_aim_profiles(kube_client, "ns")

    assert profiles == []


@pytest.mark.asyncio
async def test_list_aim_profiles_strict_maps_api_failure_to_external_service_error(
    kube_client: MagicMock,
) -> None:
    """Read endpoints request strict behavior so upstream failures become 502s."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(
        status=500, reason="server error"
    )

    with pytest.raises(ExternalServiceError, match="Failed to list AIMProfiles"):
        await list_aim_profiles(kube_client, "ns", model_name="model", strict=True)


@pytest.mark.asyncio
async def test_list_aim_profiles_strict_maps_parse_failure_to_external_service_error(
    kube_client: MagicMock,
) -> None:
    """A malformed upstream item must not silently produce a partial 200 response."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [{"metadata": {}}]}

    with pytest.raises(ExternalServiceError, match="Failed to parse AIMProfile"):
        await list_aim_profiles(kube_client, "ns", model_name="model", strict=True)


@pytest.mark.asyncio
async def test_list_base_role_profiles_strict_maps_api_failure_to_external_service_error(
    kube_client: MagicMock,
) -> None:
    """The create path requests strict so a K8s failure becomes a 502, not an empty list (then a misleading 400)."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(
        status=500, reason="server error"
    )

    with pytest.raises(ExternalServiceError, match="Failed to list base-role AIMProfiles"):
        await list_base_role_profiles(kube_client, "ns", strict=True)


@pytest.mark.asyncio
async def test_list_base_role_profiles_non_strict_swallows_failure(
    kube_client: MagicMock,
) -> None:
    """The onboard wizard leaves strict off, so an upstream failure degrades to static defaults."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(
        status=500, reason="server error"
    )

    assert await list_base_role_profiles(kube_client, "ns") == []


@pytest.mark.asyncio
async def test_list_base_role_profiles_scopes_to_one_producing_model(
    kube_client: MagicMock,
) -> None:
    """A namespace holds one base model per image family, so the role label alone
    spans them all. Callers asking what a specific base image offers must narrow
    on the producing model or they read a sibling family's runtime matrix."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    await list_base_role_profiles(kube_client, "ns", model_name="aim-audio-base")

    selector = kube_client.custom_objects.list_namespaced_custom_object.await_args.kwargs["label_selector"]
    assert (
        selector == f"{AIM_PROFILE_ROLE_LABEL}={AIM_PROFILE_ROLE_BASE},{AIM_PROFILE_SOURCE_MODEL_LABEL}=aim-audio-base"
    )


@pytest.mark.asyncio
async def test_list_base_role_profiles_spans_every_model_without_a_name(
    kube_client: MagicMock,
) -> None:
    """Callers asking what the namespace offers overall still get every family."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    await list_base_role_profiles(kube_client, "ns")

    selector = kube_client.custom_objects.list_namespaced_custom_object.await_args.kwargs["label_selector"]
    assert selector == f"{AIM_PROFILE_ROLE_LABEL}={AIM_PROFILE_ROLE_BASE}"


@pytest.mark.asyncio
async def test_wait_for_aim_profile_returns_immediately_when_present(
    kube_client: MagicMock,
) -> None:
    """When the profile already exists the helper must short-circuit
    without sleeping — the most common path during retries."""
    profile_dict = _profile_resource_dict()
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [profile_dict]}

    with patch("app.custom_models.gateway.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        result = await wait_for_aim_profile(kube_client, "kw-test-project", "llama-3-8b", timeout_seconds=10)

    assert result is not None
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_wait_for_aim_profile_polls_until_profile_appears(
    kube_client: MagicMock,
) -> None:
    """Aim-engine reconciles asynchronously — the helper must keep polling
    until the profile appears within the timeout window."""
    profile_dict = _profile_resource_dict()
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = [
        {"items": []},
        {"items": []},
        {"items": [profile_dict]},
    ]

    with patch("app.custom_models.gateway.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        result = await wait_for_aim_profile(
            kube_client, "ns", "llama-3-8b", timeout_seconds=10, poll_interval_seconds=0.01
        )

    assert result is not None
    assert kube_client.custom_objects.list_namespaced_custom_object.await_count == 3
    assert mock_sleep.await_count == 2


@pytest.mark.asyncio
async def test_wait_for_aim_profile_returns_none_on_timeout(
    kube_client: MagicMock,
) -> None:
    """If aim-engine never emits the profile the helper returns ``None`` so
    the caller can surface a precondition/timeout error of its choosing
    rather than receiving a generic ``TimeoutError`` exception."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    fake_time_values = iter([0.0, 0.0, 1.0, 2.0])

    def fake_monotonic() -> float:
        return next(fake_time_values)

    with (
        patch("app.custom_models.gateway.time.monotonic", side_effect=fake_monotonic),
        patch("app.custom_models.gateway.asyncio.sleep", new=AsyncMock()),
    ):
        result = await wait_for_aim_profile(kube_client, "ns", "model", timeout_seconds=1, poll_interval_seconds=0.5)

    assert result is None


@pytest.mark.asyncio
async def test_wait_for_aim_profile_rejects_non_positive_timeout(
    kube_client: MagicMock,
) -> None:
    """A non-positive timeout is always a programmer error — fail loud
    rather than silently never polling."""
    with pytest.raises(ValueError, match="timeout_seconds"):
        await wait_for_aim_profile(kube_client, "ns", "m", timeout_seconds=0)


@pytest.mark.asyncio
async def test_wait_for_aim_profile_rejects_non_positive_poll_interval(
    kube_client: MagicMock,
) -> None:
    """A zero poll interval would busy-loop and starve other tasks; reject."""
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        await wait_for_aim_profile(kube_client, "ns", "m", poll_interval_seconds=0)


@pytest.mark.asyncio
async def test_patch_aim_profile_uses_merge_patch_with_annotation_only_by_default(
    kube_client: MagicMock,
) -> None:
    """A merge-patch preserves unrelated annotations and spec fields aim-engine
    populated. The annotation-only path runs when no custom profile overrides
    are supplied — verifying the body has no ``spec`` key in that case."""
    annotated = _profile_resource_dict(
        annotations={AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION: "amdenterpriseai/aim-base:0.11"},
    )
    kube_client.custom_objects.patch_namespaced_custom_object.return_value = annotated

    result = await patch_aim_profile(
        kube_client,
        namespace="kw-test-project",
        profile_name="llama-3-8b-default",
        image_ref="amdenterpriseai/aim-base:0.11",
    )

    kube_client.custom_objects.patch_namespaced_custom_object.assert_awaited_once()
    call_kwargs = kube_client.custom_objects.patch_namespaced_custom_object.await_args.kwargs
    assert call_kwargs["group"] == AIM_API_GROUP
    assert call_kwargs["version"] == AIM_API_VERSION
    assert call_kwargs["namespace"] == "kw-test-project"
    assert call_kwargs["plural"] == AIM_PROFILE_PLURAL
    assert call_kwargs["name"] == "llama-3-8b-default"
    assert call_kwargs["_content_type"] == "application/merge-patch+json"
    assert call_kwargs["body"] == {
        "metadata": {"annotations": {AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION: "amdenterpriseai/aim-base:0.11"}}
    }
    assert "spec" not in call_kwargs["body"]
    assert result.metadata.annotations[AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION] == ("amdenterpriseai/aim-base:0.11")


@pytest.mark.asyncio
async def test_patch_aim_profile_forwards_custom_profile_spec_verbatim(
    kube_client: MagicMock,
) -> None:
    """A non-empty ``custom_profile_spec`` lands on ``body['spec']`` unchanged.
    The pass-through is intentional — the API does not validate the dict
    shape; aim-engine rejects unknown keys at admission."""
    kube_client.custom_objects.patch_namespaced_custom_object.return_value = _profile_resource_dict()

    overrides = {
        "engine": "vllm",
        "engineArgs": {"max-model-len": 8192},
        "metric": "latency",
        "precision": "fp8",
        "acceleratorModel": "MI300X",
        "acceleratorCount": 1,
    }

    await patch_aim_profile(
        kube_client,
        namespace="ns",
        profile_name="profile",
        image_ref="amdenterpriseai/aim-base:0.11",
        custom_profile_spec=overrides,
    )

    body = kube_client.custom_objects.patch_namespaced_custom_object.await_args.kwargs["body"]
    assert body["spec"] == overrides
    assert body["metadata"]["annotations"][AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION] == "amdenterpriseai/aim-base:0.11"


@pytest.mark.asyncio
async def test_patch_aim_profile_copies_custom_profile_spec_to_isolate_caller_mutations(
    kube_client: MagicMock,
) -> None:
    """A caller mutating the dict after the call must not retroactively change
    the patch body sent to the API server — defensive shallow copy guards
    against accidental aliasing across retries."""
    kube_client.custom_objects.patch_namespaced_custom_object.return_value = _profile_resource_dict()

    overrides: dict[str, object] = {"engine": "vllm"}

    await patch_aim_profile(
        kube_client,
        namespace="ns",
        profile_name="profile",
        image_ref="amdenterpriseai/aim-base:0.11",
        custom_profile_spec=overrides,
    )

    overrides["engine"] = "tgi"

    body = kube_client.custom_objects.patch_namespaced_custom_object.await_args.kwargs["body"]
    assert body["spec"] == {"engine": "vllm"}


@pytest.mark.asyncio
async def test_patch_aim_profile_treats_empty_custom_profile_as_annotation_only(
    kube_client: MagicMock,
) -> None:
    """An empty dict is semantically equivalent to None — should not produce
    an empty ``spec: {}`` body that aim-engine could mis-handle."""
    kube_client.custom_objects.patch_namespaced_custom_object.return_value = _profile_resource_dict()

    await patch_aim_profile(
        kube_client,
        namespace="ns",
        profile_name="profile",
        image_ref="amdenterpriseai/aim-base:0.11",
        custom_profile_spec={},
    )

    body = kube_client.custom_objects.patch_namespaced_custom_object.await_args.kwargs["body"]
    assert "spec" not in body


@pytest.mark.asyncio
async def test_patch_aim_profile_rejects_empty_image_ref(
    kube_client: MagicMock,
) -> None:
    """An empty image-ref would patch a literal ``"": ""`` annotation that
    aim-engine treats the same as the missing-annotation failure mode — far
    better to reject up-front than to deploy a pod with an empty image."""
    with pytest.raises(ValueError, match="image_ref"):
        await patch_aim_profile(kube_client, "ns", "profile", "")
    kube_client.custom_objects.patch_namespaced_custom_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_aim_profile_translates_404_to_precondition_failure(
    kube_client: MagicMock,
) -> None:
    """The profile can disappear between the upstream wait helper returning
    a result and this patch being applied (e.g. aim-engine re-reconciles
    and emits a new profile). The cluster surfaces that race as a 404;
    we translate it to ``PreconditionNotMetException`` so the caller's
    compensation path can treat it the same as the "profile never
    appeared" timeout case, instead of seeing an opaque 500."""
    kube_client.custom_objects.patch_namespaced_custom_object.side_effect = ApiException(status=404)

    with pytest.raises(PreconditionNotMetException, match="not found at patch time"):
        await patch_aim_profile(
            kube_client,
            namespace="kw-test-project",
            profile_name="llama-3-8b-default",
            image_ref="amdenterpriseai/aim-base:0.11",
        )


@pytest.mark.asyncio
async def test_patch_aim_profile_maps_non_404_api_errors_to_external_service_error(
    kube_client: MagicMock,
) -> None:
    """A 500 from the API server is a genuine infrastructure failure — wrap as
    ``ExternalServiceError`` so the FastAPI layer maps it to HTTP 502 (async
    ``ApiException`` is not registered on the app exception handlers)."""
    kube_client.custom_objects.patch_namespaced_custom_object.side_effect = ApiException(status=500)

    with pytest.raises(ExternalServiceError, match="Failed to patch AIMProfile 'profile'"):
        await patch_aim_profile(
            kube_client,
            namespace="ns",
            profile_name="profile",
            image_ref="amdenterpriseai/aim-base:0.11",
        )
