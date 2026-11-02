# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for aims gateway layer - K8s interaction functions."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from kubernetes_asyncio.client import ApiException

from api_common.exceptions import ConflictException, ExternalServiceError
from app.aims.constants import (
    AIM_COND_HTTP_ROUTE_READY,
    AIM_COND_INFERENCE_SERVICE_READY,
    FINE_TUNED_LABEL,
    NAMESPACE_AIM_MODEL_LABEL,
)
from app.aims.crds import AIMModelResource, ResolvedRef
from app.aims.enums import AIMModelStatus, AIMServiceStatus
from app.aims.gateway import (
    _get_aims_by_name,
    _get_httproutes_for_aim_services,
    aim_service_has_capability,
    create_aim_model,
    create_aim_profile_set,
    create_aim_service,
    create_namespace_aim_service,
    delete_aim_artifact,
    delete_aim_model,
    delete_aim_profile,
    delete_aim_profile_set,
    delete_aim_service,
    get_aim_artifact,
    get_aim_by_name,
    get_aim_cluster_profile_by_name,
    get_aim_model,
    get_aim_profile_by_name,
    get_aim_profile_set_by_name,
    get_aim_service_by_id,
    list_aim_artifact_source_uris,
    list_aim_artifacts_by_label_selector,
    list_aim_cluster_profiles_by_aim_ids,
    list_aim_models,
    list_aim_profile_sets_for_model,
    list_aim_profiles_by_aim_ids,
    list_aim_service_replicas,
    list_aim_services,
    list_aim_services_for_model,
    list_aim_services_referencing_artifact,
    list_aims,
    patch_aim_model,
    patch_aim_profile_set,
    patch_aim_service_spec,
)
from app.aims.schemas import AIMDeployRequest
from app.inference.enums import InferenceCapability
from tests.factory import (
    make_aim_cluster_model,
    make_aim_cluster_profile,
    make_aim_profile_set,
    make_aim_service_k8s,
)


def _make_pod(
    name: str = "pod-abc",
    phase: str = "Running",
    ready: bool = True,
    gpu_limits: dict[str, str] | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    """Build a minimal mock K8s pod for list_aim_service_replicas tests."""
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.creation_timestamp = created_at or datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    pod.status.phase = phase
    cs = MagicMock()
    cs.ready = ready
    pod.status.container_statuses = [cs]
    container = MagicMock()
    container.resources.limits = gpu_limits or {}
    pod.spec.containers = [container]
    return pod


def _pods_result(*pods: MagicMock) -> MagicMock:
    """Wrap pod mocks in an object that mimics the k8s list response."""
    result = MagicMock()
    result.items = list(pods)
    return result


@pytest.fixture
def kube_client() -> MagicMock:
    """Mock K8s client."""
    mock = MagicMock()
    mock.custom_objects = MagicMock()
    mock.custom_objects.list_cluster_custom_object = AsyncMock(return_value={"items": []})
    mock.custom_objects.get_cluster_custom_object = AsyncMock()
    mock.custom_objects.get_namespaced_custom_object = AsyncMock()
    mock.custom_objects.list_namespaced_custom_object = AsyncMock(return_value={"items": []})
    mock.custom_objects.create_namespaced_custom_object = AsyncMock()
    mock.custom_objects.delete_namespaced_custom_object = AsyncMock()
    mock.custom_objects.patch_namespaced_custom_object = AsyncMock()
    mock.get_events_for_resource = AsyncMock(return_value=[])
    mock.core_v1 = MagicMock()
    mock.core_v1.list_namespaced_pod = AsyncMock(return_value=_pods_result())
    return mock


@pytest.mark.asyncio
async def test_list_aims(kube_client: MagicMock) -> None:
    """Test listing AIMs."""
    aim = make_aim_cluster_model()
    kube_client.custom_objects.list_cluster_custom_object.return_value = {"items": [aim.model_dump(by_alias=True)]}

    result = await list_aims(kube_client)

    assert len(result) == 1
    assert result[0].metadata.name == "llama3-8b"


@pytest.mark.asyncio
async def test_list_aims_with_status_filter(kube_client: MagicMock) -> None:
    """Test listing AIMs with status filter."""
    ready = make_aim_cluster_model(name="ready", status=AIMModelStatus.READY)
    pending = make_aim_cluster_model(name="pending", status=AIMModelStatus.PENDING)
    kube_client.custom_objects.list_cluster_custom_object.return_value = {
        "items": [ready.model_dump(by_alias=True), pending.model_dump(by_alias=True)]
    }

    result = await list_aims(kube_client, statuses=[AIMModelStatus.READY])

    assert len(result) == 1
    assert result[0].metadata.name == "ready"


@pytest.mark.asyncio
async def test_list_aims_crd_not_found(kube_client: MagicMock) -> None:
    """Test returns empty when CRD not found."""
    with patch("app.aims.gateway.get_resource_version", return_value=None):
        result = await list_aims(kube_client)
    assert result == []


@pytest.mark.asyncio
async def test_get_aim_by_name(kube_client: MagicMock) -> None:
    """Test getting AIM by name."""
    aim = make_aim_cluster_model(name="my-aim")
    kube_client.custom_objects.get_cluster_custom_object.return_value = aim.model_dump(by_alias=True)

    result = await get_aim_by_name(kube_client, "my-aim")

    assert result is not None
    assert result.metadata.name == "my-aim"


@pytest.mark.asyncio
async def test_get_aim_by_name_not_found(kube_client: MagicMock) -> None:
    """Test returns None when not found."""
    kube_client.custom_objects.get_cluster_custom_object.side_effect = ApiException(status=404, reason="Not Found")

    result = await get_aim_by_name(kube_client, "missing")
    assert result is None


@pytest.mark.asyncio
async def test_list_aim_services(kube_client: MagicMock) -> None:
    """Test listing AIMServices."""
    svc = make_aim_service_k8s()
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [svc.model_dump(by_alias=True)]}

    # `list_aim_services` enriches results via HTTPRoute / KServe lookups which
    # call `get_resource_version`; patch it so the helper resolves a version
    # without a real kube client. AIM call sites now read AIM_API_VERSION
    # directly so no patch is needed for the AIM list call itself.
    with patch("app.aims.gateway.get_resource_version", return_value="v1alpha1"):
        result = await list_aim_services(kube_client, "test-ns")

    assert len(result) == 1


@pytest.mark.asyncio
async def test_list_aim_services_keeps_deployment_with_unknown_resolved_scope(kube_client: MagicMock) -> None:
    """A resolvedModel.scope value the engine adds later must not drop the whole deployment from
    the list — only a genuinely malformed item should be skipped."""
    svc = make_aim_service_k8s()
    dumped = svc.model_dump(by_alias=True)
    dumped["status"]["resolvedModel"]["scope"] = "SomeFutureScope"
    other = make_aim_service_k8s()
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [dumped, other.model_dump(by_alias=True)]
    }

    with patch("app.aims.gateway.get_resource_version", return_value="v1alpha1"):
        result = await list_aim_services(kube_client, "test-ns")

    assert len(result) == 2
    assert result[0].status.resolved_model.scope == "SomeFutureScope"


@pytest.mark.asyncio
async def test_get_aim_service_by_id(kube_client: MagicMock) -> None:
    """Test getting AIMService by ID."""
    wid = uuid4()
    svc = make_aim_service_k8s(workload_id=wid)
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [svc.model_dump(by_alias=True)]}

    result = await get_aim_service_by_id(kube_client, "test-ns", wid)

    assert result is not None


@pytest.mark.asyncio
async def test_get_aim_service_by_id_not_found(kube_client: MagicMock) -> None:
    """Test returns None when service not found."""
    result = await get_aim_service_by_id(kube_client, "test-ns", uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_create_aim_service(kube_client: MagicMock) -> None:
    """Test creating AIMService."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="img")
    svc = make_aim_service_k8s()
    kube_client.custom_objects.create_namespaced_custom_object.return_value = svc.model_dump(by_alias=True)

    result = await create_aim_service(kube_client, "test-ns", aim, req, "user", "wb-aim-test123", "test-group-id")

    assert result is not None
    kube_client.custom_objects.create_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_create_aim_service_manifest_uses_camelcase_for_cluster(kube_client: MagicMock) -> None:
    """Manifest sent to K8s API uses camelCase for imagePullSecrets, profile.name, autoScaling."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(
        model="img",
        image_pull_secrets=["secret1"],
        profile_name="profile-a",
        min_replicas=2,
        max_replicas=8,
        auto_scaling={"metrics": []},
    )
    svc = make_aim_service_k8s()
    kube_client.custom_objects.create_namespaced_custom_object.return_value = svc.model_dump(by_alias=True)

    await create_aim_service(kube_client, "test-ns", aim, req, "user", "wb-aim-test456", "test-group-id")

    call_args = kube_client.custom_objects.create_namespaced_custom_object.call_args
    manifest = call_args.kwargs["body"]
    spec = manifest["spec"]
    assert "imagePullSecrets" in spec
    assert spec["imagePullSecrets"][0]["name"] == "secret1"
    assert spec["profile"]["name"] == "profile-a"
    assert "template" not in spec
    assert spec["minReplicas"] == 2
    assert spec["maxReplicas"] == 8
    assert "autoScaling" in spec


