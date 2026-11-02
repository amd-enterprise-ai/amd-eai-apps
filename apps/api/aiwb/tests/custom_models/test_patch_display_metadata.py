# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for PATCH display metadata on custom-onboarded AIMModels."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import tenacity
import yaml
from kubernetes_asyncio.client import ApiException, CustomObjectsApi
from minio.error import S3Error
from pydantic import ValidationError

from api_common.exceptions import ConflictException, ExternalServiceError, NotFoundException, ValidationException
from app.aims.crds import AIMModelResource, AIMProfileResource
from app.custom_models.constants import (
    CANONICAL_REPO_ID_ANNOTATION,
    MODEL_DISPLAY_NAME_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
    SOURCE_DESCRIPTION_ANNOTATION,
    SOURCE_TAGS_ANNOTATION,
    SOURCE_URI_ANNOTATION,
)
from app.custom_models.manifest import write_manifest_to_s3
from app.custom_models.schemas import CustomModelPatchRequest
from app.custom_models.service import (
    _model_resource_to_manifest_document,
    patch_onboarded_model,
)
from app.custom_models.utils import display_metadata_response_from_model, parse_source_tags
from app.dispatch.crds import K8sMetadata
from app.dispatch.kube_client import KubernetesClient
from app.minio import MinioClient
from app.workloads.constants import DISPLAY_NAME_ANNOTATION, MODEL_NAME_LABEL, MODEL_SOURCE_TYPE_LABEL
from app.workloads.enums import ModelSourceType
from tests.factory import make_aim_profile_set


@pytest.fixture(autouse=True)
def _disable_write_manifest_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_manifest_to_s3.retry, "wait", tenacity.wait_none())
    monkeypatch.setattr(write_manifest_to_s3.retry, "stop", tenacity.stop_after_attempt(1))


def _no_such_key_s3_error() -> S3Error:
    return S3Error(
        code="NoSuchKey",
        message="no such key",
        resource="key",
        request_id="r",
        host_id="h",
        response=MagicMock(status=404),
    )


@pytest.fixture
def mock_minio_client() -> MagicMock:
    mock = MagicMock(spec=MinioClient)
    mock.download_object.side_effect = _no_such_key_s3_error()
    return mock


def _make_custom_onboarded_model(
    *,
    name: str = "llama-3-8b-import-12345678",
    display_name: str = "Llama 3 8B",
    description: str = "An open model.",
    tags: list[str] | None = None,
) -> AIMModelResource:
    annotations: dict[str, str] = {
        SOURCE_URI_ANNOTATION: f"s3://test-bucket/test-namespace/custom-models/{name}/weights/",
        DISPLAY_NAME_ANNOTATION: display_name,
        MODEL_DISPLAY_NAME_ANNOTATION: display_name,
        SOURCE_DESCRIPTION_ANNOTATION: description,
    }
    if tags is not None:
        annotations[SOURCE_TAGS_ANNOTATION] = json.dumps(tags)
    sanitized = display_name.replace(" ", "-")
    return AIMModelResource(
        metadata=K8sMetadata(
            name=name,
            namespace="test-namespace",
            labels={
                MODEL_NAME_LABEL: sanitized,
                MODEL_SOURCE_TYPE_LABEL: ModelSourceType.CUSTOM,
            },
            annotations=annotations,
        ),
        spec={
            "modelSources": [
                {
                    "modelId": "meta-llama/Meta-Llama-3-8B-Instruct",
                    "sourceUri": annotations[SOURCE_URI_ANNOTATION],
                }
            ]
        },
    )


def _patched_model_stub(**overrides: Any) -> dict[str, Any]:
    base = _make_custom_onboarded_model().model_dump(by_alias=True)
    base.update(overrides)
    return base


_REPO_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
_EXISTING_IMAGE = "docker.io/amdenterpriseai/aim:1.0.0"


def _existing_model_sources(name: str) -> list[dict[str, Any]]:
    return [
        {
            "modelId": _REPO_ID,
            "sourceUri": f"s3://test-bucket/test-namespace/custom-models/{name}/weights/",
            "env": [{"name": "HF_TOKEN", "valueFrom": {"secretKeyRef": {"name": "hf-token", "key": "token"}}}],
        }
    ]


