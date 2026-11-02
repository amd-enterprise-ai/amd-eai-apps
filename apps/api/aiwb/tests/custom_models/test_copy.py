# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_common.exceptions import ConflictException, NotFoundException, ValidationException
from app.aims.crds import AIMModelResource
from app.custom_models.constants import (
    MODEL_DISPLAY_NAME_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
    REVISION_ANNOTATION,
    SOURCE_DESCRIPTION_ANNOTATION,
    SOURCE_SHA_ANNOTATION,
    SOURCE_TAGS_ANNOTATION,
    SOURCE_URI_ANNOTATION,
)
from app.custom_models.service import copy_custom_model
from app.workloads.constants import MODEL_SOURCE_TYPE_LABEL

_SOURCE_IMAGE = "docker.io/amd/model:1.0.0"
_SOURCE_BASE_MODEL = "model"


@pytest.fixture(autouse=True)
def mock_ensure_base_model() -> Iterator[AsyncMock]:
    with patch(
        "app.custom_models.service.ensure_namespace_aim_base_model",
        new=AsyncMock(return_value=_SOURCE_BASE_MODEL),
    ) as mock:
        yield mock


def _build_source_model(
    *,
    name: str = "source-model",
    display_name: str = "source-model",
    source_type: str = "custom",
) -> AIMModelResource:
    return AIMModelResource.model_validate(
        {
            "metadata": {
                "name": name,
                "namespace": "test-namespace",
                "labels": {
                    "aim.eai.amd.com/model-name": display_name,
                    MODEL_SOURCE_TYPE_LABEL: source_type,
                },
                "annotations": {
                    MODEL_DISPLAY_NAME_ANNOTATION: display_name,
                    "aim.eai.amd.com/display-name": display_name,
                    "aiwb.apps.eai.amd.com/canonical-repo-id": "org/model",
                    SOURCE_URI_ANNOTATION: "s3://test-bucket/custom-models/source-model/weights/",
                    REVISION_ANNOTATION: "main",
                    SOURCE_SHA_ANNOTATION: "abc123",
                    SOURCE_DESCRIPTION_ANNOTATION: "desc",
                    SOURCE_TAGS_ANNOTATION: '["tag-a"]',
                },
            },
            "spec": {
                "profiles": {
                    "derivedFrom": {
                        "selector": {
                            "role": "base",
                            "modelRef": {"name": "aim-base", "scope": "Namespace"},
                        }
                    },
                    "versionPolicy": "all",
                    "overrides": {
                        "aimId": "org/model",
                        "modelId": "org/model",
                        "image": _SOURCE_IMAGE,
                        "modelSources": [
                            {
                                "modelId": "org/model",
                                "sourceUri": "s3://test-bucket/custom-models/source-model/weights/",
                                "env": [
                                    {
                                        "name": "HF_TOKEN",
                                        "valueFrom": {"secretKeyRef": {"name": "hf-secret", "key": "token"}},
                                    }
                                ],
                            }
                        ],
                    },
                }
            },
        }
    )


@pytest.mark.asyncio
async def test_copy_custom_model_creates_copied_model_and_manifest(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    mock_ensure_base_model: AsyncMock,
    test_namespace: str,
    test_user: str,
) -> None:
    source = _build_source_model()

    with (
        patch("app.custom_models.service.aims_gateway.get_aim_model", new=AsyncMock(return_value=source)),
        patch("app.custom_models.service.aims_gateway.list_aim_models", new=AsyncMock(return_value=[source])),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
        patch("app.custom_models.service._sync_manifest_to_s3", new=AsyncMock()) as mock_sync,
    ):
        await copy_custom_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace=test_namespace,
            source_model_name="source-model",
            submitter=test_user,
        )

    assert mock_create.await_count == 1
    await_args = mock_create.await_args
    assert await_args is not None
    manifest = await_args.args[2]
    copy_name = manifest["metadata"]["name"]
    assert copy_name != "source-model"
    assert copy_name.startswith("source-model-copy-")
    assert manifest["metadata"]["annotations"][MODEL_DISPLAY_NAME_ANNOTATION] == "source-model-copy"
    assert source.metadata.annotations[MODEL_DISPLAY_NAME_ANNOTATION] == "source-model"
    selector = manifest["spec"]["profiles"]["derivedFrom"]["selector"]
    assert selector["modelRef"]["name"] == _SOURCE_BASE_MODEL
    assert manifest["spec"]["profiles"]["overrides"]["image"] == _SOURCE_IMAGE
    mock_ensure_base_model.assert_awaited_once_with(
        mock_kube_client,
        test_namespace,
        image_ref=_SOURCE_IMAGE,
    )
    mock_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_copy_custom_model_preserves_precision_annotation(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    test_namespace: str,
    test_user: str,
) -> None:
    """Precision is pruned from overrides, so it survives only on the annotation;
    copy must carry it into the copied model (re-stamped by the onboard builder)."""
    source = _build_source_model()
    source.metadata.annotations[MODEL_PRECISION_ANNOTATION] = "fp8"

    with (
        patch("app.custom_models.service.aims_gateway.get_aim_model", new=AsyncMock(return_value=source)),
        patch("app.custom_models.service.aims_gateway.list_aim_models", new=AsyncMock(return_value=[source])),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
        patch("app.custom_models.service._sync_manifest_to_s3", new=AsyncMock()),
    ):
        await copy_custom_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace=test_namespace,
            source_model_name="source-model",
            submitter=test_user,
        )

    await_args = mock_create.await_args
    assert await_args is not None
    manifest = await_args.args[2]
    assert manifest["metadata"]["annotations"][MODEL_PRECISION_ANNOTATION] == "fp8"


