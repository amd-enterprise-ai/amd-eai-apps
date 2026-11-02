# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the inference capability router.

These tests verify the HTTP shape of the inference endpoints and confirm
that requests are delegated correctly to the underlying AIM service layer.
Service-layer behavior (deployment, scaling, undeployment, metrics) is
already covered by `tests/aims/test_service.py`; we do not re-test it here.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, MagicMock, patch
from uuid import uuid4

from fastapi import status
from fastapi.testclient import TestClient

from api_common.exceptions import NotFoundException
from app import app  # type: ignore[attr-defined]
from app.aims.crds import AdapterRuntime
from app.aims.enums import AcceleratorType, AdapterMode, AIMModelStatus, AIMServiceStatus
from app.metrics.schemas import MetricsScalar
from app.minio import MinioClient, get_minio_client_optional
from tests.dependency_overrides import (
    BASE_OVERRIDES,
    PROMETHEUS_OVERRIDES,
    SESSION_OVERRIDES,
    override_dependencies,
)
from tests.factory import make_aim_cluster_model, make_aim_cluster_profile, make_aim_service_k8s

_STORAGE_CLIENT = MagicMock(spec=MinioClient)

# ---------------------------------------------------------------------------
# Cluster catalog endpoints
# ---------------------------------------------------------------------------


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_returns_catalog(mock_list: MagicMock) -> None:
    """GET /v1/inference/models returns the base-model catalog as a paginated envelope."""
    mock_list.return_value = [make_aim_cluster_model(as_response=True)]
    with TestClient(app) as client:
        response = client.get("/v1/inference/models")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "data" in body
    assert "pagination" in body
    assert len(body["data"]) == 1
    assert body["pagination"] == {"page": 1, "pageSize": 10, "total": 1}
    # Loose top-level pagination keys must not appear
    assert "total" not in body
    assert "page" not in body
    assert "pageSize" not in body
    assert "totalPages" not in body
    assert "totalPages" not in body["pagination"]
    mock_list.assert_called_once_with(ANY, statuses=None, accelerator_type=None)


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_passes_status_filter(mock_list: MagicMock) -> None:
    """`?statusFilter=Ready&statusFilter=Failed` is forwarded to the underlying service."""
    mock_list.return_value = []
    with TestClient(app) as client:
        response = client.get(
            "/v1/inference/models",
            params=[("statusFilter", "Ready"), ("statusFilter", "Failed")],
        )

    assert response.status_code == status.HTTP_200_OK
    mock_list.assert_called_once_with(
        ANY,
        statuses=[AIMModelStatus.READY, AIMModelStatus.FAILED],
        accelerator_type=None,
    )