@pytest.mark.asyncio
async def test_create_namespace_aim_service(kube_client: MagicMock) -> None:
    """Test creating namespace-model AIMService."""
    req = AIMDeployRequest(model="wb-model")
    svc = make_aim_service_k8s()
    kube_client.custom_objects.create_namespaced_custom_object.return_value = svc.model_dump(by_alias=True)

    result = await create_namespace_aim_service(
        kube_client=kube_client,
        namespace="test-ns",
        model_name="wb-model",
        deploy_request=req,
        submitter="user",
        service_name="wb-aim-test123",
        display_name="My Custom Model",
        canonical_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        is_fine_tuned=False,
    )

    assert result is not None
    call_args = kube_client.custom_objects.create_namespaced_custom_object.call_args
    labels = call_args.kwargs["body"]["metadata"]["labels"]
    assert labels[NAMESPACE_AIM_MODEL_LABEL] == "true"
    assert "aiwb.apps.eai.amd.com/fine-tuned" not in labels


@pytest.mark.asyncio
async def test_delete_aim_service(kube_client: MagicMock) -> None:
    """Test deleting AIMService."""
    wid = uuid4()
    svc = make_aim_service_k8s(workload_id=wid, name="my-svc")
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [svc.model_dump(by_alias=True)]}

    result = await delete_aim_service(kube_client, "test-ns", wid)

    assert result == "my-svc"


@pytest.mark.asyncio
async def test_delete_aim_service_not_found(kube_client: MagicMock) -> None:
    """Test raises when service not found."""
    with pytest.raises(ValueError, match="No AIMService found"):
        await delete_aim_service(kube_client, "test-ns", uuid4())


@pytest.mark.asyncio
async def test_patch_aim_service_spec_merge_patches_by_name(kube_client: MagicMock) -> None:
    """Only the given spec fields are sent, against the named resource directly."""
    svc = make_aim_service_k8s(name="wb-aim-target")
    kube_client.custom_objects.patch_namespaced_custom_object.return_value = svc.model_dump(by_alias=True)

    result = await patch_aim_service_spec(kube_client, "ns", "wb-aim-target", {"adapters": None})

    assert result.metadata.name == "wb-aim-target"
    call_kwargs = kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["name"] == "wb-aim-target"
    assert call_kwargs["plural"] == "aimservices"
    assert call_kwargs["body"] == {"spec": {"adapters": None}}
    assert call_kwargs["_content_type"] == "application/merge-patch+json"


@pytest.mark.asyncio
async def test_patch_aim_service_spec_reraises_the_api_rejection(kube_client: MagicMock) -> None:
    """The API server's own status is what tells a caller whether a CEL rule or a conflict fired,
    so it is left intact instead of being flattened into a gateway error."""
    kube_client.custom_objects.patch_namespaced_custom_object.side_effect = ApiException(status=422, reason="Invalid")

    with pytest.raises(ApiException) as exc_info:
        await patch_aim_service_spec(kube_client, "ns", "wb-aim-target", {"adapters": []})

    assert exc_info.value.status == 422


def test_aim_service_has_capability_chat_true() -> None:
    """Test service is chattable when conditions are ready and has chat tag."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(
        status=AIMServiceStatus.RUNNING,
        model_ref="llama",
        conditions=conditions,
    )
    aim = make_aim_cluster_model(name="llama", tags=["chat"])
    aims_by_name = {"llama": aim}

    result = aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT)

    assert result is True


def test_aim_service_has_capability_chat_false_missing_conditions() -> None:
    """Test service not chattable when conditions are not ready."""
    svc = make_aim_service_k8s(
        status=AIMServiceStatus.PENDING,
        model_ref="llama",
    )
    aim = make_aim_cluster_model(name="llama", tags=["chat"])
    aims_by_name = {"llama": aim}

    result = aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT)

    assert result is False


def test_aim_service_has_capability_chat_false_no_chat_tag() -> None:
    """Test service not chattable without chat tag."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(
        status=AIMServiceStatus.RUNNING,
        model_ref="llama",
        conditions=conditions,
    )
    aim = make_aim_cluster_model(name="llama", tags=["text-generation"])  # No chat tag
    aims_by_name = {"llama": aim}

    result = aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT)

    assert result is False


def test_aim_service_has_capability_chat_false_aim_not_found() -> None:
    """Test service not chattable when AIM not found."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(
        status=AIMServiceStatus.RUNNING,
        model_ref="missing",
        conditions=conditions,
    )
    aims_by_name: dict[str, AIMModelResource] = {}

    result = aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT)

    assert result is False


def test_aim_service_has_capability_chat_uses_spec_model_name_when_resolved_model_name_is_canonical_id() -> None:
    """Chattable check must look up the AIM by spec.model.name, not status.resolvedModel.name.

    Under the v1alpha2 profile reconciler, status.resolvedModel.name holds the
    canonical model id (e.g. "amd/Llama-3.1-8B-Instruct-FP8-KV"), which contains
    a slash and is not the AIMClusterModel resource name. aims_by_name is keyed
    by resource name, so using the canonical id misses the lookup.
    """
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(
        status=AIMServiceStatus.RUNNING,
        model_ref="llama3-8b",
        conditions=conditions,
    )
    # Simulate v1alpha2 profile reconciler: status carries the canonical id
    # (with a slash) while spec.model.name remains the K8s resource name.
    svc.status.resolved_model = ResolvedRef(name="amd/Llama-3.1-8B-Instruct-FP8-KV")

    aim = make_aim_cluster_model(name="llama3-8b", tags=["chat"])
    # Map is keyed by spec resource name; the canonical id is intentionally absent
    # to prove the lookup uses spec.model.name.
    aims_by_name = {"llama3-8b": aim}

    result = aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT)

    assert result is True


def test_aim_service_has_capability_chat_degraded_but_healthy() -> None:
    """Test DEGRADED service is chattable if conditions are healthy."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(
        status=AIMServiceStatus.DEGRADED,
        model_ref="llama",
        conditions=conditions,
    )
    aim = make_aim_cluster_model(name="llama", tags=["chat"])
    aims_by_name = {"llama": aim}

    result = aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT)

    assert result is True


def test_aim_service_has_capability_chat_namespace_model_label() -> None:
    """Namespace AIMModel services are chat-capable without catalog lookup."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(
        status=AIMServiceStatus.RUNNING,
        model_ref="custom-model",
        conditions=conditions,
    )
    svc.metadata.labels[NAMESPACE_AIM_MODEL_LABEL] = "true"
    aims_by_name: dict[str, AIMModelResource] = {}

    result = aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT)

    assert result is True


def test_aim_service_has_capability_transcription_true() -> None:
    """A catalog model tagged for speech-to-text is transcription-capable."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="whisper", conditions=conditions)
    aim = make_aim_cluster_model(name="whisper", tags=["speech-to-text", "automatic-speech-recognition", "audio"])
    aims_by_name = {"whisper": aim}

    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is True


def test_aim_service_has_capability_distinguishes_chat_and_transcription() -> None:
    """A chat model is not transcription-capable, and a transcription model is not chat."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    chat_svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="llama", conditions=conditions)
    whisper_svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="whisper", conditions=conditions)
    aims_by_name = {
        "llama": make_aim_cluster_model(name="llama", tags=["chat"]),
        "whisper": make_aim_cluster_model(name="whisper", tags=["transcription"]),
    }

    assert aim_service_has_capability(chat_svc, aims_by_name, InferenceCapability.CHAT) is True
    assert aim_service_has_capability(chat_svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is False
    assert aim_service_has_capability(whisper_svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is True
    assert aim_service_has_capability(whisper_svc, aims_by_name, InferenceCapability.CHAT) is False


def test_aim_service_has_capability_namespace_model_is_chat_only() -> None:
    """Namespace (custom-onboarded) models are chat by label, not transcription.

    They have no cluster-scoped AIMClusterModel to read a capability tag from, so
    only chat is inferred here; transcription classification for these is handled
    from their own source tags separately.
    """
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="custom-whisper", conditions=conditions)
    svc.metadata.labels[NAMESPACE_AIM_MODEL_LABEL] = "true"
    aims_by_name: dict[str, AIMModelResource] = {}

    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT) is True
    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is False


def test_aim_service_has_capability_fine_tuned_model_is_chat_only() -> None:
    """Fine-tuned models are scoped like custom-onboarded ones: chat by label only.

    They carry ``FINE_TUNED_LABEL`` rather than the namespace label, and neither has a
    cluster-scoped AIMClusterModel to read a capability tag from.
    """
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="tuned-whisper", conditions=conditions)
    svc.metadata.labels[FINE_TUNED_LABEL] = "true"
    aims_by_name: dict[str, AIMModelResource] = {}

    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT) is True
    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is False


def test_aim_service_has_capability_false_until_serving_ready() -> None:
    """No capability is exposed until the service passes the serving-readiness gate."""
    svc = make_aim_service_k8s(status=AIMServiceStatus.PENDING, model_ref="whisper")
    aims_by_name = {"whisper": make_aim_cluster_model(name="whisper", tags=["transcription"])}

    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is False


def test_aim_service_has_capability_model_with_both_tags_matches_both() -> None:
    """A model tagged for both chat and transcription satisfies either filter."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="multi", conditions=conditions)
    aims_by_name = {"multi": make_aim_cluster_model(name="multi", tags=["chat", "transcription"])}

    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT) is True
    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is True