def _make_profiles_shaped_model(
    *,
    name: str = "llama-3-8b-import-12345678",
    display_name: str = "Llama 3 8B",
    image: str = _EXISTING_IMAGE,
    overrides_extra: dict[str, Any] | None = None,
) -> AIMModelResource:
    """A v1alpha2 custom AIMModel whose runtime settings live in spec.profiles.overrides (the editable shape)."""
    overrides: dict[str, Any] = {
        "aimId": _REPO_ID,
        "modelId": _REPO_ID,
        "image": image,
        "modelSources": _existing_model_sources(name),
    }
    if overrides_extra:
        overrides.update(overrides_extra)
    return AIMModelResource(
        metadata=K8sMetadata(
            name=name,
            namespace="test-namespace",
            labels={
                MODEL_NAME_LABEL: display_name.replace(" ", "-"),
                MODEL_SOURCE_TYPE_LABEL: ModelSourceType.CUSTOM,
            },
            annotations={
                DISPLAY_NAME_ANNOTATION: display_name,
                MODEL_DISPLAY_NAME_ANNOTATION: display_name,
            },
        ),
        spec={
            "profiles": {
                "derivedFrom": {"selector": {"role": "base", "modelRef": {"name": "aim-base", "scope": "Namespace"}}},
                "versionPolicy": "all",
                "overrides": overrides,
            }
        },
    )


def _make_aim_profile(name: str = "llama-3-8b-profile-default") -> AIMProfileResource:
    return AIMProfileResource(metadata=K8sMetadata(name=name, namespace="test-namespace"))


@pytest.fixture
def mock_profile_gateway() -> Any:
    """Patch the AIMProfile lookup and patch helpers used by runtime-profile edits.

    Yields ``(find_mock, patch_mock)``; both default to a ready profile. Tests
    that exercise the not-ready path set ``find_mock.return_value = None``.

    ``find_mock`` stands in for the Default set's effective-profile resolution the
    patch fallback uses when the edit does not itself narrow the Default.
    """
    profile = _make_aim_profile()
    with (
        patch(
            "app.custom_models.service._default_effective_profile",
            new_callable=AsyncMock,
            return_value=profile,
        ) as find_mock,
        patch(
            "app.custom_models.service.patch_aim_profile",
            new_callable=AsyncMock,
            return_value=profile,
        ) as patch_mock,
    ):
        yield find_mock, patch_mock


@pytest.fixture
def mock_kube_client() -> MagicMock:
    # Both layers carry spec= so a typo in a KubernetesClient attribute or a
    # CustomObjectsApi method name fails the test immediately rather than
    # silently auto-creating a mock attribute.
    mock = MagicMock(spec=KubernetesClient)
    mock.custom_objects = MagicMock(spec=CustomObjectsApi)
    mock.custom_objects.list_namespaced_custom_object = AsyncMock(return_value={"items": []})
    mock.custom_objects.patch_namespaced_custom_object = AsyncMock(return_value=_patched_model_stub())
    return mock


async def test_patch_display_name_only_patches_name_labels(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    existing = _make_custom_onboarded_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    patched = _make_custom_onboarded_model(display_name="Renamed Model")
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )

    request = CustomModelPatchRequest(display_name="Renamed Model")
    result = await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=request,
    )

    patch_kwargs = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs
    patch_body = patch_kwargs["body"]
    assert "labels" in patch_body["metadata"]
    assert "annotations" in patch_body["metadata"]
    assert MODEL_NAME_LABEL in patch_body["metadata"]["labels"]
    assert DISPLAY_NAME_ANNOTATION in patch_body["metadata"]["annotations"]
    assert MODEL_DISPLAY_NAME_ANNOTATION in patch_body["metadata"]["annotations"]
    assert SOURCE_DESCRIPTION_ANNOTATION not in patch_body["metadata"]["annotations"]
    assert SOURCE_TAGS_ANNOTATION not in patch_body["metadata"]["annotations"]
    assert result.display_name == "Renamed Model"


async def test_patch_tags_serialized_and_returned(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    existing = _make_custom_onboarded_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    patched = _make_custom_onboarded_model(tags=["llama", "chat"])
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )

    request = CustomModelPatchRequest(tags=["llama", "chat"])
    result = await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=request,
    )

    patch_body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert json.loads(patch_body["metadata"]["annotations"][SOURCE_TAGS_ANNOTATION]) == ["llama", "chat"]
    assert result.tags == ["llama", "chat"]


def test_tags_round_trip_through_source_annotation() -> None:
    tags = ["text-generation", "license:apache-2.0"]
    assert parse_source_tags(json.dumps(tags)) == tags


def test_display_name_falls_back_to_platform_annotation_not_sanitized_label() -> None:
    # When the custom-models display annotation is absent, the response must use the
    # raw platform display-name annotation, never the sanitized (lowercased/truncated)
    # MODEL_NAME_LABEL value.
    model = AIMModelResource(
        metadata=K8sMetadata(
            name="llama-3-8b-import-12345678",
            namespace="test-namespace",
            labels={MODEL_NAME_LABEL: "llama-3-8b"},
            annotations={DISPLAY_NAME_ANNOTATION: "Llama 3 8B"},
        ),
        spec={"modelSources": []},
    )

    result = display_metadata_response_from_model(model)

    assert result.display_name == "Llama 3 8B"


