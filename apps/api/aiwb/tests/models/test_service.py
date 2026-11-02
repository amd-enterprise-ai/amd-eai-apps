# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import copy
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import yaml
from kubernetes_asyncio.client import CustomObjectsApi
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import (
    DeletionConflictException,
    ExternalServiceError,
    NotFoundException,
    ValidationException,
)
from app.aims.constants import ADAPTER_PROFILE_FEATURE, AIM_PROFILE_SOURCE_MODEL_LABEL
from app.aims.crds import (
    AIMImageMetadata,
    AIMModelMetadata,
    AIMModelProfilesSpec,
    AIMModelResource,
    AIMModelSource,
    AIMModelSpec,
    AIMModelStatusFields,
    AIMProfileResource,
    AIMProfileSpec,
    AIMProfileStatus,
    ProfileOverrides,
)
from app.charts.config import FINETUNING_CHART_NAME, MLFLOW_CHART_NAME
from app.config import SUBMITTER_ANNOTATION
from app.custom_models.constants import SOURCE_DESCRIPTION_ANNOTATION
from app.dispatch.crds import K8sMetadata
from app.dispatch.kube_client import KubernetesClient
from app.minio.client import MinioClient
from app.minio.config import MINIO_BUCKET
from app.models.schemas import (
    FinetunableModelResponse,
    FinetuneCreate,
    FinetuningHyperparameters,
    FineTuningOutput,
    LoraHyperparameters,
    LoraSettings,
    TrainingType,
)
from app.models.service import (
    ADAPTER_ORGANISATION,
    _cleanup_prefix_for_source,
    _extract_s3_prefix,
    _get_training_output,
    _newest_first,
    _registered_at,
    delete_model,
    get_aim_model,
    get_finetunable_models,
    run_finetune_model_workload,
)
from app.overlays.models import Overlay
from app.secrets.schemas import SecretResponse
from app.workloads.constants import (
    DESCRIPTION_ANNOTATION,
    DISPLAY_NAME_ANNOTATION,
    MODEL_ID_LABEL,
    MODEL_NAME_LABEL,
    TRAINING_OUTPUT_ANNOTATION,
    WORKLOAD_ID_LABEL,
    WORKLOAD_TYPE_LABEL,
)
from app.workloads.enums import TrainingOutput, WorkloadStatus, WorkloadType
from app.workloads.models import Workload
from app.workloads.schemas import WorkloadResponse
from tests import factory


@pytest.mark.asyncio
async def test_get_aim_model_not_found(test_namespace: str) -> None:
    mock_kube_client = MagicMock()

    with (
        patch("app.models.service.aims_gateway.get_aim_model", return_value=None),
        patch("app.models.service.aims_gateway.find_aim_model_by_label", return_value=None),
        pytest.raises(NotFoundException, match="Model nonexistent not found"),
    ):
        await get_aim_model(mock_kube_client, test_namespace, "nonexistent")


@pytest.mark.asyncio
async def test_get_aim_model_falls_back_to_label_lookup(test_namespace: str) -> None:
    """When name lookup fails, falls back to WORKLOAD_ID_LABEL selector."""
    mock_kube_client = MagicMock()
    model_uuid = str(uuid4())
    aim_model = AIMModelResource.model_validate({"metadata": {"name": "finetuned-model-cr"}, "spec": {}, "status": {}})

    with (
        patch("app.models.service.aims_gateway.get_aim_model", return_value=None),
        patch("app.models.service.aims_gateway.find_aim_model_by_label", return_value=aim_model) as mock_label_lookup,
    ):
        result = await get_aim_model(mock_kube_client, test_namespace, model_uuid)

    mock_label_lookup.assert_called_once_with(mock_kube_client, test_namespace, f"{WORKLOAD_ID_LABEL}={model_uuid}")


@pytest.mark.parametrize(
    "source_uri,expected_prefix",
    [
        ("s3://bucket/path/to/weights/", "path/to/weights/"),
        ("s3://bucket/weights", "weights"),
        ("s3://bucket/a/b/c", "a/b/c"),
        ("s3://bucket-name", ""),  # no path component — guard against empty prefix
    ],
)
def test_extract_s3_prefix(source_uri: str, expected_prefix: str) -> None:
    assert _extract_s3_prefix(source_uri) == expected_prefix


@pytest.mark.parametrize(
    ("source_uri", "expected_prefix"),
    [
        (
            "s3://default-bucket/qa-test/finetuned-models/meta-llama/model-a/run-1/checkpoint-final",
            "qa-test/finetuned-models/meta-llama/model-a/run-1/",
        ),
        (
            "s3://default-bucket/qa-test/finetuned-models/meta-llama/model-a/run-1/checkpoint-final/",
            "qa-test/finetuned-models/meta-llama/model-a/run-1/",
        ),
        (
            "s3://default-bucket/qa-test/finetuned-models/meta-llama/model-a/run-1/checkpoint-final-merged",
            "qa-test/finetuned-models/meta-llama/model-a/run-1/",
        ),
        (
            "s3://default-bucket/qa-test/finetuned-models/meta-llama/model-a/run-1/checkpoint-final-merged/",
            "qa-test/finetuned-models/meta-llama/model-a/run-1/",
        ),
        (
            "s3://default-bucket/qa-test/finetuned-models/meta-llama/model-a/run-1/adapter",
            "qa-test/finetuned-models/meta-llama/model-a/run-1/",
        ),
        (
            "s3://default-bucket/qa-test/finetuned-models/meta-llama/model-a/run-1/adapter/",
            "qa-test/finetuned-models/meta-llama/model-a/run-1/",
        ),
        (
            "s3://default-bucket/qa-test/finetuned-models/checkpoint-final",
            "qa-test/finetuned-models/checkpoint-final",
        ),
        (
            "s3://default-bucket/qa-test/finetuned-models/checkpoint-final/",
            "qa-test/finetuned-models/checkpoint-final/",
        ),
    ],
)
def test_cleanup_prefix_for_source(source_uri: str, expected_prefix: str) -> None:
    assert _cleanup_prefix_for_source(source_uri) == expected_prefix


@pytest.mark.parametrize(
    ("wants_adapter", "training_type", "expected"),
    [
        (True, TrainingType.LORA, TrainingOutput.LORA),
        (False, TrainingType.LORA, TrainingOutput.MERGED),
        (False, TrainingType.FULL, None),
        (False, None, None),
    ],
)
def test_get_training_output(
    wants_adapter: bool,
    training_type: TrainingType | None,
    expected: TrainingOutput | None,
) -> None:
    assert _get_training_output(wants_adapter=wants_adapter, training_type=training_type) is expected


@pytest.mark.asyncio
async def test_delete_model_success(db_session: AsyncSession, test_namespace: str) -> None:
    """Test successfully deleting a model by CR name with S3 cleanup and workload marked DELETED."""
    model_name = "my-finetuned-model"
    workload_id = uuid4()
    mock_kube_client = AsyncMock(spec=KubernetesClient)
    mock_minio_client = MagicMock(spec=MinioClient)

    aim_model = AIMModelResource(
        metadata=K8sMetadata(
            name=model_name,
            namespace=test_namespace,
            labels={WORKLOAD_ID_LABEL: str(workload_id)},
        ),
        spec=AIMModelSpec(model_sources=[AIMModelSource(source_uri="s3://my-bucket/path/to/weights/")]),
    )

    chart = await factory.create_chart(db_session, name="ft-chart")
    workload = await factory.create_workload(
        db_session,
        id=workload_id,
        namespace=test_namespace,
        chart=chart,
        workload_type=WorkloadType.FINE_TUNING,
        status=WorkloadStatus.COMPLETE,
        include_isolation_data=False,
    )

    with (
        patch("app.aims.gateway.get_aim_model", return_value=aim_model) as mock_get,
        patch("app.aims.gateway.list_aim_services_for_model", return_value=[]) as mock_list_services,
        patch("app.aims.gateway.delete_aim_model", new_callable=AsyncMock) as mock_delete_cr,
        patch("app.models.service.delete_from_s3", new_callable=AsyncMock) as mock_delete_s3,
        patch("app.models.service.delete_object_from_s3", new_callable=AsyncMock) as mock_delete_marker,
    ):
        await delete_model(mock_kube_client, model_name, test_namespace, mock_minio_client, session=db_session)

        mock_get.assert_called_once_with(mock_kube_client, test_namespace, model_name)
        mock_list_services.assert_called_once_with(mock_kube_client, test_namespace, model_name)
        mock_delete_cr.assert_called_once_with(mock_kube_client, test_namespace, model_name)
        mock_delete_s3.assert_called_once_with("path/to/weights/", mock_minio_client, model_name)
        mock_delete_marker.assert_called_once_with("path/to/weights/", mock_minio_client, model_name)

    await db_session.refresh(workload)
    assert workload.status == WorkloadStatus.DELETED


@pytest.mark.parametrize(
    ("terminal_dir", "trailing_slash"),
    [
        ("checkpoint-final", False),
        ("checkpoint-final", True),
        ("checkpoint-final-merged", False),
        ("checkpoint-final-merged", True),
        ("adapter", False),
        ("adapter", True),
    ],
)
@pytest.mark.asyncio
async def test_delete_model_cleans_profiles_override_weights_sources(
    test_namespace: str, terminal_dir: str, trailing_slash: bool
) -> None:
    """delete_model reclaims fine-tune run roots from profiles.overrides.modelSources."""
    model_name = "profiles-only-model"
    source_uri = (
        "s3://default-bucket/qa-test/finetuned-models/meta-llama/model-a/run-1/"
        f"{terminal_dir}{'/' if trailing_slash else ''}"
    )
    mock_kube_client = AsyncMock(spec=KubernetesClient)
    mock_minio_client = MagicMock(spec=MinioClient)

    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=model_name, namespace=test_namespace),
        spec=AIMModelSpec(
            model_sources=[],
            profiles=AIMModelProfilesSpec(
                overrides=ProfileOverrides(
                    model_sources=[AIMModelSource(model_id="meta-llama/model-a", source_uri=source_uri)]
                )
            ),
        ),
    )

    with (
        patch("app.aims.gateway.get_aim_model", return_value=aim_model),
        patch("app.aims.gateway.list_aim_services_for_model", return_value=[]),
        patch("app.aims.gateway.delete_aim_model", new_callable=AsyncMock),
        patch("app.models.service.delete_from_s3", new_callable=AsyncMock) as mock_delete_s3,
        patch("app.models.service.delete_object_from_s3", new_callable=AsyncMock) as mock_delete_marker,
    ):
        await delete_model(mock_kube_client, model_name, test_namespace, mock_minio_client)

    mock_delete_s3.assert_called_once_with(
        "qa-test/finetuned-models/meta-llama/model-a/run-1/",
        mock_minio_client,
        model_name,
    )
    mock_delete_marker.assert_called_once_with(
        "qa-test/finetuned-models/meta-llama/model-a/run-1/",
        mock_minio_client,
        model_name,
    )


@pytest.mark.asyncio
async def test_delete_model_not_found(test_namespace: str) -> None:
    """Test delete_model raises NotFoundException when neither AIMModel CR nor K8s Job exists."""
    model_name = "nonexistent-model"
    mock_kube_client = AsyncMock(spec=KubernetesClient)
    mock_minio_client = MagicMock(spec=MinioClient)

    with (
        patch("app.aims.gateway.get_aim_model", return_value=None),
        patch("app.models.service._find_job_by_name", new_callable=AsyncMock, return_value=None),
        patch("app.models.service._find_job_by_label", new_callable=AsyncMock, return_value=None),
        pytest.raises(NotFoundException, match=f"Model {model_name} not found"),
    ):
        await delete_model(mock_kube_client, model_name, test_namespace, mock_minio_client, session=None)


@pytest.mark.asyncio
async def test_delete_model_cancels_in_progress_job(db_session: AsyncSession, test_namespace: str) -> None:
    """delete_model cancels a PENDING/RUNNING fine-tuning job and marks the workload DELETED."""
    job_name = "wb-finetuning-abc123"
    workload_id = uuid4()
    mock_kube_client = MagicMock()
    mock_kube_client.batch_v1.delete_namespaced_job = AsyncMock()
    mock_minio_client = MagicMock(spec=MinioClient)

    chart = await factory.create_chart(db_session, name="ft-chart-job")
    workload = await factory.create_workload(
        db_session,
        id=workload_id,
        namespace=test_namespace,
        chart=chart,
        workload_type=WorkloadType.FINE_TUNING,
        status=WorkloadStatus.RUNNING,
        include_isolation_data=False,
    )

    mock_job = MagicMock()
    mock_job.metadata.name = job_name
    mock_job.metadata.labels = {WORKLOAD_ID_LABEL: str(workload_id)}

    with (
        patch("app.aims.gateway.get_aim_model", return_value=None),
        patch("app.models.service._find_job_by_name", new_callable=AsyncMock, return_value=mock_job),
        patch("app.aims.gateway.find_aim_model_by_label", new_callable=AsyncMock, return_value=None),
    ):
        await delete_model(mock_kube_client, job_name, test_namespace, mock_minio_client, session=db_session)

    mock_kube_client.batch_v1.delete_namespaced_job.assert_called_once_with(name=job_name, namespace=test_namespace)

    await db_session.refresh(workload)
    assert workload.status == WorkloadStatus.DELETED