@override_dependencies(BASE_OVERRIDES)
def test_list_inference_models_rejects_unknown_status() -> None:
    """Unknown status values are rejected with 422."""
    with TestClient(app) as client:
        response = client.get(
            "/v1/inference/models",
            params={"statusFilter": "NotAStatus"},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_empty_returns_paginated_envelope(mock_list: MagicMock) -> None:
    """Empty catalog returns the nested envelope with zero items and correct metadata."""
    mock_list.return_value = []
    with TestClient(app) as client:
        response = client.get("/v1/inference/models")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["data"] == []
    assert body["pagination"] == {"page": 1, "pageSize": 10, "total": 0}
    assert "total" not in body
    assert "page" not in body
    assert "pageSize" not in body
    assert "totalPages" not in body
    assert "totalPages" not in body["pagination"]


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_uses_default_page_size_of_10(mock_list: MagicMock) -> None:
    """Without query params, default page=1 and pageSize=10 are applied."""
    models = [make_aim_cluster_model(as_response=True, name=f"model-{i}") for i in range(25)]
    mock_list.return_value = models
    with TestClient(app) as client:
        response = client.get("/v1/inference/models")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 10
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 25


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_custom_page_navigation(mock_list: MagicMock) -> None:
    """Page slicing covers the right rows and pagination metadata is consistent."""
    models = [make_aim_cluster_model(as_response=True, name=f"model-{i}") for i in range(15)]
    mock_list.return_value = models
    with TestClient(app) as client:
        first = client.get("/v1/inference/models")
        second = client.get("/v1/inference/models", params={"page": 2, "pageSize": 10})

    assert first.status_code == status.HTTP_200_OK
    first_body = first.json()
    assert len(first_body["data"]) == 10
    assert first_body["pagination"]["page"] == 1
    assert first_body["pagination"]["pageSize"] == 10
    assert first_body["pagination"]["total"] == 15

    assert second.status_code == status.HTTP_200_OK
    second_body = second.json()
    assert len(second_body["data"]) == 5
    assert second_body["pagination"]["page"] == 2
    assert second_body["pagination"]["total"] == 15


@override_dependencies(BASE_OVERRIDES)
def test_list_inference_models_rejects_invalid_page_size() -> None:
    """`pageSize` must be in [1, 100]; values outside the bound are 422."""
    with TestClient(app) as client:
        too_small = client.get("/v1/inference/models", params={"pageSize": 0})
        too_large = client.get("/v1/inference/models", params={"pageSize": 101})

    assert too_small.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert too_large.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_status_filter_applies_before_pagination(mock_list: MagicMock) -> None:
    """When a status filter narrows the set, `total` reflects only the filtered rows.

    The service layer applies the status filter; paginate_list then slices
    only the already-filtered list. Here we return a pre-filtered single model
    to verify the total reflects the filtered count.
    """
    mock_list.return_value = [make_aim_cluster_model(as_response=True, status=AIMModelStatus.READY)]
    with TestClient(app) as client:
        response = client.get(
            "/v1/inference/models",
            params={"statusFilter": "Ready"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["total"] == 1
    mock_list.assert_called_once_with(ANY, statuses=[AIMModelStatus.READY], accelerator_type=None)


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_exposes_discovered_hardware(mock_list: MagicMock) -> None:
    """The catalog payload passes through ``status.discoveredProfiles.byHardware``
    from the engine, no AIWB-side enrichment — so the FE can render
    EPYC-aware tiles by reading accelerator metadata straight off the
    resource."""
    model = make_aim_cluster_model(
        as_response=True,
        accelerator_type="cpu",
        accelerator_model="EPYC_ZEN5",
        accelerator_count=1,
    )
    mock_list.return_value = [model]
    with TestClient(app) as client:
        response = client.get("/v1/inference/models")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    by_hardware = body["data"][0]["status"]["discoveredProfiles"]["byHardware"]
    assert len(by_hardware) == 1
    entry = by_hardware[0]
    assert entry["acceleratorType"] == "cpu"
    assert entry["acceleratorModel"] == "EPYC_ZEN5"
    assert entry["acceleratorCount"] == 1
    assert entry["supported"] is True


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_accelerator_type_filter_forwarded(mock_list: MagicMock) -> None:
    """`?acceleratorType=cpu` flows through to the service layer as a single-element
    list — the wire param is the same; the service now accepts a list."""
    mock_list.return_value = []
    with TestClient(app) as client:
        response = client.get("/v1/inference/models", params={"acceleratorType": "cpu"})

    assert response.status_code == status.HTTP_200_OK
    mock_list.assert_called_once_with(ANY, statuses=None, accelerator_type=[AcceleratorType.CPU])


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_accelerator_type_filter_multivalue_forwarded(mock_list: MagicMock) -> None:
    """`?acceleratorType=cpu&acceleratorType=gpu` flows through as a multi-element
    list so the service can OR the families together."""
    mock_list.return_value = []
    with TestClient(app) as client:
        response = client.get(
            "/v1/inference/models",
            params=[("acceleratorType", "cpu"), ("acceleratorType", "gpu")],
        )

    assert response.status_code == status.HTTP_200_OK
    mock_list.assert_called_once_with(
        ANY,
        statuses=None,
        accelerator_type=[AcceleratorType.CPU, AcceleratorType.GPU],
    )


@override_dependencies(BASE_OVERRIDES)
def test_list_inference_models_rejects_unknown_accelerator_type() -> None:
    """Accelerator values outside the enum are rejected with 422 — keeps the wire
    contract tight rather than silently treating typos as "no filter"."""
    with TestClient(app) as client:
        response = client.get("/v1/inference/models", params={"acceleratorType": "tpu"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aims")
def test_list_inference_models_accelerator_type_filter_excludes_other_types(mock_list: MagicMock) -> None:
    """When the service returns only the CPU-matching subset, the response carries
    just those models — confirming the filter narrows the catalog rather than
    flagging the rejected entries."""
    cpu_model = make_aim_cluster_model(
        as_response=True,
        name="cpu-aim",
        accelerator_type="cpu",
        accelerator_model="EPYC_ZEN5",
    )
    mock_list.return_value = [cpu_model]

    with TestClient(app) as client:
        response = client.get("/v1/inference/models", params={"acceleratorType": "cpu"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    by_hardware = body["data"][0]["status"]["discoveredProfiles"]["byHardware"]
    assert [h["acceleratorType"] for h in by_hardware] == ["cpu"]


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.get_aim_by_resource_name")
def test_get_inference_model_returns_single_model(mock_get: MagicMock) -> None:
    """GET /v1/inference/models/{name} returns one base model."""
    mock_get.return_value = make_aim_cluster_model(as_response=True, name="llama3-8b")
    with TestClient(app) as client:
        response = client.get("/v1/inference/models/llama3-8b")

    assert response.status_code == status.HTTP_200_OK
    mock_get.assert_called_once_with(ANY, "llama3-8b")


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.get_aim_by_resource_name")
def test_get_inference_model_returns_404_when_missing(mock_get: MagicMock) -> None:
    """GET /v1/inference/models/{name} returns 404 when not found."""
    mock_get.side_effect = NotFoundException("not found")
    with TestClient(app) as client:
        response = client.get("/v1/inference/models/missing-model")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_cluster_profiles")
def test_list_inference_profiles_filters_by_aim_id(mock_list: MagicMock) -> None:
    """GET /v1/inference/profiles?aimId=... narrows the result to one model."""
    mock_list.return_value = [make_aim_cluster_profile()]
    with TestClient(app) as client:
        response = client.get("/v1/inference/profiles", params={"aimId": "org/llama3-8b"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["pagination"] == {"page": 1, "pageSize": 10, "total": 1}
    mock_list.assert_called_once_with(ANY, aim_ids=["org/llama3-8b"])


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_cluster_profiles")
def test_list_inference_profiles_batches_multiple_aim_ids(mock_list: MagicMock) -> None:
    """Repeating ?aimId=... batches multiple models into one call."""
    mock_list.return_value = [make_aim_cluster_profile() for _ in range(2)]
    with TestClient(app) as client:
        # httpx encodes a list value as repeated params, matching the wire format.
        response = client.get(
            "/v1/inference/profiles",
            params=[("aimId", "org/llama3-8b"), ("aimId", "org/mistral-7b")],
        )

    assert response.status_code == status.HTTP_200_OK
    mock_list.assert_called_once_with(ANY, aim_ids=["org/llama3-8b", "org/mistral-7b"])


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_cluster_profiles")
def test_list_inference_profiles_rejects_empty_aim_id(mock_list: MagicMock) -> None:
    """Empty ?aimId= is rejected with 422 by the schema's per-item min_length=1."""
    with TestClient(app) as client:
        response = client.get("/v1/inference/profiles", params={"aimId": ""})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_list.assert_not_called()


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_cluster_profiles")
def test_list_inference_profiles_rejects_too_many_aim_ids(mock_list: MagicMock) -> None:
    """More than max_length aimId values → 422."""
    with TestClient(app) as client:
        response = client.get(
            "/v1/inference/profiles",
            params=[("aimId", f"org/m{i}") for i in range(51)],
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    mock_list.assert_not_called()


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_cluster_profiles")
def test_list_inference_profiles_accepts_max_aim_ids(mock_list: MagicMock) -> None:
    """Exactly max_length aimId values are accepted (boundary)."""
    mock_list.return_value = []
    aim_ids = [f"org/m{i}" for i in range(50)]
    with TestClient(app) as client:
        response = client.get(
            "/v1/inference/profiles",
            params=[("aimId", a) for a in aim_ids],
        )

    assert response.status_code == status.HTTP_200_OK
    mock_list.assert_called_once_with(ANY, aim_ids=aim_ids)


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_cluster_profiles")
def test_list_inference_profiles_no_filter_returns_all_paginated(mock_list: MagicMock) -> None:
    """Without aimId the full catalog is returned (paginated)."""
    mock_list.return_value = [make_aim_cluster_profile() for _ in range(3)]
    with TestClient(app) as client:
        response = client.get("/v1/inference/profiles")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 3
    assert body["pagination"]["total"] == 3
    mock_list.assert_called_once_with(ANY, aim_ids=None)


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_cluster_profiles")
def test_list_inference_profiles_empty_returns_200(mock_list: MagicMock) -> None:
    """No matching profiles returns 200 + empty data, not 404."""
    mock_list.return_value = []
    with TestClient(app) as client:
        response = client.get("/v1/inference/profiles", params={"aimId": "org/unknown"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_cluster_profiles")
def test_list_inference_profiles_pagination(mock_list: MagicMock) -> None:
    """Pagination slices the list and reports correct totals."""
    mock_list.return_value = [make_aim_cluster_profile() for _ in range(5)]
    with TestClient(app) as client:
        response = client.get("/v1/inference/profiles", params={"page": 2, "pageSize": 2})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"] == {"page": 2, "pageSize": 2, "total": 5}


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.get_aim_cluster_profile")
def test_get_inference_profile_by_name(mock_get: MagicMock) -> None:
    """GET /v1/inference/profiles/{name} returns the single matching profile."""
    profile = make_aim_cluster_profile(name="profile-x", aim_id="org/llama3-8b")
    mock_get.return_value = profile
    with TestClient(app) as client:
        response = client.get("/v1/inference/profiles/profile-x")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["metadata"]["name"] == "profile-x"
    mock_get.assert_called_once_with(ANY, "profile-x")


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.get_aim_cluster_profile")
def test_get_inference_profile_by_name_404(mock_get: MagicMock) -> None:
    """Unknown profile name returns 404."""
    mock_get.side_effect = NotFoundException("AIMClusterProfile 'missing' not found")
    with TestClient(app) as client:
        response = client.get("/v1/inference/profiles/missing")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.deploy_aim")
def test_deploy_inference_returns_202(mock_deploy: MagicMock) -> None:
    """POST /v1/projects/{project}/inference returns 202 with the deployment."""
    mock_deploy.return_value = make_aim_service_k8s(as_response=True)
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/test-namespace/inference",
            json={"model": "meta-llama-3-8b"},
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    mock_deploy.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.deploy_aim")
def test_deploy_inference_rejects_snake_case_field_names(mock_deploy: MagicMock) -> None:
    """Inference deploy must reject snake_case fields; only camelCase is accepted."""
    mock_deploy.return_value = make_aim_service_k8s(as_response=True)
    with TestClient(app) as client:
        snake_resp = client.post(
            "/v1/projects/test-ns/inference",
            json={
                "model": "llama3-8b",
                "hf_token": "secret-xyz",
                "min_replicas": 2,
                "max_replicas": 10,
                "auto_scaling": {"metrics": []},
            },
        )
        camel_resp = client.post(
            "/v1/projects/test-ns/inference",
            json={
                "model": "llama3-8b",
                "hfToken": "secret-xyz",
                "minReplicas": 2,
                "maxReplicas": 10,
                "autoScaling": {"metrics": []},
            },
        )

    assert snake_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert camel_resp.status_code == status.HTTP_202_ACCEPTED


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.deploy_aim")
def test_deploy_inference_accepts_engine_env_name_value_entries(mock_deploy: MagicMock) -> None:
    """engineEnv uses name/value entries so env var names may contain underscores."""
    mock_deploy.return_value = make_aim_service_k8s(as_response=True)
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/test-ns/inference",
            json={
                "model": "llama3-8b",
                "engineEnv": [{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}],
            },
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    mock_deploy.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.deploy_aim", autospec=True)
def test_deploy_inference_passes_max_lora_rank_to_the_service(mock_deploy: MagicMock) -> None:
    mock_deploy.return_value = make_aim_service_k8s(as_response=True)
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/test-ns/inference",
            json={
                "model": "llama3-8b",
                "adapterMode": "dynamic",
                "maxLoraRank": 32,
            },
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert mock_deploy.call_args.kwargs["deploy_request"].max_lora_rank == 32


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.deploy_aim", autospec=True)
def test_deploy_inference_rejects_max_lora_rank_as_an_engine_arg(mock_deploy: MagicMock) -> None:
    """Callers reaching for the vLLM flag name are pointed at the supported field and its ranks."""
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/test-ns/inference",
            json={
                "model": "llama3-8b",
                "adapterMode": "dynamic",
                "engineArgs": {"max-lora-rank": 32},
            },
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "maxLoraRank" in response.text
    assert "512" in response.text
    mock_deploy.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.deploy_aim", autospec=True)
def test_deploy_inference_rejects_max_lora_rank_without_dynamic_adapter_mode(mock_deploy: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/test-ns/inference",
            json={"model": "llama3-8b", "maxLoraRank": 32},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "maxLoraRank" in response.text
    assert "dynamic" in response.text
    mock_deploy.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.deploy_aim", autospec=True)
def test_deploy_inference_rejects_a_fractional_max_lora_rank(mock_deploy: MagicMock) -> None:
    """A JSON number that happens to be whole (``32.0``) is still not an integer, and would
    otherwise be coerced onto rank 32 without the caller ever having asked for it."""
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/test-ns/inference",
            json={"model": "llama3-8b", "adapterMode": "dynamic", "maxLoraRank": 32.0},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "maxLoraRank" in response.text
    mock_deploy.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.deploy_aim", autospec=True)
def test_deploy_inference_rejects_unsupported_max_lora_rank(mock_deploy: MagicMock) -> None:
    """The refusal names the field and the ranks it accepts, so the caller can correct it."""
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/test-ns/inference",
            json={"model": "llama3-8b", "adapterMode": "dynamic", "maxLoraRank": 33},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "maxLoraRank" in response.text
    assert "512" in response.text
    mock_deploy.assert_not_called()


@override_dependencies({**SESSION_OVERRIDES, get_minio_client_optional: lambda: _STORAGE_CLIENT})
@patch("app.inference.router.deploy_aim")
def test_deploy_inference_passes_adapters_and_storage_client_to_the_service(mock_deploy: MagicMock) -> None:
    """Adapters reach the service alongside the storage client its readiness check needs; without
    the client threaded through, that check would silently never run."""
    mock_deploy.return_value = make_aim_service_k8s(as_response=True)
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/test-ns/inference",
            json={"model": "llama3-8b", "adapters": ["my-adapter"], "adapterMode": "dynamic"},
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    kwargs = mock_deploy.call_args.kwargs
    assert kwargs["deploy_request"].adapters == ["my-adapter"]
    assert kwargs["deploy_request"].adapter_mode is AdapterMode.DYNAMIC
    assert kwargs["minio_client"] is _STORAGE_CLIENT


# ---------------------------------------------------------------------------
# List with capability filter
# ---------------------------------------------------------------------------


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_without_filter(mock_list: MagicMock) -> None:
    """GET /v1/projects/{project}/inference returns all deployments by default."""
    mock_list.return_value = [make_aim_service_k8s(as_response=True)]
    with TestClient(app) as client:
        response = client.get("/v1/projects/test-namespace/inference")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["total"] == 1
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    # Nested pagination envelope must not leak loose top-level keys.
    assert "total" not in body
    assert "page" not in body
    assert "pageSize" not in body
    assert "totalPages" not in body
    assert "totalPages" not in body["pagination"]
    mock_list.assert_called_once_with(ANY, "test-namespace", status_filter=None)


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_passes_status_filter(mock_list: MagicMock) -> None:
    """`?statusFilter=Running` is forwarded to the underlying service."""
    mock_list.return_value = []
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"statusFilter": "Running"},
        )

    assert response.status_code == status.HTTP_200_OK
    mock_list.assert_called_once_with(
        ANY,
        "test-namespace",
        status_filter=[AIMServiceStatus.RUNNING],
    )


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_chattable_aim_services")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_capability_chat_routes_to_chattable(
    mock_list_all: MagicMock,
    mock_list_chattable: MagicMock,
) -> None:
    """`?capability=chat` switches to the chattable lookup."""
    mock_list_chattable.return_value = [make_aim_service_k8s(as_response=True)]
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"capability": "chat"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["total"] == 1
    mock_list_chattable.assert_called_once_with(ANY, "test-namespace")
    mock_list_all.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_chattable_aim_services")
@patch("app.inference.service.aims_service.list_transcribable_aim_services")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_capability_transcription_routes_to_transcribable(
    mock_list_all: MagicMock,
    mock_list_transcribable: MagicMock,
    mock_list_chattable: MagicMock,
) -> None:
    """`?capability=transcription` uses the transcription lookup, not the chat one."""
    mock_list_transcribable.return_value = [make_aim_service_k8s(as_response=True)]
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"capability": "transcription"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["total"] == 1
    mock_list_transcribable.assert_called_once_with(ANY, "test-namespace")
    mock_list_chattable.assert_not_called()
    mock_list_all.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
def test_list_inference_deployments_rejects_unknown_capability() -> None:
    """Unknown capability values are rejected with 422."""
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"capability": "unsupported"},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_chattable_aim_services")
def test_list_inference_deployments_chat_filter_applies_status_filter_in_python(
    mock_list_chattable: MagicMock,
) -> None:
    """Status filter still applies on top of the chat capability."""
    running = make_aim_service_k8s(as_response=True, status=AIMServiceStatus.RUNNING)
    failed = make_aim_service_k8s(as_response=True, status=AIMServiceStatus.FAILED)
    mock_list_chattable.return_value = [running, failed]

    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"capability": "chat", "statusFilter": "Running"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    # total reflects the filtered set, not the raw K8s response (2 services).
    assert body["pagination"]["total"] == 1


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_transcribable_aim_services")
def test_list_inference_deployments_transcription_filter_applies_status_filter_in_python(
    mock_list_transcribable: MagicMock,
) -> None:
    """Status filter still applies on top of the transcription capability."""
    running = make_aim_service_k8s(as_response=True, status=AIMServiceStatus.RUNNING)
    failed = make_aim_service_k8s(as_response=True, status=AIMServiceStatus.FAILED)
    mock_list_transcribable.return_value = [running, failed]

    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"capability": "transcription", "statusFilter": "Running"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    # total reflects the filtered set, not the raw K8s response (2 services).
    assert body["pagination"]["total"] == 1


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_paginates_results(mock_list: MagicMock) -> None:
    """Page slicing covers the right rows and pagination metadata is consistent."""
    mock_list.return_value = [make_aim_service_k8s(as_response=True) for _ in range(15)]
    with TestClient(app) as client:
        first = client.get("/v1/projects/test-namespace/inference")
        second = client.get(
            "/v1/projects/test-namespace/inference",
            params={"page": 2, "pageSize": 10},
        )

    assert first.status_code == status.HTTP_200_OK
    first_body = first.json()
    assert len(first_body["data"]) == 10
    assert first_body["pagination"]["page"] == 1
    assert first_body["pagination"]["pageSize"] == 10
    assert first_body["pagination"]["total"] == 15

    assert second.status_code == status.HTTP_200_OK
    second_body = second.json()
    assert len(second_body["data"]) == 5
    assert second_body["pagination"]["page"] == 2
    assert second_body["pagination"]["total"] == 15


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_uses_default_page_size_of_10(mock_list: MagicMock) -> None:
    """Without query params, the endpoint returns 10 items on page 1."""
    mock_list.return_value = [make_aim_service_k8s(as_response=True) for _ in range(25)]
    with TestClient(app) as client:
        response = client.get("/v1/projects/test-namespace/inference")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 10
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 25


@override_dependencies(SESSION_OVERRIDES)
def test_list_inference_deployments_rejects_invalid_page_size() -> None:
    """`pageSize` must be in [1, 100]; values outside the bound are 422."""
    with TestClient(app) as client:
        too_small = client.get(
            "/v1/projects/test-namespace/inference",
            params={"pageSize": 0},
        )
        too_large = client.get(
            "/v1/projects/test-namespace/inference",
            params={"pageSize": 101},
        )

    assert too_small.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert too_large.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_service.list_chattable_aim_services")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_pagination_composes_with_capability_chat(
    mock_list_all: MagicMock,
    mock_list_chattable: MagicMock,
) -> None:
    """Pagination slices the chattable list, not the unfiltered one."""
    mock_list_chattable.return_value = [make_aim_service_k8s(as_response=True) for _ in range(12)]
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"capability": "chat", "page": 2, "pageSize": 5},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 5
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["pageSize"] == 5
    assert body["pagination"]["total"] == 12
    mock_list_chattable.assert_called_once_with(ANY, "test-namespace")
    mock_list_all.assert_not_called()


# ---------------------------------------------------------------------------
# Historical (DB-persisted) deployments via statusFilter=Deleted
# ---------------------------------------------------------------------------


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_repository.list_aim_services_history")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_status_filter_deleted_returns_db_history(
    mock_list_live: MagicMock, mock_list_history: MagicMock
) -> None:
    """`?statusFilter=Deleted` surfaces DB history rows (live K8s never sets DELETED)."""
    deleted_id = uuid4()
    history_row = MagicMock(
        id=deleted_id,
        namespace="test-namespace",
        model="llama3-8b",
        status=AIMServiceStatus.DELETED.value,
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        created_by=None,
    )
    mock_list_history.return_value = [history_row]
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"statusFilter": "Deleted"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert len(body["data"]) == 1
    deleted_entry = body["data"][0]
    assert deleted_entry["statusValue"] == AIMServiceStatus.DELETED.value
    assert deleted_entry["id"] == str(deleted_id)
    assert deleted_entry["spec"]["model"]["name"] == "llama3-8b"
    assert deleted_entry["endpoints"] == {}
    # DELETED is API-only, so the live K8s call is skipped entirely.
    mock_list_live.assert_not_called()
    mock_list_history.assert_called_once_with(ANY, namespace="test-namespace", status=AIMServiceStatus.DELETED)


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_repository.list_aim_services_history")
@patch("app.inference.service.aims_service.list_chattable_aim_services")
def test_list_inference_deployments_capability_with_deleted_only_skips_live(
    mock_list_chattable: MagicMock, mock_list_history: MagicMock
) -> None:
    """`?capability=chat&statusFilter=Deleted` must not return live services.

    A Deleted-only filter selects API-only history rows; the capability-specific
    live lookup must be short-circuited so no live (chattable) services leak in.
    """
    deleted_id = uuid4()
    history_row = MagicMock(
        id=deleted_id,
        namespace="test-namespace",
        model="whisper",
        status=AIMServiceStatus.DELETED.value,
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        created_by=None,
    )
    mock_list_history.return_value = [history_row]
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"capability": "chat", "statusFilter": "Deleted"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["statusValue"] == AIMServiceStatus.DELETED.value
    # The Deleted-only guard must short-circuit before the capability lister.
    mock_list_chattable.assert_not_called()
    mock_list_history.assert_called_once()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_repository.list_aim_services_history")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_status_filter_deleted_carries_submitter_annotation(
    mock_list_live: MagicMock, mock_list_history: MagicMock
) -> None:
    """Deleted history rows expose `created_by` via the submitter annotation.

    The UI "Created by" field on the AIM detail page reads
    ``metadata.annotations["airm.silogen.ai/submitter"]``. Without this
    annotation, deleted entries display blank instead of the original
    submitter — a behavioral regression vs. the legacy history endpoint.
    """
    history_row = MagicMock(
        id=uuid4(),
        namespace="test-namespace",
        model="llama3-8b",
        status=AIMServiceStatus.DELETED.value,
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        created_by="alice@example.com",
    )
    mock_list_history.return_value = [history_row]
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"statusFilter": "Deleted"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    annotations = body["data"][0]["metadata"]["annotations"]
    assert annotations["airm.silogen.ai/submitter"] == "alice@example.com"
    mock_list_live.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_repository.list_aim_services_history")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_status_filter_deleted_omits_submitter_when_unknown(
    mock_list_live: MagicMock, mock_list_history: MagicMock
) -> None:
    """Legacy rows with NULL `created_by` omit the annotation rather than emit an empty string."""
    history_row = MagicMock(
        id=uuid4(),
        namespace="test-namespace",
        model="llama3-8b",
        status=AIMServiceStatus.DELETED.value,
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        created_by=None,
    )
    mock_list_history.return_value = [history_row]
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"statusFilter": "Deleted"},
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    annotations = body["data"][0]["metadata"]["annotations"]
    assert "airm.silogen.ai/submitter" not in annotations
    mock_list_live.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_repository.list_aim_services_history")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_without_deleted_filter_skips_db(
    mock_list_live: MagicMock, mock_list_history: MagicMock
) -> None:
    """Without `Deleted` in the filter, the DB history lookup is never performed."""
    mock_list_live.return_value = [make_aim_service_k8s(as_response=True)]
    with TestClient(app) as client:
        response = client.get("/v1/projects/test-namespace/inference")

    assert response.status_code == status.HTTP_200_OK
    mock_list_live.assert_called_once()
    mock_list_history.assert_not_called()


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_repository.list_aim_services_history")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_status_filter_deleted_scopes_db_to_project(
    mock_list_live: MagicMock, mock_list_history: MagicMock
) -> None:
    """The DB history query is scoped to the authorized project — no cross-project leak."""
    mock_list_history.return_value = []
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params={"statusFilter": "Deleted"},
        )

    assert response.status_code == status.HTTP_200_OK
    mock_list_live.assert_not_called()
    mock_list_history.assert_called_once_with(ANY, namespace="test-namespace", status=AIMServiceStatus.DELETED)


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.service.aims_repository.list_aim_services_history")
@patch("app.inference.service.aims_service.list_aim_services")
def test_list_inference_deployments_mixed_live_and_deleted_filter_merges(
    mock_list_live: MagicMock, mock_list_history: MagicMock
) -> None:
    """`?statusFilter=Running&statusFilter=Deleted` returns live Running + DB Deleted rows."""
    mock_list_live.return_value = [make_aim_service_k8s(as_response=True, status=AIMServiceStatus.RUNNING)]
    deleted_id = uuid4()
    history_row = MagicMock(
        id=deleted_id,
        namespace="test-namespace",
        model="llama3-8b",
        status=AIMServiceStatus.DELETED.value,
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        created_by=None,
    )
    mock_list_history.return_value = [history_row]
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/test-namespace/inference",
            params=[("statusFilter", "Running"), ("statusFilter", "Deleted")],
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["pagination"]["total"] == 2
    statuses = {entry["statusValue"] for entry in body["data"]}
    assert statuses == {AIMServiceStatus.RUNNING.value, AIMServiceStatus.DELETED.value}
    # Live call must strip DELETED from the filter (K8s would never return it).
    mock_list_live.assert_called_once_with(ANY, "test-namespace", status_filter=[AIMServiceStatus.RUNNING])
    mock_list_history.assert_called_once()