def test_display_name_falls_back_to_cr_name_when_no_annotations_present() -> None:
    model = AIMModelResource(
        metadata=K8sMetadata(
            name="llama-3-8b-import-12345678",
            namespace="test-namespace",
            labels={MODEL_NAME_LABEL: "llama-3-8b"},
        ),
        spec={"modelSources": []},
    )

    result = display_metadata_response_from_model(model)

    assert result.display_name == "llama-3-8b-import-12345678"


def test_model_manifest_document_strips_empty_legacy_fields_for_profiles_shape() -> None:
    # A v1alpha2 profiles-shaped AIMModel must not emit the default-empty legacy
    # fields (image/modelSources/env) alongside profiles, or the durable manifest
    # trips the CEL "image XOR profiles" rule and becomes non-reapplyable.
    model = AIMModelResource(
        metadata=K8sMetadata(name="llama-3-8b-import-12345678", namespace="test-namespace"),
        spec={
            "profiles": {
                "derivedFrom": {
                    "selector": {"role": "base", "modelRef": {"name": "base-model", "scope": "cluster"}},
                },
                "versionPolicy": "all",
                "overrides": {
                    "aimId": "meta-llama/Meta-Llama-3-8B-Instruct",
                    "modelId": "meta-llama/Meta-Llama-3-8B-Instruct",
                    "image": "docker.io/example/llama:1.0.0",
                    "modelSources": [{"modelId": "meta-llama/Meta-Llama-3-8B-Instruct", "sourceUri": "s3://b/k/"}],
                },
            }
        },
    )

    document = _model_resource_to_manifest_document(model)
    spec = document["spec"]

    assert "profiles" in spec
    assert "image" not in spec
    assert "modelSources" not in spec
    assert "env" not in spec


def test_model_manifest_document_keeps_legacy_fields_for_flat_shape() -> None:
    # Legacy (v1alpha1 flat) AIMModels have no profiles block; their populated
    # modelSources must be preserved in the durable manifest.
    model = _make_custom_onboarded_model()

    document = _model_resource_to_manifest_document(model)
    spec = document["spec"]

    assert "profiles" not in spec
    assert spec["modelSources"][0]["modelId"] == "meta-llama/Meta-Llama-3-8B-Instruct"


def test_parse_source_tags_drops_non_string_and_malformed_values() -> None:
    # CR annotations are externally mutable; a hand-edited value must not break
    # response construction. Non-string elements are dropped; non-list / non-JSON
    # values degrade to an empty list.
    assert parse_source_tags(json.dumps(["llama", 123, {"k": "v"}, None, "chat"])) == ["llama", "chat"]
    assert parse_source_tags(json.dumps({"not": "a list"})) == []
    assert parse_source_tags("not json") == []
    assert parse_source_tags(None) == []