@pytest.mark.asyncio
async def test_delete_model_cancels_job_and_cleans_completed_model(test_namespace: str) -> None:
    """delete_model deletes the AIMModel CR and S3 weights when a completed model is found by job name."""
    job_name = "wb-finetuning-abc123"
    s3_uri = "s3://bucket/ns/finetuned-models/llama3/run1/checkpoint-final/"

    mock_kube_client = MagicMock()
    mock_kube_client.batch_v1.delete_namespaced_job = AsyncMock()
    mock_minio_client = MagicMock(spec=MinioClient)

    model_id = str(uuid4())
    mock_job = MagicMock()
    mock_job.metadata.name = job_name
    mock_job.metadata.labels = {WORKLOAD_ID_LABEL: model_id}

    mock_aim_model = AIMModelResource(
        metadata=K8sMetadata(name=job_name),
        spec=AIMModelSpec(model_sources=[AIMModelSource(source_uri=s3_uri)]),
    )

    with (
        patch("app.aims.gateway.get_aim_model", new_callable=AsyncMock, return_value=None),
        patch("app.models.service._find_job_by_name", new_callable=AsyncMock, return_value=mock_job),
        patch("app.aims.gateway.find_aim_model_by_label", new_callable=AsyncMock, return_value=mock_aim_model),
        patch("app.aims.gateway.list_aim_services_for_model", new_callable=AsyncMock, return_value=[]),
        patch("app.aims.gateway.delete_aim_model", new_callable=AsyncMock) as mock_delete_cr,
        patch("app.models.service.delete_from_s3", new_callable=AsyncMock) as mock_delete_s3,
        patch("app.models.service.delete_object_from_s3", new_callable=AsyncMock) as mock_delete_marker,
    ):
        await delete_model(mock_kube_client, job_name, test_namespace, mock_minio_client, session=None)

    mock_kube_client.batch_v1.delete_namespaced_job.assert_called_once_with(name=job_name, namespace=test_namespace)
    mock_delete_cr.assert_called_once_with(mock_kube_client, test_namespace, job_name)
    mock_delete_s3.assert_called_once()
    mock_delete_marker.assert_called_once_with("ns/finetuned-models/llama3/run1/", mock_minio_client, job_name)


@pytest.mark.parametrize(
    ("terminal_dir", "trailing_slash"),
    [
        ("checkpoint-final", False),
        ("checkpoint-final", True),
        ("checkpoint-final-merged", False),
        ("checkpoint-final-merged", True),
        ("adapter", False),
        ("adapter", True),
    ],
)
@pytest.mark.asyncio
async def test_delete_model_job_lookup_cleans_profiles_override_weights_sources(
    test_namespace: str, terminal_dir: str, trailing_slash: bool
) -> None:
    """Job-name deletion also reclaims fine-tune run roots across terminal output paths."""
    job_name = "wb-finetuning-abc123"
    source_uri = (
        "s3://default-bucket/qa-test/finetuned-models/meta-llama/model-b/run-2/"
        f"{terminal_dir}{'/' if trailing_slash else ''}"
    )

    mock_kube_client = MagicMock()
    mock_kube_client.batch_v1.delete_namespaced_job = AsyncMock()
    mock_minio_client = MagicMock(spec=MinioClient)

    model_id = str(uuid4())
    mock_job = MagicMock()
    mock_job.metadata.name = job_name
    mock_job.metadata.labels = {WORKLOAD_ID_LABEL: model_id}

    mock_aim_model = AIMModelResource(
        metadata=K8sMetadata(name=job_name),
        spec=AIMModelSpec(
            model_sources=[],
            profiles=AIMModelProfilesSpec(
                overrides=ProfileOverrides(
                    model_sources=[AIMModelSource(model_id="meta-llama/model-b", source_uri=source_uri)]
                )
            ),
        ),
    )

    with (
        patch("app.aims.gateway.get_aim_model", new_callable=AsyncMock, return_value=None),
        patch("app.models.service._find_job_by_name", new_callable=AsyncMock, return_value=mock_job),
        patch("app.aims.gateway.find_aim_model_by_label", new_callable=AsyncMock, return_value=mock_aim_model),
        patch("app.aims.gateway.list_aim_services_for_model", new_callable=AsyncMock, return_value=[]),
        patch("app.aims.gateway.delete_aim_model", new_callable=AsyncMock),
        patch("app.models.service.delete_from_s3", new_callable=AsyncMock) as mock_delete_s3,
        patch("app.models.service.delete_object_from_s3", new_callable=AsyncMock) as mock_delete_marker,
    ):
        await delete_model(mock_kube_client, job_name, test_namespace, mock_minio_client, session=None)

    mock_delete_s3.assert_called_once_with(
        "qa-test/finetuned-models/meta-llama/model-b/run-2/",
        mock_minio_client,
        job_name,
    )
    mock_delete_marker.assert_called_once_with(
        "qa-test/finetuned-models/meta-llama/model-b/run-2/",
        mock_minio_client,
        job_name,
    )


_DEFAULT = object()


def make_overlay(
    canonical_name: str | None = None,
    compatible_accelerators: list[str] | None = None,
    aim_id: str | None | object = _DEFAULT,
    model_id: str | None | object = _DEFAULT,
    hf_token_required: bool | str | int | None = None,
    training_type: str | None = None,
    **extra_overlay_fields: object,
) -> MagicMock:
    """Build a mock Overlay.

    `aim_id` and `model_id` each default to the canonical_name (the typical real-world
    setup where the overlay's manifest identifiers mirror the model identifier). Pass
    explicit strings to override, or `None` to omit that field; passing `None` for
    both omits the aimManifest entirely. The two parameters can diverge so tests can
    construct overlays where the family identity (aimId) and the artifact identity
    (modelId) differ. Production code joins on
    `modelId`.

    `hf_token_required` mirrors the overlay's `metadata.hfTokenRequired` field (the
    recipe's own declaration of whether the base weights are gated on Hugging Face).
    Omitted when None so tests can exercise the "not declared" case.

    `training_type` mirrors `metadata.trainingType`, the recipe's sole declaration of how
    it trains. Omitted when None so tests can exercise the "not declared" case.
    """
    overlay = MagicMock(spec=Overlay)
    overlay.canonical_name = canonical_name
    overlay_data: dict = {**extra_overlay_fields}
    metadata: dict = {}
    if compatible_accelerators is not None:
        metadata["compatibleAccelerators"] = compatible_accelerators
    if hf_token_required is not None:
        metadata["hfTokenRequired"] = hf_token_required
    if training_type is not None:
        metadata["trainingType"] = training_type
    if metadata:
        overlay_data["metadata"] = metadata
    resolved_aim_id = canonical_name if aim_id is _DEFAULT else aim_id
    resolved_model_id = canonical_name if model_id is _DEFAULT else model_id
    if resolved_aim_id is not None or resolved_model_id is not None:
        aim_manifest: dict = {}
        if resolved_aim_id is not None:
            aim_manifest["aimId"] = resolved_aim_id
        if resolved_model_id is not None:
            aim_manifest["modelId"] = resolved_model_id
        overlay_data["aimManifest"] = aim_manifest
    overlay.overlay = overlay_data
    return overlay


def make_profile(
    spec_aim_id: str | None = None,
    status: str = "Ready",
) -> MagicMock:
    """Build a mock AIMClusterProfile carrying spec.aim_id via typed attributes.

    Status is a typed model — use attribute access, not dict access — to match
    the production crds.py shape.
    """
    profile = MagicMock()
    profile.spec.aim_id = spec_aim_id or ""
    profile.status.status = status
    return profile


def make_cluster_model(
    aim_id: str | None = None,
    status: str = "Ready",
    created_at: datetime | None = None,
) -> MagicMock:
    """Build a mock AIMClusterModel carrying status.aim_id, status.status and its creation time.

    ``creation_timestamp`` is set explicitly because selection orders versions by it; left
    as an auto-created attribute the mock would be uncomparable rather than simply absent.
    """
    model = MagicMock()
    model.status.aim_id = aim_id or ""
    model.status.status = status
    model.metadata.creation_timestamp = created_at
    return model


def patch_cluster_model(aim_id: str, name: str = "default-cluster-model") -> AbstractContextManager[MagicMock]:
    """Patch list_aims to return a single Ready AIMClusterModel with the given aimId."""
    model = make_cluster_model(aim_id=aim_id, status="Ready")
    model.metadata.name = name
    return patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=[model])


def patch_cluster_profiles(aim_ids: list[str] | None = None) -> AbstractContextManager[MagicMock]:
    """Patch list_aim_cluster_profiles_by_aim_ids to advertise the given aimIds."""
    profiles = [make_profile(spec_aim_id=aim_id) for aim_id in (aim_ids or [])]
    return patch("app.aims.gateway.list_aim_cluster_profiles_by_aim_ids", return_value=profiles)


def make_custom_objects_api() -> AsyncMock:
    """Build a CustomObjectsApi stub whose every method can be awaited.

    `kubernetes_asyncio` generates its API methods as plain `def`s that return an awaitable
    rather than as `async def`s. `AsyncMock`'s spec inspection therefore reads them as
    synchronous and hands back `MagicMock` children, whose return value blows up the moment a
    gateway awaits it. Every call through this API in `app/` is awaited, so each method is
    replaced with an `AsyncMock` explicitly. Keeping the spec is still what makes a method this
    API does not have fail here, at the fixture, rather than somewhere inside a test.

    Listing returns no items, so a lookup a test has not patched reads as "no such resources in
    the cluster" rather than handing parsing code a bare mock.
    """
    custom_objects = AsyncMock(spec=CustomObjectsApi)
    for name in dir(CustomObjectsApi):
        if name.startswith("_") or not callable(getattr(CustomObjectsApi, name, None)):
            continue
        method = AsyncMock(return_value={"items": []}) if name.startswith("list_") else AsyncMock()
        setattr(custom_objects, name, method)
    return custom_objects


def make_kube_client() -> AsyncMock:
    """Build a KubernetesClient stub the CRD gateways can read through.

    `custom_objects` is assigned in `KubernetesClient.__init__`, so a class-level spec does not
    carry it and every gateway call through it would fail on attribute access.
    """
    kube_client = AsyncMock(spec=KubernetesClient)
    kube_client.custom_objects = make_custom_objects_api()
    return kube_client


def make_cluster_profile(
    source_model: str,
    *,
    model_id: str = "",
    adapter_capable: bool = False,
    status: str = "Ready",
    name: str = "",
) -> AIMProfileResource:
    """Build an AIMClusterProfile published by `source_model`.

    The source-model label is what ties a profile back to the version that published it;
    every profile sharing an aimId is otherwise indistinguishable. `name` is there for the
    tests where one version publishes several profiles, since the cluster would never hold
    two resources under the one name.
    """
    return AIMProfileResource(
        metadata=K8sMetadata(
            name=name or f"{source_model}-profile", labels={AIM_PROFILE_SOURCE_MODEL_LABEL: source_model}
        ),
        spec=AIMProfileSpec(
            model_id=model_id,
            features=[ADAPTER_PROFILE_FEATURE] if adapter_capable else [],
        ),
        status=AIMProfileStatus(status=status),
    )


def patch_source_profiles(profiles: list[AIMProfileResource] | None = None) -> AbstractContextManager[AsyncMock]:
    """Patch the cluster-profile lookup the base-model selection reads capability from."""
    return patch(
        "app.models.service.aims_gateway.list_aim_cluster_profiles_by_aim_ids",
        new_callable=AsyncMock,
        return_value=list(profiles or []),
    )