def test_aim_service_has_capability_model_matching_neither_is_false() -> None:
    """A model with no chat/transcription tag matches no capability filter."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="vision", conditions=conditions)
    aims_by_name = {"vision": make_aim_cluster_model(name="vision", tags=["image-text-to-text"])}

    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.CHAT) is False
    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is False


@pytest.mark.parametrize("tag", ["transcription", "speech-to-text", "automatic-speech-recognition"])
def test_aim_service_has_capability_each_transcription_tag_matches(tag: str) -> None:
    """Each recognized transcription tag alone makes a model transcription-capable."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="asr", conditions=conditions)
    aims_by_name = {"asr": make_aim_cluster_model(name="asr", tags=[tag])}

    assert aim_service_has_capability(svc, aims_by_name, InferenceCapability.TRANSCRIPTION) is True


@pytest.mark.asyncio
async def test_list_aim_services_capability_filter_excludes_by_capability_not_readiness(kube_client: MagicMock) -> None:
    """A fully ready service is excluded when its catalog capability doesn't match the filter.

    The service is ready and its catalog model is tagged only for transcription, so the
    chat filter must drop it via the capability check itself (not the readiness gate),
    while the transcription filter keeps it.
    """
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="whisper", conditions=conditions)
    aim = make_aim_cluster_model(name="whisper", tags=["transcription"])
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [svc.model_dump(by_alias=True)]}
    kube_client.custom_objects.list_cluster_custom_object.return_value = {"items": [aim.model_dump(by_alias=True)]}

    with patch("app.aims.gateway.get_resource_version", return_value="v1alpha1"):
        chat_result = await list_aim_services(kube_client, "test-ns", capability=InferenceCapability.CHAT)
        transcription_result = await list_aim_services(
            kube_client, "test-ns", capability=InferenceCapability.TRANSCRIPTION
        )

    assert len(chat_result) == 0
    assert len(transcription_result) == 1


@pytest.mark.asyncio
async def test_list_aim_cluster_profiles_by_aim_ids(kube_client: MagicMock) -> None:
    """Test listing AIMClusterProfiles."""
    t = make_aim_cluster_profile()
    kube_client.custom_objects.list_cluster_custom_object.return_value = {"items": [t.model_dump(by_alias=True)]}

    result = await list_aim_cluster_profiles_by_aim_ids(kube_client)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_list_aims_handles_exception(kube_client: MagicMock) -> None:
    """Test list_aims returns empty on exception."""
    kube_client.custom_objects.list_cluster_custom_object.side_effect = Exception("API error")

    result = await list_aims(kube_client)

    assert result == []


@pytest.mark.asyncio
async def test_get_aim_by_name_handles_non_404_exception(kube_client: MagicMock) -> None:
    """Test get_aim_by_name handles non-404 exceptions."""
    kube_client.custom_objects.get_cluster_custom_object.side_effect = Exception("Server error")

    result = await get_aim_by_name(kube_client, "test")

    assert result is None


@pytest.mark.asyncio
async def test_list_aim_services_handles_exception(kube_client: MagicMock) -> None:
    """Test list_aim_services returns empty on exception."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = Exception("API error")

    result = await list_aim_services(kube_client, "ns")

    assert result == []


@pytest.mark.asyncio
async def test_get_aim_service_by_id_raises_on_api_error(kube_client: MagicMock) -> None:
    """A k8s failure must not resolve to None — that reads as "not found" to callers."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(status=403, reason="Forbidden")

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await get_aim_service_by_id(kube_client, "ns", uuid4())


@pytest.mark.asyncio
async def test_get_aim_service_by_id_raises_on_parse_failure(kube_client: MagicMock) -> None:
    """A resource that exists but fails to parse must not be mistaken for a deleted one."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [{"malformed": True}]}

    with pytest.raises(ExternalServiceError, match="Failed to parse"):
        await get_aim_service_by_id(kube_client, "ns", uuid4())


@pytest.mark.asyncio
async def test_list_aim_cluster_profiles_propagates_api_errors(kube_client: MagicMock) -> None:
    """RBAC and other ApiException failures must propagate as ExternalServiceError —
    swallowing them as an empty list hides the cause (e.g. SA missing list verb)."""
    kube_client.custom_objects.list_cluster_custom_object.side_effect = ApiException(
        status=403,
        reason="Forbidden",
    )

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await list_aim_cluster_profiles_by_aim_ids(kube_client)


@pytest.mark.asyncio
async def test_list_aim_profiles_propagates_api_errors(kube_client: MagicMock) -> None:
    """Namespace-scoped variant must also surface RBAC failures rather than masking them."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(
        status=403,
        reason="Forbidden",
    )

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await list_aim_profiles_by_aim_ids(kube_client, namespace="ns")


@pytest.mark.asyncio
async def test_get_aim_cluster_profile_by_name_returns_match(kube_client: MagicMock) -> None:
    """Direct K8s GET by name returns the validated CR."""
    profile = make_aim_cluster_profile(name="profile-x", aim_id="org/llama")
    kube_client.custom_objects.get_cluster_custom_object.return_value = profile.model_dump(by_alias=True)

    result = await get_aim_cluster_profile_by_name(kube_client, "profile-x")

    assert result is not None
    assert result.metadata.name == "profile-x"
    call_kwargs = kube_client.custom_objects.get_cluster_custom_object.call_args.kwargs
    assert call_kwargs["name"] == "profile-x"


@pytest.mark.asyncio
async def test_get_aim_cluster_profile_by_name_returns_none_on_404(kube_client: MagicMock) -> None:
    """404 from K8s maps to None so the service can raise NotFoundException."""
    kube_client.custom_objects.get_cluster_custom_object.side_effect = ApiException(status=404, reason="Not Found")

    result = await get_aim_cluster_profile_by_name(kube_client, "missing")
    assert result is None


@pytest.mark.asyncio
async def test_get_aim_cluster_profile_by_name_propagates_api_errors(kube_client: MagicMock) -> None:
    """RBAC and other non-404 ApiException failures surface as ExternalServiceError."""
    kube_client.custom_objects.get_cluster_custom_object.side_effect = ApiException(status=403, reason="Forbidden")

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await get_aim_cluster_profile_by_name(kube_client, "anything")


@pytest.mark.asyncio
async def test_get_aim_profile_by_name_returns_match(kube_client: MagicMock) -> None:
    """Direct K8s GET by name in a namespace returns the validated CR."""
    profile = make_aim_cluster_profile(name="profile-y", aim_id="org/ft")
    kube_client.custom_objects.get_namespaced_custom_object.return_value = profile.model_dump(by_alias=True)

    result = await get_aim_profile_by_name(kube_client, "test-ns", "profile-y")

    assert result is not None
    assert result.metadata.name == "profile-y"
    call_kwargs = kube_client.custom_objects.get_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["namespace"] == "test-ns"
    assert call_kwargs["name"] == "profile-y"


@pytest.mark.asyncio
async def test_get_aim_profile_by_name_returns_none_on_404(kube_client: MagicMock) -> None:
    """404 maps to None for the namespace-scoped variant too."""
    kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404, reason="Not Found")

    result = await get_aim_profile_by_name(kube_client, "test-ns", "missing")
    assert result is None


@pytest.mark.asyncio
async def test_get_aim_profile_by_name_propagates_api_errors(kube_client: MagicMock) -> None:
    """Non-404 ApiException surfaces as ExternalServiceError for the namespace variant."""
    kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=403, reason="Forbidden")

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await get_aim_profile_by_name(kube_client, "test-ns", "anything")


@pytest.mark.asyncio
async def test_get_aim_by_name_crd_not_available(kube_client: MagicMock) -> None:
    """Test get_aim_by_name returns None when CRD not available."""
    with patch("app.aims.gateway.get_resource_version", return_value=None):
        result = await get_aim_by_name(kube_client, "test")
    assert result is None