async def test_patch_empty_body_raises_validation_error(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    request = CustomModelPatchRequest()
    with pytest.raises(ValidationException, match="At least one"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name="llama-3-8b-import-12345678",
            request=request,
        )


async def test_patch_explicit_nulls_treated_as_absent(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    request = CustomModelPatchRequest(display_name=None, description=None, tags=None)
    with pytest.raises(ValidationException, match="At least one"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name="llama-3-8b-import-12345678",
            request=request,
        )
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


def test_patch_request_rejects_empty_display_name() -> None:
    with pytest.raises(ValidationError):
        CustomModelPatchRequest(display_name="")


async def test_patch_missing_model_returns_404(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(side_effect=ApiException(status=404))

    request = CustomModelPatchRequest(display_name="New Name")
    with pytest.raises(NotFoundException, match="not found"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name="missing-model",
            request=request,
        )

    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


async def test_patch_non_byom_model_returns_404(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    finetuned = AIMModelResource(
        metadata=K8sMetadata(
            name="finetuned-model",
            namespace="test-namespace",
            annotations={SOURCE_URI_ANNOTATION: "s3://test-bucket/test-namespace/models/finetuned/weights/"},
        ),
        spec={"modelSources": []},
    )
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=finetuned.model_dump(by_alias=True)
    )

    request = CustomModelPatchRequest(display_name="New Name")
    with pytest.raises(NotFoundException, match="not found"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name="finetuned-model",
            request=request,
        )


async def test_patch_get_non_404_api_error_maps_to_external_service_error(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    # Non-404 K8s read failures (e.g. RBAC 403) must surface as the documented 502,
    # not leak as a generic 500 via the async ApiException the app does not handle.
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        side_effect=ApiException(status=403, reason="Forbidden")
    )

    request = CustomModelPatchRequest(display_name="New Name")
    with pytest.raises(ExternalServiceError, match="Forbidden"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name="llama-3-8b-import-12345678",
            request=request,
        )

    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


async def test_patch_display_name_check_non_404_api_error_maps_to_external_service_error(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    # The display-name uniqueness lookup is the second unprotected read; a non-404
    # failure there must also map to 502 rather than a generic 500.
    existing = _make_custom_onboarded_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.list_namespaced_custom_object = AsyncMock(
        side_effect=ApiException(status=403, reason="Forbidden")
    )

    request = CustomModelPatchRequest(display_name="Taken Name")
    with pytest.raises(ExternalServiceError, match="display-name availability"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=request,
        )

    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


async def test_patch_display_name_conflict_returns_409(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    existing = _make_custom_onboarded_model(name="model-a", display_name="Original")
    other = _make_custom_onboarded_model(name="model-b", display_name="Taken Name")
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.list_namespaced_custom_object = AsyncMock(
        return_value={"items": [other.model_dump(by_alias=True)]}
    )

    request = CustomModelPatchRequest(display_name="Taken Name")
    with pytest.raises(ConflictException, match="already exists"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=request,
        )


async def test_patch_display_name_check_scopes_lookup_to_custom_models(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    # The uniqueness lookup must filter to custom-onboarded models so a name
    # collision with a fine-tuned/official AIMModel (which also carry
    # MODEL_NAME_LABEL) does not spuriously 409 a custom-model rename.
    existing = _make_custom_onboarded_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.list_namespaced_custom_object = AsyncMock(return_value={"items": []})

    request = CustomModelPatchRequest(display_name="Renamed Model")
    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=request,
    )

    selector = mock_kube_client.custom_objects.list_namespaced_custom_object.call_args.kwargs["label_selector"]
    assert f"{MODEL_NAME_LABEL}=Renamed-Model" in selector
    assert f"{MODEL_SOURCE_TYPE_LABEL}={ModelSourceType.CUSTOM}" in selector


async def test_patch_syncs_manifest_to_s3(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    existing = _make_custom_onboarded_model()
    patched = _make_custom_onboarded_model(description="Updated description")
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )

    with patch(
        "app.custom_models.service._upsert_manifest_documents_to_s3_unlocked", new_callable=AsyncMock
    ) as sync_mock:
        request = CustomModelPatchRequest(description="Updated description")
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=request,
        )

    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_called_once()
    sync_mock.assert_called_once()
    # A metadata-only edit mirrors just the AIMModel document.
    documents = sync_mock.call_args.args[2]
    assert [doc["kind"] for doc in documents] == ["AIMModel"]
    assert documents[0]["metadata"]["name"] == existing.metadata.name


async def test_patch_returns_metadata_when_s3_mirror_sync_fails(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    """Cluster CRs are authoritative; a failed S3 mirror write must not turn PATCH into 500."""
    existing = _make_custom_onboarded_model()
    patched = _make_custom_onboarded_model(display_name="After Patch")
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )

    with patch(
        "app.custom_models.service._upsert_manifest_documents_to_s3_unlocked",
        new_callable=AsyncMock,
        side_effect=RuntimeError("minio down"),
    ):
        request = CustomModelPatchRequest(display_name="After Patch")
        result = await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=request,
        )

    assert result.name == patched.metadata.name
    assert result.display_name == "After Patch"
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_called_once()


async def test_patch_preserves_existing_aim_profile_in_manifest(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    existing = _make_custom_onboarded_model()
    patched = _make_custom_onboarded_model(tags=["new-tag"])
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )

    profile_doc = {
        "apiVersion": "aim.eai.amd.com/v1alpha2",
        "kind": "AIMProfile",
        "metadata": {"name": "profile-default", "namespace": "test-namespace"},
        "spec": {"model": {"name": existing.metadata.name}},
    }
    prior_manifest = yaml.safe_dump_all(
        [_model_resource_to_manifest_document(existing), profile_doc],
        sort_keys=False,
    ).encode()
    mock_minio_client.download_object.side_effect = None
    mock_minio_client.download_object.return_value = prior_manifest

    request = CustomModelPatchRequest(tags=["new-tag"])
    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=request,
    )

    uploaded = mock_minio_client.upload_object.call_args.kwargs["data"]
    docs = list(yaml.safe_load_all(uploaded.decode()))
    kinds = {(doc.get("kind"), doc.get("metadata", {}).get("name")) for doc in docs}
    assert ("AIMModel", existing.metadata.name) in kinds
    assert ("AIMProfile", "profile-default") in kinds


# ---------------------------------------------------------------------------
# Runtime-profile edits: image + customProfile
# ---------------------------------------------------------------------------


async def test_patch_runtime_profile_rejects_model_without_spec_profiles(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    """Legacy flat AIMModels must not accept runtime edits — empty modelSources would corrupt the CR."""
    existing = _make_custom_onboarded_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    with pytest.raises(ValidationException, match="spec.profiles"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=CustomModelPatchRequest(image="docker.io/amdenterpriseai/aim:2.0.0"),
        )
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


async def test_patch_runtime_profile_rejects_empty_overrides_model_sources(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    existing = _make_profiles_shaped_model()
    dumped = existing.model_dump(by_alias=True)
    dumped["spec"]["profiles"]["overrides"]["modelSources"] = []
    broken = AIMModelResource.model_validate(dumped)
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=broken.model_dump(by_alias=True)
    )
    with pytest.raises(ValidationException, match="modelSources"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=CustomModelPatchRequest(image="docker.io/amdenterpriseai/aim:2.0.0"),
        )
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()


async def test_patch_image_only_repatches_overrides_and_live_profile(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    _, patch_profile_mock = mock_profile_gateway
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    new_image = "docker.io/amdenterpriseai/aim:2.0.0"
    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=CustomModelPatchRequest(image=new_image),
    )

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    overrides = body["spec"]["profiles"]["overrides"]
    assert overrides["image"] == new_image
    # Identity and BYO weights are immutable across an image edit.
    assert overrides["aimId"] == _REPO_ID
    assert overrides["modelId"] == _REPO_ID
    assert overrides["modelSources"] == _existing_model_sources(existing.metadata.name)
    # An image-only edit changes no annotations/labels.
    assert "metadata" not in body

    # The live profile is repointed; with no customProfile there are no spec
    # knobs to merge, so the patch is image-ref-annotation only.
    patch_profile_mock.assert_awaited_once()
    profile_kwargs = patch_profile_mock.call_args.kwargs
    assert profile_kwargs["image_ref"] == new_image
    assert profile_kwargs["custom_profile_spec"] is None


async def test_patch_image_only_preserves_s3_identity_when_canonical_source_is_external_uri(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    """An S3-backed model edit must preserve existing aimId/modelId identity, not rewrite to canonical source URI."""
    _, patch_profile_mock = mock_profile_gateway
    model_name = "llama-3-8b-import-12345678"
    s3_identity = f"s3/{model_name}"
    external_source_uri = "s3://external-user-bucket/models/llama-3-8b/"
    existing = _make_profiles_shaped_model(
        name=model_name,
        overrides_extra={
            "aimId": s3_identity,
            "modelId": s3_identity,
            "modelSources": [{"modelId": s3_identity, "sourceUri": external_source_uri}],
        },
    )
    existing.metadata.annotations = existing.metadata.annotations or {}
    existing.metadata.annotations[CANONICAL_REPO_ID_ANNOTATION] = external_source_uri
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    new_image = "docker.io/amdenterpriseai/aim:2.0.0"
    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=model_name,
        request=CustomModelPatchRequest(image=new_image),
    )

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    overrides = body["spec"]["profiles"]["overrides"]
    assert overrides["image"] == new_image
    assert overrides["aimId"] == s3_identity
    assert overrides["modelId"] == s3_identity
    assert overrides["modelSources"] == [{"modelId": s3_identity, "sourceUri": external_source_uri}]

    profile_kwargs = patch_profile_mock.call_args.kwargs
    assert profile_kwargs["image_ref"] == new_image
    assert profile_kwargs["custom_profile_spec"] is None


async def test_patch_image_edit_aim_profile_k8s_error_maps_to_external_service_error(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    """AIMProfile patch failures must wrap as ExternalServiceError (502), not raw async ApiException."""
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    patched_body = existing.model_dump(by_alias=True)
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        side_effect=[
            patched_body,
            ApiException(status=403, reason="Forbidden"),
        ]
    )
    with patch(
        "app.custom_models.service._default_effective_profile",
        new_callable=AsyncMock,
        return_value=_make_aim_profile(),
    ):
        with pytest.raises(ExternalServiceError, match="Failed to patch AIMProfile"):
            await patch_onboarded_model(
                kube_client=mock_kube_client,
                minio_client=mock_minio_client,
                namespace="test-namespace",
                name=existing.metadata.name,
                request=CustomModelPatchRequest(image="docker.io/amdenterpriseai/aim:2.0.0"),
            )


async def test_patch_custom_profile_rewrites_overrides_and_merges_profile_spec(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    _, patch_profile_mock = mock_profile_gateway
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    custom_profile = {"engine": "vllm", "engineArgs": {"max-model-len": 8192}, "precision": "float16"}
    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=CustomModelPatchRequest(image=_EXISTING_IMAGE, custom_profile=custom_profile),
    )

    overrides = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"][
        "profiles"
    ]["overrides"]
    # Opaque runtime knobs flow into the overrides verbatim, alongside the
    # server-stamped reserved identity/image/weights keys.
    assert overrides["engine"] == "vllm"
    assert overrides["engineArgs"] == {"max-model-len": 8192}
    assert overrides["precision"] == "float16"
    assert overrides["image"] == _EXISTING_IMAGE
    assert overrides["aimId"] == _REPO_ID

    # The live profile spec is merged with runtime knobs only — never the
    # reserved keys, which aim-engine derives from the AIMModel.
    profile_spec = patch_profile_mock.call_args.kwargs["custom_profile_spec"]
    assert profile_spec == custom_profile
    assert "aimId" not in profile_spec
    assert "modelSources" not in profile_spec


async def test_patch_custom_profile_precision_stamps_durable_annotation(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    """Precision is pruned from overrides, so an edited precision must also land
    on the durable annotation the edit prefill and deploy default read back."""
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=CustomModelPatchRequest(image=_EXISTING_IMAGE, custom_profile={"precision": "fp8"}),
    )

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert body["metadata"]["annotations"][MODEL_PRECISION_ANNOTATION] == "fp8"


async def test_patch_custom_profile_precision_null_clears_durable_annotation(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    """A null precision resets to the aim-engine default (merge-patch semantics),
    so the durable annotation must be cleared with a null value rather than left
    stale for the edit prefill and deploy default to read."""
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=CustomModelPatchRequest(image=_EXISTING_IMAGE, custom_profile={"precision": None}),
    )

    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    # Null annotation value deletes the key under merge-patch, resetting the stored precision.
    assert body["metadata"]["annotations"][MODEL_PRECISION_ANNOTATION] is None


async def test_patch_persists_runtime_profile_fields_from_edit_wizard(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    """An edit-wizard PATCH (canonical acceleratorModel + engineArgs/engineEnv) must rewrite overrides and merge onto the live profile spec."""
    _, patch_profile_mock = mock_profile_gateway
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    custom_profile = {
        "imageFamilyId": "aim-base",
        "acceleratorType": "gpu",
        "acceleratorModel": "MI300X",
        "acceleratorCount": 1,
        "precision": "fp16",
        "engineArgs": {"max-model-len": 8192},
        # Sent as name/value entries; collapsed to a map on both overrides and the
        # live-profile spec patch (env var names stay outside the camelCase contract).
        "engineEnv": [{"name": "VLLM_ROCM_USE_AITER", "value": "1"}],
    }
    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=CustomModelPatchRequest(image=_EXISTING_IMAGE, custom_profile=custom_profile),
    )

    overrides = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"][
        "profiles"
    ]["overrides"]
    assert overrides["acceleratorModel"] == "MI300X"
    assert overrides["precision"] == "fp16"
    assert overrides["engineArgs"] == {"max-model-len": 8192}
    assert overrides["engineEnv"] == {"VLLM_ROCM_USE_AITER": "1"}

    profile_spec = patch_profile_mock.call_args.kwargs["custom_profile_spec"]
    assert profile_spec["engineArgs"] == {"max-model-len": 8192}
    assert profile_spec["engineEnv"] == {"VLLM_ROCM_USE_AITER": "1"}


async def test_patch_custom_profile_null_field_preserved_for_reset(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    # Reset-to-default sends an explicit null; merge-patch deletes the key, so
    # the null must survive into both the overrides body and the profile spec
    # patch (an exclude_none dump would silently swallow the reset).
    _, patch_profile_mock = mock_profile_gateway
    existing = _make_profiles_shaped_model(overrides_extra={"engineArgs": {"max-model-len": 4096}})
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=CustomModelPatchRequest(image=_EXISTING_IMAGE, custom_profile={"engineArgs": None}),
    )

    overrides = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"][
        "profiles"
    ]["overrides"]
    assert "engineArgs" in overrides
    assert overrides["engineArgs"] is None
    assert patch_profile_mock.call_args.kwargs["custom_profile_spec"] == {"engineArgs": None}


