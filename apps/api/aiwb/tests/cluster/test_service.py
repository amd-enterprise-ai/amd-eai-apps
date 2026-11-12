# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for cluster service."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from kubernetes_asyncio.client import ApiException, V1Node, V1NodeList, V1NodeStatus

from app.cluster.enums import ClusterAcceleratorType
from app.cluster.service import (
    _accelerator_resource_type,
    _resolve_cluster_base_image_ref,
    get_aim_image_families,
    get_cluster_accelerators,
    get_cluster_gpu_device_ids,
    get_cluster_resources,
    get_project_gpu_allocation_ceiling,
    get_project_gpu_quota_from_kueue,
    get_project_quota_state,
    parse_cpu_value,
    parse_memory_value,
)
from app.cluster.utils import (
    node_aim_accelerator_model_counts,
    node_aim_gpu_accelerator_model,
    normalize_gpu_device_id,
    parse_container_image_repository_and_tag,
)
from app.custom_models.constants import (
    DEFAULT_AIM_DEPLOYMENT_IMAGE_REF,
    EPYC_AIM_DEPLOYMENT_IMAGE_REF,
    RADEON_AIM_DEPLOYMENT_IMAGE_REF,
)
from app.projects.crds import Namespace


def test_parse_cpu_value():
    """Test CPU value parsing."""
    assert parse_cpu_value("1") == 1000
    assert parse_cpu_value("500m") == 500
    assert parse_cpu_value("2.5") == 2500
    assert parse_cpu_value("") == 0


def test_parse_memory_value():
    """Test memory value parsing."""
    assert parse_memory_value("1024Ki") == 1024 * 1024
    assert parse_memory_value("1Mi") == 1024 * 1024
    assert parse_memory_value("1Gi") == 1024 * 1024 * 1024
    assert parse_memory_value("1000") == 1000
    assert parse_memory_value("") == 0


def test_resolve_cluster_base_image_ref_treats_nvidia_rtx_as_non_radeon() -> None:
    image_refs = _resolve_cluster_base_image_ref(
        [
            Mock(
                accelerator_model="RTX4090",
                accelerator_type=ClusterAcceleratorType.GPU,
                accelerator_vendor="nvidia",
            )
        ]
    )
    assert image_refs == [DEFAULT_AIM_DEPLOYMENT_IMAGE_REF]


def test_resolve_cluster_base_image_ref_keeps_radeon_detection_for_amd_r_series() -> None:
    image_refs = _resolve_cluster_base_image_ref(
        [
            Mock(
                accelerator_model="R9700",
                accelerator_type=ClusterAcceleratorType.GPU,
                accelerator_vendor="amd",
            )
        ]
    )
    assert image_refs == [RADEON_AIM_DEPLOYMENT_IMAGE_REF]


def test_resolve_cluster_base_image_ref_treats_nvidia_w_series_as_non_radeon() -> None:
    image_refs = _resolve_cluster_base_image_ref(
        [
            Mock(
                accelerator_model="W7900",
                accelerator_type=ClusterAcceleratorType.GPU,
                accelerator_vendor="nvidia",
            )
        ]
    )
    assert image_refs == [DEFAULT_AIM_DEPLOYMENT_IMAGE_REF]


def test_resolve_cluster_base_image_ref_treats_amd_w_series_as_radeon() -> None:
    image_refs = _resolve_cluster_base_image_ref(
        [
            Mock(
                accelerator_model="W7900",
                accelerator_type=ClusterAcceleratorType.GPU,
                accelerator_vendor="amd",
            )
        ]
    )
    assert image_refs == [RADEON_AIM_DEPLOYMENT_IMAGE_REF]


def test_accelerator_resource_type_treats_w_series_as_gpu() -> None:
    assert _accelerator_resource_type("W7900") == ClusterAcceleratorType.GPU


@pytest.mark.parametrize(
    ("image_ref", "expected_repository", "expected_tag_or_digest"),
    [
        ("amdenterpriseai/aim-base:0.11", "amdenterpriseai/aim-base", "0.11"),
        ("localhost:5000/aim-base:latest", "localhost:5000/aim-base", "latest"),
        (
            "amdenterpriseai/aim-base@sha256:abcdef0123456789",
            "amdenterpriseai/aim-base",
            "sha256:abcdef0123456789",
        ),
        (
            "amdenterpriseai/aim-base:0.11@sha256:abcdef0123456789",
            "amdenterpriseai/aim-base",
            "sha256:abcdef0123456789",
        ),
        (
            "localhost:5000/aim-base:latest@sha256:abcdef0123456789",
            "localhost:5000/aim-base",
            "sha256:abcdef0123456789",
        ),
    ],
)
def test_parse_container_image_repository_and_tag(
    image_ref: str,
    expected_repository: str,
    expected_tag_or_digest: str,
) -> None:
    repository, tag_or_digest = parse_container_image_repository_and_tag(image_ref)
    assert repository == expected_repository
    assert tag_or_digest == expected_tag_or_digest


@pytest.mark.parametrize(
    ("device_id", "expected"),
    [
        ("74a1", "74a1"),
        ("0x75a8", "75a8"),
        ("0X75A8", "75a8"),
        (" 74B5 ", "74b5"),
        (7448, "7448"),
    ],
)
def test_normalize_gpu_device_id(device_id: str | int, expected: str) -> None:
    assert normalize_gpu_device_id(device_id) == expected


@pytest.mark.parametrize(
    "image_ref",
    [
        "",
        "repo-only",
        "repo@",
        "@sha256:abc",
        "repo@sha256:",
        "registry.example.com:5000/custom-base",
        "registry.example.com:5000/vendor/custom-base",
    ],
)
def test_parse_container_image_repository_and_tag_rejects_invalid(image_ref: str) -> None:
    with pytest.raises(ValueError):
        parse_container_image_repository_and_tag(image_ref)


