# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AIMs service layer."""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from kubernetes_asyncio.client import ApiException
from pydantic.alias_generators import to_camel

from api_common.exceptions import ExternalServiceError, NotFoundException, ValidationException
from app.aims.constants import AIM_COND_HTTP_ROUTE_READY, AIM_COND_INFERENCE_SERVICE_READY
from app.aims.crds import (
    AIMModelProfilesDerivedFrom,
    AIMModelProfilesSpec,
    AIMModelResource,
    AIMModelSource,
    AIMModelSpec,
    AIMModelStatusFields,
    AIMProfileResource,
    AIMProfileSpec,
    AIMProfileStatus,
    AIMServiceResource,
    AIMServiceSpec,
    AIMServiceStatusFields,
    ProfileOverrides,
    ProfileSelector,
    ResolvedRef,
)
from app.aims.enums import AcceleratorType, AIMModelStatus, AIMServiceStatus, OptimizationMetric
from app.aims.schemas import AIMDeployRequest
from app.aims.service import (
    _resolve_namespace_deploy_profile,
    deploy_aim,
    get_aim_by_resource_name,
    get_aim_cluster_profile,
    get_aim_profile,
    get_aim_service,
    list_aim_cluster_profiles,
    list_aim_services,
    list_aims,
    list_chattable_aim_services,
    list_transcribable_aim_services,
    undeploy_aim,
)
from app.custom_models.constants import (
    IMPORT_ERROR_ANNOTATION,
    IMPORT_STATE_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
)
from app.dispatch.crds import K8sMetadata
from app.inference.enums import InferenceCapability
from app.workloads.constants import MODEL_NAME_LABEL, MODEL_SOURCE_TYPE_LABEL
from app.workloads.enums import ModelSourceType
from tests.factory import (
    make_aim_cluster_model,
    make_aim_cluster_profile,
    make_aim_profile_set,
    make_aim_service_k8s,
)


@pytest.fixture
def kube_client() -> MagicMock:
    """Mock K8s client."""
    return MagicMock()


@pytest.mark.asyncio
async def test_list_aims(kube_client: MagicMock) -> None:
    """Test list_aims service function."""
    aim = make_aim_cluster_model()
    with patch("app.aims.service.get_aims_from_k8s", return_value=[aim]):
        result = await list_aims(kube_client)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_list_aims_filters_out_base_only_cluster_models(kube_client: MagicMock) -> None:
    base_only = AIMModelResource.model_validate(
        {
            "metadata": {"name": "aim-base-013", "namespace": "ns"},
            "spec": {"image": "amdenterpriseai/aim-base:0.13"},
            "status": {
                "status": "Ready",
                "managedProfiles": {
                    "base": 8,
                    "deployable": 0,
                    "notAvailable": 0,
                    "ready": 8,
                    "total": 8,
                },
            },
        }
    )
    regular = make_aim_cluster_model(name="llama3-8b")
    with patch("app.aims.service.get_aims_from_k8s", return_value=[base_only, regular]):
        result = await list_aims(kube_client)

    assert [aim.metadata.name for aim in result] == ["llama3-8b"]


@pytest.mark.asyncio
async def test_list_aims_keeps_non_base_only_models(kube_client: MagicMock) -> None:
    not_base_only = AIMModelResource.model_validate(
        {
            "metadata": {"name": "not-base-only", "namespace": "ns"},
            "spec": {"image": "amdenterpriseai/other:1.0"},
            "status": {
                "status": "Ready",
                "managedProfiles": {
                    "base": 1,
                    "deployable": 1,
                    "notAvailable": 0,
                    "ready": 2,
                    "total": 2,
                },
            },
        }
    )
    with patch("app.aims.service.get_aims_from_k8s", return_value=[not_base_only]):
        result = await list_aims(kube_client)

    assert [aim.metadata.name for aim in result] == ["not-base-only"]


@pytest.mark.asyncio
async def test_list_aims_filters_out_base_family_images_without_profiles(kube_client: MagicMock) -> None:
    radeon_base = AIMModelResource.model_validate(
        {
            "metadata": {"name": "amdenterpriseai-aim-radeon-base-0-12", "namespace": "ns"},
            "spec": {"image": "amdenterpriseai/aim-radeon-base:0.12"},
            "status": {
                "status": "NotAvailable",
                "imageMetadata": {"model": {"title": "AIM Radeon Base"}},
                "managedProfiles": {
                    "base": 0,
                    "deployable": 0,
                    "notAvailable": 0,
                    "ready": 0,
                    "total": 0,
                },
            },
        }
    )
    regular = make_aim_cluster_model(name="llama3-8b")
    with patch("app.aims.service.get_aims_from_k8s", return_value=[radeon_base, regular]):
        result = await list_aims(kube_client)

    assert [aim.metadata.name for aim in result] == ["llama3-8b"]


@pytest.mark.asyncio
async def test_get_aim_by_resource_name_success(kube_client: MagicMock) -> None:
    """Test successful retrieval."""
    aim = make_aim_cluster_model(name="my-aim")
    with patch("app.aims.service.get_aim_by_name", return_value=aim):
        result = await get_aim_by_resource_name(kube_client, "my-aim")
    assert result.metadata.name == "my-aim"


@pytest.mark.asyncio
async def test_get_aim_by_resource_name_not_found(kube_client: MagicMock) -> None:
    """Test raises NotFoundException."""
    with patch("app.aims.service.get_aim_by_name", return_value=None):
        with pytest.raises(NotFoundException):
            await get_aim_by_resource_name(kube_client, "missing")


@pytest.mark.asyncio
async def test_list_aims_passes_through_discovered_hardware(kube_client: MagicMock) -> None:
    """The catalog returns the AIMClusterModel resource as-is; the engine's
    ``status.discoveredProfiles.byHardware`` survives unchanged so consumers
    can read accelerator metadata directly from the resource."""
    aim = make_aim_cluster_model(
        name="llama3-8b",
        accelerator_type="gpu",
        accelerator_model="MI300X",
        accelerator_count=1,
    )

    with patch("app.aims.service.get_aims_from_k8s", return_value=[aim]):
        result = await list_aims(kube_client)

    assert len(result) == 1
    assert result[0].status.discovered_profiles is not None
    by_hardware = result[0].status.discovered_profiles.by_hardware
    assert len(by_hardware) == 1
    entry = by_hardware[0]
    assert entry.accelerator_type == "gpu"
    assert entry.accelerator_model == "MI300X"
    assert entry.accelerator_count == 1
    assert entry.supported is True