async def test_patch_dropping_one_map_key_tombstones_it_for_merge_patch(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    # Removing one of several engineArgs/engineEnv pairs must send the surviving
    # keys plus an explicit null for the dropped key; otherwise merge-patch keeps
    # the stale pair on the live resource.
    _, patch_profile_mock = mock_profile_gateway
    existing = _make_profiles_shaped_model(
        overrides_extra={
            "engineArgs": {"max-model-len": 8192, "attention-backend": "TRITON_ATTN"},
            "engineEnv": {"KEEP_ME": "1", "DROP_ME": "2"},
        }
    )
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    custom_profile = {
        "engineArgs": {"max-model-len": 8192},
        "engineEnv": [{"name": "KEEP_ME", "value": "1"}],
    }
    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=CustomModelPatchRequest(image=_EXISTING_IMAGE, custom_profile=custom_profile),
    )

    overrides = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"][
        "profiles"
    ]["overrides"]
    assert overrides["engineArgs"] == {"max-model-len": 8192, "attention-backend": None}
    assert overrides["engineEnv"] == {"KEEP_ME": "1", "DROP_ME": None}

    profile_spec = patch_profile_mock.call_args.kwargs["custom_profile_spec"]
    assert profile_spec["engineArgs"] == {"max-model-len": 8192, "attention-backend": None}
    assert profile_spec["engineEnv"] == {"KEEP_ME": "1", "DROP_ME": None}


