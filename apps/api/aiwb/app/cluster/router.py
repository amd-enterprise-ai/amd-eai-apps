# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Cluster resources router for AIWB API."""

from textwrap import dedent

from fastapi import APIRouter, Depends, status

from api_common.schemas import ListResponse

from ..dispatch.kube_client import KubernetesClient, get_kube_client
from .schemas import AimImageFamily, ClusterAccelerator, ClusterResourcesResponse
from .service import get_aim_image_families, get_cluster_accelerators
from .service import get_cluster_resources as get_cluster_resources_service

router = APIRouter(tags=["Cluster"])


@router.get(
    "/resources",
    response_model=ClusterResourcesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cluster resources",
    response_description="Aggregated capacity across ready nodes.",
    description=dedent("""
        Get available cluster resources including CPU, memory, ephemeral storage, and GPU count.

        This endpoint queries the Kubernetes cluster to determine the total available resources
        across all ready nodes. The resources returned are:

        - **CPU**: Available CPU in milli-cores (1 core = 1000 milli-cores)
        - **Memory**: Available memory in bytes
        - **Ephemeral Storage**: Available ephemeral storage in bytes
        - **GPU Count**: Total number of GPUs available
        - **Total Node Count**: Number of ready nodes in the cluster

        This information can be used by the UI to display resource limits when deploying workloads.
    """),
)
async def get_cluster_resources(
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> ClusterResourcesResponse:
    """Get cluster resource availability."""
    return await get_cluster_resources_service(kube_client)


@router.get(
    "/cluster/aim-images",
    response_model=ListResponse[AimImageFamily],
    status_code=status.HTTP_200_OK,
    summary="List aim-engine container image families",
    response_description="Supported image families and tags for runtime profile selection.",
    description=dedent("""
        Returns aim-engine container image families available for runtime profile
        configuration, including an explicit **Automatic** entry.

        Each family lists its container repository (when applicable) and the
        tags/versions the workbench exposes in image dropdowns. Default base
        image families are selected from detected cluster accelerator labels.
    """),
)
async def list_aim_images(
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> ListResponse[AimImageFamily]:
    """List supported aim-engine image families and tags."""
    return ListResponse(data=await get_aim_image_families(kube_client))


@router.get(
    "/cluster/accelerators",
    response_model=ListResponse[ClusterAccelerator],
    status_code=status.HTTP_200_OK,
    summary="List cluster accelerators",
    response_description="Accelerator products present on ready nodes.",
    description=dedent("""
        Returns accelerator models detected on ready cluster nodes.

        Detection is based on aim-engine accelerator labels
        (``feature.node.kubernetes.io/aim-accelerator.*``). For each model, the
        response includes accelerator type (for example CPU/GPU/APU), acceleratorVendor,
        display name, device identifier, and aggregated allocatable count
        across all ready nodes.

        When GPU ``device-id`` labels are missing, the API falls back to
        ``acceleratorModel``. ``productName`` and ``acceleratorVendor`` are empty when
        labels do not provide values.

        Returns an empty list when no ready nodes carry accelerator model labels.
    """),
)
async def list_cluster_accelerators(
    kube_client: KubernetesClient = Depends(get_kube_client),
) -> ListResponse[ClusterAccelerator]:
    """List accelerator products available in the cluster."""
    accelerators = await get_cluster_accelerators(kube_client)
    return ListResponse(data=accelerators)