@pytest.mark.asyncio
async def test_list_aims_passes_through_multiple_hardware_groups(kube_client: MagicMock) -> None:
    """When the engine publishes multiple hardware groups, every group is
    surfaced verbatim and in order — the UI renders the AIM's full set of
    runtime options without picking a representative."""
    aim = AIMModelResource.model_validate(
        {
            "metadata": {"name": "multi-hw", "namespace": "ns"},
            "spec": {"image": "img"},
            "status": {
                "status": "Ready",
                "discoveredProfiles": {
                    "byHardware": [
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 1,
                            "supported": True,
                        },
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 2,
                            "supported": True,
                        },
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 8,
                            "supported": False,
                        },
                    ],
                },
            },
        }
    )

    with patch("app.aims.service.get_aims_from_k8s", return_value=[aim]):
        result = await list_aims(kube_client)

    assert result[0].status.discovered_profiles is not None
    by_hardware = result[0].status.discovered_profiles.by_hardware
    assert len(by_hardware) == 3
    assert [h.accelerator_count for h in by_hardware] == [1, 2, 8]
    assert [h.supported for h in by_hardware] == [True, True, False]
    assert all(h.accelerator_type == "gpu" and h.accelerator_model == "MI300X" for h in by_hardware)


@pytest.mark.asyncio
async def test_list_aims_passes_through_unknown_accelerator_type(kube_client: MagicMock) -> None:
    """Hardware groups with an accelerator family AIWB doesn't model still
    surface in the response — the raw engine value is passed through verbatim
    so the UI doesn't lose useful data."""
    aim = make_aim_cluster_model(
        name="unknown-hw",
        accelerator_type="tpu",
        accelerator_model="TPU_V5",
        accelerator_count=4,
    )

    with patch("app.aims.service.get_aims_from_k8s", return_value=[aim]):
        result = await list_aims(kube_client)

    assert result[0].status.discovered_profiles is not None
    by_hardware = result[0].status.discovered_profiles.by_hardware
    assert len(by_hardware) == 1
    entry = by_hardware[0]
    assert entry.accelerator_type == "tpu"
    assert entry.accelerator_model == "TPU_V5"
    assert entry.accelerator_count == 4


@pytest.mark.asyncio
async def test_list_aims_passes_through_aim_without_discovery(kube_client: MagicMock) -> None:
    """AIMs whose engine hasn't populated discoveredProfiles yet still appear
    in the catalog (no filter); ``status.discovered_profiles`` is ``None`` on
    the response, matching the underlying CRD shape."""
    aim = make_aim_cluster_model(name="no-discovery")

    with patch("app.aims.service.get_aims_from_k8s", return_value=[aim]):
        result = await list_aims(kube_client)

    assert len(result) == 1
    assert result[0].status.discovered_profiles is None


@pytest.mark.asyncio
async def test_list_aims_filters_by_accelerator_type_single(kube_client: MagicMock) -> None:
    """Single-value `accelerator_type=[CPU]` returns only AIMs with a CPU footprint;
    AIMs with unknown or missing accelerator families are excluded."""
    cpu_aim = make_aim_cluster_model(
        name="cpu-aim",
        accelerator_type="cpu",
        accelerator_model="EPYC_ZEN5",
    )
    gpu_aim = make_aim_cluster_model(
        name="gpu-aim",
        accelerator_type="gpu",
        accelerator_model="MI300X",
        accelerator_count=1,
    )
    unknown_aim = make_aim_cluster_model(
        name="unknown-aim",
        accelerator_type="tpu",
    )

    with patch("app.aims.service.get_aims_from_k8s", return_value=[cpu_aim, gpu_aim, unknown_aim]):
        result = await list_aims(kube_client, accelerator_type=[AcceleratorType.CPU])

    assert len(result) == 1
    assert result[0].metadata.name == "cpu-aim"
    assert result[0].status.discovered_profiles is not None
    assert result[0].status.discovered_profiles.by_hardware[0].accelerator_type == "cpu"


@pytest.mark.asyncio
async def test_list_aims_filters_by_accelerator_type_multiple(kube_client: MagicMock) -> None:
    """Multi-value `accelerator_type=[CPU, GPU]` ORs the requested families together
    — both the CPU and GPU AIMs match, the unknown-family AIM does not."""
    cpu_aim = make_aim_cluster_model(name="cpu-aim", accelerator_type="cpu", accelerator_model="EPYC_ZEN5")
    gpu_aim = make_aim_cluster_model(name="gpu-aim", accelerator_type="gpu", accelerator_model="MI300X")
    unknown_aim = make_aim_cluster_model(name="unknown-aim", accelerator_type="tpu")

    with patch("app.aims.service.get_aims_from_k8s", return_value=[cpu_aim, gpu_aim, unknown_aim]):
        result = await list_aims(kube_client, accelerator_type=[AcceleratorType.CPU, AcceleratorType.GPU])

    names = {aim.metadata.name for aim in result}
    assert names == {"cpu-aim", "gpu-aim"}


@pytest.mark.asyncio
async def test_list_aims_filter_excludes_aims_with_no_hardware(kube_client: MagicMock) -> None:
    """AIMs whose engine hasn't published a hardware breakdown drop out when a
    filter is set (no way to know if they match), but reappear when the filter
    is removed — same behavior as the prior scalar implementation."""
    aim = make_aim_cluster_model(name="no-discovery")

    with patch("app.aims.service.get_aims_from_k8s", return_value=[aim]):
        filtered = await list_aims(kube_client, accelerator_type=[AcceleratorType.CPU])
        unfiltered = await list_aims(kube_client)

    assert filtered == []
    assert len(unfiltered) == 1
    assert unfiltered[0].status.discovered_profiles is None


