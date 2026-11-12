# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import yaml
from kubernetes.client import ApiException

from app.workloads.constants import (
    CHART_ID_LABEL,
    DATASET_ID_LABEL,
    DISPLAY_NAME_ANNOTATION,
    TRAINING_OUTPUT_ANNOTATION,
    WORKLOAD_ID_LABEL,
    WORKLOAD_TYPE_LABEL,
)
from app.workloads.enums import WorkloadStatus, WorkloadType
from app.workloads.models import Workload
from app.workloads.schemas import WorkloadResourceType
from app.workloads.utils import (
    apply_manifest,
    derive_deployment_status,
    derive_job_status,
    generate_display_name,
    generate_workload_name,
    get_dynamic_client,
    get_resource_type,
    get_workload_host_from_HTTPRoute_manifest,
    get_workload_internal_url,
    pin_jobs_to_gpu_devices,
    sanitize_user_id,
)

from .conftest import apply_test_manifest, make_condition, make_deployment_status, make_job_status


def test_generate_workload_name() -> None:
    """Test workload name generation follows pattern and length constraints."""
    mock_workload = MagicMock(spec=Workload)
    mock_workload.id = uuid4()
    mock_workload.chart.name = "my-test-chart"

    name = generate_workload_name(mock_workload)

    # Should follow pattern: wb-{chart_name}-{timestamp}-{uuid_prefix}
    assert name.startswith("wb-my-test-chart-")
    # Should respect Kubernetes name length limit
    assert len(name) <= 53


def test_generate_workload_name_long_chart_name() -> None:
    """Test workload name generation with very long chart name."""
    mock_workload = MagicMock(spec=Workload)
    mock_workload.id = uuid4()
    # Chart name longer than 33 chars should be truncated
    mock_workload.chart.name = "this-is-a-very-long-chart-name-that-exceeds-the-limit"

    name = generate_workload_name(mock_workload)

    # Should still respect max length
    assert len(name) <= 53
    assert name.startswith("wb-this-is-a-very-long-chart-name-th")


def test_generate_workload_name_with_underscores() -> None:
    """Test workload name generation replaces underscores with dashes."""
    mock_workload = MagicMock(spec=Workload)
    mock_workload.id = uuid4()
    mock_workload.chart.name = "chart_with_underscores"

    name = generate_workload_name(mock_workload)

    # Underscores should be replaced with dashes
    assert "chart-with-underscores" in name
    assert "_" not in name


def test_generate_display_name() -> None:
    """Display name is formed from the chart name and the workload UUID prefix."""
    mock_workload = MagicMock(spec=Workload)
    workload_id = uuid4()
    mock_workload.id = workload_id
    mock_workload.chart.name = "workspace-chart"

    display_name = generate_display_name(mock_workload)

    uuid_prefix = str(workload_id)[:8]
    assert display_name == f"workspace-chart-{uuid_prefix}"


def test_get_workload_internal_url() -> None:
    """Test internal URL generation for workload."""
    url = get_workload_internal_url("test-workload", "test-namespace")

    assert url == "http://test-workload.test-namespace.svc.cluster.local"


def test_get_workload_internal_url_with_special_chars() -> None:
    """Test internal URL generation preserves workload name as-is."""
    url = get_workload_internal_url("wb-chart-12345-ab12", "prod-namespace")

    assert url == "http://wb-chart-12345-ab12.prod-namespace.svc.cluster.local"


def test_get_workload_host_from_HTTPRoute_manifest_success() -> None:
    """Test extracting external URL from HTTPRoute manifest."""
    manifest = """
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: test-route
spec:
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /workloads/abc123
"""
    cluster_host = "https://cluster.example.com"

    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host=cluster_host)

    assert url == "https://cluster.example.com/workloads/abc123"


def test_get_workload_host_from_HTTPRoute_manifest_no_httproute() -> None:
    """Test extracting URL from manifest without HTTPRoute returns None."""
    manifest = """
apiVersion: v1
kind: Service
metadata:
  name: test-service
"""
    cluster_host = "https://cluster.example.com"

    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host=cluster_host)

    assert url is None


def test_get_workload_host_from_HTTPRoute_manifest_no_path_prefix() -> None:
    """Test extracting URL from HTTPRoute without PathPrefix returns None."""
    manifest = """
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: test-route
spec:
  rules:
    - matches:
        - path:
            type: Exact
            value: /exact-path
"""
    cluster_host = "https://cluster.example.com"

    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host=cluster_host)

    assert url is None