async def test_patch_combined_metadata_and_profile_in_single_model_patch(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    _, patch_profile_mock = mock_profile_gateway
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.list_namespaced_custom_object = AsyncMock(return_value={"items": []})
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    new_image = "docker.io/amdenterpriseai/aim:2.0.0"
    await patch_onboarded_model(
        kube_client=mock_kube_client,
        minio_client=mock_minio_client,
        namespace="test-namespace",
        name=existing.metadata.name,
        request=CustomModelPatchRequest(display_name="Renamed Model", image=new_image),
    )

    # Metadata and profile land in one AIMModel merge-patch.
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_called_once()
    body = mock_kube_client.custom_objects.patch_namespaced_custom_object.call_args.kwargs["body"]
    assert DISPLAY_NAME_ANNOTATION in body["metadata"]["annotations"]
    assert body["spec"]["profiles"]["overrides"]["image"] == new_image
    patch_profile_mock.assert_awaited_once()


async def test_patch_profile_edit_without_ready_profile_returns_409(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
    mock_profile_gateway: Any,
) -> None:
    find_mock, patch_profile_mock = mock_profile_gateway
    find_mock.return_value = None  # aim-engine has not emitted a profile yet
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )

    with pytest.raises(ConflictException, match="not ready"):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=CustomModelPatchRequest(image="docker.io/amdenterpriseai/aim:2.0.0"),
        )

    # No CR mutation when the readiness precondition fails.
    mock_kube_client.custom_objects.patch_namespaced_custom_object.assert_not_called()
    patch_profile_mock.assert_not_awaited()