# ---------------------------------------------------------------------------
# Get one deployment (the chat-bypass endpoint)
# ---------------------------------------------------------------------------


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.get_aim_service")
def test_get_inference_deployment_returns_endpoints(mock_get: MagicMock) -> None:
    """GET /{id} returns the deployment with computed endpoints used by chat bypass."""
    mock_get.return_value = make_aim_service_k8s(as_response=True)
    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-namespace/inference/{uuid4()}")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    # `endpoints` is a computed field on AIMServiceResponse — must be present
    # (possibly empty) for the chat-bypass client to inspect `endpoints.internal`.
    assert "endpoints" in body


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.get_aim_service")
def test_get_inference_deployment_echoes_engine_args_verbatim(mock_get: MagicMock) -> None:
    """Readback is pure passthrough — engine args are echoed as stored, whatever their keys."""
    deployment = make_aim_service_k8s(as_response=True)
    deployment.spec.profile_overrides = {"engineArgs": {"max-lora-rank": 32}}
    mock_get.return_value = deployment

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-namespace/inference/{uuid4()}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["spec"]["profileOverrides"]["engineArgs"]["max-lora-rank"] == 32


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.get_aim_service", autospec=True)
def test_get_inference_deployment_surfaces_adapter_runtime_max_rank(mock_get: MagicMock) -> None:
    deployment = make_aim_service_k8s(as_response=True)
    deployment.spec.adapter_runtime = AdapterRuntime(max_rank=32)
    mock_get.return_value = deployment

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-namespace/inference/{uuid4()}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["spec"]["adapterRuntime"]["maxRank"] == 32


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.get_aim_service")
def test_get_inference_deployment_returns_404_when_missing(mock_get: MagicMock) -> None:
    """GET /{id} returns 404 when the deployment is not found."""
    mock_get.side_effect = NotFoundException("not found")
    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-namespace/inference/{uuid4()}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Patch (scaling policy)