def test_get_workload_host_from_HTTPRoute_manifest_no_cluster_host() -> None:
    """Test extracting URL without cluster host returns None."""
    manifest = """
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: test-route
spec:
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /workloads/abc123
"""

    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host="")

    assert url is None


def test_get_workload_host_from_HTTPRoute_manifest_invalid_yaml() -> None:
    """Test extracting URL from invalid YAML returns None."""
    manifest = "invalid: yaml: content: ["

    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host="https://cluster.example.com")

    assert url is None


def test_get_workload_host_from_HTTPRoute_manifest_multiple_documents() -> None:
    """Test extracting URL from manifest with multiple documents."""
    manifest = """
apiVersion: v1
kind: Service
metadata:
  name: test-service
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: test-route
spec:
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api/workloads/xyz789
"""
    cluster_host = "https://cluster.example.com"

    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host=cluster_host)

    assert url == "https://cluster.example.com/api/workloads/xyz789"


def test_sanitize_user_id_basic_email() -> None:
    """Test basic email sanitization replaces @ with dash."""
    result = sanitize_user_id("user@example.com")

    assert result == "user-example-com"


def test_sanitize_user_id_with_dots() -> None:
    """Test sanitization replaces dots with dashes."""
    result = sanitize_user_id("user.name@domain.com")

    assert result == "user-name-domain-com"


def test_sanitize_user_id_with_underscores() -> None:
    """Test sanitization replaces underscores with dashes."""
    result = sanitize_user_id("user_name@example.com")

    assert result == "user-name-example-com"


def test_sanitize_user_id_with_plus() -> None:
    """Test sanitization replaces plus with dash."""
    result = sanitize_user_id("user+tag@example.com")

    assert result == "user-tag-example-com"


def test_sanitize_user_id_mixed_special_chars() -> None:
    """Test sanitization handles multiple special characters."""
    result = sanitize_user_id("user.name+tag@sub_domain.example.com")

    assert result == "user-name-tag-sub-domain-example-com"


def test_sanitize_user_id_uppercase_conversion() -> None:
    """Test sanitization converts to lowercase."""
    result = sanitize_user_id("User.Name@DOMAIN.COM")

    assert result == "user-name-domain-com"


def test_sanitize_user_id_already_sanitized() -> None:
    """Test that already sanitized input is unchanged."""
    result = sanitize_user_id("user-example-com")

    assert result == "user-example-com"


def test_sanitize_user_id_no_special_chars() -> None:
    """Test input with no special characters."""
    result = sanitize_user_id("username")

    assert result == "username"


def test_sanitize_user_id_empty_string() -> None:
    """Test handling of empty string."""
    result = sanitize_user_id("")

    assert result == ""


@pytest.mark.parametrize(
    "input_email,expected_output",
    [
        ("user@example.com", "user-example-com"),
        ("User.Name@DOMAIN.COM", "user-name-domain-com"),
        ("first.last+tag@company.co.uk", "first-last-tag-company-co-uk"),
        ("user_name@sub_domain.example.com", "user-name-sub-domain-example-com"),
        ("admin+test@test.org", "admin-test-test-org"),
        ("simple", "simple"),
        ("", ""),
        ("UPPERCASE@EXAMPLE.COM", "uppercase-example-com"),
        ("user@multiple.sub.domains.com", "user-multiple-sub-domains-com"),
        ("complex.user+tag_test@example.com", "complex-user-tag-test-example-com"),
    ],
)
def test_sanitize_user_id_parametrized(input_email: str, expected_output: str) -> None:
    """Use @pytest.mark.parametrize for various email formats."""
    result = sanitize_user_id(input_email)

    assert result == expected_output