@pytest.mark.asyncio
async def test_list_aim_services_with_chattable_filter(kube_client: MagicMock) -> None:
    """Test listing services with chattable filter."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(status=AIMServiceStatus.RUNNING, model_ref="llama", conditions=conditions)
    aim = make_aim_cluster_model(name="llama", tags=["chat"])
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [svc.model_dump(by_alias=True)]}
    kube_client.custom_objects.list_cluster_custom_object.return_value = {"items": [aim.model_dump(by_alias=True)]}

    # See test_list_aim_services for why the HTTPRoute/KServe path needs a
    # patched version resolver while the AIM-flow does not.
    with patch("app.aims.gateway.get_resource_version", return_value="v1alpha1"):
        result = await list_aim_services(kube_client, "test-ns", capability=InferenceCapability.CHAT)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_list_aim_services_chattable_filters_out_non_chattable(kube_client: MagicMock) -> None:
    """Test chattable filter excludes non-chattable services."""
    svc = make_aim_service_k8s(status=AIMServiceStatus.PENDING)  # Not RUNNING
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [svc.model_dump(by_alias=True)]}
    kube_client.custom_objects.list_cluster_custom_object.return_value = {"items": []}

    result = await list_aim_services(kube_client, "test-ns", capability=InferenceCapability.CHAT)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_aims_by_name(kube_client: MagicMock) -> None:
    """Test _get_aims_by_name returns AIMs indexed by name."""
    aim1 = make_aim_cluster_model(name="llama")
    aim2 = make_aim_cluster_model(name="mistral")
    kube_client.custom_objects.list_cluster_custom_object.return_value = {
        "items": [aim1.model_dump(by_alias=True), aim2.model_dump(by_alias=True)]
    }

    result = await _get_aims_by_name(kube_client)

    assert len(result) == 2
    assert "llama" in result
    assert "mistral" in result
    assert result["llama"].metadata.name == "llama"
    assert result["mistral"].metadata.name == "mistral"


@pytest.mark.asyncio
async def test_list_aim_cluster_profiles_filters_by_aim_id(kube_client: MagicMock) -> None:
    """Each requested aimId is pushed to the API server as a field selector.

    aim-engine added ``spec.aimId`` to the AIMClusterProfile CRD's
    ``selectableFields``, so the gateway delegates filtering to the API
    server. Multi-id requests fan out to N calls (K8s field selectors are
    equality-only) and the gateway never re-applies the filter in Python.
    """
    llama = make_aim_cluster_profile(name="llama-profile", aim_id="org/llama")
    cohere = make_aim_cluster_profile(name="cohere-profile", aim_id="org/cohere")

    list_mock = kube_client.custom_objects.list_cluster_custom_object

    list_mock.side_effect = lambda **kwargs: {
        "spec.aimId=org/llama": {"items": [llama.model_dump(by_alias=True)]},
        "spec.aimId=org/cohere": {"items": [cohere.model_dump(by_alias=True)]},
    }[kwargs["field_selector"]]

    result = await list_aim_cluster_profiles_by_aim_ids(kube_client, aim_ids=["org/llama"])
    assert {p.metadata.name for p in result} == {"llama-profile"}
    assert list_mock.call_args.kwargs["field_selector"] == "spec.aimId=org/llama"

    list_mock.reset_mock()
    result = await list_aim_cluster_profiles_by_aim_ids(kube_client, aim_ids=["org/llama", "org/cohere"])
    assert {p.metadata.name for p in result} == {"llama-profile", "cohere-profile"}
    field_selectors = [c.kwargs["field_selector"] for c in list_mock.call_args_list]
    assert field_selectors == ["spec.aimId=org/llama", "spec.aimId=org/cohere"]


@pytest.mark.asyncio
async def test_list_aim_cluster_profiles_no_filter_omits_field_selector(kube_client: MagicMock) -> None:
    """No aim_ids → single unfiltered list call, no field selector sent.

    Guards against accidentally adding a client-side filter once the
    server-side narrowing is in place: the kube call's items are returned
    verbatim.
    """
    llama = make_aim_cluster_profile(name="llama-profile", aim_id="org/llama")
    mistral = make_aim_cluster_profile(name="mistral-profile", aim_id="org/mistral")
    list_mock = kube_client.custom_objects.list_cluster_custom_object
    list_mock.return_value = {"items": [llama.model_dump(by_alias=True), mistral.model_dump(by_alias=True)]}

    result = await list_aim_cluster_profiles_by_aim_ids(kube_client, aim_ids=None)

    assert {p.metadata.name for p in result} == {"llama-profile", "mistral-profile"}
    assert list_mock.call_count == 1
    assert "field_selector" not in list_mock.call_args.kwargs


@pytest.mark.asyncio
async def test_list_aim_profiles_filters_by_aim_id(kube_client: MagicMock) -> None:
    """Namespaced variant pushes the aimId filter to the API server too."""
    llama = make_aim_cluster_profile(name="llama-profile", aim_id="org/llama")
    cohere = make_aim_cluster_profile(name="cohere-profile", aim_id="org/cohere")

    list_mock = kube_client.custom_objects.list_namespaced_custom_object
    list_mock.side_effect = lambda **kwargs: {
        "spec.aimId=org/llama": {"items": [llama.model_dump(by_alias=True)]},
        "spec.aimId=org/cohere": {"items": [cohere.model_dump(by_alias=True)]},
    }[kwargs["field_selector"]]

    result = await list_aim_profiles_by_aim_ids(kube_client, namespace="ns", aim_ids=["org/llama"])
    assert {p.metadata.name for p in result} == {"llama-profile"}
    assert list_mock.call_args.kwargs["field_selector"] == "spec.aimId=org/llama"
    assert list_mock.call_args.kwargs["namespace"] == "ns"

    list_mock.reset_mock()
    result = await list_aim_profiles_by_aim_ids(kube_client, namespace="ns", aim_ids=["org/llama", "org/cohere"])
    assert {p.metadata.name for p in result} == {"llama-profile", "cohere-profile"}
    field_selectors = [c.kwargs["field_selector"] for c in list_mock.call_args_list]
    assert field_selectors == ["spec.aimId=org/llama", "spec.aimId=org/cohere"]


@pytest.mark.asyncio
async def test_list_aim_profiles_no_filter_omits_field_selector(kube_client: MagicMock) -> None:
    """No aim_ids → single namespaced list, no field selector sent."""
    llama = make_aim_cluster_profile(name="llama-profile", aim_id="org/llama")
    list_mock = kube_client.custom_objects.list_namespaced_custom_object
    list_mock.return_value = {"items": [llama.model_dump(by_alias=True)]}

    result = await list_aim_profiles_by_aim_ids(kube_client, namespace="ns")

    assert {p.metadata.name for p in result} == {"llama-profile"}
    assert list_mock.call_count == 1
    assert "field_selector" not in list_mock.call_args.kwargs


@pytest.mark.asyncio
async def test_list_aim_services_with_status_filter(kube_client: MagicMock) -> None:
    """Test status_filter includes only specified statuses."""
    svc_running = make_aim_service_k8s(status=AIMServiceStatus.RUNNING)
    svc_deleted = make_aim_service_k8s(status=AIMServiceStatus.DELETED)
    svc_pending = make_aim_service_k8s(status=AIMServiceStatus.PENDING)

    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [
            svc_running.model_dump(by_alias=True),
            svc_deleted.model_dump(by_alias=True),
            svc_pending.model_dump(by_alias=True),
        ]
    }

    # Filter to only include RUNNING and PENDING (exclude DELETED). The
    # HTTPRoute/KServe enrichment helpers still resolve the served version,
    # so patch get_resource_version (see test_list_aim_services).
    with patch("app.aims.gateway.get_resource_version", return_value="v1alpha1"):
        result = await list_aim_services(
            kube_client, "test-ns", status_filter=[AIMServiceStatus.RUNNING, AIMServiceStatus.PENDING]
        )

    assert len(result) == 2
    statuses = {svc.status.status for svc in result}
    assert AIMServiceStatus.RUNNING in statuses
    assert AIMServiceStatus.PENDING in statuses
    assert AIMServiceStatus.DELETED not in statuses


@pytest.mark.asyncio
async def test_get_httproutes_for_aim_services_indexes_by_name(kube_client: MagicMock) -> None:
    """Test HTTPRoutes are indexed by AIMService owner name."""
    httproute_item = {
        "metadata": {
            "name": "my-route",
            "namespace": "test-ns",
            "ownerReferences": [{"kind": "AIMService", "name": "my-svc", "controller": True, "uid": "123"}],
        },
        "spec": {
            "rules": [
                {
                    "backendRefs": [{"kind": "Service", "name": "my-svc-predictor", "port": 80}],
                    "matches": [{"path": {"type": "PathPrefix", "value": "/v1/chat"}}],
                }
            ]
        },
    }
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [httproute_item]}

    with patch("app.aims.gateway.get_resource_version", return_value="v1"):
        result = await _get_httproutes_for_aim_services(kube_client, "test-ns")

    assert "my-svc" in result
    assert result["my-svc"].metadata.name == "my-route"
    assert len(result["my-svc"].spec.rules) == 1


@pytest.mark.asyncio
async def test_get_httproutes_for_aim_services_empty(kube_client: MagicMock) -> None:
    """Test returns empty dict when no HTTPRoutes found."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    with patch("app.aims.gateway.get_resource_version", return_value="v1"):
        result = await _get_httproutes_for_aim_services(kube_client, "test-ns")

    assert result == {}


@pytest.mark.asyncio
async def test_get_httproutes_for_aim_services_skips_non_aimservice(kube_client: MagicMock) -> None:
    """Test skips HTTPRoutes not owned by AIMService."""
    httproute_item = {
        "metadata": {
            "name": "my-route",
            "namespace": "test-ns",
            "ownerReferences": [{"kind": "Other", "name": "other-svc", "controller": True, "uid": "123"}],
        },
        "spec": {"rules": []},
    }
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [httproute_item]}

    with patch("app.aims.gateway.get_resource_version", return_value="v1"):
        result = await _get_httproutes_for_aim_services(kube_client, "test-ns")

    assert result == {}