async def test_patch_display_name_restamps_drifted_named_profile_set(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    """A model PATCH restamps AIWB-authored siblings whose identity has drifted, not the Default."""
    existing = _make_profiles_shaped_model()
    patched = _make_profiles_shaped_model(display_name="Renamed Model")
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )
    default_set = make_aim_profile_set(
        name=f"{existing.metadata.name}-profiles-abc",
        model_name=existing.metadata.name,
        extra_spec={"overrides": {"aimId": "org/model-a", "modelId": "org/model-a"}},
    )
    drifted = make_aim_profile_set(
        name=f"{existing.metadata.name}-low-latency-7f3b6c8e",
        model_name=existing.metadata.name,
        is_aiwb_authored=True,
        extra_spec={
            "overrides": {
                "aimId": "org/model-a",
                "modelId": "org/model-a",
                "modelSources": [{"modelId": "org/model-a", "sourceUri": "hf://org/model-a"}],
                "engineArgs": {"max-model-len": 4096},
            }
        },
    )
    restamp = AsyncMock(return_value=drifted)
    with (
        patch(
            "app.custom_models.service.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(return_value=[default_set, drifted]),
        ),
        patch("app.custom_models.service.aims_gateway.patch_aim_profile_set", restamp),
    ):
        result = await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=CustomModelPatchRequest(display_name="Renamed Model"),
        )

    restamp.assert_awaited_once()
    assert restamp.await_args is not None
    _, namespace, name, body = restamp.await_args.args
    assert namespace == "test-namespace"
    assert name == drifted.metadata.name
    overrides = body["spec"]["overrides"]
    assert overrides["aimId"] == _REPO_ID
    assert overrides["modelId"] == _REPO_ID
    assert overrides["modelSources"][0]["modelId"] == _REPO_ID
    assert "engineArgs" not in overrides
    assert "image" not in overrides
    assert result.display_name == "Renamed Model"