@pytest.mark.asyncio
async def test_apply_manifest_success_single_document() -> None:
    """Test applying manifest with single YAML document."""
    manifest = """
apiVersion: v1
kind: Service
metadata:
  name: test-service
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    # Verify resource was created
    mock_api_resource.create.assert_called_once()
    call_args = mock_api_resource.create.call_args

    # Verify namespace was injected
    assert call_args.kwargs["body"]["metadata"]["namespace"] == "test-namespace"

    # Verify workload ID label was injected
    assert call_args.kwargs["body"]["metadata"]["labels"][WORKLOAD_ID_LABEL] == str(workload.id)

    # Service is not a CRD kind, so should not have chart label
    assert CHART_ID_LABEL not in call_args.kwargs["body"]["metadata"]["labels"]


@pytest.mark.asyncio
async def test_apply_manifest_multiple_documents() -> None:
    """Test applying manifest with multiple YAML documents (separated by '---')."""
    manifest = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
data:
  key: value
---
apiVersion: v1
kind: Service
metadata:
  name: test-service
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    # Verify both resources were created
    assert mock_api_resource.create.call_count == 2


@pytest.mark.asyncio
async def test_apply_manifest_creates_metadata() -> None:
    """Test that metadata section is created when missing."""
    manifest = """
apiVersion: v1
kind: Service
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    # Verify metadata was created
    call_args = mock_api_resource.create.call_args
    assert "metadata" in call_args.kwargs["body"]
    assert call_args.kwargs["body"]["metadata"]["namespace"] == "test-namespace"


@pytest.mark.asyncio
async def test_apply_manifest_injects_namespace() -> None:
    """Test namespace injection overwrites existing namespace."""
    manifest = """
apiVersion: v1
kind: Service
metadata:
  name: test-service
  namespace: old-namespace
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        await apply_manifest(mock_kube_client, manifest, workload, "new-namespace", "test-user@example.com")

    # Verify namespace was overwritten
    call_args = mock_api_resource.create.call_args
    assert call_args.kwargs["body"]["metadata"]["namespace"] == "new-namespace"


@pytest.mark.asyncio
async def test_apply_manifest_injects_workload_label() -> None:
    """Test WORKLOAD_ID_LABEL injected for all resources."""
    manifest = """
apiVersion: v1
kind: Service
metadata:
  name: test-service
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    # Verify workload ID label was injected
    call_args = mock_api_resource.create.call_args
    assert WORKLOAD_ID_LABEL in call_args.kwargs["body"]["metadata"]["labels"]
    assert call_args.kwargs["body"]["metadata"]["labels"][WORKLOAD_ID_LABEL] == str(workload.id)


@pytest.mark.asyncio
async def test_apply_manifest_injects_chart_label_for_crd() -> None:
    """Test CHART_ID_LABEL only injected for primary workload resource kinds."""
    manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-workload
spec:
  replicas: 1
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        await apply_manifest(
            mock_kube_client,
            manifest,
            workload,
            "test-namespace",
            "test-user@example.com",
            extra_annotations={TRAINING_OUTPUT_ANNOTATION: "merged"},
        )

    # Verify chart label was injected for CRD
    call_args = mock_api_resource.create.call_args
    body = call_args.kwargs["body"]
    assert CHART_ID_LABEL in body["metadata"]["labels"]
    assert body["metadata"]["labels"][CHART_ID_LABEL] == str(workload.chart_id)
    assert WORKLOAD_TYPE_LABEL in body["metadata"]["labels"]
    assert DISPLAY_NAME_ANNOTATION in body["metadata"]["annotations"]
    assert body["metadata"]["annotations"][DISPLAY_NAME_ANNOTATION] == workload.display_name
    assert body["metadata"]["annotations"][TRAINING_OUTPUT_ANNOTATION] == "merged"


@pytest.mark.asyncio
async def test_apply_manifest_conditional_dataset_label() -> None:
    """Dataset label is only stamped when a dataset_id is present on the workload."""
    manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-workload
spec:
  replicas: 1
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = uuid4()

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    call_args = mock_api_resource.create.call_args
    assert DATASET_ID_LABEL in call_args.kwargs["body"]["metadata"]["labels"]
    assert call_args.kwargs["body"]["metadata"]["labels"][DATASET_ID_LABEL] == str(workload.dataset_id)


@pytest.mark.asyncio
async def test_apply_manifest_handles_409_conflict() -> None:
    """Test that 409 (resource exists) is handled gracefully."""
    manifest = """
apiVersion: v1
kind: Service
metadata:
  name: test-service
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True

    # Simulate 409 conflict
    conflict_error = ApiException(status=409, reason="Conflict")
    mock_api_resource.create.side_effect = conflict_error

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        # Should not raise exception
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    # Verify create was called
    mock_api_resource.create.assert_called_once()


@pytest.mark.asyncio
async def test_apply_manifest_raises_on_other_api_errors() -> None:
    """Test that non-409 ApiException raises RuntimeError."""
    manifest = """