@pytest.mark.asyncio
async def test_get_httproutes_for_aim_services_requires_controller(kube_client: MagicMock) -> None:
    """Test only indexes owner references with controller=True."""
    httproute_item = {
        "metadata": {
            "name": "my-route",
            "namespace": "test-ns",
            "ownerReferences": [{"kind": "AIMService", "name": "my-svc", "controller": False, "uid": "123"}],
        },
        "spec": {"rules": []},
    }
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [httproute_item]}

    with patch("app.aims.gateway.get_resource_version", return_value="v1"):
        result = await _get_httproutes_for_aim_services(kube_client, "test-ns")

    assert result == {}


@pytest.mark.asyncio
async def test_get_httproutes_for_aim_services_crd_missing(kube_client: MagicMock) -> None:
    """Test returns empty dict when HTTPRoute CRD not found."""
    with patch("app.aims.gateway.get_resource_version", return_value=None):
        result = await _get_httproutes_for_aim_services(kube_client, "test-ns")

    assert result == {}
    # Verify we didn't try to list when CRD doesn't exist
    kube_client.custom_objects.list_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_get_httproutes_for_aim_services_handles_exception(kube_client: MagicMock) -> None:
    """Test handles exception gracefully."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = Exception("API error")

    with patch("app.aims.gateway.get_resource_version", return_value="v1"):
        result = await _get_httproutes_for_aim_services(kube_client, "test-ns")

    assert result == {}
    # Verify the API was called despite the error
    kube_client.custom_objects.list_namespaced_custom_object.assert_called_once()


# =============================================================================
# list_aim_service_replicas
# =============================================================================


def _setup_pod_serialization(kube_client: MagicMock, pod_dicts: list[dict]) -> None:
    """Wire sanitize_for_serialization to return successive dicts for each pod call."""
    kube_client._api_client.sanitize_for_serialization.side_effect = pod_dicts


@pytest.mark.asyncio
async def test_list_aim_service_replicas_returns_parsed_replica(kube_client: MagicMock) -> None:
    """Returns raw pod dicts serialized from Kubernetes objects."""
    pod = _make_pod(name="pod-abc")
    pod_dict = {"metadata": {"name": "pod-abc"}, "status": {"phase": "Running"}}
    kube_client.core_v1.list_namespaced_pod.return_value = _pods_result(pod)
    _setup_pod_serialization(kube_client, [pod_dict])

    result = await list_aim_service_replicas(kube_client, "test-ns", uuid4())

    assert len(result) == 1
    assert result[0]["metadata"]["name"] == "pod-abc"
    assert result[0]["status"]["phase"] == "Running"


@pytest.mark.asyncio
async def test_list_aim_service_replicas_sorted_by_name(kube_client: MagicMock) -> None:
    """Results are sorted alphabetically by metadata.name."""
    pods = [_make_pod(name=n) for n in ("pod-zzz", "pod-aaa", "pod-mmm")]
    pod_dicts = [{"metadata": {"name": n}} for n in ("pod-zzz", "pod-aaa", "pod-mmm")]
    kube_client.core_v1.list_namespaced_pod.return_value = _pods_result(*pods)
    _setup_pod_serialization(kube_client, pod_dicts)

    result = await list_aim_service_replicas(kube_client, "test-ns", uuid4())

    assert [r["metadata"]["name"] for r in result] == ["pod-aaa", "pod-mmm", "pod-zzz"]


@pytest.mark.asyncio
async def test_list_aim_service_replicas_skips_pods_without_name(kube_client: MagicMock) -> None:
    """Pods missing a metadata name are silently skipped."""
    named = _make_pod(name="pod-ok")
    unnamed = _make_pod()
    unnamed.metadata.name = None
    kube_client.core_v1.list_namespaced_pod.return_value = _pods_result(named, unnamed)
    _setup_pod_serialization(kube_client, [{"metadata": {"name": "pod-ok"}}])

    result = await list_aim_service_replicas(kube_client, "test-ns", uuid4())

    assert len(result) == 1
    assert result[0]["metadata"]["name"] == "pod-ok"


@pytest.mark.asyncio
async def test_list_aim_service_replicas_handles_exception(kube_client: MagicMock) -> None:
    """Returns an empty list when the k8s API call fails."""
    kube_client.core_v1.list_namespaced_pod.side_effect = Exception("API error")

    result = await list_aim_service_replicas(kube_client, "test-ns", uuid4())

    assert result == []


# --- get_aim_model ---


@pytest.mark.asyncio
async def test_get_aim_model(kube_client: MagicMock) -> None:
    """Test getting a namespace-scoped AIMModel by name."""
    raw = {"metadata": {"name": "ft-model", "namespace": "test-ns"}, "spec": {"modelSources": []}}
    kube_client.custom_objects.get_namespaced_custom_object.return_value = raw

    result = await get_aim_model(kube_client, "test-ns", "ft-model")

    assert result is not None
    assert isinstance(result, AIMModelResource)
    assert result.metadata.name == "ft-model"


@pytest.mark.asyncio
async def test_get_aim_model_404(kube_client: MagicMock) -> None:
    """Test returns None when AIMModel resource does not exist (404)."""
    kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404, reason="Not Found")

    result = await get_aim_model(kube_client, "test-ns", "missing")

    assert result is None


@pytest.mark.asyncio
async def test_get_aim_model_non_404_exception(kube_client: MagicMock) -> None:
    """Test non-404 exceptions are re-raised so callers aren't silently misled."""
    kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(
        status=500, reason="Server error"
    )

    with pytest.raises(ApiException):
        await get_aim_model(kube_client, "test-ns", "ft-model")


# --- list_aim_services_for_model ---


@pytest.mark.asyncio
async def test_list_aim_services_for_model(kube_client: MagicMock) -> None:
    """Test listing AIMServices that reference a specific model."""
    matching = make_aim_service_k8s(model_ref="ft-model")
    other = make_aim_service_k8s(model_ref="other-model")
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [matching.model_dump(by_alias=True), other.model_dump(by_alias=True)]
    }

    result = await list_aim_services_for_model(kube_client, "test-ns", "ft-model")

    assert len(result) == 1
    assert result[0].spec.model.name == "ft-model"


@pytest.mark.asyncio
async def test_list_aim_services_for_model_no_matches(kube_client: MagicMock) -> None:
    """Test returns empty when no services reference the model."""
    svc = make_aim_service_k8s(model_ref="other-model")
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [svc.model_dump(by_alias=True)]}

    result = await list_aim_services_for_model(kube_client, "test-ns", "ft-model")

    assert result == []


@pytest.mark.asyncio
async def test_list_aim_services_for_model_propagates_non_404_exception(kube_client: MagicMock) -> None:
    """Non-404 exceptions propagate so the active-deployment guard is never silently bypassed."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = Exception("API error")

    with pytest.raises(Exception, match="API error"):
        await list_aim_services_for_model(kube_client, "test-ns", "ft-model")


@pytest.mark.asyncio
async def test_list_aim_services_for_model_returns_empty_on_404(kube_client: MagicMock) -> None:
    """404 from the API returns empty list — model has no services."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(status=404, reason="Not Found")

    result = await list_aim_services_for_model(kube_client, "test-ns", "ft-model")

    assert result == []


@pytest.mark.asyncio
async def test_list_aim_services_for_model_raises_on_parse_failure(kube_client: MagicMock) -> None:
    """A matching service that fails to parse must not be dropped silently — that would under-report
    active deployments and could let an in-use model be deleted."""
    matching = make_aim_service_k8s(model_ref="ft-model")
    malformed = matching.model_dump(by_alias=True)
    malformed["metadata"] = {}  # drop required metadata fields
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [malformed]}

    with pytest.raises(ExternalServiceError, match="Failed to parse"):
        await list_aim_services_for_model(kube_client, "test-ns", "ft-model")


@pytest.mark.asyncio
async def test_list_aim_services_for_model_namespace_wide_returns_all(kube_client: MagicMock) -> None:
    """With resource_name=None the list is namespace-wide, not filtered to one model."""
    svc_a = make_aim_service_k8s(model_ref="model-a")
    svc_b = make_aim_service_k8s(model_ref="model-b")
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [svc_a.model_dump(by_alias=True), svc_b.model_dump(by_alias=True)]
    }

    result = await list_aim_services_for_model(kube_client, "test-ns")

    assert {r.spec.model.name for r in result} == {"model-a", "model-b"}


@pytest.mark.asyncio
async def test_list_aim_services_for_model_namespace_wide_skips_unparseable(kube_client: MagicMock) -> None:
    """Namespace-wide (resource_name=None) composes display-time inUseBy refs, so one malformed
    CR is skipped rather than 502-ing the whole models grid — unlike the filtered delete-safety path."""
    valid = make_aim_service_k8s(model_ref="model-a")
    malformed = make_aim_service_k8s(model_ref="model-b").model_dump(by_alias=True)
    malformed["metadata"] = {}  # drop required metadata fields to force a parse failure
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [valid.model_dump(by_alias=True), malformed]
    }

    result = await list_aim_services_for_model(kube_client, "test-ns")

    assert [r.spec.model.name for r in result] == ["model-a"]


# --- delete_aim_model ---