# ---------------------------------------------------------------------------


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.service.aims_service.update_aim_service_spec")
def test_patch_inference_scaling_policy(mock_update: MagicMock) -> None:
    """A scaling-only request goes down the same path as any other spec change, and leaves the
    adapter set alone rather than being read as a request to detach everything."""
    mock_update.return_value = make_aim_service_k8s(min_replicas=2, max_replicas=10, as_response=True)
    deployment_id = uuid4()
    with TestClient(app) as client:
        response = client.patch(
            f"/v1/projects/test-namespace/inference/{deployment_id}",
            json={"minReplicas": 2, "maxReplicas": 10, "autoScaling": {"metrics": []}},
        )

    assert response.status_code == status.HTTP_200_OK
    mock_update.assert_called_once()
    kwargs = mock_update.call_args.kwargs
    assert kwargs["adapters"] is None
    scaling = kwargs["scaling"]
    assert (scaling.min_replicas, scaling.max_replicas, scaling.auto_scaling) == (2, 10, {"metrics": []})


@override_dependencies(BASE_OVERRIDES)
def test_patch_inference_without_fields_returns_400() -> None:
    """PATCH with an empty body returns 400 — no fields to update."""
    with TestClient(app) as client:
        response = client.patch(
            f"/v1/projects/test-namespace/inference/{uuid4()}",
            json={},
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_dependencies({**BASE_OVERRIDES, get_minio_client_optional: lambda: _STORAGE_CLIENT})
@patch("app.inference.service.aims_service.update_aim_service_spec")
def test_patch_inference_adapters(mock_update: MagicMock) -> None:
    """Adapters reach the service alongside the storage client its readiness check needs; without
    the client threaded through, that check would silently never run."""
    mock_update.return_value = make_aim_service_k8s(as_response=True)
    deployment_id = uuid4()
    with TestClient(app) as client:
        response = client.patch(
            f"/v1/projects/test-namespace/inference/{deployment_id}",
            json={"adapters": ["my-adapter"]},
        )

    assert response.status_code == status.HTTP_200_OK
    kwargs = mock_update.call_args.kwargs
    assert kwargs["adapters"] == ["my-adapter"]
    assert kwargs["scaling"] is None
    assert kwargs["id"] == deployment_id
    assert kwargs["minio_client"] is _STORAGE_CLIENT


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.service.aims_service.update_aim_service_spec")
def test_patch_inference_detaching_all_adapters_reaches_the_service(mock_update: MagicMock) -> None:
    """An empty list is a real instruction (detach everything), not an omitted field."""
    mock_update.return_value = make_aim_service_k8s(as_response=True)
    with TestClient(app) as client:
        response = client.patch(
            f"/v1/projects/test-namespace/inference/{uuid4()}",
            json={"adapters": []},
        )

    assert response.status_code == status.HTTP_200_OK
    assert mock_update.call_args.kwargs["adapters"] == []
    assert mock_update.call_args.kwargs["scaling"] is None


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.service.aims_service.update_aim_service_spec")
def test_patch_inference_changes_adapters_and_scaling_in_one_request(mock_update: MagicMock) -> None:
    """Both changes go out as one spec update rather than one call each, so a caller can never be
    left with half of what they asked for."""
    mock_update.return_value = make_aim_service_k8s(as_response=True)
    with TestClient(app) as client:
        response = client.patch(
            f"/v1/projects/test-namespace/inference/{uuid4()}",
            json={
                "adapters": ["my-adapter"],
                "minReplicas": 2,
                "maxReplicas": 10,
                "autoScaling": {"metrics": [{"type": "PodMetric"}]},
            },
        )

    assert response.status_code == status.HTTP_200_OK
    mock_update.assert_called_once()
    kwargs = mock_update.call_args.kwargs
    assert kwargs["adapters"] == ["my-adapter"]
    scaling = kwargs["scaling"]
    assert (scaling.min_replicas, scaling.max_replicas, scaling.auto_scaling) == (
        2,
        10,
        {"metrics": [{"type": "PodMetric"}]},
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@override_dependencies(SESSION_OVERRIDES)
@patch("app.inference.router.undeploy_aim")
def test_undeploy_inference_returns_204(mock_undeploy: MagicMock) -> None:
    """DELETE /{id} returns 204."""
    mock_undeploy.return_value = None
    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/test-namespace/inference/{uuid4()}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_undeploy.assert_called_once()


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.inference.router.get_metric_by_workload_id")
@patch("app.inference.router.get_aim_service")
def test_get_inference_metric_returns_200(mock_get_aim: MagicMock, mock_metric: MagicMock) -> None:
    """GET /{id}/metrics/{metric} returns a metric payload."""
    mock_get_aim.return_value = make_aim_service_k8s(as_response=True)
    mock_metric.return_value = MetricsScalar(data=42.0)
    end = datetime.now(UTC)
    start = end - timedelta(hours=1)
    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-namespace/inference/{uuid4()}/metrics/total_tokens",
            params={"start": start.isoformat(), "end": end.isoformat()},
        )

    assert response.status_code == status.HTTP_200_OK


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.inference.router.get_metric_by_workload_id")
@patch("app.inference.router.get_aim_service")
def test_get_inference_metric_forwards_pod_name(mock_get_aim: MagicMock, mock_metric: MagicMock) -> None:
    """`podName` is forwarded to the metrics service as `pod_name`."""
    mock_get_aim.return_value = make_aim_service_k8s(as_response=True)
    mock_metric.return_value = MetricsScalar(data=42.0)
    end = datetime.now(UTC)
    start = end - timedelta(hours=1)
    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-namespace/inference/{uuid4()}/metrics/total_tokens",
            params={"start": start.isoformat(), "end": end.isoformat(), "podName": "pod-abc123"},
        )

    assert response.status_code == status.HTTP_200_OK
    assert mock_metric.call_args.kwargs["pod_name"] == "pod-abc123"