apiVersion: v1
kind: Service
metadata:
  name: test-service
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True

    # Simulate 403 Forbidden error
    forbidden_error = ApiException(status=403, reason="Forbidden")
    forbidden_error.body = "Access denied"
    mock_api_resource.create.side_effect = forbidden_error

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        with pytest.raises(RuntimeError, match="Failed to create Service/test-service"):
            await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")


@pytest.mark.asyncio
async def test_apply_manifest_invalid_yaml() -> None:
    """Test error handling for malformed YAML."""
    manifest = "invalid: yaml: content: ["

    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        # Invalid YAML should raise exception
        with pytest.raises(Exception):
            await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")


@pytest.mark.asyncio
async def test_apply_manifest_missing_apiversion() -> None:
    """Test handling of documents without apiVersion."""
    manifest = """
kind: Service
metadata:
  name: test-service
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        # Should skip document without apiVersion
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    # Verify create was not called
    mock_api_resource.create.assert_not_called()


@pytest.mark.asyncio
async def test_apply_manifest_missing_kind() -> None:
    """Test handling of documents without kind."""
    manifest = """
apiVersion: v1
metadata:
  name: test-service
spec:
  ports:
    - port: 80
"""
    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        # Should skip document without kind
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    # Verify create was not called
    mock_api_resource.create.assert_not_called()


@pytest.mark.asyncio
async def test_apply_manifest_empty_yaml() -> None:
    """Test handling of empty YAML string."""
    manifest = ""

    workload = MagicMock(spec=Workload)
    workload.id = uuid4()
    workload.chart_id = uuid4()
    workload.type = WorkloadType.INFERENCE
    workload.display_name = "test-workload"
    workload.dataset_id = None

    mock_kube_client = AsyncMock()
    mock_dynamic_client = MagicMock()
    mock_api_resource = MagicMock()

    mock_dynamic_client.resources.get.return_value = mock_api_resource
    mock_api_resource.namespaced = True
    mock_api_resource.create = MagicMock()

    with patch("app.workloads.utils.get_dynamic_client", spec=get_dynamic_client, return_value=mock_dynamic_client):
        # Should handle empty YAML gracefully
        await apply_manifest(mock_kube_client, manifest, workload, "test-namespace", "test-user@example.com")

    # Verify create was not called
    mock_api_resource.create.assert_not_called()


@pytest.mark.asyncio
async def test_apply_manifest_deployment_preserves_existing_template_labels() -> None:
    """Deployment keeps existing pod template labels untouched (Kyverno/AIRM handles workload-id)."""
    manifest = "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: d\nspec:\n  template:\n    metadata:\n      labels:\n        app: test\n    spec:\n      containers:\n        - name: main\n          image: nginx\n"
    [body], workload = await apply_test_manifest(manifest)

    assert body["metadata"]["labels"][WORKLOAD_ID_LABEL] == str(workload.id)
    assert body["spec"]["template"]["metadata"]["labels"]["app"] == "test"
    assert WORKLOAD_ID_LABEL not in body["spec"]["template"]["metadata"]["labels"]


@pytest.mark.asyncio
async def test_apply_manifest_multi_doc_all_get_metadata_labels() -> None:
    """In a multi-doc manifest, all resources get workload-id on metadata.labels."""
    manifest = (
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: c\ndata:\n  k: v\n"
        "---\n"
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: d\nspec:\n  template:\n    metadata:\n      labels:\n        app: test\n    spec:\n      containers:\n        - name: m\n          image: nginx\n"
        "---\n"
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: s\nspec:\n  ports:\n    - port: 80\n"
    )
    bodies, workload = await apply_test_manifest(manifest)

    assert len(bodies) == 3
    for body in bodies:
        assert body["metadata"]["labels"][WORKLOAD_ID_LABEL] == str(workload.id)


def test_generate_workload_name_boundary_length() -> None:
    """Test name generation at exactly 53 character boundary."""
    mock_workload = MagicMock(spec=Workload)
    mock_workload.id = uuid4()
    # Chart name that, when combined with prefix, timestamp, and UUID, should hit exactly 53 chars
    # Pattern: wb-{chart_name}-{timestamp}-{uuid_prefix} (max 53 chars)
    # wb- (3) + chart_name (33) + - (1) + timestamp (10) + - (1) + uuid (4) = 52
    # With a 33-char chart name, we should get exactly 52-53 chars
    mock_workload.chart.name = "a" * 33

    name = generate_workload_name(mock_workload)

    # Should be at or under the 53 character limit
    assert len(name) <= 53
    # Should start with the expected prefix
    assert name.startswith("wb-")
    # Should contain the chart name (truncated to 33 chars)
    assert name[3:36] == "a" * 33


def test_generate_workload_name_empty_chart_name() -> None:
    """Test handling of empty chart name."""
    mock_workload = MagicMock(spec=Workload)
    mock_workload.id = uuid4()
    mock_workload.chart.name = ""

    name = generate_workload_name(mock_workload)

    # Should still generate a valid name
    assert len(name) > 0
    assert len(name) <= 53
    # Pattern should be wb--{timestamp}-{uuid_prefix}
    assert name.startswith("wb--")


def test_get_workload_host_path_value_empty_string() -> None:
    """Test HTTPRoute parsing with empty path value, verify returns None."""
    manifest = """
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: test-route
spec:
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: ""
"""
    cluster_host = "https://cluster.example.com"

    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host=cluster_host)

    # Empty path value should return None
    assert url is None


@pytest.mark.parametrize(
    "conditions, ready_replicas, expected",
    [
        ([make_condition("ReplicaFailure", "True")], None, WorkloadStatus.FAILED),
        ([make_condition("Available", "True")], None, WorkloadStatus.RUNNING),
        ([make_condition("Progressing", "True")], None, WorkloadStatus.PENDING),
        (
            [make_condition("Available", "True"), make_condition("ReplicaFailure", "True")],
            None,
            WorkloadStatus.FAILED,
        ),
        (
            [make_condition("Progressing", "True"), make_condition("Available", "True")],
            None,
            WorkloadStatus.RUNNING,
        ),
        (
            [make_condition("Available", "False"), make_condition("Progressing", "False")],
            3,
            WorkloadStatus.RUNNING,
        ),
        ([make_condition("Available", "False")], 0, WorkloadStatus.PENDING),
        ([make_condition("Available", "False")], None, WorkloadStatus.PENDING),
        (None, 1, WorkloadStatus.RUNNING),
        (None, 0, WorkloadStatus.PENDING),
        (None, None, WorkloadStatus.PENDING),
        ([], None, WorkloadStatus.PENDING),
        ([], 5, WorkloadStatus.RUNNING),
        (
            [make_condition("Progressing", "False", reason="ProgressDeadlineExceeded")],
            None,
            WorkloadStatus.FAILED,
        ),
        (
            [
                make_condition("Available", "True"),
                make_condition("Progressing", "False", reason="ProgressDeadlineExceeded"),
            ],
            None,
            WorkloadStatus.RUNNING,
        ),
    ],
    ids=[
        "replica_failure",
        "available",
        "progressing",
        "replica_failure_beats_available",
        "available_beats_progressing",
        "conditions_false_with_ready_replicas",
        "conditions_false_zero_replicas",
        "conditions_false_none_replicas",
        "no_conditions_ready_replicas",
        "no_conditions_zero_replicas",
        "no_conditions_none_replicas",
        "empty_conditions_none_replicas",
        "empty_conditions_with_replicas",
        "progress_deadline_exceeded",
        "available_beats_progress_deadline",
    ],
)
def test_derive_deployment_status(
    conditions: list[MagicMock] | None,
    ready_replicas: int | None,
    expected: WorkloadStatus,
) -> None:
    assert (
        derive_deployment_status(make_deployment_status(conditions=conditions, ready_replicas=ready_replicas))
        == expected
    )


def test_derive_deployment_status_none() -> None:
    assert derive_deployment_status(None) == WorkloadStatus.PENDING


def test_derive_job_status_none() -> None:
    assert derive_job_status(None) == WorkloadStatus.PENDING


@pytest.mark.parametrize(
    "conditions, active, ready, succeeded, failed, expected",
    [
        ([make_condition("Failed", "True")], None, None, None, None, WorkloadStatus.FAILED),
        ([make_condition("FailureTarget", "True")], None, None, None, None, WorkloadStatus.FAILED),
        ([make_condition("Complete", "True")], None, None, None, None, WorkloadStatus.COMPLETE),
        ([make_condition("Suspended", "True")], None, None, None, None, WorkloadStatus.PENDING),
        (
            [make_condition("Complete", "True"), make_condition("Failed", "True")],
            None,
            None,
            None,
            None,
            WorkloadStatus.FAILED,
        ),
        (
            [make_condition("Suspended", "True"), make_condition("Complete", "True")],
            None,
            None,
            None,
            None,
            WorkloadStatus.COMPLETE,
        ),
        ([make_condition("Failed", "False")], 1, 1, None, None, WorkloadStatus.RUNNING),
        ([make_condition("Failed", "False")], 1, 0, None, None, WorkloadStatus.PENDING),
        ([make_condition("Complete", "False")], None, None, 2, None, WorkloadStatus.COMPLETE),
        ([make_condition("Complete", "False")], None, None, None, 1, WorkloadStatus.FAILED),
        (None, 1, 1, None, None, WorkloadStatus.RUNNING),
        (None, 1, None, None, None, WorkloadStatus.PENDING),
        (None, 1, 0, None, None, WorkloadStatus.PENDING),
        (None, None, None, 1, None, WorkloadStatus.COMPLETE),
        (None, None, None, None, 1, WorkloadStatus.FAILED),
        (None, 2, 2, 1, 1, WorkloadStatus.RUNNING),
        (None, 2, 0, 1, 1, WorkloadStatus.PENDING),
        (None, 0, 0, 0, 0, WorkloadStatus.PENDING),
        (None, None, None, None, None, WorkloadStatus.PENDING),
        ([], None, None, None, None, WorkloadStatus.PENDING),
    ],
    ids=[
        "failed_condition",
        "failure_target_condition",
        "complete_condition",
        "suspended_condition",
        "failed_beats_complete",
        "complete_beats_suspended",
        "condition_false_active_and_ready",
        "condition_false_active_not_ready",
        "condition_false_succeeded_pods",
        "condition_false_failed_pods",
        "no_conditions_active_and_ready",
        "no_conditions_active_ready_none",
        "no_conditions_active_not_ready",
        "no_conditions_succeeded",
        "no_conditions_failed",
        "active_and_ready_beats_succeeded_and_failed",
        "active_not_ready_is_pending",
        "all_counters_zero",
        "all_counters_none",
        "empty_conditions_no_counters",
    ],
)
def test_derive_job_status(
    conditions: list[MagicMock] | None,
    active: int | None,
    ready: int | None,
    succeeded: int | None,
    failed: int | None,
    expected: WorkloadStatus,
) -> None:
    assert (
        derive_job_status(
            make_job_status(conditions=conditions, active=active, ready=ready, succeeded=succeeded, failed=failed)
        )
        == expected
    )


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        pytest.param(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: test\n",
            WorkloadResourceType.DEPLOYMENT,
            id="deployment",
        ),
        pytest.param(
            "apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: test\n",
            WorkloadResourceType.JOB,
            id="job",
        ),
        pytest.param(
            "apiVersion: v1\nkind: Service\nmetadata:\n  name: svc\n---\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: test\n",
            WorkloadResourceType.DEPLOYMENT,
            id="multi_doc_with_deployment",
        ),
    ],
)
def test_get_resource_type(manifest: str, expected: WorkloadResourceType) -> None:
    assert get_resource_type(manifest) == expected


def test_external_url_uses_route_own_hostname() -> None:
    """External URL is built from the route's own spec.hostnames when present."""
    manifest = (
        "apiVersion: gateway.networking.k8s.io/v1\nkind: HTTPRoute\nmetadata:\n  name: r\n"
        "spec:\n  hostnames:\n    - workspaces.example.com\n"
        "  rules:\n    - matches:\n        - path:\n            type: PathPrefix\n            value: /workbench/u/w\n"
    )
    # cluster_host is the workloads host; the route's own hostname must win.
    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host="https://workloads.example.com")
    assert url == "https://workspaces.example.com/workbench/u/w"