@pytest.mark.asyncio
async def test_copy_custom_model_increments_copy_suffix_when_name_exists(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    test_namespace: str,
    test_user: str,
) -> None:
    source = _build_source_model()
    existing_copy = _build_source_model(name="source-model-copy", display_name="source-model-copy")

    with (
        patch("app.custom_models.service.aims_gateway.get_aim_model", new=AsyncMock(return_value=source)),
        patch(
            "app.custom_models.service.aims_gateway.list_aim_models",
            new=AsyncMock(return_value=[source, existing_copy]),
        ),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
        patch("app.custom_models.service._sync_manifest_to_s3", new=AsyncMock()),
    ):
        await copy_custom_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace=test_namespace,
            source_model_name="source-model",
            submitter=test_user,
        )

    await_args = mock_create.await_args
    assert await_args is not None
    manifest = await_args.args[2]
    assert manifest["metadata"]["annotations"][MODEL_DISPLAY_NAME_ANNOTATION] == "source-model-copy-2"


@pytest.mark.asyncio
async def test_copy_custom_model_normalizes_existing_copy_suffix(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    test_namespace: str,
    test_user: str,
) -> None:
    source = _build_source_model(name="source-model-copy", display_name="source-model-copy")
    existing_base = _build_source_model(name="source-model", display_name="source-model")
    existing_copy = _build_source_model(name="source-model-copy-2", display_name="source-model-copy-2")

    with (
        patch("app.custom_models.service.aims_gateway.get_aim_model", new=AsyncMock(return_value=source)),
        patch(
            "app.custom_models.service.aims_gateway.list_aim_models",
            new=AsyncMock(return_value=[existing_base, source, existing_copy]),
        ),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
        patch("app.custom_models.service._sync_manifest_to_s3", new=AsyncMock()),
    ):
        await copy_custom_model(
            kube_client=mock_kube_client,
            minio_client=mock_minio_client,
            namespace=test_namespace,
            source_model_name="source-model-copy",
            submitter=test_user,
        )

    await_args = mock_create.await_args
    assert await_args is not None
    manifest = await_args.args[2]
    assert manifest["metadata"]["annotations"][MODEL_DISPLAY_NAME_ANNOTATION] == "source-model-copy-3"