@pytest.mark.asyncio
async def test_list_aims_filter_matches_when_any_group_matches(kube_client: MagicMock) -> None:
    """An AIM with mixed hardware groups (hypothetical CPU+GPU AIM) matches a
    filter requesting either family — surfacing the AIM in both CPU-only and
    GPU-only catalog views."""
    aim = AIMModelResource.model_validate(
        {
            "metadata": {"name": "mixed-aim", "namespace": "ns"},
            "spec": {"image": "img"},
            "status": {
                "status": "Ready",
                "discoveredProfiles": {
                    "byHardware": [
                        {"acceleratorType": "cpu", "acceleratorModel": "EPYC_ZEN5", "supported": True},
                        {
                            "acceleratorType": "gpu",
                            "acceleratorModel": "MI300X",
                            "acceleratorCount": 1,
                            "supported": True,
                        },
                    ],
                },
            },
        }
    )

    with patch("app.aims.service.get_aims_from_k8s", return_value=[aim]):
        cpu_result = await list_aims(kube_client, accelerator_type=[AcceleratorType.CPU])
        gpu_result = await list_aims(kube_client, accelerator_type=[AcceleratorType.GPU])

    assert len(cpu_result) == 1
    assert cpu_result[0].metadata.name == "mixed-aim"
    assert len(gpu_result) == 1
    assert gpu_result[0].metadata.name == "mixed-aim"


@pytest.mark.asyncio
async def test_discovered_hardware_survives_list_and_detail(kube_client: MagicMock) -> None:
    """The discovered hardware breakdown survives both the list and detail
    call paths. AIWB no longer enriches the response, so this is essentially a
    contract lock-in — both endpoints return the AIMClusterModel as-is, with
    the engine's ``status.discoveredProfiles.byHardware`` intact."""
    aim = make_aim_cluster_model(
        name="llama3-8b",
        accelerator_type="gpu",
        accelerator_model="MI300X",
        accelerator_count=1,
    )

    with patch("app.aims.service.get_aim_by_name", return_value=aim):
        result = await get_aim_by_resource_name(kube_client, "llama3-8b")

    assert result.status.discovered_profiles is not None
    by_hardware = result.status.discovered_profiles.by_hardware
    assert len(by_hardware) == 1
    entry = by_hardware[0]
    assert entry.accelerator_type == "gpu"
    assert entry.accelerator_model == "MI300X"
    assert entry.accelerator_count == 1


@pytest.mark.asyncio
async def test_deploy_aim(kube_client: MagicMock) -> None:
    """Test deploying an AIM with model name."""
    aim = make_aim_cluster_model()
    svc = make_aim_service_k8s()
    req = AIMDeployRequest(model="meta-llama-3-8b")

    with (
        patch("app.aims.service.get_aim_by_name", return_value=aim),
        patch("app.aims.service.create_aim_service_in_k8s", return_value=svc),
    ):
        result = await deploy_aim(kube_client, req, "ns", "user")

    assert result is not None


@pytest.mark.asyncio
async def test_deploy_aim_with_resource_name(kube_client: MagicMock) -> None:
    """Test deploying an AIM using resource_name."""
    aim = make_aim_cluster_model(name="my-aim")
    svc = make_aim_service_k8s()
    req = AIMDeployRequest(model="my-aim")

    with (
        patch("app.aims.service.get_aim_by_name", return_value=aim),
        patch("app.aims.service.create_aim_service_in_k8s", return_value=svc),
    ):
        result = await deploy_aim(kube_client, req, "ns", "user")

    assert result is not None


@pytest.mark.asyncio
async def test_deploy_aim_not_found_raises_error(kube_client: MagicMock) -> None:
    """Test deploy raises NotFoundException when model not found."""
    req = AIMDeployRequest(model="nonexistent-model")

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=None),
        pytest.raises(NotFoundException, match="'nonexistent-model' not found"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_finetuned_aim_propagates_aimmodel_labels(kube_client: MagicMock) -> None:
    """User-given name comes from AIMModel labels; canonical name (slash-preserved) comes from spec.modelSources."""
    model_labels = {
        MODEL_NAME_LABEL: "my-finetune",
        # System labels — present on AIMModel but must not reach the gateway call
        "airm.silogen.ai/workload-id": str(uuid4()),
        "app.kubernetes.io/managed-by": "aim-model-controller",
    }
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name="wb-finetune-job", namespace="ns", labels=model_labels),
        spec=AIMModelSpec(
            model_sources=[AIMModelSource(model_id="Qwen/Qwen2.5-0.5B-Instruct", source_uri="s3://bucket/path")]
        ),
        status=AIMModelStatusFields(),
    )
    req = AIMDeployRequest(model="wb-finetune-job")

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=aim_model),
        patch("app.aims.service.find_aim_profile_for_model", return_value=None),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

        call_kwargs = mock_create.call_args.kwargs
        # User-given name comes from MODEL_NAME_LABEL on the AIMModel.
        assert call_kwargs["display_name"] == "my-finetune"
        # Canonical name comes from spec.model_sources (slash-preserved).
        assert call_kwargs["canonical_name"] == "Qwen/Qwen2.5-0.5B-Instruct"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_name", "mi300x-throughput-fp8"),
        ("image_pull_secrets", ["registry-credentials"]),
        ("hf_token", "hf-secret-name"),
    ],
)
async def test_deploy_finetuned_aim_rejects_disallowed_overrides(
    kube_client: MagicMock, field: str, value: object
) -> None:
    """Fine-tuned deployments reject profile_name, image pull secrets, and hf_token."""
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name="wb-finetune-job", namespace="ns"),
        spec=AIMModelSpec(),
        status=AIMModelStatusFields(),
    )
    req = AIMDeployRequest(model="wb-finetune-job", **{field: value})

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=aim_model),
        pytest.raises(ValidationException, match=to_camel(field)),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_finetuned_aim_accepts_profile_selector_and_overrides(kube_client: MagicMock) -> None:
    """Fine-tuned deployments propagate selector criteria and profileOverrides to the manifest builder."""
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name="wb-finetune-job", namespace="ns"),
        spec=AIMModelSpec(),
        status=AIMModelStatusFields(),
    )
    req = AIMDeployRequest(
        model="wb-finetune-job",
        metric=OptimizationMetric.LATENCY,
        precision="fp8",
        gpu_model="MI300X",
        gpu_count=2,
        engine_args={"max-model-len": 8192},
        engine_env=[{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}],
    )

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=aim_model),
        patch("app.aims.service.find_aim_profile_for_model", return_value=None),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["resolved_profile_name"] is None
    deploy_request = mock_create.call_args.kwargs["deploy_request"]
    assert deploy_request.metric == OptimizationMetric.LATENCY
    assert deploy_request.precision == "fp8"
    assert deploy_request.gpu_model == "MI300X"
    assert deploy_request.gpu_count == 2
    assert deploy_request.engine_args == {"max-model-len": 8192}
    assert deploy_request.engine_env == [{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}]