@pytest.mark.asyncio
async def test_get_aim_image_families_includes_automatic_first():
    families = await get_aim_image_families(
        make_kube_client(
            [make_node("74a1", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Instinct_MI300X")],
            cluster_model_items=[
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13"),
            ],
        )
    )
    assert len(families) == 2
    assert families[0].family_id == "automatic"
    assert families[0].repository is None
    assert families[0].tags == []


@pytest.mark.asyncio
async def test_get_aim_image_families_includes_aim_base_from_supported_base_cluster_models():
    families = await get_aim_image_families(
        make_kube_client(
            [make_node("74a1", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Instinct_MI300X")],
            cluster_model_items=[
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.11"),
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13"),
            ],
        )
    )
    by_id = {family.family_id: family for family in families}
    assert set(by_id) == {"automatic", "aim-base"}
    repository, _ = parse_container_image_repository_and_tag(DEFAULT_AIM_DEPLOYMENT_IMAGE_REF)
    assert by_id["aim-base"].repository == repository
    assert by_id["aim-base"].tags == ["0.13", "0.11"]


@pytest.mark.asyncio
async def test_get_aim_image_families_is_idempotent():
    kube_client = make_kube_client(
        [make_node("74a1", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Instinct_MI300X")],
        cluster_model_items=[
            make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13.1"),
        ],
    )
    first = await get_aim_image_families(kube_client)
    second = await get_aim_image_families(kube_client)
    assert [f.model_dump() for f in first] == [f.model_dump() for f in second]


@pytest.mark.asyncio
async def test_get_aim_image_families_stable_order():
    families = await get_aim_image_families(
        make_kube_client(
            [make_node("74a1", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Instinct_MI300X")],
            cluster_model_items=[
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-radeon-base:0.12"),
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13"),
            ],
        )
    )
    ids = [family.family_id for family in families]
    assert ids == ["automatic", "aim-base", "aim-radeon-base"]


@pytest.mark.asyncio
async def test_get_aim_image_families_returns_independent_copies():
    kube_client = make_kube_client(
        [make_node("74a1", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Instinct_MI300X")],
        cluster_model_items=[
            make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13"),
        ],
    )
    families = await get_aim_image_families(kube_client)
    families[1].tags.append("mutated-tag")

    fresh = await get_aim_image_families(kube_client)
    assert fresh[1].tags == ["0.13"]


@pytest.mark.asyncio
async def test_get_aim_image_families_uses_supported_base_cluster_models():
    families = await get_aim_image_families(
        make_kube_client(
            [make_node("73bf", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Radeon_RX_7900_XTX")],
            cluster_model_items=[
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13"),
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13.1"),
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-radeon-base:0.12"),
                # Not base-only (inference managedProfiles present) => ignored.
                make_base_cluster_model_item(
                    image_ref="amdenterpriseai/should-not-appear:9.9",
                    managed_profiles={"base": 1, "inference": 1},
                ),
                # Base-only but unsupported => ignored.
                make_base_cluster_model_item(
                    image_ref="amdenterpriseai/unsupported:9.9",
                    discovered_supported=0,
                ),
            ],
        )
    )
    by_id = {family.family_id: family for family in families}
    assert set(by_id) == {"automatic", "aim-base", "aim-radeon-base"}
    assert by_id["aim-base"].tags == ["0.13.1", "0.13"]
    assert by_id["aim-radeon-base"].tags == ["0.12"]


@pytest.mark.asyncio
async def test_get_aim_image_families_surfaces_audio_capable_instinct_base():
    """An audio-enabled MI300X base is discovered like any other base once it is
    registered as a base-only AIMClusterModel.

    Base selection is data-driven (``is_supported_base_cluster_model``), so no code
    change is needed to make an audio-capable base selectable for custom-model
    onboarding — publishing and registering the image is the only prerequisite.
    This locks that behaviour in.
    """
    families = await get_aim_image_families(
        make_kube_client(
            [make_node("74a1", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Instinct_MI300X")],
            cluster_model_items=[
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-instinct-audio-base:2026.10"),
            ],
        )
    )

    by_id = {family.family_id: family for family in families}
    assert "aim-instinct-audio-base" in by_id
    assert by_id["aim-instinct-audio-base"].tags == ["2026.10"]


@pytest.mark.asyncio
async def test_get_aim_image_families_sorts_base_family_tags_descending():
    families = await get_aim_image_families(
        make_kube_client(
            [make_node("74a1", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Instinct_MI300X")],
            cluster_model_items=[
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.11"),
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13"),
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13.0"),
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13.1"),
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.12"),
            ],
        )
    )
    by_id = {family.family_id: family for family in families}
    assert by_id["aim-base"].tags == ["0.13.1", "0.13.0", "0.13", "0.12", "0.11"]


@pytest.mark.asyncio
async def test_get_aim_image_families_returns_automatic_only_when_no_supported_base_cluster_models():
    families = await get_aim_image_families(
        make_kube_client(
            [
                make_node(
                    "74a1",
                    allocatable={"amd.com/gpu": "1"},
                    product_name="AMD_Instinct_MI300X",
                    aim_accelerator_labels={"MI300X": "1"},
                ),
                make_node(
                    "73bf",
                    allocatable={"amd.com/gpu": "1"},
                    product_name="AMD_Radeon_RX_7900_XTX",
                    aim_accelerator_labels={"R9700": "1"},
                ),
            ],
            cluster_model_items=[
                make_base_cluster_model_item(
                    image_ref="amdenterpriseai/unsupported:9.9",
                    discovered_supported=0,
                ),
                make_base_cluster_model_item(
                    image_ref="amdenterpriseai/not-base-only:9.9",
                    managed_profiles={"base": 1, "inference": 1},
                ),
            ],
        )
    )
    by_id = {family.family_id: family for family in families}
    assert set(by_id) == {"automatic"}


@pytest.mark.asyncio
async def test_get_aim_image_families_falls_back_when_cluster_model_lookup_fails():
    families = await get_aim_image_families(
        make_kube_client(
            [
                make_node(
                    "73bf",
                    allocatable={"amd.com/gpu": "1"},
                    product_name="AMD rAdEoN RX 7900 XTX",
                    aim_accelerator_labels={"R9700": "1"},
                )
            ],
            cluster_model_side_effect=RuntimeError("kube unavailable"),
        )
    )
    by_id = {family.family_id: family for family in families}
    assert set(by_id) == {"automatic", "aim-radeon-base"}


@pytest.mark.asyncio
async def test_get_aim_image_families_falls_back_to_epyc_base_when_only_epyc_cpu_detected():
    families = await get_aim_image_families(
        make_kube_client(
            [
                make_node(
                    allocatable={"cpu": "128"},
                    aim_accelerator_labels={"EPYC_ZEN5": "1", "CPU": "1"},
                )
            ],
            cluster_model_side_effect=RuntimeError("kube unavailable"),
        )
    )
    by_id = {family.family_id: family for family in families}
    assert set(by_id) == {"automatic", "aim-epyc-base"}
    epyc_repository, epyc_tag = parse_container_image_repository_and_tag(EPYC_AIM_DEPLOYMENT_IMAGE_REF)
    assert by_id["aim-epyc-base"].repository == epyc_repository
    assert by_id["aim-epyc-base"].tags == [epyc_tag]


@pytest.mark.asyncio
async def test_get_aim_image_families_skips_invalid_cluster_model_images():
    families = await get_aim_image_families(
        make_kube_client(
            [make_node("73bf", allocatable={"amd.com/gpu": "1"}, product_name="AMD rAdEoN RX 7900 XTX")],
            cluster_model_items=[
                make_base_cluster_model_item(image_ref="amdenterpriseai/aim-radeon-base:0.12"),
                make_base_cluster_model_item(image_ref="not-a-valid-image-ref"),
            ],
        )
    )
    by_id = {family.family_id: family for family in families}
    assert set(by_id) == {"automatic", "aim-radeon-base"}


@pytest.mark.asyncio
async def test_get_aim_image_families_returns_repository_and_tags():
    # cluster/aim-images currently exposes repository+tags only.
    families = await get_aim_image_families(
        make_kube_client(
            [make_node("74a1", allocatable={"amd.com/gpu": "1"}, product_name="AMD_Instinct_MI300X")],
            cluster_model_items=[make_base_cluster_model_item(image_ref="amdenterpriseai/aim-base:0.13")],
        )
    )
    by_id = {family.family_id: family for family in families}
    assert by_id["aim-base"].repository == "amdenterpriseai/aim-base"


def make_node(
    device_id: str | None = None,
    ready: bool = True,
    allocatable: dict | None = None,
    beta_device_id: str | None = None,
    product_name: str | None = None,
    beta_product_name: str | None = None,
    aim_accelerator_labels: dict[str, str] | None = None,
) -> Mock:
    """Build a mock V1Node.

    Args:
        device_id: Value for the amd.com/gpu.device-id label.
        ready: Whether the node has a Ready=True condition.
        allocatable: Dict of allocatable resources (cpu, memory, etc.).
        beta_device_id: Value for the beta.amd.com/gpu.device-id label.
        product_name: Value for the amd.com/gpu.product-name label.
        beta_product_name: Value for the beta.amd.com/gpu.product-name label.
    """
    node = Mock(spec=V1Node)
    node.status = Mock(spec=V1NodeStatus)

    condition = Mock()
    condition.type = "Ready"
    condition.status = "True" if ready else "False"
    node.status.conditions = [condition]

    labels: dict[str, str] = {}
    if device_id:
        labels["amd.com/gpu.device-id"] = device_id
    if beta_device_id:
        labels["beta.amd.com/gpu.device-id"] = beta_device_id
    if product_name:
        labels["amd.com/gpu.product-name"] = product_name
    if beta_product_name:
        labels["beta.amd.com/gpu.product-name"] = beta_product_name
    if aim_accelerator_labels:
        for suffix, value in aim_accelerator_labels.items():
            labels[f"feature.node.kubernetes.io/aim-accelerator.{suffix}"] = value
    metadata = Mock()
    metadata.labels = labels
    node.metadata = metadata

    if allocatable is not None:
        node.status.allocatable = allocatable
        node.to_dict = Mock(return_value={"status": {"allocatable": allocatable}})

    return node


@pytest.mark.asyncio
async def test_get_cluster_resources():
    allocatable = {"cpu": "4", "memory": "8Gi", "ephemeral-storage": "100Gi", "amd.com/gpu": "2"}
    result = await get_cluster_resources(make_kube_client([make_node(allocatable=allocatable)]))

    assert result.data.total_node_count == 1
    assert result.data.available_resources.cpu_milli_cores == 4000
    assert result.data.available_resources.memory_bytes == 8 * 1024 * 1024 * 1024
    assert result.data.available_resources.ephemeral_storage_bytes == 100 * 1024 * 1024 * 1024
    assert result.data.available_resources.gpu_count == 2


@pytest.mark.asyncio
async def test_get_cluster_resources_multiple_nodes():
    allocatable = {"cpu": "8", "memory": "16Gi", "ephemeral-storage": "200Gi", "amd.com/gpu": "4"}
    nodes = [make_node(allocatable=allocatable), make_node(allocatable=allocatable)]
    result = await get_cluster_resources(make_kube_client(nodes))

    assert result.data.total_node_count == 2
    assert result.data.available_resources.cpu_milli_cores == 16000
    assert result.data.available_resources.memory_bytes == 32 * 1024 * 1024 * 1024
    assert result.data.available_resources.ephemeral_storage_bytes == 400 * 1024 * 1024 * 1024
    assert result.data.available_resources.gpu_count == 8


def make_kube_client(
    nodes: list[Mock],
    cluster_model_items: list[dict] | None = None,
    cluster_model_side_effect: Exception | None = None,
) -> Mock:
    """Build a mock KubernetesClient for node + AIMClusterModel reads."""
    mock_response = Mock(spec=V1NodeList)
    mock_response.items = nodes

    mock_kube_client = Mock()
    mock_kube_client.core_v1 = Mock()
    mock_kube_client.core_v1.list_node = AsyncMock(return_value=mock_response)
    mock_kube_client.custom_objects = Mock()
    if cluster_model_side_effect is not None:
        mock_kube_client.custom_objects.list_cluster_custom_object = AsyncMock(side_effect=cluster_model_side_effect)
    else:
        mock_kube_client.custom_objects.list_cluster_custom_object = AsyncMock(
            return_value={"items": cluster_model_items or []}
        )
    return mock_kube_client


def make_base_cluster_model_item(
    *,
    image_ref: str,
    managed_profiles: dict[str, int] | None = None,
    discovered_supported: int = 1,
    image_pull_secret_name: str | None = None,
) -> dict:
    # AIMClusterModel-based discovery uses spec.image and status.managedProfiles.
    effective_managed_profiles = managed_profiles or {
        "base": 1,
        "deployable": 0,
        "notAvailable": 0,
        "ready": 1,
        "total": 1,
    }
    spec: dict[str, object] = {"image": image_ref}
    if image_pull_secret_name:
        spec["imagePullSecrets"] = [{"name": image_pull_secret_name}]
    return {
        "metadata": {"name": f"cluster-model-{abs(hash(image_ref)) % 100000}"},
        "spec": spec,
        "status": {
            "managedProfiles": effective_managed_profiles,
            "discoveredProfiles": {"supported": discovered_supported},
        },
    }


@pytest.mark.asyncio
async def test_get_cluster_gpu_device_ids_returns_device_ids():
    result = await get_cluster_gpu_device_ids(make_kube_client([make_node("74a1"), make_node("74a9")]))

    assert result == {"74a1", "74a9"}


@pytest.mark.asyncio
async def test_get_cluster_gpu_device_ids_deduplicates():
    result = await get_cluster_gpu_device_ids(
        make_kube_client([make_node("74a1"), make_node("74a1"), make_node("74a1")])
    )

    assert result == {"74a1"}


@pytest.mark.asyncio
async def test_get_cluster_gpu_device_ids_no_label_returns_empty():
    result = await get_cluster_gpu_device_ids(make_kube_client([make_node(device_id=None), make_node(device_id=None)]))

    assert result == set()


@pytest.mark.asyncio
async def test_get_cluster_gpu_device_ids_excludes_not_ready_nodes():
    result = await get_cluster_gpu_device_ids(
        make_kube_client([make_node("74a1", ready=True), make_node("74b0", ready=False)])
    )

    assert result == {"74a1"}


@pytest.mark.asyncio
async def test_get_cluster_gpu_device_ids_falls_back_to_beta_label():
    result = await get_cluster_gpu_device_ids(make_kube_client([make_node("74a1"), make_node(beta_device_id="74b0")]))

    assert result == {"74a1", "74b0"}


@pytest.mark.asyncio
async def test_get_cluster_gpu_device_ids_propagates_kube_error():
    mock_kube_client = Mock()
    mock_kube_client.core_v1 = Mock()
    mock_kube_client.core_v1.list_node = AsyncMock(side_effect=RuntimeError("kube unavailable"))

    with patch("app.cluster.service.logger") as mock_logger:
        with pytest.raises(RuntimeError, match="kube unavailable"):
            await get_cluster_gpu_device_ids(mock_kube_client)

    mock_logger.exception.assert_called_once()


def _gpu_allocatable(count: int) -> dict:
    return {"amd.com/gpu": str(count)}


@pytest.mark.asyncio
async def test_get_cluster_accelerators_single_node():
    node = make_node(
        "74a1",
        allocatable=_gpu_allocatable(4),
        product_name="AMD_Instinct_MI300X",
        aim_accelerator_labels={"MI300X": "4", "EPYC_ZEN5": "1"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 2
    by_model = {entry.accelerator_model: entry for entry in result}
    assert by_model["MI300X"].accelerator_type == "gpu"
    assert by_model["MI300X"].device_id == "74a1"
    assert by_model["MI300X"].accelerator_vendor == ""
    assert by_model["MI300X"].product_name == "AMD Instinct MI300X"
    assert by_model["MI300X"].allocatable_count == 4
    assert by_model["EPYC_ZEN5"].accelerator_type == "cpu"
    assert by_model["EPYC_ZEN5"].device_id == "EPYC_ZEN5"
    assert by_model["EPYC_ZEN5"].accelerator_vendor == ""
    assert by_model["EPYC_ZEN5"].product_name == ""
    assert by_model["EPYC_ZEN5"].allocatable_count == 1


@pytest.mark.asyncio
async def test_get_cluster_accelerators_maps_radeon_product_name_to_aim_engine_model():
    node = make_node(
        "7551",
        allocatable=_gpu_allocatable(8),
        product_name="AMD_Radeon_AI_PRO_R9700S",
        aim_accelerator_labels={"R9700": "8", "EPYC_ZEN5": "1"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 2
    by_model = {entry.accelerator_model: entry for entry in result}
    assert by_model["R9700"].device_id == "7551"
    assert by_model["R9700"].product_name == "AMD Radeon AI PRO R9700S"


def test_node_aim_gpu_accelerator_model_excludes_cpu_and_scheme_labels():
    node = make_node(
        "7551",
        allocatable=_gpu_allocatable(8),
        aim_accelerator_labels={
            "R9700": "8",
            "EPYC_ZEN5": "1",
            "GPU": "8",
            "CPU": "1",
            "partitioning-scheme.default": "8",
        },
    )
    assert node_aim_gpu_accelerator_model(node) == "R9700"


def test_node_aim_accelerator_model_counts_excludes_non_model_labels():
    node = make_node(
        "74a1",
        aim_accelerator_labels={
            "MI300X": "8",
            "EPYC_ZEN5": "1",
            "GPU": "8",
            "CPU": "1",
            "APU": "2",
            "partitioning-scheme.default": "8",
            "vendor.GPU.AMD": "8",
        },
    )
    assert node_aim_accelerator_model_counts(node) == {"MI300X": 8, "EPYC_ZEN5": 1}


@pytest.mark.asyncio
async def test_get_cluster_accelerators_prefers_labeled_product_name_over_device_id_fallback():
    nodes = [
        make_node("74a1", allocatable=_gpu_allocatable(2), aim_accelerator_labels={"MI300X": "2"}),
        make_node(
            "74a1",
            allocatable=_gpu_allocatable(4),
            product_name="AMD_Instinct_MI300X",
            aim_accelerator_labels={"MI300X": "4"},
        ),
    ]
    result = await get_cluster_accelerators(make_kube_client(nodes))
    assert len(result) == 1
    assert result[0].product_name == "AMD Instinct MI300X"
    assert result[0].allocatable_count == 6


@pytest.mark.asyncio
async def test_get_cluster_accelerators_keeps_labeled_product_name_when_later_node_lacks_label():
    nodes = [
        make_node(
            "74a1",
            allocatable=_gpu_allocatable(2),
            product_name="AMD_Instinct_MI300X",
            aim_accelerator_labels={"MI300X": "2"},
        ),
        make_node("74a1", allocatable=_gpu_allocatable(4), aim_accelerator_labels={"MI300X": "4"}),
    ]
    result = await get_cluster_accelerators(make_kube_client(nodes))
    assert len(result) == 1
    assert result[0].product_name == "AMD Instinct MI300X"
    assert result[0].allocatable_count == 6


@pytest.mark.asyncio
async def test_get_cluster_accelerators_sums_across_nodes():
    nodes = [
        make_node(
            "74a1",
            allocatable=_gpu_allocatable(4),
            product_name="AMD_Instinct_MI300X",
            aim_accelerator_labels={"MI300X": "4"},
        ),
        make_node(
            "74a1",
            allocatable=_gpu_allocatable(8),
            product_name="AMD_Instinct_MI300X",
            aim_accelerator_labels={"MI300X": "8"},
        ),
    ]
    result = await get_cluster_accelerators(make_kube_client(nodes))
    assert len(result) == 1
    assert result[0].allocatable_count == 12


@pytest.mark.asyncio
async def test_get_cluster_accelerators_multiple_device_ids():
    nodes = [
        make_node(
            "74a1",
            allocatable=_gpu_allocatable(2),
            product_name="AMD_Instinct_MI300X",
            aim_accelerator_labels={"MI300X": "2"},
        ),
        make_node(
            "74a9",
            allocatable=_gpu_allocatable(1),
            product_name="AMD_Instinct_MI250X",
            aim_accelerator_labels={"MI250X": "1"},
        ),
    ]
    result = await get_cluster_accelerators(make_kube_client(nodes))
    by_id = {entry.device_id: entry for entry in result}
    assert by_id["74a1"].allocatable_count == 2
    assert by_id["74a9"].allocatable_count == 1


@pytest.mark.asyncio
async def test_get_cluster_accelerators_excludes_not_ready_nodes():
    nodes = [
        make_node(
            "74a1",
            allocatable=_gpu_allocatable(4),
            product_name="AMD_Instinct_MI300X",
            aim_accelerator_labels={"MI300X": "4"},
        ),
        make_node(
            "74b0",
            ready=False,
            allocatable=_gpu_allocatable(8),
            product_name="Other",
            aim_accelerator_labels={"MI300X": "8"},
        ),
    ]
    result = await get_cluster_accelerators(make_kube_client(nodes))
    assert len(result) == 1
    assert result[0].device_id == "74a1"


@pytest.mark.asyncio
async def test_get_cluster_accelerators_no_gpu_label_returns_empty():
    result = await get_cluster_accelerators(make_kube_client([make_node(device_id=None), make_node(device_id=None)]))
    assert result == []


@pytest.mark.asyncio
async def test_get_cluster_accelerators_falls_back_to_beta_device_id():
    node = make_node(
        beta_device_id="74b0",
        allocatable=_gpu_allocatable(2),
        beta_product_name="AMD_GPU",
        aim_accelerator_labels={"MI300X": "2"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 1
    assert result[0].device_id == "74b0"
    assert result[0].product_name == "AMD GPU"


@pytest.mark.asyncio
async def test_get_cluster_accelerators_missing_product_name_is_empty():
    node = make_node("74a1", allocatable=_gpu_allocatable(1), aim_accelerator_labels={"MI300X": "1"})
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert result[0].product_name == ""


@pytest.mark.asyncio
async def test_get_cluster_accelerators_counts_only_amd_gpus_when_nvidia_present():
    allocatable = {"nvidia.com/gpu": "8", "amd.com/gpu": "2"}
    node = make_node(
        "74a1",
        allocatable=allocatable,
        product_name="AMD_Instinct_MI300X",
        aim_accelerator_labels={"MI300X": "2"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 1
    assert result[0].allocatable_count == 2


@pytest.mark.asyncio
async def test_get_cluster_accelerators_zero_allocatable_on_labeled_node():
    node = make_node(
        "74a1",
        allocatable=_gpu_allocatable(0),
        product_name="AMD_Instinct_MI300X",
        aim_accelerator_labels={"MI300X": "0"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 1
    assert result[0].allocatable_count == 0


@pytest.mark.asyncio
async def test_get_cluster_accelerators_falls_back_to_model_when_gpu_labels_missing():
    node = make_node(
        device_id=None,
        allocatable=_gpu_allocatable(4),
        aim_accelerator_labels={"MI300X": "4"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 1
    assert result[0].accelerator_type == "gpu"
    assert result[0].device_id == "MI300X"
    assert result[0].product_name == ""


@pytest.mark.asyncio
async def test_get_cluster_accelerators_infers_apu_accelerator_type():
    node = make_node(device_id=None, aim_accelerator_labels={"APU_STRIX_HALO": "2"})
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 1
    assert result[0].accelerator_type == "apu"
    assert result[0].device_id == "APU_STRIX_HALO"
    assert result[0].product_name == ""


@pytest.mark.asyncio
async def test_get_cluster_accelerators_includes_cpu_family_count_when_model_missing():
    node = make_node(
        "74a1",
        allocatable=_gpu_allocatable(8),
        product_name="AMD_Instinct_MI300X",
        aim_accelerator_labels={"MI300X": "8", "CPU": "112"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    by_model = {entry.accelerator_model: entry for entry in result}
    assert by_model["CPU"].accelerator_type == "cpu"
    assert by_model["CPU"].accelerator_vendor == ""
    assert by_model["CPU"].allocatable_count == 112


@pytest.mark.asyncio
async def test_get_cluster_accelerators_folds_generic_cpu_into_single_known_model():
    nodes = [
        make_node(
            "74a1",
            allocatable=_gpu_allocatable(8),
            product_name="AMD_Instinct_MI300X",
            aim_accelerator_labels={"MI300X": "8", "CPU": "112", "vendor.CPU.AMD": "112", "vendor.GPU.AMD": "8"},
        ),
        make_node(
            allocatable={"cpu": "16"},
            aim_accelerator_labels={"EPYC_ZEN4": "16", "CPU": "16", "vendor.CPU.AMD": "16"},
        ),
    ]
    result = await get_cluster_accelerators(make_kube_client(nodes))
    by_model = {entry.accelerator_model: entry for entry in result}
    assert "CPU" not in by_model
    assert by_model["EPYC_ZEN4"].accelerator_type == "cpu"
    assert by_model["EPYC_ZEN4"].accelerator_vendor == "amd"
    assert by_model["EPYC_ZEN4"].allocatable_count == 128


@pytest.mark.asyncio
async def test_get_cluster_accelerators_classifies_nvidia_model_as_gpu():
    node = make_node(
        allocatable={"nvidia.com/gpu": "8"},
        aim_accelerator_labels={"H100": "8", "GPU": "8", "vendor.GPU.NVIDIA": "8"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 1
    assert result[0].accelerator_type == "gpu"
    assert result[0].accelerator_model == "H100"
    assert result[0].device_id == "H100"
    assert result[0].accelerator_vendor == "nvidia"
    assert result[0].allocatable_count == 8


@pytest.mark.asyncio
async def test_get_cluster_accelerators_returns_cpu_vendor_label():
    node = make_node(
        allocatable={"cpu": "112"},
        aim_accelerator_labels={"CPU": "112", "vendor.CPU.AMD": "112"},
    )
    result = await get_cluster_accelerators(make_kube_client([node]))
    assert len(result) == 1
    assert result[0].accelerator_type == "cpu"
    assert result[0].accelerator_vendor == "amd"


@pytest.mark.asyncio
async def test_get_cluster_accelerators_empty_node_list():
    result = await get_cluster_accelerators(make_kube_client([]))
    assert result == []


@pytest.mark.asyncio
async def test_get_cluster_accelerators_propagates_kube_error():
    mock_kube_client = Mock()
    mock_kube_client.core_v1 = Mock()
    mock_kube_client.core_v1.list_node = AsyncMock(side_effect=RuntimeError("kube unavailable"))

    with patch("app.cluster.service.logger") as mock_logger:
        with pytest.raises(RuntimeError, match="kube unavailable"):
            await get_cluster_accelerators(mock_kube_client)

    mock_logger.exception.assert_called_once()


def _local_queue_list(cluster_queue_name: str) -> dict:
    return {"items": [{"spec": {"clusterQueue": cluster_queue_name}}]}


def _cluster_queue(resources: list[dict]) -> dict:
    return {"spec": {"resourceGroups": [{"flavors": [{"resources": resources}]}]}}


def make_kueue_kube_client(
    local_queues: dict | None = None,
    cluster_queue: dict | None = None,
    list_side_effect: Exception | None = None,
    get_side_effect: Exception | None = None,
) -> Mock:
    mock_kube_client = Mock()
    mock_kube_client.custom_objects = Mock()
    if list_side_effect is not None:
        mock_kube_client.custom_objects.list_namespaced_custom_object = AsyncMock(side_effect=list_side_effect)
    else:
        mock_kube_client.custom_objects.list_namespaced_custom_object = AsyncMock(
            return_value=local_queues or {"items": []}
        )
    if get_side_effect is not None:
        mock_kube_client.custom_objects.get_cluster_custom_object = AsyncMock(side_effect=get_side_effect)
    else:
        mock_kube_client.custom_objects.get_cluster_custom_object = AsyncMock(return_value=cluster_queue or {})
    return mock_kube_client


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_matches_amd_resource():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue([{"name": "amd.com/gpu", "nominalQuota": 4}]),
    )
    result = await get_project_gpu_quota_from_kueue("team-a", kube_client)
    assert result == 4


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_matches_nvidia_resource():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue([{"name": "nvidia.com/gpu", "nominalQuota": 8}]),
    )
    result = await get_project_gpu_quota_from_kueue("team-a", kube_client)
    assert result == 8


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_no_local_queue_in_namespace():
    kube_client = make_kueue_kube_client(local_queues={"items": []})
    result = await get_project_gpu_quota_from_kueue("team-a", kube_client)
    assert result is None


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_no_gpu_resource_in_cluster_queue():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue([{"name": "cpu", "nominalQuota": 100}]),
    )
    result = await get_project_gpu_quota_from_kueue("team-a", kube_client)
    assert result is None


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_returns_none_on_malformed_quota():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue([{"name": "amd.com/gpu", "nominalQuota": "not-a-number"}]),
    )
    result = await get_project_gpu_quota_from_kueue("team-a", kube_client)
    assert result is None


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_returns_none_when_quota_missing():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue([{"name": "amd.com/gpu"}]),
    )
    result = await get_project_gpu_quota_from_kueue("team-a", kube_client)
    assert result is None


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_cluster_queue_not_found():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        get_side_effect=ApiException(status=404, reason="Not Found"),
    )
    result = await get_project_gpu_quota_from_kueue("team-a", kube_client)
    assert result is None


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_returns_none_when_local_queue_api_missing():
    kube_client = make_kueue_kube_client(list_side_effect=ApiException(status=404, reason="Not Found"))
    result = await get_project_gpu_quota_from_kueue("team-a", kube_client)
    assert result is None


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_propagates_list_errors():
    kube_client = make_kueue_kube_client(list_side_effect=ApiException(status=500, reason="Internal Server Error"))
    with patch("app.cluster.service.logger") as mock_logger, pytest.raises(ApiException):
        await get_project_gpu_quota_from_kueue("team-a", kube_client)

    mock_logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_get_project_gpu_quota_from_kueue_propagates_get_errors():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        get_side_effect=ApiException(status=500, reason="Internal Server Error"),
    )
    with patch("app.cluster.service.logger") as mock_logger, pytest.raises(ApiException):
        await get_project_gpu_quota_from_kueue("team-a", kube_client)

    mock_logger.exception.assert_called_once()


# =============================================================================
# get_project_gpu_allocation_ceiling
# =============================================================================


@pytest.mark.asyncio
async def test_get_project_gpu_allocation_ceiling_standalone_uses_cluster_capacity() -> None:
    namespace = Namespace(name="team-a")
    cluster_resources = Mock()
    cluster_resources.data.available_resources.gpu_count = 16

    with (
        patch("app.cluster.service.STANDALONE_MODE", True),
        patch("app.cluster.service.get_cluster_resources", AsyncMock(return_value=cluster_resources)) as mock_cluster,
        patch("app.cluster.service.get_project_gpu_quota_from_kueue", AsyncMock()) as mock_quota,
    ):
        result = await get_project_gpu_allocation_ceiling(namespace, Mock())

    assert result == 16
    mock_cluster.assert_called_once()
    mock_quota.assert_not_called()


@pytest.mark.asyncio
async def test_get_project_gpu_allocation_ceiling_joint_mode_uses_project_quota() -> None:
    namespace = Namespace(name="team-a")
    cluster_resources = Mock()
    cluster_resources.data.available_resources.gpu_count = 16

    with (
        patch("app.cluster.service.STANDALONE_MODE", False),
        patch("app.cluster.service.get_cluster_resources", AsyncMock(return_value=cluster_resources)) as mock_cluster,
        patch("app.cluster.service.get_project_gpu_quota_from_kueue", AsyncMock(return_value=4)) as mock_quota,
    ):
        result = await get_project_gpu_allocation_ceiling(namespace, Mock())

    assert result == 4
    mock_quota.assert_called_once()
    assert mock_quota.call_args.args[0] == "team-a"
    mock_cluster.assert_not_called()


@pytest.mark.asyncio
async def test_get_project_gpu_allocation_ceiling_joint_mode_falls_back_to_cluster_when_quota_is_zero() -> None:
    namespace = Namespace(name="team-a")
    cluster_resources = Mock()
    cluster_resources.data.available_resources.gpu_count = 8

    with (
        patch("app.cluster.service.STANDALONE_MODE", False),
        patch("app.cluster.service.get_cluster_resources", AsyncMock(return_value=cluster_resources)) as mock_cluster,
        patch("app.cluster.service.get_project_gpu_quota_from_kueue", AsyncMock(return_value=0)) as mock_quota,
    ):
        result = await get_project_gpu_allocation_ceiling(namespace, Mock())

    assert result == 8
    mock_quota.assert_called_once()
    mock_cluster.assert_called_once()


@pytest.mark.asyncio
async def test_get_project_gpu_allocation_ceiling_joint_mode_falls_back_to_cluster_without_quota() -> None:
    namespace = Namespace(name="team-a")
    cluster_resources = Mock()
    cluster_resources.data.available_resources.gpu_count = 8

    with (
        patch("app.cluster.service.STANDALONE_MODE", False),
        patch("app.cluster.service.get_cluster_resources", AsyncMock(return_value=cluster_resources)) as mock_cluster,
        patch("app.cluster.service.get_project_gpu_quota_from_kueue", AsyncMock(return_value=None)) as mock_quota,
    ):
        result = await get_project_gpu_allocation_ceiling(namespace, Mock())

    assert result == 8
    mock_quota.assert_called_once()
    mock_cluster.assert_called_once()


@pytest.mark.asyncio
async def test_get_project_gpu_allocation_ceiling_returns_none_on_cluster_error() -> None:
    namespace = Namespace(name="team-a")

    with (
        patch("app.cluster.service.STANDALONE_MODE", True),
        patch(
            "app.cluster.service.get_cluster_resources",
            AsyncMock(side_effect=RuntimeError("kube unavailable")),
        ),
        patch("app.cluster.service.logger") as mock_logger,
    ):
        result = await get_project_gpu_allocation_ceiling(namespace, Mock())

    assert result is None
    mock_logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_get_project_gpu_allocation_ceiling_joint_mode_returns_none_on_quota_error() -> None:
    namespace = Namespace(name="team-a")

    with (
        patch("app.cluster.service.STANDALONE_MODE", False),
        patch(
            "app.cluster.service.get_project_gpu_quota_from_kueue",
            AsyncMock(side_effect=RuntimeError("kube unavailable")),
        ),
        patch("app.cluster.service.logger") as mock_logger,
    ):
        result = await get_project_gpu_allocation_ceiling(namespace, Mock())

    assert result is None
    mock_logger.exception.assert_called_once()


# =============================================================================
# get_project_quota_state
# =============================================================================


def _cluster_queue_with_resources(resources: list[dict]) -> dict:
    return {"spec": {"resourceGroups": [{"flavors": [{"resources": resources}]}]}}


@pytest.mark.asyncio
async def test_get_project_quota_state_no_local_queue_returns_unmanaged():
    kube_client = make_kueue_kube_client(local_queues={"items": []})
    result = await get_project_quota_state("team-a", kube_client)
    assert result.is_quota_managed is False
    assert result.quotas.gpu_count is None
    assert result.quotas.cpu_milli_cores is None
    assert result.quotas.memory_bytes is None
    assert result.quotas.ephemeral_storage_bytes is None


@pytest.mark.asyncio
async def test_get_project_quota_state_returns_all_quota_fields():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue_with_resources(
            [
                {"name": "amd.com/gpu", "nominalQuota": "4"},
                {"name": "cpu", "nominalQuota": "8"},
                {"name": "memory", "nominalQuota": "17179869184"},
                {"name": "ephemeral-storage", "nominalQuota": "0"},
            ]
        ),
    )
    result = await get_project_quota_state("team-a", kube_client)
    assert result.is_quota_managed is True
    assert result.quotas.gpu_count == 4
    assert result.quotas.cpu_milli_cores == 8000
    assert result.quotas.memory_bytes == 17179869184
    assert result.quotas.ephemeral_storage_bytes == 0


@pytest.mark.asyncio
async def test_get_project_quota_state_parses_unit_suffixed_quantities():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue_with_resources(
            [
                {"name": "cpu", "nominalQuota": "500m"},
                {"name": "memory", "nominalQuota": "16Gi"},
                {"name": "ephemeral-storage", "nominalQuota": "10Gi"},
            ]
        ),
    )
    result = await get_project_quota_state("team-a", kube_client)
    assert result.is_quota_managed is True
    assert result.quotas.cpu_milli_cores == 500
    assert result.quotas.memory_bytes == 16 * 1024**3
    assert result.quotas.ephemeral_storage_bytes == 10 * 1024**3


@pytest.mark.asyncio
async def test_get_project_quota_state_gpu_zero_is_quota_managed():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue_with_resources([{"name": "amd.com/gpu", "nominalQuota": "0"}]),
    )
    result = await get_project_quota_state("team-a", kube_client)
    assert result.is_quota_managed is True
    assert result.quotas.gpu_count == 0


@pytest.mark.asyncio
async def test_get_project_quota_state_no_gpu_resource_leaves_gpu_count_none():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue_with_resources([{"name": "cpu", "nominalQuota": "4"}]),
    )
    result = await get_project_quota_state("team-a", kube_client)
    assert result.is_quota_managed is True
    assert result.quotas.gpu_count is None
    assert result.quotas.cpu_milli_cores == 4000


@pytest.mark.asyncio
async def test_get_project_quota_state_nvidia_gpu_resource():
    kube_client = make_kueue_kube_client(
        local_queues=_local_queue_list("team-a"),
        cluster_queue=_cluster_queue_with_resources([{"name": "nvidia.com/gpu", "nominalQuota": "2"}]),
    )
    result = await get_project_quota_state("team-a", kube_client)
    assert result.is_quota_managed is True
    assert result.quotas.gpu_count == 2


@pytest.mark.asyncio
async def test_get_project_quota_state_404_on_local_queues_returns_unmanaged():
    kube_client = make_kueue_kube_client(list_side_effect=ApiException(status=404, reason="Not Found"))
    result = await get_project_quota_state("team-a", kube_client)
    assert result.is_quota_managed is False


@pytest.mark.asyncio
async def test_get_project_quota_state_propagates_list_errors():
    kube_client = make_kueue_kube_client(list_side_effect=ApiException(status=500, reason="Internal Server Error"))
    with patch("app.cluster.service.logger") as mock_logger, pytest.raises(ApiException):
        await get_project_quota_state("team-a", kube_client)
    mock_logger.exception.assert_called_once()