@pytest.mark.asyncio
async def test_get_finetunable_models_success(db_session: AsyncSession) -> None:
    """Test successfully getting finetunable models from overlays."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("meta-llama/Llama-3.1-8B"),
        make_overlay("microsoft/DialoGPT-medium"),
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["meta-llama/Llama-3.1-8B", "microsoft/DialoGPT-medium"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert [m.canonical_name for m in result] == ["meta-llama/Llama-3.1-8B", "microsoft/DialoGPT-medium"]


@pytest.mark.asyncio
async def test_get_finetunable_models_empty(db_session: AsyncSession) -> None:
    """Test get_finetunable_models returns empty list when no overlays exist."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=[]),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={}),
        patch_cluster_profiles([]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert result == []


@pytest.mark.asyncio
async def test_get_finetunable_models_filters_incompatible_gpus(db_session: AsyncSession) -> None:
    """Overlays whose compatibleAccelerators have no intersection with cluster GPU IDs are excluded."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("meta-llama/Llama-3.1-8B", compatible_accelerators=["74a1", "74a9"]),
        make_overlay("big-model/70B", compatible_accelerators=["75a0"]),  # not in cluster
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["meta-llama/Llama-3.1-8B", "big-model/70B"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert [m.canonical_name for m in result] == ["meta-llama/Llama-3.1-8B"]


@pytest.mark.asyncio
async def test_get_finetunable_models_no_compatible_accelerators_always_included(db_session: AsyncSession) -> None:
    """Overlays without compatibleAccelerators are compatible with all hardware."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("legacy-model/1B"),  # no compatibleAccelerators
        make_overlay("new-model/7B", compatible_accelerators=["75a0"]),  # not in cluster
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["legacy-model/1B", "new-model/7B"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert [m.canonical_name for m in result] == ["legacy-model/1B"]


@pytest.mark.asyncio
async def test_get_finetunable_models_empty_cluster_gpu_ids_excludes_all_constrained(db_session: AsyncSession) -> None:
    """When the cluster reports no GPU IDs, overlays with compatibleAccelerators are excluded."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("legacy-model/1B"),  # no compatibleAccelerators — always included
        make_overlay("new-model/7B", compatible_accelerators=["74a1"]),  # constrained — excluded
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={}),
        patch_cluster_profiles(["legacy-model/1B", "new-model/7B"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert [m.canonical_name for m in result] == ["legacy-model/1B"]


@pytest.mark.asyncio
async def test_get_finetunable_models_skips_generic_overlays(db_session: AsyncSession) -> None:
    """Generic overlays (canonical_name=None) are excluded from the finetunable list."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay(None),  # generic overlay
        make_overlay("meta-llama/Llama-3.1-8B"),
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["meta-llama/Llama-3.1-8B"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert [m.canonical_name for m in result] == ["meta-llama/Llama-3.1-8B"]


@pytest.mark.asyncio
async def test_get_finetunable_models_enriches_gpu_metadata(db_session: AsyncSession) -> None:
    """Each result carries gpu_count and compatible_accelerators from the overlay."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("meta-llama/Llama-3.1-8B", compatible_accelerators=["74a1", "74a9"], finetuningGpus=4),
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["meta-llama/Llama-3.1-8B"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert len(result) == 1
    assert isinstance(result[0], FinetunableModelResponse)
    assert result[0].gpu_count == 4
    assert result[0].compatible_accelerators == ["74a1", "74a9"]
    # 74a1 is in the cluster and resolves to a display name; 74a9 is not
    assert result[0].compatible_accelerator_names == ["AMD Instinct MI300X"]


@pytest.mark.asyncio
async def test_get_finetunable_models_gpu_count_none_when_absent(db_session: AsyncSession) -> None:
    """gpu_count is None when finetuningGpus is not set in the overlay."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [make_overlay("meta-llama/Llama-3.1-8B")]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["meta-llama/Llama-3.1-8B"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert result[0].gpu_count is None
    assert result[0].compatible_accelerators == []


@pytest.mark.asyncio
async def test_get_finetunable_models_excludes_recipe_without_matching_template(db_session: AsyncSession) -> None:
    """Recipes whose aimManifest.modelId has no matching cluster template are excluded."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("meta-llama/Llama-3.1-8B"),  # template present
        make_overlay("orphan/model-13B"),  # no template
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["meta-llama/Llama-3.1-8B"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert [m.canonical_name for m in result] == ["meta-llama/Llama-3.1-8B"]


@pytest.mark.asyncio
async def test_get_finetunable_models_excludes_recipe_without_aim_manifest(db_session: AsyncSession) -> None:
    """Recipes lacking aimManifest.modelId are excluded — the cluster cannot vouch for them."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("meta-llama/Llama-3.1-8B", aim_id=None, model_id=None),  # no aimManifest
        make_overlay("microsoft/DialoGPT-medium"),
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["meta-llama/Llama-3.1-8B", "microsoft/DialoGPT-medium"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert [m.canonical_name for m in result] == ["microsoft/DialoGPT-medium"]


@pytest.mark.asyncio
async def test_get_finetunable_models_excludes_when_no_templates_present(db_session: AsyncSession) -> None:
    """When the cluster advertises no AIMClusterProfiles, all recipes are hidden."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [make_overlay("meta-llama/Llama-3.1-8B")]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles([]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert result == []


@pytest.mark.asyncio
async def test_get_finetunable_models_combines_template_and_gpu_filters(db_session: AsyncSession) -> None:
    """A recipe is shown only when BOTH a matching template exists AND GPUs are compatible."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("template-and-gpu-ok/A", compatible_accelerators=["74a1"]),
        make_overlay("template-ok-gpu-bad/B", compatible_accelerators=["75a0"]),  # GPU mismatch
        make_overlay("gpu-ok-template-missing/C", compatible_accelerators=["74a1"]),  # no template
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["template-and-gpu-ok/A", "template-ok-gpu-bad/B"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert [m.canonical_name for m in result] == ["template-and-gpu-ok/A"]


@pytest.mark.asyncio
async def test_get_finetunable_models_reflects_templates_added_after_first_call(db_session: AsyncSession) -> None:
    """Recipe hidden when no template, then visible once a matching template appears on the cluster."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [make_overlay("meta-llama/Llama-3.1-8B")]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch(
            "app.aims.gateway.list_aim_cluster_profiles_by_aim_ids",
            side_effect=[[], [make_profile(spec_aim_id="meta-llama/Llama-3.1-8B")]],
        ),
    ):
        before = await get_finetunable_models(db_session, kube_client)
        after = await get_finetunable_models(db_session, kube_client)

    assert before == []
    assert [m.canonical_name for m in after] == ["meta-llama/Llama-3.1-8B"]


@pytest.mark.asyncio
async def test_get_finetunable_models_carries_hf_token_required_from_overlay(db_session: AsyncSession) -> None:
    """Each result mirrors the recipe overlay's metadata.hfTokenRequired flag.

    Three overlays cover the full domain: explicitly gated, explicitly not gated, and not
    declared. Only an explicit `false` produces an open model — an undeclared recipe is
    reported as gated, so the UI asks for a token rather than starting a job that cannot
    pull its weights.
    """
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("gated/model", hf_token_required=True),
        make_overlay("open/model", hf_token_required=False),
        make_overlay("undeclared/model"),
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["gated/model", "open/model", "undeclared/model"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    by_name = {m.canonical_name: m for m in result}
    assert by_name["gated/model"].hf_token_required is True
    assert by_name["open/model"].hf_token_required is False
    assert by_name["undeclared/model"].hf_token_required is True


@pytest.mark.asyncio
async def test_get_finetunable_models_treats_non_bool_hf_token_required_as_gated(db_session: AsyncSession) -> None:
    """A malformed overlay value (string, int) is reported as gated rather than leaking through.

    Guards the contract surfaced to the UI: `hfTokenRequired` is always a bool. An unreadable
    declaration resolves to gated, since presenting it as open drops the token prompt and the
    job dies at weight download.
    """
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [make_overlay("weird/model", hf_token_required="yes")]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["weird/model"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert result[0].hf_token_required is True


@pytest.mark.asyncio
async def test_get_finetunable_models_serializes_hf_token_required_as_camel_case(db_session: AsyncSession) -> None:
    """The wire payload uses camelCase `hfTokenRequired` so the UI can read it directly."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [make_overlay("gated/model", hf_token_required=True)]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["gated/model"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    payload = result[0].model_dump(by_alias=True)
    assert payload["hfTokenRequired"] is True
    assert "hf_token_required" not in payload


@pytest.mark.parametrize("non_ready_status", ["Pending", "Progressing", "Degraded", "Failed", "NotAvailable"])
@pytest.mark.asyncio
async def test_get_finetunable_models_excludes_recipe_when_template_not_ready(
    db_session: AsyncSession, non_ready_status: str
) -> None:
    """Templates whose status.status is not Ready do not contribute their modelId, even if spec.modelId is populated."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [make_overlay("meta-llama/Llama-3.1-8B")]
    kube_client = make_kube_client()
    not_ready_template = make_profile(spec_aim_id="meta-llama/Llama-3.1-8B", status=non_ready_status)

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch("app.aims.gateway.list_aim_cluster_profiles_by_aim_ids", return_value=[not_ready_template]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert result == []


@pytest.mark.asyncio
async def test_delete_model_with_active_deployments_raises_conflict(test_namespace: str) -> None:
    """Deleting a model with active AIMService deployments raises DeletionConflictException."""
    model_name = "deployed-model"
    mock_kube_client = AsyncMock(spec=KubernetesClient)
    mock_minio_client = MagicMock(spec=MinioClient)

    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=model_name, namespace=test_namespace),
        spec=AIMModelSpec(model_sources=[AIMModelSource(source_uri="s3://bucket/path/")]),
    )

    with (
        patch("app.aims.gateway.get_aim_model", return_value=aim_model),
        patch("app.aims.gateway.list_aim_services_for_model", return_value=[MagicMock()]),
        patch("app.aims.gateway.delete_aim_model", new_callable=AsyncMock) as mock_delete_cr,
        patch("app.models.service.delete_from_s3", new_callable=AsyncMock) as mock_delete_s3,
        pytest.raises(DeletionConflictException),
    ):
        await delete_model(mock_kube_client, model_name, test_namespace, mock_minio_client)

    mock_delete_cr.assert_not_called()
    mock_delete_s3.assert_not_called()


@pytest.mark.asyncio
async def test_delete_model_force_deletes_with_active_deployments(test_namespace: str) -> None:
    """With force=True, active AIMServices are deleted first, then the model is removed."""
    model_name = "deployed-model"
    mock_kube_client = AsyncMock(spec=KubernetesClient)
    mock_minio_client = MagicMock(spec=MinioClient)

    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=model_name, namespace=test_namespace),
        spec=AIMModelSpec(model_sources=[AIMModelSource(source_uri="s3://bucket/path/")]),
    )
    mock_svc = MagicMock()
    mock_svc.metadata.name = "wb-aim-active-123"
    mock_svc.id = str(uuid4())

    with (
        patch("app.aims.gateway.get_aim_model", return_value=aim_model),
        patch("app.aims.gateway.list_aim_services_for_model", return_value=[mock_svc]),
        patch("app.aims.gateway.delete_aim_service", new_callable=AsyncMock) as mock_delete_svc,
        patch("app.aims.gateway.delete_aim_model", new_callable=AsyncMock) as mock_delete_cr,
        patch("app.models.service.delete_from_s3", new_callable=AsyncMock),
    ):
        await delete_model(mock_kube_client, model_name, test_namespace, mock_minio_client, force=True)

    mock_delete_svc.assert_called_once()
    mock_delete_cr.assert_called_once_with(mock_kube_client, test_namespace, model_name)


@pytest.mark.asyncio
async def test_delete_model_s3_not_found_logs_warning(test_namespace: str) -> None:
    """If S3 weights are missing, delete_model logs a warning and continues without raising."""
    model_name = "model-missing-s3"
    mock_kube_client = AsyncMock(spec=KubernetesClient)
    mock_minio_client = MagicMock(spec=MinioClient)

    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=model_name, namespace=test_namespace),
        spec=AIMModelSpec(model_sources=[AIMModelSource(source_uri="s3://bucket/weights/")]),
    )

    with (
        patch("app.aims.gateway.get_aim_model", return_value=aim_model),
        patch("app.aims.gateway.list_aim_services_for_model", return_value=[]),
        patch("app.aims.gateway.delete_aim_model", new_callable=AsyncMock),
        patch("app.models.service.delete_from_s3", side_effect=NotFoundException("S3 object not found")),
    ):
        # Should not raise — CR is deleted, S3 miss logged as warning
        await delete_model(mock_kube_client, model_name, test_namespace, mock_minio_client)


# ============================================================================
# Orchestration Tests - run_finetune_model_workload
# ============================================================================


@pytest.mark.asyncio
async def test_run_finetune_model_workload_with_uuid(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test run_finetune_model_workload with existing AIMModel UUID (transfer learning)."""
    model_uuid = uuid4()
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=str(model_uuid), namespace=test_namespace),
        spec=AIMModelSpec(
            model_sources=[
                AIMModelSource(model_id="acme/base-model", source_uri="s3://bucket/models/base-model/weights")
            ]
        ),
        status=AIMModelStatusFields(
            status="Ready",
            image_metadata=AIMImageMetadata(model=AIMModelMetadata(canonical_name="meta-llama/Llama-3.1-8B")),
        ),
    )

    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(
        display_name="Finetuned-Model",
        dataset_id=dataset.id,
        batch_size=4,
        learning_rate=0.0001,
        epochs=3,
    )

    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.aims_gateway.get_aim_model", return_value=aim_model),
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", return_value="mock-manifest"),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock) as mock_apply,
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id=model_uuid,
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args[1] if mock_apply.call_args[1] else {}
        extra_labels = call_kwargs.get("extra_labels", {})
        assert extra_labels[MODEL_NAME_LABEL] == "Finetuned-Model"
        assert extra_labels[MODEL_ID_LABEL] == str(result.workload_id)

        assert result.display_name == "Finetuned-Model"
        assert result.base_model == "meta-llama/Llama-3.1-8B"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_resolves_weights_from_profiles_overrides(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """A re-finetune base whose weights live under spec.profiles.overrides.modelSources
    (the v1alpha2 imported / fine-tuned shape, with no flat spec.modelSources) succeeds,
    and that override URI is forwarded as the base model URI for training."""
    model_uuid = uuid4()
    override_uri = "s3://bucket/ns/finetuned-models/llama3/run1/checkpoint-final"
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=str(model_uuid), namespace=test_namespace),
        spec=AIMModelSpec(
            model_sources=[],  # legacy flat field empty — weights only in profiles overrides
            profiles=AIMModelProfilesSpec(
                overrides=ProfileOverrides(
                    model_id="meta-llama/Llama-3.1-8B",
                    model_sources=[AIMModelSource(model_id="meta-llama/Llama-3.1-8B", source_uri=override_uri)],
                )
            ),
        ),
        status=AIMModelStatusFields(status="Ready", aim_id="meta-llama/Llama-3.1-8B"),
    )

    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(display_name="Re-Finetuned-Model", dataset_id=dataset.id)

    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}
    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.aims_gateway.get_aim_model", return_value=aim_model),
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id=model_uuid,
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    assert result.base_model == "meta-llama/Llama-3.1-8B"
    assert len(helm_overrides_captured) == 1
    overrides = helm_overrides_captured[0]
    # basemodel is the override weights URI with the s3:// scheme stripped, as the
    # training chart expects.
    assert overrides["basemodel"] == override_uri.removeprefix("s3://")
    # modelId is carried forward from the resolved source so the published AIMModel CR
    # gets the correct artifact identity.
    assert overrides["aimManifest"]["modelManifest"]["modelId"] == "meta-llama/Llama-3.1-8B"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_with_canonical_name(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test run_finetune_model_workload with canonical name (HuggingFace download)."""
    # Create dataset
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")

    # Create chart
    chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    # Create finetuning request
    finetuning_data = FinetuneCreate(
        display_name="HF-Finetuned-Model",
        dataset_id=dataset.id,
        batch_size=4,
        learning_rate=0.0001,
        epochs=3,
    )

    # Mock dependencies
    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", return_value="mock-manifest"),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock) as mock_apply,
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args[1] if mock_apply.call_args[1] else {}
        extra_labels = call_kwargs.get("extra_labels", {})
        assert extra_labels[MODEL_NAME_LABEL] == "HF-Finetuned-Model"
        assert extra_labels[MODEL_ID_LABEL] == str(result.workload_id)
        assert result.display_name == "HF-Finetuned-Model"
        assert result.base_model == "meta-llama/Llama-3.1-8B"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_succeeds_when_profile_listing_fails(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """A failed profile listing falls back rather than failing the submission.

    The gateway raises on an API-server error, which reaches the caller as a 502. The
    selection is written so that *missing* profile evidence falls back — refusing on it
    would block fine-tuning that works today — so an error reaching the submission would
    defeat that design for a transient blip. The submission call site degrades the error
    to no evidence; the other callers of the same gateway function still see the raise.
    """
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(display_name="Degraded-Profiles-Model", dataset_id=dataset.id)

    overlay = make_overlay("meta-llama/Llama-3.1-8B", aim_id="meta-llama/Llama-3.1-8B")

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B", name="llama-v1"),
        patch(
            "app.models.service.aims_gateway.list_aim_cluster_profiles_by_aim_ids",
            new_callable=AsyncMock,
            side_effect=ExternalServiceError("Failed to list AIMClusterProfiles: ServiceUnavailable"),
        ),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    assert result.display_name == "Degraded-Profiles-Model"
    # The fallback still picked a base model, so the manifest names one.
    assert len(helm_overrides_captured) == 1
    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "llama-v1"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_stamps_description_on_workload_resource(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """The description is stamped onto the workload's own Job/Deployment so it is readable
    from GET /projects/{project}/workloads/{id}, which sources annotations from that resource."""
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(
        display_name="Described-Model",
        description="A helpful description",
        dataset_id=dataset.id,
    )

    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", return_value="mock-manifest"),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock) as mock_apply,
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    mock_apply.assert_called_once()
    extra_annotations = mock_apply.call_args.kwargs["extra_annotations"]
    assert extra_annotations[DESCRIPTION_ANNOTATION] == "A helpful description"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_omits_description_annotation_when_absent(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """No description supplied leaves the workload resource without the description annotation."""
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(display_name="Undescribed-Model", dataset_id=dataset.id)

    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", return_value="mock-manifest"),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock) as mock_apply,
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    mock_apply.assert_called_once()
    extra_annotations = mock_apply.call_args.kwargs["extra_annotations"] or {}
    assert DESCRIPTION_ANNOTATION not in extra_annotations


@pytest.mark.asyncio
async def test_run_finetune_model_workload_uses_multiple_datasets(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    datasets = [
        await factory.create_dataset(
            db_session,
            namespace=test_namespace,
            name=f"Training Dataset {index}",
            path=f"training-{index}.jsonl",
        )
        for index in range(2)
    ]
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)
    overlay = MagicMock(spec=Overlay)
    overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}
    captured_overrides: list[dict] = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        captured_overrides.append(overlays_values[-1])
        return "mock-manifest"

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=FinetuneCreate(
                display_name="Multi-dataset model",
                dataset_ids=[dataset.id for dataset in datasets],
            ),
            submitter=test_user,
            namespace=test_namespace,
        )

    training_data = captured_overrides[0]["finetuning_config"]["data_conf"]["training_data"]
    assert training_data["datasets"] == [{"path": f"{MINIO_BUCKET}/{dataset.path}"} for dataset in datasets]
    workload = await db_session.get(Workload, result.workload_id)
    assert workload is not None
    assert workload.dataset_id == datasets[0].id
    assert workload.dataset_refs == [{"id": str(dataset.id), "name": dataset.name} for dataset in datasets]


@pytest.mark.asyncio
async def test_run_finetune_model_workload_with_single_segment_hf_name(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Single-segment HuggingFace model IDs (for example 'gpt2') should remain supported."""
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(
        display_name="HF-Single-Segment-Finetuned-Model",
        dataset_id=dataset.id,
        batch_size=4,
        learning_rate=0.0001,
        epochs=3,
    )

    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "gpt2"
    mock_overlay.overlay = {"aimManifest": {"aimId": "gpt2", "modelId": "gpt2"}}

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch_cluster_model("gpt2"),
        patch("app.models.service.render_helm_template", return_value="mock-manifest"),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
        patch(
            "app.models.service.get_aim_model", new_callable=AsyncMock, side_effect=NotFoundException("not found")
        ) as mock_get_aim_model,
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="gpt2",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    assert result.base_model == "gpt2"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_includes_mlflow_tracking_when_mlflow_workspace_running(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """Finetuning config gets MLflow tracking from workload endpoints (internal), not output."""
    finetuning_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    mlflow_chart = await factory.create_chart(db_session, name=MLFLOW_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    mlflow_workload = await factory.create_workload(
        db_session,
        namespace=test_namespace,
        chart=mlflow_chart,
        status=WorkloadStatus.RUNNING,
        workload_type=WorkloadType.WORKSPACE,
        include_isolation_data=False,
    )
    mlflow_response = WorkloadResponse.model_validate(mlflow_workload)
    expected_uri = mlflow_response.endpoints["internal"]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    test_overlay = MagicMock(spec=Overlay)
    test_overlay.canonical_name = "test/model"
    test_overlay.overlay = {"aimManifest": {"aimId": "test/model", "modelId": "test/model"}}

    kube_client = make_kube_client()
    with (
        patch("app.models.service.list_overlays", return_value=[test_overlay]),
        patch_cluster_model("test/model"),
        patch("app.models.service.get_workloads", new_callable=AsyncMock, return_value=[mlflow_workload]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=kube_client,
            model_id="test/model",
            finetuning_data=FinetuneCreate(display_name="my-run", dataset_id=dataset.id),
            submitter="test@example.com",
            namespace=test_namespace,
        )

    assert len(helm_overrides_captured) == 1
    overrides = helm_overrides_captured[0]
    assert "finetuning_config" in overrides
    tracking = overrides["finetuning_config"].get("tracking")
    assert tracking is not None
    assert tracking["mlflow_server_uri"] == expected_uri
    assert tracking["experiment_name"] == "my-run"
    assert overrides["finetuning_config"]["training_args"]["report_to"] == ["mlflow"]


@pytest.mark.asyncio
async def test_run_finetune_model_workload_skips_mlflow_tracking_when_no_mlflow_workspace(
    db_session: AsyncSession, test_namespace: str
) -> None:
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    test_overlay = MagicMock(spec=Overlay)
    test_overlay.canonical_name = "test/model"
    test_overlay.overlay = {"aimManifest": {"aimId": "test/model", "modelId": "test/model"}}

    kube_client = make_kube_client()
    with (
        patch("app.models.service.list_overlays", return_value=[test_overlay]),
        patch_cluster_model("test/model"),
        patch("app.models.service.get_workloads", new_callable=AsyncMock, return_value=[]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=kube_client,
            model_id="test/model",
            finetuning_data=FinetuneCreate(display_name="my-run", dataset_id=dataset.id),
            submitter="test@example.com",
            namespace=test_namespace,
        )

    assert len(helm_overrides_captured) == 1
    overrides = helm_overrides_captured[0]
    assert "finetuning_config" in overrides
    assert "tracking" not in overrides["finetuning_config"]


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sets_bucket_storage_host(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """bucketStorageHost in helm overrides uses MINIO_URL so pods do not inherit a stale chart default."""
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    test_overlay = MagicMock(spec=Overlay)
    test_overlay.canonical_name = "test/model"
    test_overlay.overlay = {"aimManifest": {"aimId": "test/model", "modelId": "test/model"}}

    minio_url = "http://minio.example.svc.cluster.local:80"
    with (
        patch("app.models.service.list_overlays", return_value=[test_overlay]),
        patch_cluster_model("test/model"),
        patch("app.models.service.get_workloads", new_callable=AsyncMock, return_value=[]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
        patch("app.models.service.MINIO_URL", minio_url),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=FinetuneCreate(display_name="my-run", dataset_id=dataset.id),
            submitter="test@example.com",
            namespace=test_namespace,
        )

    assert len(helm_overrides_captured) == 1
    overrides = helm_overrides_captured[0]
    assert overrides["bucketStorageHost"] == minio_url


@pytest.mark.asyncio
async def test_run_finetune_model_workload_without_hf_token_does_not_call_get_secret_details(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)
    finetuning_data = FinetuneCreate(
        display_name="No-HF-Token-Model",
        dataset_id=dataset.id,
        batch_size=4,
        learning_rate=0.0001,
        epochs=3,
    )
    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", return_value="mock-manifest"),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
        patch("app.models.service.get_secret_details") as mock_get_secret,
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )
        mock_get_secret.assert_not_called()


@pytest.mark.asyncio
async def test_run_finetune_model_workload_with_hf_token(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    # Create dataset
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")

    # Create chart
    chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    # Create finetuning request with HF token secret name
    finetuning_data = FinetuneCreate(
        display_name="HF-Token-Model",
        dataset_id=dataset.id,
        batch_size=4,
        learning_rate=0.0001,
        epochs=3,
        hf_token_secret_name="hf-token-secret",
    )

    # Mock dependencies
    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    hf_secret = SecretResponse(metadata=K8sMetadata(name="hf-token-secret", namespace=test_namespace))

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", return_value="mock-manifest") as mock_render,
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
        patch("app.models.service.get_secret_details", return_value=hf_secret) as mock_get_secret,
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

        # Verify render was called with HF token secret
        call_args = mock_render.call_args
        overlays = call_args[1]["overlays_values"]
        helm_overrides = overlays[-1]

        assert "hfTokenSecret" in helm_overrides
        assert helm_overrides["hfTokenSecret"]["name"] == "hf-token-secret"
        assert helm_overrides["hfTokenSecret"]["key"] == "token"

        mock_get_secret.assert_called_once_with(
            namespace=test_namespace,
            secret_name="hf-token-secret",
            kube_client=mock_kube_client,
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sets_aim_manifest_helm_overrides(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """aimManifest helm overrides are set so the aimmodel-applier sidecar creates the AIMModel CR after training."""
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    test_overlay = MagicMock(spec=Overlay)
    test_overlay.canonical_name = "test/model"
    test_overlay.overlay = {"aimManifest": {"aimId": "test/model", "modelId": "test/model"}}

    with (
        patch("app.models.service.list_overlays", return_value=[test_overlay]),
        patch_cluster_model("test/model"),
        patch("app.models.service.get_workloads", new_callable=AsyncMock, return_value=[]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock) as mock_apply,
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=FinetuneCreate(display_name="my-finetuned-model", dataset_id=dataset.id),
            submitter="test@example.com",
            namespace=test_namespace,
        )

    assert len(helm_overrides_captured) == 1
    overrides = helm_overrides_captured[0]
    model_manifest = overrides.get("aimManifest", {}).get("modelManifest")
    assert model_manifest is not None, (
        "aimManifest.modelManifest must be in helm overrides to enable the manifest-applier sidecar"
    )
    assert model_manifest["enabled"] is True
    assert model_manifest["modelName"].startswith("wb-"), "modelName should be the workload's K8s resource name"
    labels = model_manifest.get("labels", {})
    # WORKLOAD_TYPE_LABEL is the contract with fine_tuning.service._is_fine_tuning_model, which
    # backs GET /v1/projects/{project}/fine-tuning/models. Without it the resulting AIMModel is
    # invisible to the Custom Models page.
    assert labels.get(WORKLOAD_TYPE_LABEL) == WorkloadType.FINE_TUNING.value
    assert labels.get(WORKLOAD_ID_LABEL) == str(result.workload_id)
    assert labels.get(MODEL_NAME_LABEL) == "my-finetuned-model"
    assert TRAINING_OUTPUT_ANNOTATION not in model_manifest["annotations"]
    apply_call = mock_apply.await_args
    assert apply_call is not None
    assert apply_call.kwargs["extra_annotations"] is None
    # Every label value MUST be a plain str — if a StrEnum or UUID leaks through,
    # yaml.dump emits it as a YAML sequence and the Helm `quote` filter renders
    # it as `"[FINE_TUNING]"`, which K8s rejects as an invalid label value.
    for key, value in labels.items():
        assert isinstance(value, str) and not isinstance(value, Enum), (
            f"label {key} must be a plain str, got {type(value).__name__}: {value!r}"
        )
    # Belt-and-suspenders: dump through PyYAML and confirm no flow-style sequence
    # leaks into the rendered output for any label value.
    rendered = yaml.dump({"labels": labels})
    assert "[" not in rendered and "]" not in rendered, (
        f"model_manifest labels must yaml-dump as scalars, not sequences:\n{rendered}"
    )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_uuid_base_uses_aim_id_for_overlay_lookup(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """When a finetuned model (UUID) has no image_metadata canonical_name, spec.aim_id is used
    for overlay lookup so the correct DeepSpeed/bf16 config is applied.

    The recipe found by that lookup declares a different identity from the model being
    re-finetuned, because the lookup resolves to the base the model came from rather than to the
    model itself. Both halves of the stamped identity must therefore come from the AIMModel, not
    the recipe — an identical fixture would let either source pass.

    The same identity also selects the AIMClusterModel to derive profiles from, so the only Ready
    cluster model here carries the AIMModel's aimId. Resolving from the recipe instead would find
    none and raise, making this fixture discriminate on both uses at once.
    """
    model_uuid = uuid4()
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=str(model_uuid), namespace=test_namespace),
        spec=AIMModelSpec(
            model_sources=[
                AIMModelSource(model_id="acme/finetuned", source_uri="s3://bucket/models/finetuned/weights")
            ],
            aim_id="meta-llama/Llama-3.1-8B",  # stamped by aimmodel-applier; no OCI image metadata
        ),
        # status.aim_id mirrors spec.aim_id — the v1alpha2 controller populates
        # it from spec or discovery, and production code reads from status.
        status=AIMModelStatusFields(status="Ready", aim_id="meta-llama/Llama-3.1-8B"),
    )

    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(
        display_name="Level-2-Finetuned",
        dataset_id=dataset.id,
    )

    mock_kube_client = make_kube_client()
    overlay_canonical_names_used: list[str | None] = []
    helm_overrides_captured: list = []

    recipe_overlay = make_overlay(
        "meta-llama/Llama-3.1-8B",
        aim_id="recipe/declared-aim-id",
        model_id="recipe/declared-model-id",
    )

    async def capture_list_overlays(session, chart_id, canonical_name, include_generic=False):
        overlay_canonical_names_used.append(canonical_name)
        return [recipe_overlay]

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.aims_gateway.get_aim_model", return_value=aim_model),
        patch("app.models.service.list_overlays", side_effect=capture_list_overlays),
        patch("app.models.service.get_workloads", return_value=[]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id=model_uuid,
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    assert result.base_model == "meta-llama/Llama-3.1-8B"
    assert overlay_canonical_names_used == ["meta-llama/Llama-3.1-8B"], (
        "Overlay lookup must use the original HF canonical name from aim_id, not the UUID"
    )

    assert len(helm_overrides_captured) == 1
    aim_manifest = helm_overrides_captured[0]["aimManifest"]["modelManifest"]
    assert aim_manifest.get("aimId") == "meta-llama/Llama-3.1-8B", (
        "aimId must come from the AIMModel status, not the recipe the canonical-name lookup found"
    )
    assert aim_manifest.get("modelId") == aim_model.spec.model_sources[0].model_id, (
        "modelId must come from the model's own weights source, not the recipe's"
    )


@pytest.mark.parametrize("dataset_namespace", [None, "another-project"])
@pytest.mark.asyncio
async def test_run_finetune_model_workload_dataset_not_found(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
    dataset_namespace: str | None,
) -> None:
    dataset_id = (
        (await factory.create_dataset(db_session, namespace=dataset_namespace)).id if dataset_namespace else uuid4()
    )
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        pytest.raises(NotFoundException, match=str(dataset_id)),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=FinetuneCreate(display_name="Invalid dataset model", dataset_ids=[dataset_id]),
            submitter=test_user,
            namespace=test_namespace,
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_reports_only_missing_dataset_ids(
    db_session: AsyncSession,
    test_namespace: str,
    test_user: str,
) -> None:
    available_dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    missing_dataset_id = uuid4()
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        pytest.raises(NotFoundException) as exc_info,
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=FinetuneCreate(
                display_name="Invalid dataset model",
                dataset_ids=[available_dataset.id, missing_dataset_id],
            ),
            submitter=test_user,
            namespace=test_namespace,
        )

    assert str(missing_dataset_id) in str(exc_info.value)
    assert str(available_dataset.id) not in str(exc_info.value)


@pytest.mark.parametrize(
    "spec",
    [
        # No weights in either the flat field or any profiles override.
        AIMModelSpec(model_sources=[]),
        # A profiles block exists but its override carries no model sources — still no weights.
        AIMModelSpec(model_sources=[], profiles=AIMModelProfilesSpec(overrides=ProfileOverrides(model_sources=[]))),
    ],
    ids=["no-profiles", "empty-profiles-override"],
)
@pytest.mark.asyncio
async def test_run_finetune_model_workload_model_without_weights(
    db_session: AsyncSession, test_namespace: str, test_user: str, spec: AIMModelSpec
) -> None:
    """When neither the flat spec.modelSources nor profiles.overrides.modelSources
    carries a weights URI, finetuning is rejected with the existing ValidationException."""
    model_uuid = uuid4()
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=str(model_uuid), namespace=test_namespace),
        spec=spec,
        status=AIMModelStatusFields(status="Ready"),
    )

    finetuning_data = FinetuneCreate(
        display_name="Finetuned-Model",
        dataset_id=uuid4(),
        batch_size=4,
        learning_rate=0.0001,
        epochs=3,
    )

    mock_kube_client = make_kube_client()

    with (
        patch("app.models.service.aims_gateway.get_aim_model", return_value=aim_model),
        pytest.raises(ValidationException, match="has no weights URI"),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id=model_uuid,
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_deployment_failure(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Test run_finetune_model_workload sets workload status to FAILED on deployment error."""
    # Create dataset
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")

    # Create chart
    chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    # Create finetuning request
    finetuning_data = FinetuneCreate(
        display_name="Failed-Deployment",
        dataset_id=dataset.id,
        batch_size=4,
        learning_rate=0.0001,
        epochs=3,
    )

    # Mock dependencies
    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", return_value="mock-manifest"),
        patch("app.models.service.apply_manifest", side_effect=Exception("K8s deployment failed")),
        pytest.raises(Exception, match="K8s deployment failed"),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_with_uuid_as_string(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """A model_id passed as a UUID string takes the transfer-learning path, same as a UUID object."""
    model_uuid = uuid4()
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=str(model_uuid), namespace=test_namespace),
        spec=AIMModelSpec(
            model_sources=[
                AIMModelSource(model_id="acme/base-model", source_uri="s3://bucket/models/base-model/weights")
            ]
        ),
        status=AIMModelStatusFields(
            status="Ready",
            image_metadata=AIMImageMetadata(model=AIMModelMetadata(canonical_name="meta-llama/Llama-3.1-8B")),
        ),
    )

    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(
        display_name="Finetuned-Model",
        dataset_id=dataset.id,
        batch_size=4,
        learning_rate=0.0001,
        epochs=3,
    )

    mock_kube_client = make_kube_client()
    mock_overlay = MagicMock(spec=Overlay)
    mock_overlay.canonical_name = "meta-llama/Llama-3.1-8B"
    mock_overlay.overlay = {"aimManifest": {"aimId": "meta-llama/Llama-3.1-8B", "modelId": "meta-llama/Llama-3.1-8B"}}

    with (
        patch("app.models.service.aims_gateway.get_aim_model", return_value=aim_model),
        patch("app.models.service.list_overlays", return_value=[mock_overlay]),
        patch_cluster_model("meta-llama/Llama-3.1-8B"),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.render_helm_template", return_value="mock-manifest"),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock) as mock_apply,
    ):
        result = await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id=str(model_uuid),
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args[1] if mock_apply.call_args[1] else {}
        extra_labels = call_kwargs.get("extra_labels", {})
        assert extra_labels[MODEL_NAME_LABEL] == "Finetuned-Model"
        assert extra_labels[MODEL_ID_LABEL] == str(result.workload_id)
        assert result.display_name == "Finetuned-Model"
        assert result.base_model == "meta-llama/Llama-3.1-8B"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sets_base_model_from_cluster_model(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """aimManifest.baseModel.name is the AIMClusterModel name matching the recipe's aimId.

    The aim-engine controller resolves modelRef by AIMClusterModel name (not AIMClusterProfile
    name). The fine-tuned AIMModel inherits the optimized profiles via the source-model label
    that aim-engine stamps on profiles when it discovers them from the AIMClusterModel.
    """
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)
    mock_kube_client = make_kube_client()

    overlay = make_overlay("meta-llama/Llama-3.1-8B", aim_id="meta-llama/Llama-3.1-8B")

    cluster_model = make_cluster_model(aim_id="meta-llama/Llama-3.1-8B", status="Ready")
    cluster_model.metadata.name = "amdenterpriseai-aim-instinct-meta-llama-3-1-8b-cluster-model"

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", return_value=[cluster_model]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    assert len(helm_overrides_captured) == 1
    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "amdenterpriseai-aim-instinct-meta-llama-3-1-8b-cluster-model"
    assert base_model["scope"] == "Auto"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sets_base_model_from_cluster_model_uuid_base(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """For UUID-based re-finetunes, aimId falls back to aim_model.status.aim_id when the overlay lacks it."""
    model_uuid = uuid4()
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name=str(model_uuid), namespace=test_namespace),
        spec=AIMModelSpec(
            model_sources=[
                AIMModelSource(model_id="acme/base-model", source_uri="s3://bucket/models/base-model/weights")
            ]
        ),
        status=AIMModelStatusFields(
            status="Ready",
            aim_id="meta-llama/Llama-3.1-8B",
            image_metadata=AIMImageMetadata(model=AIMModelMetadata(canonical_name="meta-llama/Llama-3.1-8B")),
        ),
    )

    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(display_name="Re-FT-Model", dataset_id=dataset.id)
    mock_kube_client = make_kube_client()

    # Overlay has no aimManifest.aimId — simulates a generic or missing recipe overlay
    overlay_without_aim_id = MagicMock(spec=Overlay)
    overlay_without_aim_id.canonical_name = "meta-llama/Llama-3.1-8B"
    overlay_without_aim_id.overlay = {}

    cluster_model = make_cluster_model(aim_id="meta-llama/Llama-3.1-8B", status="Ready")
    cluster_model.metadata.name = "amdenterpriseai-aim-instinct-meta-llama-3-1-8b-cluster-model"

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.aims_gateway.get_aim_model", return_value=aim_model),
        patch("app.models.service.list_overlays", return_value=[overlay_without_aim_id]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", return_value=[cluster_model]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id=model_uuid,
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    assert len(helm_overrides_captured) == 1
    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "amdenterpriseai-aim-instinct-meta-llama-3-1-8b-cluster-model"
    assert base_model["scope"] == "Auto"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_raises_when_no_ready_cluster_model(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """When no Ready AIMClusterModel matches the recipe aimId, a ValidationException is raised.

    There is no fallback — a fine-tuning job without a resolvable model would produce a
    broken AIMModel that can never deploy, so we fail fast before the job is submitted.
    """
    dataset = await factory.create_dataset(db_session, namespace=test_namespace, name="Training Dataset")
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, chart_type=WorkloadType.FINE_TUNING)

    finetuning_data = FinetuneCreate(display_name="FT-Model-No-Profile", dataset_id=dataset.id)
    mock_kube_client = make_kube_client()

    overlay = make_overlay("meta-llama/Llama-3.1-8B", aim_id="meta-llama/Llama-3.1-8B")
    not_ready_model = make_cluster_model(aim_id="meta-llama/Llama-3.1-8B", status="Pending")

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", return_value=[not_ready_model]),
        pytest.raises(ValidationException),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=mock_kube_client,
            model_id="meta-llama/Llama-3.1-8B",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )


# ============================================================================
# Fine-tuning output shape - adapter vs model, LoRA settings
# ============================================================================


async def launch_finetune(
    db_session: AsyncSession,
    namespace: str,
    finetuning_data: FinetuneCreate,
    *,
    overlay: MagicMock,
    model_id: str = "test/model",
    mlflow_workloads: list | None = None,
) -> dict:
    """Run a fine-tune launch against a stubbed cluster and return the rendered helm values.

    The recipe overlay is the only interesting input for output-shape tests, so everything
    else on the launch path is stubbed to its success case. `mlflow_workloads` stands in for
    the project's running MLflow workspaces; the default of none skips tracking entirely.
    """
    captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):  # noqa: ARG001
        captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch_cluster_model(overlay.canonical_name),
        patch("app.models.service.get_workloads", new_callable=AsyncMock, return_value=mlflow_workloads or []),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id=model_id,
            finetuning_data=finetuning_data,
            submitter="test@example.com",
            namespace=namespace,
        )

    assert len(captured) == 1
    return captured[0]


@pytest.mark.asyncio
async def test_run_finetune_model_workload_defaults_to_model_output(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """A request that says nothing about output trains a model, exactly as it did before adapters existed.

    Guards the backward-compatible default: existing clients send no `output` and no `lora`,
    and must keep getting a merged model with the recipe's own PEFT config untouched.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-model", dataset_id=dataset.id)

    assert finetuning_data.output is FineTuningOutput.MODEL
    assert finetuning_data.lora is None

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="lora")
    )

    assert overrides["aimManifest"]["modelManifest"]["enabled"] is True
    assert overrides["aimManifest"]["adapterManifest"]["enabled"] is False
    assert (
        overrides["aimManifest"]["modelManifest"]["annotations"][TRAINING_OUTPUT_ANNOTATION]
        == TrainingOutput.MERGED.value
    )
    assert SOURCE_DESCRIPTION_ANNOTATION not in overrides["aimManifest"]["modelManifest"]["annotations"]
    assert overrides["aimManifest"]["modelManifest"]["annotations"][SUBMITTER_ANNOTATION] == "test@example.com"
    # An untouched peft_conf is what preserves the recipe's own rank/alpha/target_modules.
    assert "peft_conf" not in overrides["finetuning_config"]
    # mergeAdapter is absent rather than True — the chart's own default governs the model arm.
    assert "mergeAdapter" not in overrides


@pytest.mark.asyncio
async def test_run_finetune_model_workload_adapter_output_enables_adapter_manifest(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """Requesting an adapter keeps the trained adapter instead of merging it into a model.

    The three settings move together: the adapter manifest is enabled, the model manifest is
    disabled, and the merge is skipped. The chart refuses to render a model manifest while the
    merge is skipped, so any one of them drifting out of step breaks the job.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(
        display_name="my-adapter",
        description="Sentiment adapter for support tickets.",
        dataset_id=dataset.id,
        output=FineTuningOutput.ADAPTER,
    )

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="lora")
    )

    assert overrides["aimManifest"]["modelManifest"]["enabled"] is False
    assert overrides["mergeAdapter"] is False

    adapter_manifest = overrides["aimManifest"]["adapterManifest"]
    assert adapter_manifest["enabled"] is True
    assert adapter_manifest["adapterName"].startswith("wb-"), "adapterName should be the workload's K8s resource name"
    assert adapter_manifest["organisation"] == ADAPTER_ORGANISATION
    assert adapter_manifest["displayName"] == "my-adapter"
    assert adapter_manifest["description"] == "Sentiment adapter for support tickets."
    assert adapter_manifest["annotations"][DISPLAY_NAME_ANNOTATION] == "my-adapter"
    assert adapter_manifest["annotations"][DESCRIPTION_ANNOTATION] == "Sentiment adapter for support tickets."
    assert adapter_manifest["annotations"][TRAINING_OUTPUT_ANNOTATION] == TrainingOutput.LORA.value
    assert adapter_manifest["annotations"][SUBMITTER_ANNOTATION] == "test@example.com"
    assert adapter_manifest["labels"][WORKLOAD_TYPE_LABEL] == WorkloadType.FINE_TUNING.value
    assert adapter_manifest["labels"][MODEL_NAME_LABEL] == "my-adapter"
    # compatibleWith renders solely from `model`; an unset one yields an adapter that reports
    # Ready but can never attach to anything.
    assert overrides["model"] == "test/model"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_model_output_keeps_description(
    db_session: AsyncSession, test_namespace: str
) -> None:
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(
        display_name="my-model",
        description="Sentiment model for support tickets.",
        dataset_id=dataset.id,
    )

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="lora")
    )

    model_manifest = overrides["aimManifest"]["modelManifest"]
    assert model_manifest["annotations"][SOURCE_DESCRIPTION_ANNOTATION] == "Sentiment model for support tickets."
    adapter_manifest = overrides["aimManifest"]["adapterManifest"]
    assert "description" not in adapter_manifest


@pytest.mark.asyncio
async def test_run_finetune_model_workload_adapter_labels_are_plain_strings(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """Adapter manifest labels survive the yaml.dump → Helm → kubectl apply round trip.

    Same hazard the model manifest guards against: a StrEnum or UUID leaking through dumps as
    a YAML sequence and renders as the invalid label value `"[FINE_TUNING]"`.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="lora")
    )

    labels = overrides["aimManifest"]["adapterManifest"]["labels"]
    adapter_manifest = overrides["aimManifest"]["adapterManifest"]
    assert DESCRIPTION_ANNOTATION not in adapter_manifest["annotations"]
    assert "description" not in adapter_manifest
    for key, value in labels.items():
        assert isinstance(value, str) and not isinstance(value, Enum), (
            f"label {key} must be a plain str, got {type(value).__name__}: {value!r}"
        )
    rendered = yaml.dump({"labels": labels})
    assert "[" not in rendered and "]" not in rendered, (
        f"adapter labels must yaml-dump as scalars, not sequences:\n{rendered}"
    )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sends_only_supplied_lora_settings(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """A partial `lora` object writes only the keys the caller named.

    Helm deep-merges maps, so an incomplete peft_kwargs layers over the recipe's own values and
    leaves its `target_modules` in place. Writing the unset keys as null — or writing the whole
    peft_conf — would wipe architecture-specific settings the platform has no business choosing.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-model", dataset_id=dataset.id, lora=LoraSettings(rank=32))

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="lora")
    )

    assert overrides["finetuning_config"]["peft_conf"] == {"peft_kwargs": {"r": 32}}


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sends_all_supplied_lora_settings(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """Each LoRA request field maps onto the peft_kwargs name the training recipe expects.

    The request spelling and the peft library's spelling deliberately differ, so this pins the
    whole mapping rather than trusting the names to line up.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(
        display_name="my-model",
        dataset_id=dataset.id,
        lora=LoraSettings(rank=16, alpha=32, dropout=0.05),
    )

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="lora")
    )

    assert overrides["finetuning_config"]["peft_conf"] == {
        "peft_kwargs": {"r": 16, "lora_alpha": 32, "lora_dropout": 0.05}
    }


@pytest.mark.asyncio
async def test_run_finetune_model_workload_empty_lora_object_matches_omitting_it(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """`lora: {}` and no `lora` at all produce the same job — an empty object is not a third state.

    Only the settings actually named travel onward, so an empty object carries no meaning of its
    own. If it wrote an empty peft_conf instead, Helm would merge a map that overrode nothing but
    still signalled intent, and the two requests would diverge for no reason a caller could see.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)

    empty_lora = await launch_finetune(
        db_session,
        test_namespace,
        FinetuneCreate(display_name="explicit-empty", dataset_id=dataset.id, lora=LoraSettings()),
        overlay=make_overlay("test/model", training_type="lora"),
    )
    omitted = await launch_finetune(
        db_session,
        test_namespace,
        FinetuneCreate(display_name="omitted", dataset_id=dataset.id),
        overlay=make_overlay("test/model", training_type="lora"),
    )

    assert "peft_conf" not in empty_lora["finetuning_config"]
    assert empty_lora["finetuning_config"] == omitted["finetuning_config"]


# The hyperparameter sections job submission may write. Naming them lets these tests assert on
# what is absent, which is the whole point: an absent section is what leaves the recipe in charge.
HYPERPARAMETER_SECTIONS = ("training_args", "batchsize_conf", "overrides")


@pytest.mark.asyncio
async def test_run_finetune_model_workload_leaves_unsupplied_hyperparameters_to_the_recipe(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """A request that names no hyperparameter trains with the recipe's own epochs, rate and batch size.

    This is the last values layer Helm merges, so anything written here beats the recipe. Writing
    a platform-chosen default would train every base model at the same numbers regardless of what
    its recipe was tuned for.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    recipe = make_overlay(
        "test/model",
        training_type="lora",
        finetuning_config={
            "training_args": {"num_train_epochs": 3},
            "batchsize_conf": {"total_train_batch_size": 16},
            "overrides": {"lr_multiplier": 0.5},
        },
    )

    overrides = await launch_finetune(
        db_session, test_namespace, FinetuneCreate(display_name="my-model", dataset_id=dataset.id), overlay=recipe
    )

    for section in HYPERPARAMETER_SECTIONS:
        assert section not in overrides["finetuning_config"], f"{section} must be left to the recipe"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sends_only_the_hyperparameter_the_caller_named(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """Overriding one hyperparameter leaves the other two with the recipe.

    The three travel independently, the same way a partial `lora` object does — a caller who wants
    more epochs has not asked for a different batch size or learning rate.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-model", dataset_id=dataset.id, epochs=5)

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="lora")
    )

    assert overrides["finetuning_config"]["training_args"] == {"num_train_epochs": 5}
    assert "batchsize_conf" not in overrides["finetuning_config"]
    assert "overrides" not in overrides["finetuning_config"]


@pytest.mark.asyncio
async def test_run_finetune_model_workload_leaves_a_silent_recipe_to_the_chart_signature(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """When neither the caller nor the recipe names a hyperparameter, the chart's own value governs.

    Nothing in the submitted layer mentions the three sections, so the merge falls through the
    recipe to the signature underneath rather than stopping at a value the API invented.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME, signature=FINETUNE_CHART_SIGNATURE)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)

    overrides = await launch_finetune(
        db_session,
        test_namespace,
        FinetuneCreate(display_name="my-model", dataset_id=dataset.id),
        overlay=make_overlay("test/model", training_type="lora"),
    )

    for section in HYPERPARAMETER_SECTIONS:
        assert section not in overrides["finetuning_config"], f"{section} must fall through to the chart"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sends_all_supplied_hyperparameters(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """Each supplied hyperparameter lands at the path the training recipe reads it from.

    The request spelling and the chart's spelling differ for all three, so this pins the whole
    mapping rather than trusting the names to line up.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(
        display_name="my-model", dataset_id=dataset.id, epochs=3, learning_rate=0.5, batch_size=8
    )

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="lora")
    )

    assert overrides["finetuning_config"]["training_args"] == {"num_train_epochs": 3}
    assert overrides["finetuning_config"]["batchsize_conf"] == {"total_train_batch_size": 8}
    assert overrides["finetuning_config"]["overrides"] == {"lr_multiplier": 0.5}


@pytest.mark.asyncio
async def test_run_finetune_model_workload_tracks_in_mlflow_without_any_hyperparameters(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """MLflow tracking still attaches when the caller names no hyperparameters.

    Tracking writes into the same section epochs does, so it has to create that section rather
    than assume an earlier write left one behind.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    mlflow_chart = await factory.create_chart(db_session, name=MLFLOW_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    mlflow_workload = await factory.create_workload(
        db_session,
        namespace=test_namespace,
        chart=mlflow_chart,
        status=WorkloadStatus.RUNNING,
        workload_type=WorkloadType.WORKSPACE,
        include_isolation_data=False,
    )

    overrides = await launch_finetune(
        db_session,
        test_namespace,
        FinetuneCreate(display_name="my-model", dataset_id=dataset.id),
        overlay=make_overlay("test/model", training_type="lora"),
        mlflow_workloads=[mlflow_workload],
    )

    training_args = overrides["finetuning_config"]["training_args"]
    assert training_args["report_to"] == ["mlflow"]
    assert "num_train_epochs" not in training_args


@pytest.mark.asyncio
async def test_run_finetune_model_workload_rejects_adapter_from_full_parameter_recipe(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """A full-parameter base model cannot produce an adapter, and says so before the job starts.

    Training every weight leaves no adapter to keep. Accepting the request would burn hours of
    GPU time and then silently deliver something other than what was asked for.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    with pytest.raises(ValidationException, match="cannot produce an adapter"):
        await launch_finetune(
            db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="full")
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_rejects_lora_settings_on_full_parameter_recipe(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """LoRA settings on a full-parameter base model are refused rather than quietly dropped.

    The refusal names the offending settings the way the caller spelled them, not the way the
    peft library does — `lora.rank`, not `r` — so the message points at the request they sent.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(
        display_name="my-model", dataset_id=dataset.id, lora=LoraSettings(rank=32, alpha=64)
    )

    with pytest.raises(ValidationException, match=r"Remove lora\.alpha, lora\.rank from the request"):
        await launch_finetune(
            db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="full")
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_allows_plain_model_from_full_parameter_recipe(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """A full-parameter recipe still trains a model when neither an adapter nor LoRA settings are asked for.

    The guard is about honouring what was requested, not about restricting full-parameter recipes.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-model", dataset_id=dataset.id)

    overrides = await launch_finetune(
        db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model", training_type="full")
    )

    assert overrides["aimManifest"]["modelManifest"]["enabled"] is True
    assert overrides["aimManifest"]["adapterManifest"]["enabled"] is False


@pytest.mark.asyncio
async def test_run_finetune_model_workload_refuses_adapter_when_recipe_omits_training_type(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """A recipe that declares nothing trains full-parameter, matching the chart's own default.

    AIWB reads the overlay and never the chart's values.yaml, so that default has to be applied
    here or an undeclared recipe would silently escape the guard.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    with pytest.raises(ValidationException, match="cannot produce an adapter"):
        await launch_finetune(db_session, test_namespace, finetuning_data, overlay=make_overlay("test/model"))


@pytest.mark.asyncio
async def test_run_finetune_model_workload_ignores_peft_type_when_training_type_undeclared(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """`metadata.trainingType` is the sole source of truth — peft_type is not consulted.

    A recipe carrying `peft_type: LORA` but no declared training type is still refused. Reading
    the peft config would let it through, so this pins that the framework-internal field is not
    a fallback: the platform must be free to change it without breaking the integration.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)
    overlay = make_overlay("test/model", finetuning_config={"peft_conf": {"peft_type": "LORA"}})

    with pytest.raises(ValidationException, match="cannot produce an adapter"):
        await launch_finetune(db_session, test_namespace, finetuning_data, overlay=overlay)


@pytest.mark.asyncio
async def test_run_finetune_model_workload_refuses_a_model_whose_identity_cannot_be_determined(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """A model run with no resolvable modelId is refused before the job starts.

    The chart renders the identity into the AIMModel CR, so an unresolvable one fails the Helm
    render hours later naming a value the caller never supplied. Refusing up front names the
    base model instead.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-model", dataset_id=dataset.id)
    # A canonical-name base carries no weights source of its own, so the recipe is the only
    # possible authority — and this one declares an aimId but no modelId.
    overlay = make_overlay("test/model", model_id=None, training_type="lora")

    with pytest.raises(ValidationException, match="Cannot determine the model identity"):
        await launch_finetune(db_session, test_namespace, finetuning_data, overlay=overlay)


@pytest.mark.asyncio
async def test_run_finetune_model_workload_survives_malformed_recipe_metadata(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """A recipe whose metadata is not a mapping reads as undeclared, not as a crash.

    Overlays are external data, and the listing endpoint already degrades gracefully on the
    same malformed input; submitting a job has to agree with it rather than return a 500.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)
    overlay = make_overlay("test/model", metadata="lora")

    with pytest.raises(ValidationException, match="cannot produce an adapter"):
        await launch_finetune(db_session, test_namespace, finetuning_data, overlay=overlay)


@pytest.mark.asyncio
async def test_run_finetune_model_workload_adapter_needs_no_model_identity(
    db_session: AsyncSession, test_namespace: str
) -> None:
    """The same recipe that cannot produce a model produces an adapter without complaint.

    Identity is rendered only while the model manifest is enabled, so requiring it on the adapter
    arm would refuse a request that has no use for it.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)
    overlay = make_overlay("test/model", model_id=None, training_type="lora")

    overrides = await launch_finetune(db_session, test_namespace, finetuning_data, overlay=overlay)

    model_manifest = overrides["aimManifest"]["modelManifest"]
    assert model_manifest["enabled"] is False
    assert "modelId" not in model_manifest
    assert "aimId" not in model_manifest
    assert overrides["aimManifest"]["adapterManifest"]["enabled"] is True


@pytest.mark.asyncio
async def test_run_finetune_model_workload_rejects_adapter_when_base_model_name_diverges_from_recipe_aim_id(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """An adapter is refused when the base model's own name doesn't match the recipe's aimId.

    compatibleWith renders from the base model's canonical name, but the deploy gate matches it
    against the base model's own aimId — if the two diverge, the resulting adapter would report
    Ready but could never attach.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="other/aim-id", training_type="lora")
    cluster_model = make_cluster_model(aim_id="other/aim-id", status="Ready")

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", return_value=[cluster_model]),
        patch_source_profiles(),
        pytest.raises(ValidationException, match="could never attach"),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_allows_model_output_when_base_model_name_diverges_from_recipe_aim_id(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """The same aimId divergence is fine for a model run — compatibleWith is only rendered for an adapter."""
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="other/aim-id", training_type="lora")
    cluster_model = make_cluster_model(aim_id="other/aim-id", status="Ready")

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", return_value=[cluster_model]),
        patch_source_profiles(),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    assert len(helm_overrides_captured) == 1
    assert helm_overrides_captured[0]["aimManifest"]["modelManifest"]["enabled"] is True


@pytest.mark.asyncio
async def test_get_finetunable_models_surfaces_training_type(db_session: AsyncSession) -> None:
    """Each result reports how its recipe trains, so callers know which can produce an adapter.

    Three overlays cover the domain the UI branches on: declared lora, declared full, and a
    recipe that declares nothing — which reports `full`, matching the chart's own default.
    """
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    overlays = [
        make_overlay("lora/model", training_type="lora"),
        make_overlay("full/model", training_type="full"),
        make_overlay("undeclared/model"),
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["lora/model", "full/model", "undeclared/model"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    by_name = {m.canonical_name: m for m in result}
    assert by_name["lora/model"].training_type is TrainingType.LORA
    assert by_name["full/model"].training_type is TrainingType.FULL
    assert by_name["undeclared/model"].training_type is TrainingType.FULL


# Mirrors the fine-tuning chart's signature.yaml: the layer every recipe merges over. The blank
# `total_train_batch_size` is why no shipped recipe advertises a batch size.
FINETUNE_CHART_SIGNATURE: dict = {
    "finetuning_config": {
        "batchsize_conf": {"total_train_batch_size": None},
        "overrides": {"lr_multiplier": 1.0},
        "training_args": {"num_train_epochs": 1},
    }
}


@pytest.mark.asyncio
async def test_get_finetunable_models_reports_the_recipe_merged_over_the_chart_signature(
    db_session: AsyncSession,
) -> None:
    """A recipe's own values win; anything it leaves alone falls back to the chart's signature."""
    finetune_chart = await factory.create_chart(
        db_session, name=FINETUNING_CHART_NAME, signature=FINETUNE_CHART_SIGNATURE
    )
    overlays = [
        make_overlay(
            "lora/model",
            training_type="lora",
            finetuning_config={
                "training_args": {"num_train_epochs": 3},
                "peft_conf": {"peft_kwargs": {"r": 64, "lora_alpha": 16.0, "lora_dropout": 0.05}},
            },
        )
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["lora/model"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert result[0].hyperparameters == FinetuningHyperparameters(
        batch_size=None,
        epochs=3,
        learning_rate=1.0,
        lora=LoraHyperparameters(rank=64, alpha=16, dropout=0.05),
    )


@pytest.mark.asyncio
async def test_get_finetunable_models_keeps_each_recipes_hyperparameters_to_itself(
    db_session: AsyncSession,
) -> None:
    """Every recipe merges over the same signature object, so one must not colour the next.

    A leak here reports a neighbouring recipe's LoRA defaults on a full-parameter model, offering
    controls that job submission then refuses.
    """
    finetune_chart = await factory.create_chart(
        db_session, name=FINETUNING_CHART_NAME, signature=FINETUNE_CHART_SIGNATURE
    )
    overlays = [
        make_overlay(
            "a-lora/model",
            training_type="lora",
            finetuning_config={
                "training_args": {"num_train_epochs": 7},
                "peft_conf": {"peft_kwargs": {"r": 128, "lora_alpha": 32, "lora_dropout": 0.2}},
            },
        ),
        make_overlay("b-plain/model"),
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["a-lora/model", "b-plain/model"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    by_name = {m.canonical_name: m for m in result}
    assert by_name["b-plain/model"].hyperparameters == FinetuningHyperparameters(
        batch_size=None, epochs=1, learning_rate=1.0, lora=None
    )


@pytest.mark.asyncio
async def test_get_finetunable_models_leaves_the_chart_signature_untouched(db_session: AsyncSession) -> None:
    """The signature is shared chart state, not scratch space for the merge."""
    finetune_chart = await factory.create_chart(
        db_session, name=FINETUNING_CHART_NAME, signature=FINETUNE_CHART_SIGNATURE
    )
    before = copy.deepcopy(finetune_chart.signature)
    overlays = [
        make_overlay(
            "lora/model",
            training_type="lora",
            finetuning_config={"training_args": {"num_train_epochs": 9}},
        )
    ]
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=overlays),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["lora/model"]),
    ):
        await get_finetunable_models(db_session, kube_client)

    assert finetune_chart.signature == before


@pytest.mark.asyncio
async def test_get_finetunable_models_reports_no_hyperparameters_when_the_chart_declares_none(
    db_session: AsyncSession,
) -> None:
    """A chart with no signature describes nothing rather than failing the listing."""
    finetune_chart = await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    kube_client = make_kube_client()

    with (
        patch("app.models.service.get_chart", return_value=finetune_chart),
        patch("app.models.service.list_overlays", return_value=[make_overlay("plain/model")]),
        patch("app.models.service.get_cluster_gpu_device_info", return_value={"74a1": "AMD Instinct MI300X"}),
        patch_cluster_profiles(["plain/model"]),
    ):
        result = await get_finetunable_models(db_session, kube_client)

    assert result[0].hyperparameters == FinetuningHyperparameters(
        batch_size=None, epochs=None, learning_rate=None, lora=None
    )


@pytest.mark.parametrize("capable_listed_first", [True, False])
@pytest.mark.asyncio
async def test_run_finetune_model_workload_prefers_adapter_capable_cluster_model(
    db_session: AsyncSession, test_namespace: str, test_user: str, capable_listed_first: bool
) -> None:
    """The version publishing adapter-capable profiles wins, wherever it sits in the list.

    Both versions are Ready, share the recipe's aimId and publish the trained weights, so
    position in the unordered cluster list is the only thing separating them — and it must
    not be what decides. The run asks for an adapter, which is what makes the capability
    worth separating them by at all.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="test/model", training_type="lora")

    old_version = make_cluster_model(aim_id="test/model", status="Ready")
    old_version.metadata.name = "model-0-11-1"
    new_version = make_cluster_model(aim_id="test/model", status="Ready")
    new_version.metadata.name = "model-0-13-0"
    listed = [new_version, old_version] if capable_listed_first else [old_version, new_version]

    profiles = [
        make_cluster_profile("model-0-11-1", model_id="test/model"),
        make_cluster_profile("model-0-13-0", model_id="test/model", adapter_capable=True),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=listed),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-0-13-0"


@pytest.mark.parametrize("capable_listed_first", [True, False])
@pytest.mark.asyncio
async def test_run_finetune_model_workload_prefers_adapter_capable_cluster_model_for_model_output(
    db_session: AsyncSession, test_namespace: str, test_user: str, capable_listed_first: bool
) -> None:
    """A model run derives from the adapter-capable version too, not just an adapter run.

    The model arm is the one that enables the model manifest, so it is the only arm that
    creates a derived AIMModel and copies source profiles into it. Deriving from the
    incapable version leaves a fine-tuned model that can never serve an adapter, and no
    later run repairs it — the profiles are copied once, at creation.

    Both versions publish the same weights and were registered at the same instant, so
    neither the weights filter nor registration time separates them and list position is
    all that is left. That is precisely the case where order alone used to decide.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id, output=FineTuningOutput.MODEL)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    registered_together = datetime(2026, 3, 1, tzinfo=UTC)
    incapable = make_cluster_model(aim_id="test/model", created_at=registered_together)
    incapable.metadata.name = "model-plain"
    capable = make_cluster_model(aim_id="test/model", created_at=registered_together)
    capable.metadata.name = "model-adapters"
    listed = [capable, incapable] if capable_listed_first else [incapable, capable]

    profiles = [
        make_cluster_profile("model-plain", model_id="acme/Model"),
        make_cluster_profile("model-adapters", model_id="acme/Model", adapter_capable=True),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=listed),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    model_manifest = helm_overrides_captured[0]["aimManifest"]["modelManifest"]
    # The model manifest is what creates the derived AIMModel, so this is the path where the
    # inherited profiles decide whether the result can serve adapters at all.
    assert model_manifest["enabled"] is True
    assert model_manifest["baseModel"] == {"name": "model-adapters", "scope": "Auto", "modelId": "acme/Model"}


@pytest.mark.asyncio
async def test_run_finetune_model_workload_prefers_capable_version_over_newer_incapable_for_model_output(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Capability outranks registration time inside the weights-matched set on a model run.

    The incapable version is the newer of the two, so ranking alone would take it. What the
    derived model inherits is not a tiebreak between equals: the older capable version is
    the only one that leaves it able to serve adapters.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id, output=FineTuningOutput.MODEL)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    newer_incapable = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    newer_incapable.metadata.name = "model-plain"
    older_capable = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    older_capable.metadata.name = "model-adapters"

    profiles = [
        make_cluster_profile("model-plain", model_id="acme/Model"),
        make_cluster_profile("model-adapters", model_id="acme/Model", adapter_capable=True),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[newer_incapable, older_capable],
        ),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model == {"name": "model-adapters", "scope": "Auto", "modelId": "acme/Model"}


@pytest.mark.asyncio
async def test_run_finetune_model_workload_model_output_falls_back_when_no_capable_version_publishes_weights(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """With nothing capable on the trained weights, a model run still derives rather than refusing.

    Capability is a tiebreak inside the weights-matched set, never a way out of it: the
    capable version here publishes another variant, so the chart's filter would copy none
    of its profiles. Preferring capability must not turn into a refusal on the model arm,
    where fine-tuning against an incapable base is a real thing to want.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id, output=FineTuningOutput.MODEL)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    capable_other_variant = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    capable_other_variant.metadata.name = "model-fp8"
    incapable_trained = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    incapable_trained.metadata.name = "model-bf16"

    profiles = [
        make_cluster_profile("model-fp8", model_id="acme/Model-FP8", adapter_capable=True),
        make_cluster_profile("model-bf16", model_id="acme/Model"),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[capable_other_variant, incapable_trained],
        ),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model == {"name": "model-bf16", "scope": "Auto", "modelId": "acme/Model"}


@pytest.mark.asyncio
async def test_run_finetune_model_workload_adapter_output_renders_no_model_manifest(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """An adapter run disables the model manifest, so it derives no AIMModel at all.

    This is what makes the capability preference belong on the model arm: the version the
    selection settles on is carried under ``modelManifest``, and an adapter run turns that
    manifest off, so nothing consumes it. Pinning the asymmetry here keeps the reasoning
    behind the model-output preference from being read as a mistake and undone.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    version = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    version.metadata.name = "model-adapters"
    profiles = [make_cluster_profile("model-adapters", model_id="acme/Model", adapter_capable=True)]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=[version]),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    aim_manifest = helm_overrides_captured[0]["aimManifest"]
    assert aim_manifest["modelManifest"]["enabled"] is False
    assert aim_manifest["adapterManifest"]["enabled"] is True


@pytest.mark.asyncio
async def test_run_finetune_model_workload_prefers_capable_version_built_from_trained_weights(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Among adapter-capable versions, the one built from the trained weights wins.

    An adapter only loads against the weights it was trained on, so a capable build of a
    different variant is no more usable than an incapable one.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    fp8_version = make_cluster_model(aim_id="test/model", status="Ready")
    fp8_version.metadata.name = "model-fp8"
    bf16_version = make_cluster_model(aim_id="test/model", status="Ready")
    bf16_version.metadata.name = "model-bf16"

    profiles = [
        make_cluster_profile("model-fp8", model_id="acme/Model-FP8", adapter_capable=True),
        make_cluster_profile("model-bf16", model_id="acme/Model", adapter_capable=True),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[fp8_version, bf16_version],
        ),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-bf16"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_sends_source_weights_id_under_base_model(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """The trained weights id reaches the manifest nested under baseModel.

    That nested value filters which source profiles the chart copies. The identically
    named key one level up is the opposite: the identity stamped onto the copies. Both
    are asserted here so a future edit cannot quietly collapse one into the other.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/family", model_id="acme/Model", training_type="lora")

    cluster_model = make_cluster_model(aim_id="test/family", status="Ready")
    cluster_model.metadata.name = "model-0-13-0"
    profiles = [make_cluster_profile("model-0-13-0", model_id="acme/Model", adapter_capable=True)]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=[cluster_model]),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    model_manifest = helm_overrides_captured[0]["aimManifest"]["modelManifest"]
    assert model_manifest["baseModel"] == {"name": "model-0-13-0", "scope": "Auto", "modelId": "acme/Model"}
    assert model_manifest["modelId"] == "acme/Model"
    assert model_manifest["aimId"] == "test/family"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_refuses_adapter_when_no_version_can_serve_one(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """An adapter request is refused when the published profiles say no version can serve one.

    The alternative is hours of GPU training for an artifact the deploy accepts and never
    starts, so the refusal happens before the job is submitted.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="test/model", training_type="lora")
    cluster_model = make_cluster_model(aim_id="test/model", status="Ready")
    cluster_model.metadata.name = "model-0-11-1"
    profiles = [make_cluster_profile("model-0-11-1", model_id="test/model")]

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=[cluster_model]),
        patch_source_profiles(profiles),
        pytest.raises(ValidationException, match="adapter-capable serving profiles"),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_allows_adapter_when_capability_is_unknown(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """No published profiles means the capability is unknown, not absent, so the run proceeds.

    Refusing on missing evidence would block fine-tuning on any cluster whose profiles
    aim-engine has not discovered yet.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="test/model", training_type="lora")
    cluster_model = make_cluster_model(aim_id="test/model", status="Ready")
    cluster_model.metadata.name = "model-0-11-1"

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=[cluster_model]),
        patch_source_profiles([]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-0-11-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("listed_newest_first", [True, False])
async def test_run_finetune_model_workload_picks_newest_of_equally_capable_versions(
    db_session: AsyncSession, test_namespace: str, test_user: str, listed_newest_first: bool
) -> None:
    """Equally capable versions are separated by registration time, not by list position.

    Both publish adapter-capable profiles on the trained weights, so nothing about the
    capability distinguishes them; without an imposed order the same request could derive
    from either, and the answer must not depend on how the API server happened to list them.

    The newer version is named so that it sorts alphabetically *last*. The ranking sorts by
    name and then re-sorts by registration time, so names that put the newest version first
    alphabetically would let this pass on the name sort alone — it would go on passing with
    the registration-time sort deleted, which is the one thing it exists to pin.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", training_type="lora")

    older = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    older.metadata.name = "model-aaa-old"
    newer = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    newer.metadata.name = "model-zzz-new"
    listed = [newer, older] if listed_newest_first else [older, newer]

    profiles = [
        make_cluster_profile("model-aaa-old", model_id="test/model", adapter_capable=True),
        make_cluster_profile("model-zzz-new", model_id="test/model", adapter_capable=True),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=listed),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-zzz-new"


@pytest.mark.asyncio
@pytest.mark.parametrize("listed_reversed", [True, False])
async def test_run_finetune_model_workload_breaks_registration_ties_by_name(
    db_session: AsyncSession, test_namespace: str, test_user: str, listed_reversed: bool
) -> None:
    """Versions sharing a registration time still resolve to the same one every run.

    Clusters that register several versions in one apply leave nothing to order by, and a
    stable name sort is what keeps the choice reproducible rather than a coin flip.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", training_type="lora")

    registered = datetime(2026, 1, 1, tzinfo=UTC)
    first = make_cluster_model(aim_id="test/model", created_at=registered)
    first.metadata.name = "model-aaa"
    second = make_cluster_model(aim_id="test/model", created_at=registered)
    second.metadata.name = "model-bbb"
    listed = [second, first] if listed_reversed else [first, second]

    profiles = [
        make_cluster_profile("model-aaa", model_id="test/model", adapter_capable=True),
        make_cluster_profile("model-bbb", model_id="test/model", adapter_capable=True),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=listed),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-aaa"


def test_registered_at_reads_a_naive_timestamp_as_utc() -> None:
    """A creation timestamp without tzinfo is read as UTC rather than blowing up the sort.

    The API server normally hands back an aware timestamp, but the resource type does not
    guarantee one, and comparing a naive datetime against an aware one raises. Assuming UTC
    is what the API server means by an unqualified time, and it keeps the ordering total.
    """
    naive = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 6, 1))

    assert _registered_at(naive) == datetime(2026, 6, 1, tzinfo=UTC)
    # Comparable against an aware timestamp is the point of the coercion.
    assert _registered_at(naive) > datetime(2026, 1, 1, tzinfo=UTC)


def test_registered_at_sorts_an_undated_version_last() -> None:
    """A version the API server gives no creation time for ranks oldest, not first.

    Nothing else on the resource orders reliably, so an absent timestamp has to resolve to
    some instant; the oldest possible one keeps a dated version ahead of it rather than
    letting a missing field jump the queue.
    """
    undated = make_cluster_model(aim_id="test/model", created_at=None)
    undated.metadata.name = "model-aaa-undated"
    dated = make_cluster_model(aim_id="test/model", created_at=datetime(2020, 1, 1, tzinfo=UTC))
    dated.metadata.name = "model-zzz-dated"

    assert _registered_at(undated) == datetime.min.replace(tzinfo=UTC)
    assert _newest_first([undated, dated]) == [dated, undated]


@pytest.mark.asyncio
@pytest.mark.parametrize("listed_capable_first", [True, False])
async def test_run_finetune_model_workload_adapter_ranks_on_capability_when_no_weights_named(
    db_session: AsyncSession, test_namespace: str, test_user: str, listed_capable_first: bool
) -> None:
    """With no weights identity, an adapter run selects on capability alone.

    A recipe that declares no modelId leaves the weights filter with nothing to say, so the
    only evidence separating the versions is which of them publishes an adapter-capable
    profile. The capable version here is both older and alphabetically last, so neither the
    ranking's own tiebreak nor the terminal fallback would land on it: only selecting on
    capability does.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="test/model", model_id=None, training_type="lora")

    incapable = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    incapable.metadata.name = "model-aaa-newer"
    capable = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    capable.metadata.name = "model-zzz-older"
    listed = [capable, incapable] if listed_capable_first else [incapable, capable]

    profiles = [
        make_cluster_profile("model-aaa-newer", model_id="test/model", adapter_capable=False),
        make_cluster_profile("model-zzz-older", model_id="test/model", adapter_capable=True),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=listed),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-zzz-older"
    # No weights were named, so nothing filters or stamps them.
    assert "modelId" not in base_model


@pytest.mark.asyncio
@pytest.mark.parametrize("unsettled_status", ["Failed", "Pending", "NotAvailable"])
async def test_run_finetune_model_workload_ignores_capability_of_unsettled_profiles(
    db_session: AsyncSession, test_namespace: str, test_user: str, unsettled_status: str
) -> None:
    """A profile that is not Ready cannot make a version look adapter-capable.

    Its capability never materialised on the cluster, so deriving from it reproduces the
    exact failure this selection exists to prevent — an adapter accepted at deploy that
    never starts. The Ready version without the capability is the honest choice.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", training_type="lora")

    settled = make_cluster_model(aim_id="test/model", status="Ready")
    settled.metadata.name = "model-0-11-1"
    unsettled = make_cluster_model(aim_id="test/model", status="Ready")
    unsettled.metadata.name = "model-0-13-0"

    profiles = [
        make_cluster_profile("model-0-11-1", model_id="test/model"),
        make_cluster_profile("model-0-13-0", model_id="test/model", adapter_capable=True, status=unsettled_status),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[unsettled, settled],
        ),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-0-11-1"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_allows_adapter_when_every_profile_is_unsettled(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Profiles that all exist but are none of them Ready leave the capability unknown.

    An unsettled profile is missing evidence, not evidence of absence — refusing here would
    hard-stop a run that succeeds once aim-engine finishes resolving the profile, while
    proceeding only risks an adapter that fails to deploy, which the warning already flags.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="test/model", training_type="lora")
    cluster_model = make_cluster_model(aim_id="test/model", status="Ready")
    cluster_model.metadata.name = "model-0-11-1"
    profiles = [make_cluster_profile("model-0-11-1", model_id="test/model", status="Pending")]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=[cluster_model]),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-0-11-1"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_full_parameter_run_derives_from_the_trained_weights(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """A full-parameter run picks the version publishing the weights its manifest filters by.

    The first listed version publishes only another variant, so deriving from it and then
    filtering by these weights copies no profile at all and the resulting model cannot serve.
    Capability is not what decides between these two: the version passed over here is the
    adapter-capable one, but it publishes other weights, and capability only ever separates
    versions that already publish the weights the run trains on.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="full")

    first_listed = make_cluster_model(aim_id="test/model", status="Ready")
    first_listed.metadata.name = "model-int4"
    also_listed = make_cluster_model(aim_id="test/model", status="Ready")
    also_listed.metadata.name = "model-bf16"
    profiles = [
        make_cluster_profile("model-int4", model_id="acme/Model-INT4", adapter_capable=True),
        make_cluster_profile("model-bf16", model_id="acme/Model"),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[first_listed, also_listed],
        ),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    model_manifest = helm_overrides_captured[0]["aimManifest"]["modelManifest"]
    assert model_manifest["baseModel"] == {"name": "model-bf16", "scope": "Auto", "modelId": "acme/Model"}
    assert model_manifest["modelId"] == "acme/Model"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_refuses_full_parameter_run_whose_weights_nothing_publishes(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """The refusal covers a full-parameter recipe, not only a LoRA one.

    No version publishes the weights this run trains on, so the manifest has nothing truthful
    to say: the filter copies no profile and dropping it would stamp other variants as these
    weights. The training type does not change that, so neither does it change the answer.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="full")

    first_listed = make_cluster_model(aim_id="test/model", status="Ready")
    first_listed.metadata.name = "model-fp8"
    also_listed = make_cluster_model(aim_id="test/model", status="Ready")
    also_listed.metadata.name = "model-int4"
    profiles = [
        make_cluster_profile("model-fp8", model_id="acme/Model-FP8"),
        make_cluster_profile("model-int4", model_id="acme/Model-INT4"),
    ]

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[first_listed, also_listed],
        ),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", return_value="mock-manifest") as mock_render,
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        with pytest.raises(ValidationException, match="No published profile of base model"):
            await run_finetune_model_workload(
                session=db_session,
                kube_client=make_kube_client(),
                model_id="test/model",
                finetuning_data=finetuning_data,
                submitter=test_user,
                namespace=test_namespace,
            )

    mock_render.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("listed_reversed", [True, False])
async def test_run_finetune_model_workload_full_parameter_run_ignores_the_listed_order(
    db_session: AsyncSession, test_namespace: str, test_user: str, listed_reversed: bool
) -> None:
    """A full-parameter run resolves to the same version whichever way the cluster listed it.

    It reads no profile, so nothing separates its candidates on merit — but list position is
    not a way to separate them either, and letting it decide is what made the same two
    versions accept or refuse depending on which came back first. Neither version here
    carries a registration time, so the ranking falls to the name sort underneath and the
    answer is the alphabetically first one from both listings.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", training_type="full")

    sorts_last = make_cluster_model(aim_id="test/model", status="Ready")
    sorts_last.metadata.name = "model-zzz"
    sorts_first = make_cluster_model(aim_id="test/model", status="Ready")
    sorts_first.metadata.name = "model-aaa"
    listed = [sorts_first, sorts_last] if listed_reversed else [sorts_last, sorts_first]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=listed),
        patch_source_profiles([]),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-aaa"


@pytest.mark.asyncio
@pytest.mark.parametrize("contradicting_listed_first", [True, False])
async def test_run_finetune_model_workload_falls_back_across_the_whole_candidate_set(
    db_session: AsyncSession, test_namespace: str, test_user: str, contradicting_listed_first: bool
) -> None:
    """The terminal fallback refuses only when no candidate has non-contradicting evidence.

    One version publishes settled profiles built from another variant's weights — evidence
    saying no — and the other publishes none at all, which is missing evidence and not a
    refusal. Reading only whichever the API server listed first made those two give opposite
    answers from the same cluster state. The decision is set-wide, so the version that does
    not contradict is what both listings derive from.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="full")

    contradicting = make_cluster_model(aim_id="test/model", status="Ready")
    contradicting.metadata.name = "model-int4"
    no_evidence = make_cluster_model(aim_id="test/model", status="Ready")
    no_evidence.metadata.name = "model-unprofiled"
    listed = [contradicting, no_evidence] if contradicting_listed_first else [no_evidence, contradicting]

    profiles = [make_cluster_profile("model-int4", model_id="acme/Model-INT4")]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch("app.models.service.aims_gateway.list_aims", new_callable=AsyncMock, return_value=listed),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model["name"] == "model-unprofiled"


@pytest.mark.asyncio
async def test_run_finetune_model_workload_refuses_adapter_when_only_another_variant_is_capable(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """A capable version built from other weights cannot stand in for the trained ones.

    The chart copies only the profiles built from the weights this run trains on, so
    deriving from the capable variant hands the adapter the incapable profiles anyway —
    the undeployable adapter this selection exists to prevent, reached by a longer route.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    capable_other_variant = make_cluster_model(aim_id="test/model", status="Ready")
    capable_other_variant.metadata.name = "model-fp8"
    trained_variant = make_cluster_model(aim_id="test/model", status="Ready")
    trained_variant.metadata.name = "model-bf16"

    profiles = [
        make_cluster_profile("model-fp8", model_id="acme/Model-FP8", adapter_capable=True),
        make_cluster_profile("model-bf16", model_id="acme/Model"),
    ]

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[capable_other_variant, trained_variant],
        ),
        patch_source_profiles(profiles),
        pytest.raises(ValidationException, match="adapter-capable serving profiles"),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_refuses_adapter_when_capability_is_on_another_profile(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """Capability and the trained weights have to meet in one profile, not one version.

    This version publishes both: a capable profile built from another variant and an
    incapable one built from the weights the run trains on. The chart filters the copies
    by the trained weights, so only the incapable profile reaches the adapter — which is
    why the version as a whole being capable is not enough to derive from.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="my-adapter", dataset_id=dataset.id, output=FineTuningOutput.ADAPTER)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    mixed_version = make_cluster_model(aim_id="test/model", status="Ready")
    mixed_version.metadata.name = "model-mixed"

    profiles = [
        make_cluster_profile("model-mixed", model_id="acme/Model-FP8", adapter_capable=True, name="profile-fp8"),
        make_cluster_profile("model-mixed", model_id="acme/Model", name="profile-bf16"),
    ]

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[mixed_version],
        ),
        patch_source_profiles(profiles),
        pytest.raises(ValidationException, match="built from the weights this run trains on"),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )


@pytest.mark.asyncio
async def test_run_finetune_model_workload_merged_model_derives_from_the_trained_weights(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """A merged model derives from the version publishing the weights it trains on.

    Capability is preferred inside the weights-matched set and cannot lift a version out of
    it. The newest capable version here publishes a different variant, so deriving from it
    would leave the chart's own filter nothing to copy, since only profiles built from the
    trained weights survive it.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    newer_capable = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    newer_capable.metadata.name = "model-fp8"
    older_trained = make_cluster_model(aim_id="test/model", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    older_trained.metadata.name = "model-bf16"

    profiles = [
        make_cluster_profile("model-fp8", model_id="acme/Model-FP8", adapter_capable=True),
        make_cluster_profile("model-bf16", model_id="acme/Model"),
    ]

    helm_overrides_captured: list = []

    async def capture_render(*, chart, name, namespace, overlays_values):
        helm_overrides_captured.append(overlays_values[-1] if overlays_values else {})
        return ""

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[newer_capable, older_trained],
        ),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", side_effect=capture_render),
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    base_model = helm_overrides_captured[0]["aimManifest"]["modelManifest"]["baseModel"]
    assert base_model == {"name": "model-bf16", "scope": "Auto", "modelId": "acme/Model"}


@pytest.mark.asyncio
async def test_run_finetune_model_workload_refuses_merged_model_whose_weights_nothing_publishes(
    db_session: AsyncSession, test_namespace: str, test_user: str
) -> None:
    """A merged model is refused when no version publishes the weights it trains on.

    Every settled profile here is built from a different variant, so there are only two
    things the manifest could say and neither is true: filtering by these weights copies no
    profile at all, and omitting the filter copies the other variants while the identity one
    level up stamps them as these weights — an adapter trained on the result would then be
    declared compatible with a profile that never served them. Refusing names the weights
    while the caller can still pick a base model version that publishes them.
    """
    await factory.create_chart(db_session, name=FINETUNING_CHART_NAME)
    dataset = await factory.create_dataset(db_session, namespace=test_namespace)
    finetuning_data = FinetuneCreate(display_name="FT-Model", dataset_id=dataset.id)

    overlay = make_overlay("test/model", aim_id="test/model", model_id="acme/Model", training_type="lora")

    first_listed = make_cluster_model(aim_id="test/model", status="Ready")
    first_listed.metadata.name = "model-fp8"
    also_listed = make_cluster_model(aim_id="test/model", status="Ready")
    also_listed.metadata.name = "model-int4"

    profiles = [
        make_cluster_profile("model-fp8", model_id="acme/Model-FP8", adapter_capable=True),
        make_cluster_profile("model-int4", model_id="acme/Model-INT4"),
    ]

    with (
        patch("app.models.service.list_overlays", return_value=[overlay]),
        patch("app.models.service.get_workloads", return_value=[]),
        patch(
            "app.models.service.aims_gateway.list_aims",
            new_callable=AsyncMock,
            return_value=[first_listed, also_listed],
        ),
        patch_source_profiles(profiles),
        patch("app.models.service.render_helm_template", return_value="mock-manifest") as mock_render,
        patch("app.models.service.apply_manifest", new_callable=AsyncMock),
        pytest.raises(
            ValidationException,
            match=r"No published profile of base model 'test/model' is built from weights 'acme/Model'",
        ),
    ):
        await run_finetune_model_workload(
            session=db_session,
            kube_client=make_kube_client(),
            model_id="test/model",
            finetuning_data=finetuning_data,
            submitter=test_user,
            namespace=test_namespace,
        )

    # Refusing after the chart rendered would leave the caller a model that is already being
    # created, so the refusal has to land before anything is submitted.
    mock_render.assert_not_called()