def test_external_url_pinned_hostname_keeps_cluster_host_scheme_and_port() -> None:
    """A pinned hostname keeps cluster_host's scheme and port (e.g. local http://...:8080)."""
    manifest = (
        "apiVersion: gateway.networking.k8s.io/v1\nkind: HTTPRoute\nmetadata:\n  name: r\n"
        "spec:\n  hostnames:\n    - workspaces.example.com\n"
        "  rules:\n    - matches:\n        - path:\n            type: PathPrefix\n            value: /workbench/u/w\n"
    )
    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host="http://localhost:8080")
    assert url == "http://workspaces.example.com:8080/workbench/u/w"


def test_external_url_falls_back_to_cluster_host_without_hostnames() -> None:
    """Routes with no hostnames fall back to cluster_host (workloads), preserving old behaviour."""
    manifest = (
        "apiVersion: gateway.networking.k8s.io/v1\nkind: HTTPRoute\nmetadata:\n  name: r\n"
        "spec:\n  rules:\n    - matches:\n        - path:\n            type: PathPrefix\n            value: /demo/abc/v1\n"
    )
    url = get_workload_host_from_HTTPRoute_manifest(manifest=manifest, cluster_host="https://workloads.example.com")
    assert url == "https://workloads.example.com/demo/abc/v1"