@pytest.mark.asyncio
async def test_delete_aim_model(kube_client: MagicMock) -> None:
    """Test successful deletion of AIMModel."""
    await delete_aim_model(kube_client, "test-ns", "ft-model")

    kube_client.custom_objects.delete_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_delete_aim_model_404(kube_client: MagicMock) -> None:
    """Test no-ops when AIMModel resource does not exist (404)."""
    kube_client.custom_objects.delete_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )

    await delete_aim_model(kube_client, "test-ns", "missing")

    # Should not raise


@pytest.mark.asyncio
async def test_delete_aim_model_non_404_exception(kube_client: MagicMock) -> None:
    """Test re-raises non-404 exceptions."""
    kube_client.custom_objects.delete_namespaced_custom_object.side_effect = Exception("Server error")

    with pytest.raises(Exception, match="Server error"):
        await delete_aim_model(kube_client, "test-ns", "ft-model")


# --- create_aim_model ---


def _aim_model_manifest(name: str = "my-aim-model") -> dict:
    return {
        "apiVersion": "aim.eai.amd.com/v1alpha1",
        "kind": "AIMModel",
        "metadata": {"name": name, "namespace": "test-ns"},
        "spec": {"modelSources": [{"modelId": "owner/model", "sourceUri": "hf://owner/model"}]},
    }


@pytest.mark.asyncio
async def test_create_aim_model_success(kube_client: MagicMock) -> None:
    """create_aim_model returns the parsed AIMModelResource on a 200/201 response."""
    manifest = _aim_model_manifest()
    kube_client.custom_objects.create_namespaced_custom_object.return_value = manifest

    result = await create_aim_model(kube_client, "test-ns", manifest)

    assert isinstance(result, AIMModelResource)
    assert result.metadata.name == "my-aim-model"
    kube_client.custom_objects.create_namespaced_custom_object.assert_called_once()
    call_kwargs = kube_client.custom_objects.create_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["plural"] == "aimmodels"
    assert call_kwargs["namespace"] == "test-ns"
    assert call_kwargs["body"] is manifest


@pytest.mark.asyncio
async def test_create_aim_model_409_maps_to_conflict_exception(kube_client: MagicMock) -> None:
    """API server 409 is mapped to ConflictException so callers don't need to know about ApiException."""
    kube_client.custom_objects.create_namespaced_custom_object.side_effect = ApiException(status=409, reason="Conflict")

    with pytest.raises(ConflictException, match="already exists"):
        await create_aim_model(kube_client, "test-ns", _aim_model_manifest())


@pytest.mark.asyncio
async def test_create_aim_model_non_409_propagates(kube_client: MagicMock) -> None:
    """Non-409 ApiException propagates unchanged so generic K8s errors surface as 5xx."""
    kube_client.custom_objects.create_namespaced_custom_object.side_effect = ApiException(
        status=500, reason="Internal Server Error"
    )

    with pytest.raises(ApiException):
        await create_aim_model(kube_client, "test-ns", _aim_model_manifest())


# --- patch_aim_model ---


@pytest.mark.asyncio
async def test_patch_aim_model_success(kube_client: MagicMock) -> None:
    """patch_aim_model returns the parsed AIMModelResource and uses merge-patch."""
    patched_manifest = _aim_model_manifest(name="my-aim-model")
    kube_client.custom_objects.patch_namespaced_custom_object.return_value = patched_manifest

    result = await patch_aim_model(
        kube_client, "test-ns", "my-aim-model", {"metadata": {"annotations": {"foo": "bar"}}}
    )

    assert isinstance(result, AIMModelResource)
    assert result.metadata.name == "my-aim-model"
    call_kwargs = kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["plural"] == "aimmodels"
    assert call_kwargs["name"] == "my-aim-model"
    assert call_kwargs["_content_type"] == "application/merge-patch+json"


@pytest.mark.parametrize("status,reason", [(500, "Internal Server Error"), (422, "Unprocessable Entity")])
@pytest.mark.asyncio
async def test_patch_aim_model_wraps_api_exception_as_external_service_error(
    kube_client: MagicMock, status: int, reason: str
) -> None:
    """K8s ApiException wraps as ExternalServiceError so the onboard endpoint's
    documented 502 response is honoured. Status passthrough (e.g. surfacing
    admission 422 or upstream 5xx directly) requires registering an async
    ApiException handler — the FastAPI app only registers the sync
    ``kubernetes.client.exceptions.ApiException`` today, so a bare re-raise
    of ``kubernetes_asyncio.client.ApiException`` would fall through to the
    generic handler as an opaque 500. Tracked as a separate follow-up."""
    api_error = ApiException(status=status, reason=reason)
    kube_client.custom_objects.patch_namespaced_custom_object.side_effect = api_error

    with pytest.raises(ExternalServiceError, match="Failed to patch AIMModel 'my-aim-model'") as exc_info:
        await patch_aim_model(kube_client, "test-ns", "my-aim-model", {"metadata": {}})
    assert exc_info.value.__cause__ is api_error


@pytest.mark.asyncio
async def test_list_aim_models_with_label_selector(kube_client: MagicMock) -> None:
    """Test list_aim_models passes label_selector to Kubernetes API."""
    model_manifest = _aim_model_manifest(name="ft-model-1")
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [model_manifest]}

    result = await list_aim_models(kube_client, "test-ns", label_selector="workload-type=FINE_TUNING")

    assert len(result) == 1
    assert result[0].metadata.name == "ft-model-1"
    kube_client.custom_objects.list_namespaced_custom_object.assert_called_once()
    call_kwargs = kube_client.custom_objects.list_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["label_selector"] == "workload-type=FINE_TUNING"


@pytest.mark.asyncio
async def test_list_aim_services_runs_helpers_concurrently(kube_client: MagicMock) -> None:
    """The three enrichment helpers must run concurrently when a capability filter is set.

    Each helper waits on a shared barrier released only after all three have
    started. Sequential execution would deadlock on asyncio.wait_for and
    fail the test.
    """
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    barrier = asyncio.Event()
    call_count = 0
    expected_calls = 3

    def make_gated(return_value):
        async def gated(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == expected_calls:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), timeout=1.0)
            return return_value

        return gated

    httproutes_gate = make_gated({})
    isvc_gate = make_gated({})
    aims_gate = make_gated({})

    with (
        patch("app.aims.gateway._get_httproutes_for_aim_services", side_effect=httproutes_gate),
        patch("app.aims.gateway._get_isvc_names", side_effect=isvc_gate),
        patch("app.aims.gateway._get_aims_by_name", side_effect=aims_gate),
    ):
        await list_aim_services(kube_client, "test-ns", capability=InferenceCapability.CHAT)

    assert call_count == expected_calls


@pytest.mark.asyncio
async def test_list_aim_services_skips_aims_lookup_when_not_chattable(kube_client: MagicMock) -> None:
    """When no capability filter is set, _get_aims_by_name must not be called.

    The K8s call for cluster-scoped AIMs is expensive; the helper short-circuits
    to an empty dict instead of hitting the API server.
    """
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    with (
        patch("app.aims.gateway._get_httproutes_for_aim_services", new=AsyncMock(return_value={})),
        patch("app.aims.gateway._get_isvc_names", new=AsyncMock(return_value={})),
        patch("app.aims.gateway._get_aims_by_name", new=AsyncMock(return_value={})) as mock_aims,
    ):
        await list_aim_services(kube_client, "test-ns", capability=None)

    mock_aims.assert_not_called()


# --- AIMArtifact gateway ---


def _artifact_item(name: str, managed_by: str = "aiwb") -> dict:
    """Minimal raw AIMArtifact list item as the API server returns it."""
    return {
        "metadata": {"name": name, "labels": {"app.kubernetes.io/managed-by": managed_by}},
        "spec": {"type": "adapter"},
    }


def _service_item(name: str, spec: object) -> dict:
    """Raw AIMService list item, with spec left untyped so malformed shapes can be exercised."""
    return {"metadata": {"name": name}, "spec": spec}


@pytest.mark.asyncio
async def test_get_aim_artifact_missing_returns_none(kube_client: MagicMock) -> None:
    """A 404 means the artifact does not exist, which is not an error for the caller."""
    kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404, reason="Not Found")

    assert await get_aim_artifact(kube_client, "test-ns", "adapter-1") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status,reason", [(500, "Internal Server Error"), (403, "Forbidden")])
async def test_get_aim_artifact_wraps_non_404_as_external_service_error(
    kube_client: MagicMock, status: int, reason: str
) -> None:
    """An unreachable cluster must surface as 502 like the other artifact calls, not a raw 500."""
    api_error = ApiException(status=status, reason=reason)
    kube_client.custom_objects.get_namespaced_custom_object.side_effect = api_error

    with pytest.raises(ExternalServiceError, match="Failed to get AIMArtifact 'adapter-1'") as exc_info:
        await get_aim_artifact(kube_client, "test-ns", "adapter-1")

    assert exc_info.value.__cause__ is api_error


@pytest.mark.asyncio
async def test_get_aim_artifact_uses_legacy_api_version(kube_client: MagicMock) -> None:
    """AIMArtifact is served under v1alpha1 while AIMService moved to v1alpha2."""
    kube_client.custom_objects.get_namespaced_custom_object.return_value = _artifact_item("adapter-1")

    await get_aim_artifact(kube_client, "test-ns", "adapter-1")

    kwargs = kube_client.custom_objects.get_namespaced_custom_object.call_args.kwargs
    assert (kwargs["version"], kwargs["plural"]) == ("v1alpha1", "aimartifacts")