def _make_custom_namespace_aim_model(
    *,
    status: AIMModelStatus = AIMModelStatus.READY,
    hf_token_required: bool = False,
    import_annotations: dict[str, str] | None = None,
) -> AIMModelResource:
    annotations = {"airm.silogen.ai/display-name": "Custom Display", **(import_annotations or {})}
    return AIMModelResource(
        metadata=K8sMetadata(
            name="custom-model",
            namespace="ns",
            labels={MODEL_SOURCE_TYPE_LABEL: ModelSourceType.CUSTOM, MODEL_NAME_LABEL: "custom-display"},
            annotations=annotations,
        ),
        spec=AIMModelSpec(
            profiles=AIMModelProfilesSpec(
                derived_from=AIMModelProfilesDerivedFrom(selector=ProfileSelector(role="base")),
                overrides=ProfileOverrides(model_id="TinyLlama/TinyLlama-1.1B-Chat-v1.0"),
            )
        ),
        status=AIMModelStatusFields(
            status=status,
            image_metadata={"model": {"hfTokenRequired": hf_token_required}},
        ),
    )


def _owner_references(owner_set: str | None) -> list[dict[str, str | bool]]:
    """The AIMProfileSet owner reference aim-engine stamps on a derived profile."""
    return [{"kind": "AIMProfileSet", "name": owner_set, "controller": True}] if owner_set else []


def _make_ready_profile(
    *,
    name: str = "custom-profile",
    with_image_ref: bool = True,
    status: str = "Ready",
    owner_set: str | None = None,
) -> AIMProfileResource:
    annotations = {"aim.eai.amd.com/deployment-image-ref": "docker.io/amd/tinyllama:1.0.0"} if with_image_ref else {}
    return AIMProfileResource(
        metadata=K8sMetadata(
            name=name, namespace="ns", annotations=annotations, owner_references=_owner_references(owner_set)
        ),
        status=AIMProfileStatus(status=status),
    )


def _make_precision_profile(
    *,
    name: str,
    precision: str,
    metric: str = "latency",
    status: str = "Ready",
    primary: bool = False,
    optimization_type: str = "general",
    owner_set: str | None = None,
) -> AIMProfileResource:
    """Build a namespace AIMProfile carrying a precision/metric for deploy-selection tests."""
    return AIMProfileResource(
        metadata=K8sMetadata(name=name, namespace="ns", owner_references=_owner_references(owner_set)),
        spec=AIMProfileSpec(precision=precision, metric=metric, primary=primary, type=optimization_type),
        status=AIMProfileStatus(status=status),
    )


@pytest.fixture
def custom_profile_reads() -> Iterator[SimpleNamespace]:
    """The two Kubernetes reads custom deploy resolves a profile from.

    Defaults to the world every model imported before profile sets existed is in:
    no AIMProfileSets, and profiles carrying no set owner reference. Tests set
    ``profile_sets`` and ``profiles`` to describe the world they need.
    """
    with (
        patch(
            "app.aims.service.list_aim_profile_sets_for_model", new_callable=AsyncMock, return_value=[]
        ) as profile_sets,
        patch("app.aims.service.list_custom_model_profiles", new_callable=AsyncMock, return_value=[]) as profiles,
    ):
        yield SimpleNamespace(profile_sets=profile_sets, profiles=profiles)