@override_dependencies(PROMETHEUS_OVERRIDES)
@patch("app.inference.router.get_metric_by_workload_id")
@patch("app.inference.router.get_aim_service")
def test_get_inference_metric_returns_404_when_deployment_not_in_project(
    mock_get_aim: MagicMock, mock_metric: MagicMock
) -> None:
    """A deployment UUID that doesn't exist in the authorized project returns 404
    and never reaches Prometheus — guards against cross-project metric leakage."""
    mock_get_aim.side_effect = NotFoundException("not found")
    end = datetime.now(UTC)
    start = end - timedelta(hours=1)
    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/test-namespace/inference/{uuid4()}/metrics/total_tokens",
            params={"start": start.isoformat(), "end": end.isoformat()},
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    mock_metric.assert_not_called()


# ---------------------------------------------------------------------------
# Replicas
# ---------------------------------------------------------------------------


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_service_replicas")
@patch("app.inference.router.get_aim_service")
def test_list_inference_replicas_returns_200(mock_get_aim: MagicMock, mock_replicas: MagicMock) -> None:
    """GET /{id}/replicas returns pod data for each replica."""
    mock_get_aim.return_value = make_aim_service_k8s(as_response=True)
    mock_replicas.return_value = [
        {"metadata": {"name": "pod-1"}, "status": {"phase": "Running"}},
        {"metadata": {"name": "pod-2"}, "status": {"phase": "Pending"}},
    ]
    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-namespace/inference/{uuid4()}/replicas")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["metadata"]["name"] == "pod-1"


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_service_replicas")
@patch("app.inference.router.get_aim_service")
def test_list_inference_replicas_returns_empty_list_when_no_pods(
    mock_get_aim: MagicMock, mock_replicas: MagicMock
) -> None:
    """No pods returns an empty list (still 200)."""
    mock_get_aim.return_value = make_aim_service_k8s(as_response=True)
    mock_replicas.return_value = []
    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-namespace/inference/{uuid4()}/replicas")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"] == []


@override_dependencies(BASE_OVERRIDES)
@patch("app.inference.router.list_aim_service_replicas")
@patch("app.inference.router.get_aim_service")
def test_list_inference_replicas_returns_404_when_deployment_not_in_project(
    mock_get_aim: MagicMock, mock_replicas: MagicMock
) -> None:
    """A deployment UUID that doesn't exist in the authorized project returns 404
    and never reaches the pod listing — guards against cross-project pod leakage."""
    mock_get_aim.side_effect = NotFoundException("not found")
    with TestClient(app) as client:
        response = client.get(f"/v1/projects/test-namespace/inference/{uuid4()}/replicas")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    mock_replicas.assert_not_called()