@pytest.mark.asyncio
async def test_list_aim_artifacts_forwards_label_selector(kube_client: MagicMock) -> None:
    """The caller's membership rule must reach the API server rather than being filtered in Python."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    await list_aim_artifacts_by_label_selector(kube_client, "test-ns", "app.kubernetes.io/managed-by in (aiwb)")

    kwargs = kube_client.custom_objects.list_namespaced_custom_object.call_args.kwargs
    assert kwargs["label_selector"] == "app.kubernetes.io/managed-by in (aiwb)"
    assert (kwargs["version"], kwargs["plural"]) == ("v1alpha1", "aimartifacts")


@pytest.mark.asyncio
async def test_list_aim_artifacts_missing_crd_returns_empty(kube_client: MagicMock) -> None:
    """A cluster without the AIMArtifact CRD installed simply has no artifacts."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(status=404, reason="Not Found")

    assert await list_aim_artifacts_by_label_selector(kube_client, "test-ns", "") == []


@pytest.mark.asyncio
async def test_list_aim_artifacts_wraps_non_404_as_external_service_error(kube_client: MagicMock) -> None:
    """An unreachable cluster must not be reported to the caller as an empty project."""
    api_error = ApiException(status=500, reason="Internal Server Error")
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = api_error

    with pytest.raises(ExternalServiceError, match="Failed to list AIMArtifacts") as exc_info:
        await list_aim_artifacts_by_label_selector(kube_client, "test-ns", "")

    assert exc_info.value.__cause__ is api_error


@pytest.mark.asyncio
async def test_list_aim_artifacts_skips_unparseable_items(kube_client: MagicMock) -> None:
    """One artifact of an unexpected shape must not hide the rest of the project's artifacts."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [_artifact_item("good-1"), {"metadata": "not-a-dict"}, _artifact_item("good-2")]
    }

    artifacts = await list_aim_artifacts_by_label_selector(kube_client, "test-ns", "")

    assert [a.metadata.name for a in artifacts] == ["good-1", "good-2"]


@pytest.mark.asyncio
async def test_source_uri_listing_surfaces_artifacts_the_typed_listing_drops(kube_client: MagicMock) -> None:
    """A record too malformed to validate still points somewhere, and safety checks must see it."""
    unparseable = {"metadata": {"name": "broken-1", "labels": "not-a-dict"}, "spec": {"sourceUri": "s3://bucket/b/"}}
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [{**_artifact_item("good-1"), "spec": {"sourceUri": "s3://bucket/a/"}}, unparseable]
    }

    typed = await list_aim_artifacts_by_label_selector(kube_client, "test-ns", "")
    assert [a.metadata.name for a in typed] == ["good-1"]

    assert await list_aim_artifact_source_uris(kube_client, "test-ns") == {
        "good-1": "s3://bucket/a/",
        "broken-1": "s3://bucket/b/",
    }


@pytest.mark.asyncio
async def test_source_uri_listing_omits_artifacts_recording_no_location(kube_client: MagicMock) -> None:
    """An artifact naming no source claims no storage, so it is absent rather than mapped to None."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [_artifact_item("no-source"), {"metadata": {"name": "odd"}, "spec": {"sourceUri": 42}}, "not-an-item"]
    }

    assert await list_aim_artifact_source_uris(kube_client, "test-ns") == {}


@pytest.mark.asyncio
async def test_source_uri_listing_is_not_narrowed_by_a_label_selector(kube_client: MagicMock) -> None:
    """A foreign record claims a prefix as effectively as a platform one, so none may be filtered out."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    await list_aim_artifact_source_uris(kube_client, "test-ns")

    assert "label_selector" not in kube_client.custom_objects.list_namespaced_custom_object.call_args.kwargs


@pytest.mark.asyncio
async def test_delete_aim_artifact_returns_true_when_accepted(kube_client: MagicMock) -> None:
    """A successful delete tells the caller the removal was actually started."""
    assert await delete_aim_artifact(kube_client, "test-ns", "adapter-1") is True

    kwargs = kube_client.custom_objects.delete_namespaced_custom_object.call_args.kwargs
    assert (kwargs["version"], kwargs["plural"], kwargs["name"]) == ("v1alpha1", "aimartifacts", "adapter-1")


@pytest.mark.asyncio
async def test_delete_aim_artifact_returns_false_when_already_gone(kube_client: MagicMock) -> None:
    """Deleting an absent artifact reaches the desired end state without raising."""
    kube_client.custom_objects.delete_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )

    assert await delete_aim_artifact(kube_client, "test-ns", "adapter-1") is False


@pytest.mark.asyncio
async def test_delete_aim_artifact_wraps_non_404_as_external_service_error(kube_client: MagicMock) -> None:
    """A refused delete must not be reported as a successful no-op."""
    api_error = ApiException(status=403, reason="Forbidden")
    kube_client.custom_objects.delete_namespaced_custom_object.side_effect = api_error

    with pytest.raises(ExternalServiceError, match="Failed to delete AIMArtifact 'adapter-1'") as exc_info:
        await delete_aim_artifact(kube_client, "test-ns", "adapter-1")

    assert exc_info.value.__cause__ is api_error


@pytest.mark.asyncio
async def test_list_aim_services_referencing_artifact_matches_attached_adapter(kube_client: MagicMock) -> None:
    """A deployment counts as a reference only when it attaches this adapter by name."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [
            _service_item("attaches-it", {"adapters": [{"name": "other"}, {"name": "adapter-1"}]}),
            _service_item("attaches-another", {"adapters": [{"name": "other"}]}),
            _service_item("attaches-none", {"model": "base"}),
        ]
    }

    referencing = await list_aim_services_referencing_artifact(kube_client, "test-ns", "adapter-1")

    assert referencing == ["attaches-it"]
    kwargs = kube_client.custom_objects.list_namespaced_custom_object.call_args.kwargs
    assert (kwargs["version"], kwargs["plural"]) == ("v1alpha2", "aimservices")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_spec",
    [
        "not-a-dict",
        None,
        {"adapters": "not-a-list"},
        {"adapters": ["not-a-dict"]},
        {"adapters": [None]},
    ],
)
async def test_list_aim_services_referencing_artifact_tolerates_malformed_neighbour(
    kube_client: MagicMock, malformed_spec: object
) -> None:
    """One malformed AIMService must not make every artifact in the namespace undeletable."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [
            _service_item("malformed", malformed_spec),
            _service_item("attaches-it", {"adapters": [{"name": "adapter-1"}]}),
        ]
    }

    assert await list_aim_services_referencing_artifact(kube_client, "test-ns", "adapter-1") == ["attaches-it"]


@pytest.mark.asyncio
async def test_list_aim_services_referencing_artifact_raises_when_cluster_unreachable(
    kube_client: MagicMock,
) -> None:
    """An unchecked namespace must never read as "no references" and let an in-use adapter be deleted."""
    api_error = ApiException(status=500, reason="Internal Server Error")
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = api_error

    with pytest.raises(ExternalServiceError, match="Failed to list AIMServices") as exc_info:
        await list_aim_services_referencing_artifact(kube_client, "test-ns", "adapter-1")

    assert exc_info.value.__cause__ is api_error


@pytest.mark.asyncio
async def test_list_aim_services_referencing_artifact_matches_a_fully_modelled_reference(
    kube_client: MagicMock,
) -> None:
    """The shape AIWB itself writes must match, not only the loose one an operator might hand-write."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [_service_item("attaches-it", {"adapters": [{"kind": "AIMArtifact", "name": "adapter-1"}]})]
    }

    assert await list_aim_services_referencing_artifact(kube_client, "test-ns", "adapter-1") == ["attaches-it"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spec",
    [
        pytest.param({"model": {"name": "base"}}, id="key-absent"),
        pytest.param({"adapters": None}, id="explicit-null"),
        pytest.param({"adapters": []}, id="empty"),
    ],
)
async def test_list_aim_services_referencing_artifact_ignores_a_service_with_no_adapters(
    kube_client: MagicMock, spec: dict
) -> None:
    """A deployment serving no adapters holds no artifact, so it must not block a deletion."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [_service_item("plain", spec)]}

    assert await list_aim_services_referencing_artifact(kube_client, "test-ns", "adapter-1") == []


@pytest.mark.asyncio
async def test_list_aim_services_referencing_artifact_falls_back_to_the_raw_name(kube_client: MagicMock) -> None:
    """A reference AIWB cannot parse is a reference all the same: reading past it would let live
    adapter weights be deleted out from under a running deployment."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [_service_item("attaches-it", {"adapters": [{"kind": "SomethingElse", "name": "adapter-1"}]})]
    }

    assert await list_aim_services_referencing_artifact(kube_client, "test-ns", "adapter-1") == ["attaches-it"]