@pytest.mark.asyncio
async def test_deploy_custom_model_requires_ready_aimmodel(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model(status=AIMModelStatus.PENDING)
    custom_profile_reads.profiles.return_value = [_make_ready_profile()]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        pytest.raises(ValidationException, match="AIMModel status"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_custom_model_rejected_when_weight_import_failed(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A failed HF→S3 weight import blocks deploy even though the AIMModel and its
    AIMProfile are Ready (profiles derive from the base image, not the weights)."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model(
        import_annotations={
            IMPORT_STATE_ANNOTATION: "Failed",
            IMPORT_ERROR_ANNOTATION: "MinIO returned HTTP 500 (disk full)",
        },
    )
    custom_profile_reads.profiles.return_value = [_make_ready_profile()]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        pytest.raises(ValidationException, match="weight import failed.*disk full"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_custom_model_rejected_while_weight_import_in_progress(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A legacy import-state=Importing annotation blocks deploy even when a Ready profile exists."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model(
        import_annotations={IMPORT_STATE_ANNOTATION: "Importing"},
    )
    custom_profile_reads.profiles.return_value = [_make_ready_profile()]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        pytest.raises(ValidationException, match="weight import is still in progress"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_custom_model_succeeds_when_weight_import_ready(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A legacy import-state=Ready annotation does not block deploy."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model(
        import_annotations={IMPORT_STATE_ANNOTATION: "Ready"},
    )
    custom_profile_reads.profiles.return_value = [_make_ready_profile()]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_deploy_custom_model_requires_profile(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A model the engine has emitted no profile for at all is reported as such, and
    points at the label the profile is expected to carry."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model()

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        pytest.raises(ValidationException, match="aim-engine has emitted no AIMProfile"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_custom_model_requires_ready_profile(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model()
    custom_profile_reads.profiles.return_value = [_make_ready_profile(status="Pending")]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        pytest.raises(ValidationException, match="AIMProfile 'custom-profile' status"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_custom_model_succeeds_without_deployment_image_annotation(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """v1alpha2 AIMProfiles embed image in spec overrides; deployment-image-ref annotation is not required."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model()
    custom_profile_reads.profiles.return_value = [_make_ready_profile(with_image_ref=False)]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    mock_create.assert_awaited_once()
    assert mock_create.call_args.kwargs["resolved_profile_name"] == "custom-profile"
    assert mock_create.call_args.kwargs["is_fine_tuned"] is False


@pytest.mark.asyncio
async def test_deploy_custom_model_passes_deploy_display_name(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A display name on the deploy request is forwarded as deploy_display_name,
    while the model identity (display_name) stays the onboarded model name."""
    req = AIMDeployRequest(model="custom-model", display_name="My TinyLlama")
    custom_model = _make_custom_namespace_aim_model()
    custom_profile_reads.profiles.return_value = [_make_ready_profile()]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["deploy_display_name"] == "My TinyLlama"
    assert call_kwargs["display_name"] == "custom-display"


@pytest.mark.asyncio
async def test_deploy_custom_model_without_display_name_passes_none(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """When the deploy request omits a display name, deploy_display_name is None
    so the manifest falls back to the onboarded model identity."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model()
    custom_profile_reads.profiles.return_value = [_make_ready_profile()]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["deploy_display_name"] is None


@pytest.mark.asyncio
async def test_deploy_custom_model_ignores_deploy_profile_fields_when_namespace_profile_ready(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """Custom deploy pins the onboarded profile; extra selector fields on the request are ignored."""
    req = AIMDeployRequest(
        model="custom-model",
        metric=OptimizationMetric.LATENCY,
        precision="fp8",
        gpu_model="MI300X",
        gpu_count=2,
    )
    custom_model = _make_custom_namespace_aim_model()
    custom_profile_reads.profiles.return_value = [_make_ready_profile()]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["resolved_profile_name"] == "custom-profile"


@pytest.mark.asyncio
async def test_deploy_finetuned_pins_namespace_profile_when_ready(kube_client: MagicMock) -> None:
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name="wb-finetune-job", namespace="ns"),
        spec=AIMModelSpec(),
        status=AIMModelStatusFields(),
    )
    req = AIMDeployRequest(model="wb-finetune-job", metric=OptimizationMetric.LATENCY, precision="fp8")

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=aim_model),
        patch("app.aims.service.find_aim_profile_for_model", return_value=_make_ready_profile(name="ft-profile")),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["resolved_profile_name"] == "ft-profile"


@pytest.mark.asyncio
async def test_deploy_finetuned_falls_back_when_profile_lookup_fails(kube_client: MagicMock) -> None:
    aim_model = AIMModelResource(
        metadata=K8sMetadata(name="wb-finetune-job", namespace="ns"),
        spec=AIMModelSpec(),
        status=AIMModelStatusFields(),
    )
    req = AIMDeployRequest(model="wb-finetune-job", precision="fp8")

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=aim_model),
        patch(
            "app.aims.service.find_aim_profile_for_model",
            side_effect=ApiException(status=503, reason="Service Unavailable"),
        ),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["resolved_profile_name"] is None


@pytest.mark.asyncio
async def test_deploy_custom_model_profile_lookup_error_raises_external_service_error(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A failed profile read must surface, not resolve off a partial list: silently
    deploying whichever profiles happened to be readable would pin the wrong one."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model()
    custom_profile_reads.profiles.side_effect = ExternalServiceError("Failed to list AIMProfiles in namespace 'ns'")

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        pytest.raises(ExternalServiceError, match="Failed to list AIMProfiles"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_custom_model_pins_profile_matching_onboarded_precision(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A custom model onboarded at fp8 must deploy the fp8 profile, not an arbitrary one.

    aim-engine emits one profile per (precision, metric) pair, and the first one it
    lists may be bf16. The resolver must pin the profile matching the onboarded
    precision annotation instead.
    """
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model()
    custom_model.metadata.annotations[MODEL_PRECISION_ANNOTATION] = "fp8"
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="model-bf16-latency", precision="bf16", metric="latency"),
        _make_precision_profile(name="model-bf16-throughput", precision="bf16", metric="throughput"),
        _make_precision_profile(name="model-fp8-throughput", precision="fp8", metric="throughput"),
        _make_precision_profile(name="model-fp8-latency", precision="fp8", metric="latency"),
    ]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    # fp8 chosen over bf16; latency preferred over throughput among fp8 profiles.
    assert mock_create.call_args.kwargs["resolved_profile_name"] == "model-fp8-latency"


@pytest.mark.asyncio
async def test_deploy_custom_model_without_precision_annotation_keeps_first_profile(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """Models onboarded before precision tracking have no annotation; behaviour is unchanged."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model()  # no precision annotation
    custom_profile_reads.profiles.return_value = [
        _make_ready_profile(name="first"),
        _make_ready_profile(name="second"),
    ]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["resolved_profile_name"] == "first"


@pytest.mark.asyncio
async def test_deploy_custom_model_falls_back_when_no_ready_profile_matches_precision(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """When the onboarded precision has no Ready profile, fall back to the first Ready one."""
    req = AIMDeployRequest(model="custom-model")
    custom_model = _make_custom_namespace_aim_model()
    custom_model.metadata.annotations[MODEL_PRECISION_ANNOTATION] = "fp8"
    # Only bf16 profiles are Ready; the fp8 profile is still Pending.
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="model-bf16-latency", precision="bf16", metric="latency"),
        _make_precision_profile(name="model-fp8-latency", precision="fp8", metric="latency", status="Pending"),
    ]

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=custom_model),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["resolved_profile_name"] == "model-bf16-latency"


def _two_set_profile_world(custom_profile_reads: SimpleNamespace, *, fast_status: str = "Ready") -> None:
    """A custom model with a Default and one authored profile, each deriving a profile."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-fast", is_aiwb_authored=True),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="default-bf16", precision="bf16", owner_set="custom-model-profiles-abc"),
        _make_precision_profile(name="fast-fp8", precision="fp8", owner_set="custom-model-fast", status=fast_status),
    ]


@pytest.mark.asyncio
async def test_deploy_custom_model_pins_the_requested_profile(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A custom model deploy now accepts a profile selection, and the manifest is
    pinned to the profile that selection derives rather than the Default's."""
    req = AIMDeployRequest(model="custom-model", profile_name="custom-model-fast")
    _two_set_profile_world(custom_profile_reads)

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=_make_custom_namespace_aim_model()),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["resolved_profile_name"] == "fast-fp8"


@pytest.mark.asyncio
async def test_deploy_custom_model_without_a_requested_profile_deploys_the_default(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """Omitting the selection keeps the pre-selection behaviour: the Default deploys."""
    req = AIMDeployRequest(model="custom-model")
    _two_set_profile_world(custom_profile_reads)

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=_make_custom_namespace_aim_model()),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = AIMServiceResource(
            metadata=K8sMetadata(name="wb-aim-test", namespace="ns"),
            spec=AIMServiceSpec(),
        )
        await deploy_aim(kube_client, req, "ns", "user")

    assert mock_create.call_args.kwargs["resolved_profile_name"] == "default-bf16"


@pytest.mark.asyncio
async def test_deploy_custom_model_rejects_an_unknown_requested_profile(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """The relaxed guard passes the selection to resolution rather than accepting it
    blindly, so an unknown one is still refused at the endpoint."""
    req = AIMDeployRequest(model="custom-model", profile_name="custom-model-slow")
    _two_set_profile_world(custom_profile_reads)

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=_make_custom_namespace_aim_model()),
        pytest.raises(ValidationException, match="Profile 'custom-model-slow' does not exist"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
async def test_deploy_custom_model_rejects_a_requested_profile_that_is_not_ready(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    req = AIMDeployRequest(model="custom-model", profile_name="custom-model-fast")
    _two_set_profile_world(custom_profile_reads, fast_status="Pending")

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=_make_custom_namespace_aim_model()),
        pytest.raises(ValidationException, match="AIMProfile 'fast-fp8' status is 'Pending'"),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("image_pull_secrets", ["registry-credentials"]),
        ("hf_token", "hf-secret-name"),
    ],
)
async def test_deploy_custom_model_still_rejects_image_and_token_fields(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace, field: str, value: object
) -> None:
    """Accepting a profile selection did not open the rest of the guard: images and
    credentials stay cluster-scoped concerns, since a custom model's weights and image
    are resolved from the model itself."""
    req = AIMDeployRequest(model="custom-model", **{field: value})
    _two_set_profile_world(custom_profile_reads)

    with (
        patch("app.aims.service.get_aim_by_name", return_value=None),
        patch("app.aims.service.get_aim_model_from_k8s", return_value=_make_custom_namespace_aim_model()),
        pytest.raises(ValidationException, match=to_camel(field)),
    ):
        await deploy_aim(kube_client, req, "ns", "user")


async def _resolve_custom_deploy_profile(
    kube_client: MagicMock,
    *,
    selection: str | None = None,
    precision: str | None = None,
) -> AIMProfileResource:
    """Resolve the profile a custom deploy would pin, bypassing the request contract.

    The deploy endpoint does not accept a profile selection yet, so these exercise the
    resolver directly at the seam that opens it. Resolving to no profile raises rather
    than returning None, so callers assert on a real profile.
    """
    custom_model = _make_custom_namespace_aim_model()
    if precision:
        custom_model.metadata.annotations[MODEL_PRECISION_ANNOTATION] = precision
    profile = await _resolve_namespace_deploy_profile(
        kube_client=kube_client,
        namespace="ns",
        model_name="custom-model",
        aim_model=custom_model,
        is_custom_model=True,
        profile_selection=selection,
    )
    assert profile is not None
    return profile


@pytest.mark.asyncio
async def test_custom_deploy_pins_the_profile_derived_from_the_selected_set(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """Selecting a narrowed set pins that set's profile, not the Default's."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-fast", is_aiwb_authored=True),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="default-bf16", precision="bf16", owner_set="custom-model-profiles-abc"),
        _make_precision_profile(name="fast-fp8", precision="fp8", owner_set="custom-model-fast"),
    ]

    profile = await _resolve_custom_deploy_profile(kube_client, selection="custom-model-fast")

    assert profile.metadata.name == "fast-fp8"


@pytest.mark.asyncio
async def test_custom_deploy_pins_the_selected_set_over_the_onboarded_precision(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """An explicit selection is the user's decision: a narrowed set derives one
    profile, and the onboarded precision must not pull the deploy off it."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-fast", is_aiwb_authored=True),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="default-fp8", precision="fp8", owner_set="custom-model-profiles-abc"),
        _make_precision_profile(name="fast-bf16", precision="bf16", owner_set="custom-model-fast"),
    ]

    profile = await _resolve_custom_deploy_profile(kube_client, selection="custom-model-fast", precision="fp8")

    assert profile.metadata.name == "fast-bf16"


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [None, "default"])
async def test_custom_deploy_resolves_the_default_set(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace, selection: str | None
) -> None:
    """Omitting a selection and asking for 'default' both resolve the Default set,
    which is how every deployment made before profile selection existed behaves."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-fast", is_aiwb_authored=True),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="fast-bf16", precision="bf16", owner_set="custom-model-fast"),
        _make_precision_profile(name="default-fp8", precision="fp8", owner_set="custom-model-profiles-abc"),
    ]

    profile = await _resolve_custom_deploy_profile(kube_client, selection=selection)

    assert profile.metadata.name == "default-fp8"


@pytest.mark.asyncio
async def test_custom_deploy_resolves_the_unnarrowed_default_by_onboarded_precision(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """An unnarrowed Default derives one profile per precision/metric pair; the
    onboarded precision picks among them, as it did before selection existed."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False)
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="default-bf16", precision="bf16", owner_set="custom-model-profiles-abc"),
        _make_precision_profile(name="default-fp8", precision="fp8", owner_set="custom-model-profiles-abc"),
    ]

    profile = await _resolve_custom_deploy_profile(kube_client, precision="fp8")

    assert profile.metadata.name == "default-fp8"