def _job_node_selector_terms(manifest: str) -> list[dict]:
    job = next(doc for doc in yaml.safe_load_all(manifest) if doc.get("kind") == "Job")
    affinity = job["spec"]["template"]["spec"]["affinity"]["nodeAffinity"]
    return affinity["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]


def test_pin_jobs_to_gpu_devices_accepts_either_device_id_label() -> None:
    """A node carrying the device ID under the current or the beta label qualifies."""
    manifest = "kind: ConfigMap\nmetadata:\n  name: config\n---\nkind: Job\nspec:\n  template:\n    spec: {}\n"

    pinned = pin_jobs_to_gpu_devices(manifest, ["75a8"])

    assert _job_node_selector_terms(pinned) == [
        {"matchExpressions": [{"key": "amd.com/gpu.device-id", "operator": "In", "values": ["75a8"]}]},
        {"matchExpressions": [{"key": "beta.amd.com/gpu.device-id", "operator": "In", "values": ["75a8"]}]},
    ]
    config_map = next(doc for doc in yaml.safe_load_all(pinned) if doc.get("kind") == "ConfigMap")
    assert config_map == {"kind": "ConfigMap", "metadata": {"name": "config"}}


def test_pin_jobs_to_gpu_devices_keeps_a_node_affinity_the_chart_requires() -> None:
    """Each term the chart already requires must now also match a device ID, rather than being replaced."""
    zone = {"key": "topology.kubernetes.io/zone", "operator": "In", "values": ["zone-a"]}
    job = {
        "kind": "Job",
        "spec": {
            "template": {
                "spec": {
                    "affinity": {
                        "nodeAffinity": {
                            "requiredDuringSchedulingIgnoredDuringExecution": {
                                "nodeSelectorTerms": [{"matchExpressions": [zone]}]
                            }
                        }
                    }
                }
            }
        },
    }

    pinned = pin_jobs_to_gpu_devices(yaml.safe_dump(job), ["74a1"])

    assert [term["matchExpressions"] for term in _job_node_selector_terms(pinned)] == [
        [zone, {"key": "amd.com/gpu.device-id", "operator": "In", "values": ["74a1"]}],
        [zone, {"key": "beta.amd.com/gpu.device-id", "operator": "In", "values": ["74a1"]}],
    ]


@pytest.mark.parametrize(
    "pod_spec",
    [
        "affinity: null",
        "affinity:\n        nodeAffinity: null",
        "affinity:\n        nodeAffinity:\n          requiredDuringSchedulingIgnoredDuringExecution: null",
        (
            "affinity:\n        nodeAffinity:\n          requiredDuringSchedulingIgnoredDuringExecution:\n"
            "            nodeSelectorTerms:\n              - matchExpressions: null"
        ),
    ],
    ids=["affinity", "node-affinity", "required", "match-expressions"],
)
def test_pin_jobs_to_gpu_devices_treats_an_empty_affinity_as_unset(pod_spec: str) -> None:
    """Charts that render an affinity section with no value still get pinned instead of failing the launch."""
    manifest = f"kind: Job\nspec:\n  template:\n    spec:\n      {pod_spec}\n"

    pinned = pin_jobs_to_gpu_devices(manifest, ["75a8"])

    assert _job_node_selector_terms(pinned) == [
        {"matchExpressions": [{"key": "amd.com/gpu.device-id", "operator": "In", "values": ["75a8"]}]},
        {"matchExpressions": [{"key": "beta.amd.com/gpu.device-id", "operator": "In", "values": ["75a8"]}]},
    ]