@pytest.mark.asyncio
async def test_list_aim_services_referencing_artifact_keeps_other_artifacts_deletable(
    kube_client: MagicMock,
) -> None:
    """The raw-name fallback stays name-scoped, and an entry it handles does not abort the scan.

    An unparseable entry blocks the artifact it names and no other, and the service listed after it
    is still reached -- otherwise one malformed entry would pin every artifact in the namespace, or
    hide a genuine reference behind itself.
    """
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [
            _service_item("malformed", {"adapters": [{"kind": "SomethingElse", "name": "adapter-1"}]}),
            _service_item("attaches-it", {"adapters": [{"name": "adapter-1"}]}),
        ]
    }

    assert await list_aim_services_referencing_artifact(kube_client, "test-ns", "adapter-2") == []
    assert await list_aim_services_referencing_artifact(kube_client, "test-ns", "adapter-1") == [
        "malformed",
        "attaches-it",
    ]


@pytest.mark.asyncio
async def test_list_aim_profile_sets_for_model_filters_on_model_label(kube_client: MagicMock) -> None:
    """The list is scoped to the namespace and filtered on the model.name label."""
    default_set = make_aim_profile_set(name="m-profiles-abc", model_name="my-model")
    aiwb_set = make_aim_profile_set(name="m-fast", model_name="my-model", is_aiwb_authored=True)
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [default_set.model_dump(by_alias=True), aiwb_set.model_dump(by_alias=True)]
    }

    result = await list_aim_profile_sets_for_model(kube_client, "test-ns", "my-model")

    assert {s.metadata.name for s in result} == {"m-profiles-abc", "m-fast"}
    call_kwargs = kube_client.custom_objects.list_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["namespace"] == "test-ns"
    assert call_kwargs["label_selector"] == "aim.eai.amd.com/model.name=my-model"


@pytest.mark.asyncio
async def test_list_aim_profile_sets_for_model_is_namespace_isolated(kube_client: MagicMock) -> None:
    """Two projects each with a same-named model: a list for one namespace only ever
    queries that namespace, so the other project's sets can never leak in."""
    project_a_set = make_aim_profile_set(name="shared-profiles-a", model_name="shared", namespace="proj-a")
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [project_a_set.model_dump(by_alias=True)]
    }

    result = await list_aim_profile_sets_for_model(kube_client, "proj-a", "shared")

    assert [s.metadata.name for s in result] == ["shared-profiles-a"]
    assert kube_client.custom_objects.list_namespaced_custom_object.call_args.kwargs["namespace"] == "proj-a"


@pytest.mark.asyncio
async def test_list_aim_profile_sets_for_model_propagates_api_errors(kube_client: MagicMock) -> None:
    """Non-404 ApiException surfaces as ExternalServiceError."""
    kube_client.custom_objects.list_namespaced_custom_object.side_effect = ApiException(status=403, reason="Forbidden")

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await list_aim_profile_sets_for_model(kube_client, "test-ns", "my-model")


@pytest.mark.asyncio
async def test_list_aim_profile_sets_for_model_skips_unparseable_sets(kube_client: MagicMock) -> None:
    """Without strict, a malformed set is dropped so an overview still renders."""
    good_set = make_aim_profile_set(name="m-profiles-abc", model_name="my-model")
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [{"metadata": None}, good_set.model_dump(by_alias=True)]
    }

    result = await list_aim_profile_sets_for_model(kube_client, "test-ns", "my-model")

    assert [s.metadata.name for s in result] == ["m-profiles-abc"]


@pytest.mark.asyncio
async def test_list_aim_profile_sets_for_model_strict_rejects_unparseable_sets(kube_client: MagicMock) -> None:
    """A set that silently vanished is indistinguishable from one the model does not
    have, so callers deciding from the list ask to fail instead."""
    kube_client.custom_objects.list_namespaced_custom_object.return_value = {"items": [{"metadata": None}]}

    with pytest.raises(ExternalServiceError, match="Failed to parse AIMProfileSet"):
        await list_aim_profile_sets_for_model(kube_client, "test-ns", "my-model", strict=True)


@pytest.mark.asyncio
async def test_get_aim_profile_set_by_name_returns_match(kube_client: MagicMock) -> None:
    profile_set = make_aim_profile_set(name="m-profiles-abc", model_name="my-model")
    kube_client.custom_objects.get_namespaced_custom_object.return_value = profile_set.model_dump(by_alias=True)

    result = await get_aim_profile_set_by_name(kube_client, "test-ns", "m-profiles-abc")

    assert result is not None
    assert result.metadata.name == "m-profiles-abc"


@pytest.mark.asyncio
async def test_get_aim_profile_set_by_name_returns_none_on_404(kube_client: MagicMock) -> None:
    kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404, reason="Not Found")

    result = await get_aim_profile_set_by_name(kube_client, "test-ns", "missing")
    assert result is None


@pytest.mark.asyncio
async def test_get_aim_profile_set_by_name_propagates_api_errors(kube_client: MagicMock) -> None:
    kube_client.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=403, reason="Forbidden")

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await get_aim_profile_set_by_name(kube_client, "test-ns", "anything")


@pytest.mark.asyncio
async def test_create_aim_profile_set_success(kube_client: MagicMock) -> None:
    profile_set = make_aim_profile_set(name="m-fast", model_name="my-model", is_aiwb_authored=True)
    manifest = profile_set.model_dump(by_alias=True)
    manifest["metadata"]["name"] = "m-fast"
    kube_client.custom_objects.create_namespaced_custom_object.return_value = profile_set.model_dump(by_alias=True)

    result = await create_aim_profile_set(kube_client, "test-ns", manifest)

    assert result.metadata.name == "m-fast"
    kube_client.custom_objects.create_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_create_aim_profile_set_409_maps_to_conflict_exception(kube_client: MagicMock) -> None:
    kube_client.custom_objects.create_namespaced_custom_object.side_effect = ApiException(status=409, reason="Conflict")

    with pytest.raises(ConflictException, match="already exists"):
        await create_aim_profile_set(kube_client, "test-ns", {"metadata": {"name": "m-fast"}})


@pytest.mark.asyncio
async def test_create_aim_profile_set_non_409_propagates(kube_client: MagicMock) -> None:
    kube_client.custom_objects.create_namespaced_custom_object.side_effect = ApiException(
        status=403, reason="Forbidden"
    )

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await create_aim_profile_set(kube_client, "test-ns", {"metadata": {"name": "m-fast"}})


@pytest.mark.asyncio
async def test_patch_aim_profile_set_uses_merge_patch(kube_client: MagicMock) -> None:
    profile_set = make_aim_profile_set(name="m-fast", model_name="my-model", is_aiwb_authored=True)
    kube_client.custom_objects.patch_namespaced_custom_object.return_value = profile_set.model_dump(by_alias=True)

    result = await patch_aim_profile_set(kube_client, "test-ns", "m-fast", {"spec": {"version": "1"}})

    assert result.metadata.name == "m-fast"
    call_kwargs = kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["_content_type"] == "application/merge-patch+json"


@pytest.mark.asyncio
async def test_patch_aim_profile_set_propagates_api_errors(kube_client: MagicMock) -> None:
    kube_client.custom_objects.patch_namespaced_custom_object.side_effect = ApiException(status=500, reason="Boom")

    with pytest.raises(ExternalServiceError, match="Failed to patch AIMProfileSet 'm-fast'"):
        await patch_aim_profile_set(kube_client, "test-ns", "m-fast", {"spec": {}})


@pytest.mark.asyncio
async def test_delete_aim_profile_set_success(kube_client: MagicMock) -> None:
    await delete_aim_profile_set(kube_client, "test-ns", "m-fast")
    kube_client.custom_objects.delete_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_delete_aim_profile_set_noop_on_404(kube_client: MagicMock) -> None:
    kube_client.custom_objects.delete_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )

    await delete_aim_profile_set(kube_client, "test-ns", "missing")


@pytest.mark.asyncio
async def test_delete_aim_profile_set_propagates_api_errors(kube_client: MagicMock) -> None:
    kube_client.custom_objects.delete_namespaced_custom_object.side_effect = ApiException(
        status=403, reason="Forbidden"
    )

    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await delete_aim_profile_set(kube_client, "test-ns", "m-fast")


@pytest.mark.asyncio
async def test_delete_aim_profile_success(kube_client: MagicMock) -> None:
    await delete_aim_profile(kube_client, "test-ns", "stale-profile")

    kwargs = kube_client.custom_objects.delete_namespaced_custom_object.call_args.kwargs
    assert (kwargs["version"], kwargs["plural"], kwargs["name"]) == ("v1alpha2", "aimprofiles", "stale-profile")


@pytest.mark.asyncio
async def test_delete_aim_profile_noop_on_404(kube_client: MagicMock) -> None:
    kube_client.custom_objects.delete_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )

    await delete_aim_profile(kube_client, "test-ns", "missing")


@pytest.mark.asyncio
async def test_delete_aim_profile_wraps_non_404_errors(kube_client: MagicMock) -> None:
    kube_client.custom_objects.delete_namespaced_custom_object.side_effect = ApiException(
        status=403, reason="Forbidden"
    )

    with pytest.raises(ExternalServiceError, match="Failed to delete AIMProfile 'stale-profile'"):
        await delete_aim_profile(kube_client, "test-ns", "stale-profile")