@pytest.mark.asyncio
async def test_custom_deploy_rejects_an_unknown_profile_selection(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """An unknown selection is refused rather than silently deploying the Default,
    which would hand the user a deployment they did not ask for. The message lists
    what they can pick, naming the Default by its alias."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-fast", is_aiwb_authored=True),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="default-bf16", precision="bf16", owner_set="custom-model-profiles-abc")
    ]

    with pytest.raises(ValidationException, match="does not exist") as excinfo:
        await _resolve_custom_deploy_profile(kube_client, selection="custom-model-slow")

    assert "'custom-model-fast'" in str(excinfo.value)
    assert "'default'" in str(excinfo.value)
    assert "custom-model-profiles-abc" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_custom_deploy_rejects_a_profile_set_from_another_project(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """Profile sets are read namespace-scoped, so another project's set is simply
    absent and reads as unknown — it never resolves across the project boundary."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False)
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="default-bf16", precision="bf16", owner_set="custom-model-profiles-abc")
    ]

    with pytest.raises(ValidationException, match="does not exist"):
        await _resolve_custom_deploy_profile(kube_client, selection="other-project-fast")


@pytest.mark.asyncio
async def test_custom_deploy_rejects_a_selected_profile_that_is_not_ready(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A selected profile that is not Ready refuses the deploy: quietly pinning a
    different, Ready profile would deploy a configuration the user did not choose."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-fast", is_aiwb_authored=True),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="default-bf16", precision="bf16", owner_set="custom-model-profiles-abc"),
        _make_precision_profile(name="fast-fp8", precision="fp8", owner_set="custom-model-fast", status="Pending"),
    ]

    with pytest.raises(ValidationException, match="AIMProfile 'fast-fp8' status is 'Pending'"):
        await _resolve_custom_deploy_profile(kube_client, selection="custom-model-fast")


