# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for workloads gateway layer - K8s interaction functions."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from kubernetes.client import ApiException, V1DeleteOptions

from app.workloads.constants import (
    TRAINING_OUTPUT_ANNOTATION,
    WORKLOAD_ID_LABEL,
    WORKLOAD_RESOURCES,
    WORKLOAD_TYPE_LABEL,
)
from app.workloads.enums import TrainingOutput, WorkloadStatus, WorkloadType
from app.workloads.gateway import (
    _workload_from_k8s_resource,
    delete_workload_resources,
    get_finetuning_workloads_annotations,
)


def _get_propagation_policy(body: object) -> str | None:
    """Extract propagation policy from either a V1DeleteOptions object or a dict."""
    if isinstance(body, V1DeleteOptions):
        return body.propagation_policy
    if isinstance(body, dict):
        return body.get("propagation_policy") or body.get("propagationPolicy")
    return None


@pytest.mark.asyncio
async def test_get_finetuning_workloads_annotations_maps_job_annotations() -> None:
    workload_id = uuid4()
    annotations = {
        "example.com/owner": "team-a",
        TRAINING_OUTPUT_ANNOTATION: TrainingOutput.LORA.value,
    }
    jobs = SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    name="fine-tuning-job",
                    labels={WORKLOAD_ID_LABEL: str(workload_id)},
                    annotations=annotations,
                )
            ),
        ]
    )
    kube_client = MagicMock()
    kube_client.batch_v1.list_namespaced_job = AsyncMock(return_value=jobs)

    with patch("app.workloads.gateway.get_kube_client", return_value=kube_client):
        annotations_by_workload = await get_finetuning_workloads_annotations(
            "test-namespace",
            [workload_id, workload_id],
        )

    assert annotations_by_workload == {workload_id: annotations}
    kube_client.batch_v1.list_namespaced_job.assert_awaited_once_with(
        namespace="test-namespace",
        label_selector=(
            f"{WORKLOAD_TYPE_LABEL}={WorkloadType.FINE_TUNING.value},{WORKLOAD_ID_LABEL} in ({workload_id})"
        ),
    )


@pytest.mark.asyncio
async def test_get_finetuning_workloads_annotations_degrades_when_kubernetes_fails() -> None:
    kube_client = MagicMock()
    kube_client.batch_v1.list_namespaced_job = AsyncMock(side_effect=RuntimeError("unavailable"))

    with patch("app.workloads.gateway.get_kube_client", return_value=kube_client):
        assert await get_finetuning_workloads_annotations("test-namespace", [uuid4()]) == {}


@pytest.mark.asyncio
async def test_get_finetuning_workloads_annotations_skips_kubernetes_without_ids() -> None:
    with patch("app.workloads.gateway.get_kube_client") as mock_get_kube_client:
        assert await get_finetuning_workloads_annotations("test-namespace", []) == {}

    mock_get_kube_client.assert_not_called()


def test_workload_from_k8s_resource_reads_annotations() -> None:
    workload_id = uuid4()
    annotations = {TRAINING_OUTPUT_ANNOTATION: TrainingOutput.MERGED.value}
    resource = SimpleNamespace(
        metadata=SimpleNamespace(
            name="fine-tuning-job",
            creation_timestamp=datetime.now(UTC),
            labels={
                WORKLOAD_ID_LABEL: str(workload_id),
            },
            annotations=annotations,
        )
    )

    workload = _workload_from_k8s_resource(resource, WorkloadStatus.RUNNING, "test-namespace")

    assert workload.id == workload_id
    assert workload.annotations == annotations


@pytest.mark.asyncio
async def test_delete_workload_resources_requests_background_propagation() -> None:
    """Deletion must request Background propagation so dependents (e.g., Kueue Workload) cascade."""
    workload_id = str(uuid4())
    namespace = "test-namespace"

    mock_api_resource = MagicMock()
    mock_dynamic_client = MagicMock()
    mock_dynamic_client.resources.get.return_value = mock_api_resource

    with patch("app.workloads.gateway.get_dynamic_client", return_value=mock_dynamic_client):
        await delete_workload_resources(namespace=namespace, workload_id=workload_id)

    assert mock_api_resource.delete.call_count == len(WORKLOAD_RESOURCES)
    for call in mock_api_resource.delete.call_args_list:
        body = call.kwargs.get("body")
        assert body is not None, "delete must be called with a body to control propagation"
        assert _get_propagation_policy(body) == "Background"


@pytest.mark.asyncio
async def test_delete_workload_resources_continues_when_resource_not_found() -> None:
    """A 404 on one resource kind must not stop deletion of the remaining kinds."""
    workload_id = str(uuid4())
    namespace = "test-namespace"

    mock_api_resource = MagicMock()
    mock_api_resource.delete.side_effect = [ApiException(status=404)] + [None] * (len(WORKLOAD_RESOURCES) - 1)
    mock_dynamic_client = MagicMock()
    mock_dynamic_client.resources.get.return_value = mock_api_resource

    with patch("app.workloads.gateway.get_dynamic_client", return_value=mock_dynamic_client):
        await delete_workload_resources(namespace=namespace, workload_id=workload_id)

    assert mock_api_resource.delete.call_count == len(WORKLOAD_RESOURCES)


@pytest.mark.asyncio
async def test_delete_workload_resources_raises_on_non_404_api_error() -> None:
    """Non-404 API errors must surface as RuntimeError so the caller can react."""
    workload_id = str(uuid4())
    namespace = "test-namespace"

    mock_api_resource = MagicMock()
    mock_api_resource.delete.side_effect = ApiException(status=500, reason="Internal Server Error")
    mock_dynamic_client = MagicMock()
    mock_dynamic_client.resources.get.return_value = mock_api_resource

    with (
        patch("app.workloads.gateway.get_dynamic_client", return_value=mock_dynamic_client),
        pytest.raises(RuntimeError),
    ):
        await delete_workload_resources(namespace=namespace, workload_id=workload_id)