@pytest.mark.asyncio
async def test_copy_custom_model_raises_not_found_when_sha_annotation_absent(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    test_namespace: str,
    test_user: str,
) -> None:
    source_without_sha = _build_source_model()
    del source_without_sha.metadata.annotations[SOURCE_SHA_ANNOTATION]

    with (
        patch(
            "app.custom_models.service.aims_gateway.get_aim_model",
            new=AsyncMock(return_value=source_without_sha),
        ),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
    ):
        with pytest.raises(NotFoundException):
            await copy_custom_model(
                kube_client=mock_kube_client,
                minio_client=mock_minio_client,
                namespace=test_namespace,
                source_model_name="source-model",
                submitter=test_user,
            )

    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_copy_custom_model_raises_not_found_for_missing_source(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    test_namespace: str,
    test_user: str,
) -> None:
    with (
        patch("app.custom_models.service.aims_gateway.get_aim_model", new=AsyncMock(return_value=None)),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
    ):
        with pytest.raises(NotFoundException):
            await copy_custom_model(
                kube_client=mock_kube_client,
                minio_client=mock_minio_client,
                namespace=test_namespace,
                source_model_name="source-model",
                submitter=test_user,
            )

    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_copy_custom_model_rolls_back_cr_when_s3_sync_fails(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    test_namespace: str,
    test_user: str,
) -> None:
    source = _build_source_model()

    with (
        patch("app.custom_models.service.aims_gateway.get_aim_model", new=AsyncMock(return_value=source)),
        patch("app.custom_models.service.aims_gateway.list_aim_models", new=AsyncMock(return_value=[source])),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()),
        patch("app.custom_models.service.aims_gateway.delete_aim_model", new=AsyncMock()) as mock_delete,
        patch("app.custom_models.service._sync_manifest_to_s3", new=AsyncMock(side_effect=Exception("S3 unavailable"))),
    ):
        with pytest.raises(Exception, match="S3 unavailable"):
            await copy_custom_model(
                kube_client=mock_kube_client,
                minio_client=mock_minio_client,
                namespace=test_namespace,
                source_model_name="source-model",
                submitter=test_user,
            )

    mock_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_copy_custom_model_raises_not_found_for_non_custom_source(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    test_namespace: str,
    test_user: str,
) -> None:
    non_custom_source = _build_source_model(source_type="fine-tuned")

    with (
        patch(
            "app.custom_models.service.aims_gateway.get_aim_model",
            new=AsyncMock(return_value=non_custom_source),
        ),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
    ):
        with pytest.raises(NotFoundException):
            await copy_custom_model(
                kube_client=mock_kube_client,
                minio_client=mock_minio_client,
                namespace=test_namespace,
                source_model_name="source-model",
                submitter=test_user,
            )

    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_copy_custom_model_raises_validation_error_when_source_missing_required_fields(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    test_namespace: str,
    test_user: str,
) -> None:
    # A source that passes the eligibility guard (both onboard stamps present) but
    # lacks overrides and has empty revision, so repo_id, revision, and image are
    # all empty — caught by build_copy_onboard_request as a ValidationException.
    bare_source = AIMModelResource.model_validate(
        {
            "metadata": {
                "name": "bare-model",
                "namespace": "test-namespace",
                "labels": {"aim.eai.amd.com/model-name": "bare-model", MODEL_SOURCE_TYPE_LABEL: "custom"},
                "annotations": {
                    "aim.eai.amd.com/display-name": "bare-model",
                    REVISION_ANNOTATION: "",
                    SOURCE_SHA_ANNOTATION: "abc123",
                },
            },
            "spec": {},
        }
    )

    with (
        patch("app.custom_models.service.aims_gateway.get_aim_model", new=AsyncMock(return_value=bare_source)),
        patch("app.custom_models.service.aims_gateway.list_aim_models", new=AsyncMock(return_value=[bare_source])),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
    ):
        with pytest.raises(ValidationException):
            await copy_custom_model(
                kube_client=mock_kube_client,
                minio_client=mock_minio_client,
                namespace=test_namespace,
                source_model_name="bare-model",
                submitter=test_user,
            )

    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_copy_custom_model_propagates_base_image_conflict(
    mock_kube_client: AsyncMock,
    mock_minio_client: MagicMock,
    mock_ensure_base_model: AsyncMock,
    test_namespace: str,
    test_user: str,
) -> None:
    source = _build_source_model()
    mock_ensure_base_model.side_effect = ConflictException(
        "Base model 'model' in project 'test-namespace' already uses image "
        "'docker.io/amd/model:0.1', which conflicts with requested image "
        "'docker.io/amd/model:1.0.0'."
    )

    with (
        patch("app.custom_models.service.aims_gateway.get_aim_model", new=AsyncMock(return_value=source)),
        patch("app.custom_models.service.aims_gateway.list_aim_models", new=AsyncMock(return_value=[source])),
        patch("app.custom_models.service.aims_gateway.create_aim_model", new=AsyncMock()) as mock_create,
    ):
        with pytest.raises(ConflictException, match="conflicts with requested image"):
            await copy_custom_model(
                kube_client=mock_kube_client,
                minio_client=mock_minio_client,
                namespace=test_namespace,
                source_model_name="source-model",
                submitter=test_user,
            )

    mock_create.assert_not_awaited()