async def test_patch_skips_identity_restamp_when_named_set_already_matches(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    existing = _make_profiles_shaped_model()
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    profiles = existing.spec.profiles
    assert profiles is not None
    identity = {
        "aimId": _REPO_ID,
        "modelId": _REPO_ID,
        "modelSources": [
            source.model_dump(by_alias=True, exclude_none=True) for source in profiles.overrides.model_sources
        ],
    }
    named = make_aim_profile_set(
        name=f"{existing.metadata.name}-low-latency-7f3b6c8e",
        model_name=existing.metadata.name,
        is_aiwb_authored=True,
        extra_spec={"overrides": identity},
    )
    restamp = AsyncMock()
    with (
        patch(
            "app.custom_models.service.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(return_value=[named]),
        ),
        patch("app.custom_models.service.aims_gateway.patch_aim_profile_set", restamp),
    ):
        await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=CustomModelPatchRequest(tags=["llama"]),
        )

    restamp.assert_not_awaited()


async def test_patch_succeeds_when_named_set_identity_restamp_fails(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    existing = _make_profiles_shaped_model()
    patched = _make_profiles_shaped_model(display_name="Renamed Model")
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )
    drifted = make_aim_profile_set(
        name=f"{existing.metadata.name}-low-latency-7f3b6c8e",
        model_name=existing.metadata.name,
        is_aiwb_authored=True,
        extra_spec={
            "overrides": {
                "aimId": "org/model-a",
                "modelId": "org/model-a",
                "modelSources": [{"modelId": "org/model-a", "sourceUri": "hf://org/model-a"}],
            }
        },
    )
    with (
        patch(
            "app.custom_models.service.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(return_value=[drifted]),
        ),
        patch(
            "app.custom_models.service.aims_gateway.patch_aim_profile_set",
            AsyncMock(side_effect=ExternalServiceError("patch failed")),
        ),
    ):
        result = await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=CustomModelPatchRequest(display_name="Renamed Model"),
        )

    assert result.display_name == "Renamed Model"


async def test_patch_succeeds_when_identity_restamp_fanout_list_fails(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    """A failure listing sibling sets during the restamp fan-out must not fail the model edit."""
    existing = _make_profiles_shaped_model()
    patched = _make_profiles_shaped_model(display_name="Renamed Model")
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )
    with patch(
        "app.custom_models.service.aims_gateway.list_aim_profile_sets_for_model",
        AsyncMock(side_effect=ExternalServiceError("list failed")),
    ):
        result = await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=CustomModelPatchRequest(display_name="Renamed Model"),
        )

    assert result.display_name == "Renamed Model"


async def test_patch_succeeds_when_service_list_raises_apiexception_during_fanout(
    mock_kube_client: MagicMock,
    mock_minio_client: MagicMock,
) -> None:
    """list_aim_services_for_model re-raises raw ApiException; the fan-out must swallow it after the commit."""
    existing = _make_profiles_shaped_model()
    patched = _make_profiles_shaped_model(display_name="Renamed Model")
    mock_kube_client.custom_objects.get_namespaced_custom_object = AsyncMock(
        return_value=existing.model_dump(by_alias=True)
    )
    mock_kube_client.custom_objects.patch_namespaced_custom_object = AsyncMock(
        return_value=patched.model_dump(by_alias=True)
    )
    with (
        patch(
            "app.custom_models.service.aims_gateway.list_aim_profile_sets_for_model",
            AsyncMock(return_value=[]),
        ),
        patch("app.custom_models.service.list_aim_profiles", AsyncMock(return_value=[])),
        patch(
            "app.custom_models.service.aims_gateway.list_aim_services_for_model",
            AsyncMock(side_effect=ApiException(status=500, reason="unavailable")),
        ),
    ):
        result = await patch_onboarded_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace="test-namespace",
            name=existing.metadata.name,
            request=CustomModelPatchRequest(display_name="Renamed Model"),
        )

    assert result.display_name == "Renamed Model"


def test_patch_request_rejects_conflicting_image_refs() -> None:
    with pytest.raises(ValidationError):
        CustomModelPatchRequest(image="docker.io/x:1", custom_profile={"image": "docker.io/y:2"})


def test_patch_request_rejects_empty_custom_profile_image() -> None:
    with pytest.raises(ValidationError):
        CustomModelPatchRequest(image="docker.io/x:1", custom_profile={"image": ""})


def test_patch_request_accepts_matching_image_refs() -> None:
    request = CustomModelPatchRequest(image="docker.io/x:1", custom_profile={"image": "docker.io/x:1"})
    assert request.image == "docker.io/x:1"