@pytest.mark.asyncio
async def test_custom_deploy_reports_a_selected_set_with_no_derived_profile_yet(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A set the engine has not derived a profile from yet cannot be deployed, and
    must not fall back to the Default's profile. The refusal names the selected
    profile, because the model does have profiles — just none from that set."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-fast", is_aiwb_authored=True),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="default-bf16", precision="bf16", owner_set="custom-model-profiles-abc")
    ]

    with pytest.raises(ValidationException, match="profile 'custom-model-fast' has no AIMProfile derived from it"):
        await _resolve_custom_deploy_profile(kube_client, selection="custom-model-fast")


@pytest.mark.asyncio
async def test_custom_deploy_resolves_the_default_when_the_model_has_no_profile_sets(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """Models imported before profile sets existed have none, and their profiles carry
    no set owner reference. They must keep deploying the profile they always have."""
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="legacy-bf16", precision="bf16"),
        _make_precision_profile(name="legacy-fp8", precision="fp8"),
    ]

    profile = await _resolve_custom_deploy_profile(kube_client, precision="fp8")

    assert profile.metadata.name == "legacy-fp8"


@pytest.mark.asyncio
async def test_custom_deploy_reads_profile_sets_and_profiles_strictly(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """Resolution decides from both lists, so neither may silently come back short: an
    item dropped upstream reads here as one the model does not have."""
    custom_profile_reads.profiles.return_value = [_make_precision_profile(name="legacy-bf16", precision="bf16")]

    await _resolve_custom_deploy_profile(kube_client)

    assert custom_profile_reads.profile_sets.await_args.kwargs["strict"] is True
    assert custom_profile_reads.profiles.await_args.kwargs["strict"] is True


@pytest.mark.asyncio
async def test_custom_deploy_refuses_when_no_set_is_identifiable_and_every_profile_is_owned(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """Two Defaults means the set layer cannot say which profile the Default is. Every
    profile here belongs to one of them, so picking one would be a guess at which set
    the user meant; the deploy is refused instead."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-profiles-def", is_aiwb_authored=False),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="bf16", precision="bf16", owner_set="custom-model-profiles-abc"),
        _make_precision_profile(name="fp8", precision="fp8", owner_set="custom-model-profiles-def"),
    ]

    with pytest.raises(ValidationException, match="Default profile cannot be identified"):
        await _resolve_custom_deploy_profile(kube_client, precision="fp8")


@pytest.mark.asyncio
async def test_custom_deploy_ignores_authored_profiles_when_the_default_has_none_yet(
    kube_client: MagicMock, custom_profile_reads: SimpleNamespace
) -> None:
    """A Default the engine has not derived a profile from yet must not borrow one
    from an authored set: that would deploy a configuration the user never selected.
    The refusal names the Default by the alias clients select it with."""
    custom_profile_reads.profile_sets.return_value = [
        make_aim_profile_set(name="custom-model-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="custom-model-fast", is_aiwb_authored=True),
    ]
    custom_profile_reads.profiles.return_value = [
        _make_precision_profile(name="fast-fp8", precision="fp8", owner_set="custom-model-fast")
    ]

    with pytest.raises(ValidationException, match="profile 'default' has no AIMProfile derived from it"):
        await _resolve_custom_deploy_profile(kube_client, precision="fp8")


@pytest.mark.asyncio
async def test_deploy_aim_with_camelcase_deploy_request(kube_client: MagicMock) -> None:
    """Test deploy_aim accepts deploy_request parsed from camelCase (as sent by UI)."""
    aim = make_aim_cluster_model()
    svc = make_aim_service_k8s()
    req = AIMDeployRequest(
        model="meta-llama-3-8b",
        imagePullSecrets=["s1"],
        hfToken="hf-secret",
        minReplicas=1,
        maxReplicas=5,
        autoScaling={"metrics": []},
    )

    with (
        patch("app.aims.service.get_aim_by_name", return_value=aim),
        patch("app.aims.service.create_aim_service_in_k8s", return_value=svc) as mock_create,
    ):
        result = await deploy_aim(kube_client, req, "ns", "user")

    assert result is not None
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["deploy_request"].image_pull_secrets == ["s1"]
    assert call_kwargs["deploy_request"].hf_token == "hf-secret"
    assert call_kwargs["deploy_request"].min_replicas == 1
    assert call_kwargs["deploy_request"].max_replicas == 5
    assert call_kwargs["deploy_request"].auto_scaling == {"metrics": []}


@pytest.mark.asyncio
async def test_undeploy_aim(kube_client: MagicMock) -> None:
    """Test undeploying an AIM."""
    svc = make_aim_service_k8s()
    with (
        patch("app.aims.service.get_aim_service_from_k8s", return_value=svc),
        patch("app.aims.service.delete_aim_service_from_k8s", return_value="svc-name"),
    ):
        await undeploy_aim(kube_client, uuid4(), "ns")


@pytest.mark.asyncio
async def test_undeploy_aim_not_found(kube_client: MagicMock) -> None:
    """Test undeploy raises when service not found."""
    with patch("app.aims.service.get_aim_service_from_k8s", return_value=None):
        with pytest.raises(NotFoundException):
            await undeploy_aim(kube_client, uuid4(), "ns")


@pytest.mark.asyncio
async def test_list_aim_services(kube_client: MagicMock) -> None:
    """Test listing AIMServices."""
    svc = make_aim_service_k8s()
    with patch("app.aims.service.get_aim_services_from_k8s", return_value=[svc]):
        result = await list_aim_services(kube_client, "ns")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_list_aim_services_returns_resolved_profile_name_only(kube_client: MagicMock) -> None:
    """status.resolvedProfile carries only the reference name on the wire. Joining
    against the AIMProfile catalog for spec details is the FE's responsibility now
    (was previously inlined here, but coupled the services endpoint to the profile
    catalog and hid RBAC failures as silent empty rows)."""
    svc = make_aim_service_k8s(profile_name="llama3-8b-latency")
    svc.status = AIMServiceStatusFields(
        status=AIMServiceStatus.RUNNING,
        resolved_profile=ResolvedRef(name="llama3-8b-latency"),
    )

    with patch("app.aims.service.get_aim_services_from_k8s", return_value=[svc]):
        result = await list_aim_services(kube_client, "ns")

    assert len(result) == 1
    resolved = result[0].status.resolved_profile
    assert resolved is not None
    assert resolved.name == "llama3-8b-latency"
    # No profile catalog lookups happen here anymore.
    assert not hasattr(resolved, "spec") or getattr(resolved, "spec", None) is None


@pytest.mark.asyncio
async def test_get_aim_service(kube_client: MagicMock) -> None:
    """Test getting single AIMService."""
    svc = make_aim_service_k8s()
    with patch("app.aims.service.get_aim_service_from_k8s", return_value=svc):
        result = await get_aim_service(kube_client, "ns", uuid4())
    assert result is not None


@pytest.mark.asyncio
async def test_get_aim_service_not_found(kube_client: MagicMock) -> None:
    """Test raises when not found."""
    with patch("app.aims.service.get_aim_service_from_k8s", return_value=None):
        with pytest.raises(NotFoundException):
            await get_aim_service(kube_client, "ns", uuid4())


@pytest.mark.asyncio
async def test_list_aim_cluster_profiles_filters_by_aim_ids(kube_client: MagicMock) -> None:
    """Delegates to the gateway with the supplied aimId list."""
    profile = make_aim_cluster_profile(aim_id="org/my-aim")
    with patch(
        "app.aims.service.get_aim_cluster_profiles_from_k8s",
        return_value=[profile],
    ) as mock_gateway:
        result = await list_aim_cluster_profiles(kube_client, aim_ids=["org/my-aim"])

    assert len(result) == 1
    mock_gateway.assert_awaited_once_with(kube_client, aim_ids=["org/my-aim"])


@pytest.mark.asyncio
async def test_list_aim_cluster_profiles_no_filter(kube_client: MagicMock) -> None:
    """Omitting aim_ids lists every profile cluster-wide."""
    profiles = [make_aim_cluster_profile(aim_id="org/a"), make_aim_cluster_profile(aim_id="org/b")]
    with patch(
        "app.aims.service.get_aim_cluster_profiles_from_k8s",
        return_value=profiles,
    ) as mock_gateway:
        result = await list_aim_cluster_profiles(kube_client)

    assert len(result) == 2
    mock_gateway.assert_awaited_once_with(kube_client, aim_ids=None)


@pytest.mark.asyncio
async def test_list_aim_cluster_profiles_returns_empty(kube_client: MagicMock) -> None:
    """No matching profiles returns an empty list (not an exception)."""
    with patch("app.aims.service.get_aim_cluster_profiles_from_k8s", return_value=[]):
        result = await list_aim_cluster_profiles(kube_client, aim_ids=["org/unknown"])

    assert result == []


@pytest.mark.asyncio
async def test_get_aim_cluster_profile_returns_match(kube_client: MagicMock) -> None:
    """Direct GET by name returns the matching profile."""
    profile = make_aim_cluster_profile(name="profile-x", aim_id="org/my-aim")
    with patch("app.aims.service.get_aim_cluster_profile_from_k8s", return_value=profile) as mock_gateway:
        result = await get_aim_cluster_profile(kube_client, "profile-x")

    assert result is profile
    mock_gateway.assert_awaited_once_with(kube_client, "profile-x")


@pytest.mark.asyncio
async def test_get_aim_cluster_profile_not_found(kube_client: MagicMock) -> None:
    """Missing profile maps to NotFoundException so the router returns 404."""
    with patch("app.aims.service.get_aim_cluster_profile_from_k8s", return_value=None):
        with pytest.raises(NotFoundException):
            await get_aim_cluster_profile(kube_client, "missing-profile")


@pytest.mark.asyncio
async def test_get_aim_profile_returns_match(kube_client: MagicMock) -> None:
    """Direct GET by name in a namespace returns the matching profile."""
    profile = make_aim_cluster_profile(name="profile-x", aim_id="org/ft-aim")
    with patch("app.aims.service.get_aim_profile_from_k8s", return_value=profile) as mock_gateway:
        result = await get_aim_profile(kube_client, "test-ns", "profile-x")

    assert result is profile
    mock_gateway.assert_awaited_once_with(kube_client, "test-ns", "profile-x")


@pytest.mark.asyncio
async def test_get_aim_profile_not_found(kube_client: MagicMock) -> None:
    """Missing namespace-scoped profile maps to NotFoundException."""
    with patch("app.aims.service.get_aim_profile_from_k8s", return_value=None):
        with pytest.raises(NotFoundException):
            await get_aim_profile(kube_client, "test-ns", "missing")


@pytest.mark.asyncio
async def test_list_chattable_aim_services(kube_client: MagicMock) -> None:
    """Chat lister requests the chat capability from the gateway."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(conditions=conditions)
    with patch("app.aims.service.get_aim_services_from_k8s", return_value=[svc]) as mock_list:
        result = await list_chattable_aim_services(kube_client, "ns")
    assert len(result) == 1
    mock_list.assert_called_once_with(kube_client, "ns", capability=InferenceCapability.CHAT)


@pytest.mark.asyncio
async def test_list_transcribable_aim_services(kube_client: MagicMock) -> None:
    """Transcription lister requests the transcription capability from the gateway."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(conditions=conditions)
    with patch("app.aims.service.get_aim_services_from_k8s", return_value=[svc]) as mock_list:
        result = await list_transcribable_aim_services(kube_client, "ns")
    assert len(result) == 1
    mock_list.assert_called_once_with(kube_client, "ns", capability=InferenceCapability.TRANSCRIPTION)
