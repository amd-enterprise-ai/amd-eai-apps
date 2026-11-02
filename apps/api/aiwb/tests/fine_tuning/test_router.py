# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for fine_tuning router endpoints using FastAPI TestClient with dependency overrides."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import status
from fastapi.testclient import TestClient

from api_common.collections import PaginatedResult
from api_common.exceptions import DeletionConflictException, NotFoundException
from app import app  # type: ignore[attr-defined]
from app.aims.crds import AIMModelResource
from app.models.schemas import FinetunableModelResponse, FinetuneJobResponse, FinetuningHyperparameters
from app.workloads.constants import WORKLOAD_TYPE_LABEL
from app.workloads.enums import WorkloadType
from tests.dependency_overrides import BASE_OVERRIDES, MINIO_OVERRIDES, SESSION_OVERRIDES, override_dependencies

NAMESPACE = "test-namespace"

# Every field is required, so a listing entry that advertises nothing has to spell that out.
NO_HYPERPARAMETERS = FinetuningHyperparameters(batch_size=None, epochs=None, learning_rate=None, lora=None)


def make_aim_model_resource(resource_name: str = "test-model-cr", fine_tuning: bool = True) -> AIMModelResource:
    labels: dict[str, str] = {}
    if fine_tuning:
        labels[WORKLOAD_TYPE_LABEL] = WorkloadType.FINE_TUNING
    return AIMModelResource.model_validate(
        {
            "metadata": {"name": resource_name, "labels": labels},
            "spec": {"image": "test-image:latest"},
            "status": {"status": "Ready", "imageMetadata": {"model": {}}},
        }
    )


def make_finetune_job_response(**kwargs: object) -> FinetuneJobResponse:
    return FinetuneJobResponse(
        workload_id=kwargs.get("workload_id", uuid4()),
        display_name=kwargs.get("display_name", "test-finetune"),
        base_model=kwargs.get("base_model", "test/base-model"),
        namespace=kwargs.get("namespace", NAMESPACE),
    )


# =============================================================================
# GET /v1/fine-tuning/models (cluster-scope catalog)
# =============================================================================


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.get_finetunable_models", autospec=True)
def test_list_finetunable_models(mock_get_finetunable: MagicMock) -> None:
    mock_get_finetunable.return_value = [
        FinetunableModelResponse(
            canonical_name="meta-llama/Llama-3.1-8B",
            gpu_count=1,
            compatible_accelerators=["74a1"],
            hyperparameters=NO_HYPERPARAMETERS,
        ),
        FinetunableModelResponse(
            canonical_name="microsoft/DialoGPT-medium",
            gpu_count=None,
            compatible_accelerators=[],
            hyperparameters=NO_HYPERPARAMETERS,
        ),
    ]

    with TestClient(app) as client:
        response = client.get("/v1/fine-tuning/models")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert len(data) == 2
    assert data[0]["canonicalName"] == "meta-llama/Llama-3.1-8B"
    assert data[0]["gpuCount"] == 1
    assert data[0]["compatibleAccelerators"] == ["74a1"]


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.get_finetunable_models", autospec=True)
def test_list_finetunable_models_empty(mock_get_finetunable: MagicMock) -> None:
    mock_get_finetunable.return_value = []

    with TestClient(app) as client:
        response = client.get("/v1/fine-tuning/models")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"] == []


# =============================================================================
# GET /v1/fine-tuning/models/{name}
# =============================================================================


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.get_finetunable_models", autospec=True)
def test_get_finetunable_model(mock_get_finetunable: MagicMock) -> None:
    canonical_name = "meta-llama/Llama-3.1-8B"
    mock_get_finetunable.return_value = [
        FinetunableModelResponse(
            canonical_name=canonical_name,
            gpu_count=1,
            compatible_accelerators=["74a1"],
            hyperparameters=NO_HYPERPARAMETERS,
        ),
        FinetunableModelResponse(
            canonical_name="microsoft/DialoGPT-medium",
            gpu_count=None,
            compatible_accelerators=[],
            hyperparameters=NO_HYPERPARAMETERS,
        ),
    ]

    with TestClient(app) as client:
        response = client.get(f"/v1/fine-tuning/models/{canonical_name}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["canonicalName"] == canonical_name


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.get_finetunable_models", autospec=True)
def test_get_finetunable_model_not_found(mock_get_finetunable: MagicMock) -> None:
    mock_get_finetunable.return_value = [
        FinetunableModelResponse(
            canonical_name="meta-llama/Llama-3.1-8B", gpu_count=1, hyperparameters=NO_HYPERPARAMETERS
        ),
    ]

    with TestClient(app) as client:
        response = client.get("/v1/fine-tuning/models/nonexistent/model")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"]


# =============================================================================
# GET /v1/projects/{project}/fine-tuning/models
# =============================================================================


@override_dependencies(BASE_OVERRIDES)
@patch("app.fine_tuning.router.list_fine_tuning_models", new_callable=AsyncMock)
def test_list_project_fine_tuned_models(mock_list: AsyncMock) -> None:
    mock_list.return_value = PaginatedResult(
        items=[make_aim_model_resource(resource_name="ft-model-1")],
        total=1,
        page=1,
        page_size=10,
        total_pages=1,
    )

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "data" in body
    assert "pagination" in body
    assert len(body["data"]) == 1
    assert body["data"][0]["metadata"]["name"] == "ft-model-1"
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 1


@override_dependencies(BASE_OVERRIDES)
@patch("app.fine_tuning.router.list_fine_tuning_models", new_callable=AsyncMock)
def test_list_project_fine_tuned_models_empty(mock_list: AsyncMock) -> None:
    mock_list.return_value = PaginatedResult(
        items=[],
        total=0,
        page=1,
        page_size=10,
        total_pages=1,
    )

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


@override_dependencies(BASE_OVERRIDES)
@patch("app.fine_tuning.router.list_fine_tuning_models", new_callable=AsyncMock)
def test_list_project_fine_tuned_models_with_page_size(mock_list: AsyncMock) -> None:
    mock_list.return_value = PaginatedResult(
        items=[make_aim_model_resource(resource_name="ft-model-3")],
        total=5,
        page=2,
        page_size=2,
        total_pages=3,
    )

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models?pageSize=2&page=2")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["pageSize"] == 2
    assert body["pagination"]["total"] == 5
    # Verify the service received the pagination params from the request.
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs["page"] == 2
    assert call_kwargs["page_size"] == 2


@override_dependencies(BASE_OVERRIDES)
@patch("app.fine_tuning.router.list_fine_tuning_models", new_callable=AsyncMock)
def test_list_project_fine_tuned_models_uses_default_page_size_of_10(mock_list: AsyncMock) -> None:
    """Without query params, the endpoint uses page=1 and pageSize=10."""
    mock_list.return_value = PaginatedResult(items=[], total=0, page=1, page_size=10, total_pages=1)

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs["page"] == 1
    assert call_kwargs["page_size"] == 10


@override_dependencies(BASE_OVERRIDES)
def test_list_project_fine_tuned_models_rejects_invalid_page_size() -> None:
    """`pageSize` must be in [1, 100]; values outside the bound are 422."""
    with TestClient(app) as client:
        too_small = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models?pageSize=0")
        too_large = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models?pageSize=101")

    assert too_small.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert too_large.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(BASE_OVERRIDES)
def test_list_project_fine_tuned_models_rejects_invalid_page() -> None:
    """`page` must be >= 1; page=0 is 422."""
    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models?page=0")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# GET /v1/projects/{project}/fine-tuning/models/{model_id}
# =============================================================================


@override_dependencies(BASE_OVERRIDES)
@patch("app.fine_tuning.router.get_fine_tuning_model", new_callable=AsyncMock)
def test_get_project_fine_tuned_model(mock_get: AsyncMock) -> None:
    resource_name = "wb-finetuning-abc123"
    mock_get.return_value = make_aim_model_resource(resource_name=resource_name)

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models/{resource_name}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["metadata"]["name"] == resource_name


@override_dependencies(BASE_OVERRIDES)
@patch("app.fine_tuning.router.get_fine_tuning_model", new_callable=AsyncMock)
def test_get_project_fine_tuned_model_not_found(mock_get: AsyncMock) -> None:
    resource_name = "nonexistent"
    mock_get.side_effect = NotFoundException(f"Fine-tuning model {resource_name} not found")

    with TestClient(app) as client:
        response = client.get(f"/v1/projects/{NAMESPACE}/fine-tuning/models/{resource_name}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"]


# =============================================================================
# DELETE /v1/projects/{project}/fine-tuning/models/{model_id}
# =============================================================================


@override_dependencies(MINIO_OVERRIDES)
@patch("app.fine_tuning.router.delete_model", autospec=True)
@patch("app.fine_tuning.router.get_fine_tuning_model", new_callable=AsyncMock)
def test_delete_project_fine_tuned_model(mock_get: AsyncMock, mock_delete: MagicMock) -> None:
    mock_get.return_value = make_aim_model_resource(resource_name="my-ft-model")
    mock_delete.return_value = None

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{NAMESPACE}/fine-tuning/models/my-ft-model")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    mock_get.assert_awaited_once()
    mock_delete.assert_called_once()


@override_dependencies(MINIO_OVERRIDES)
@patch("app.fine_tuning.router.delete_model", autospec=True)
@patch("app.fine_tuning.router.get_fine_tuning_model", new_callable=AsyncMock)
def test_delete_project_fine_tuned_model_force(mock_get: AsyncMock, mock_delete: MagicMock) -> None:
    mock_get.return_value = make_aim_model_resource(resource_name="my-ft-model")
    mock_delete.return_value = None

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{NAMESPACE}/fine-tuning/models/my-ft-model?force=true")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert mock_delete.call_args.kwargs["force"] is True


@override_dependencies(MINIO_OVERRIDES)
@patch("app.fine_tuning.router.delete_model", autospec=True)
@patch("app.fine_tuning.router.get_fine_tuning_model", new_callable=AsyncMock)
def test_delete_project_fine_tuned_model_not_found(mock_get: AsyncMock, mock_delete: MagicMock) -> None:
    mock_get.side_effect = NotFoundException("Fine-tuning model my-ft-model not found")

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{NAMESPACE}/fine-tuning/models/my-ft-model")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    mock_delete.assert_not_called()


@override_dependencies(MINIO_OVERRIDES)
@patch("app.fine_tuning.router.delete_model", autospec=True)
@patch("app.fine_tuning.router.get_fine_tuning_model", new_callable=AsyncMock)
def test_delete_project_fine_tuned_model_conflict(mock_get: AsyncMock, mock_delete: MagicMock) -> None:
    mock_get.return_value = make_aim_model_resource(resource_name="my-ft-model")
    mock_delete.side_effect = DeletionConflictException(
        "Model my-ft-model has 1 active deployment(s). Use force=true to delete anyway."
    )

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{NAMESPACE}/fine-tuning/models/my-ft-model")

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "active deployment" in response.json()["detail"]


# =============================================================================
# POST /v1/projects/{project}/fine-tuning/jobs
# =============================================================================


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.run_finetune_model_workload", autospec=True)
def test_create_fine_tuning_job_with_uuid(mock_run: MagicMock) -> None:
    base_model_uuid = uuid4()
    dataset_id = uuid4()
    mock_run.return_value = make_finetune_job_response()

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{NAMESPACE}/fine-tuning/jobs",
            json={
                "baseModel": str(base_model_uuid),
                "displayName": "my-finetune",
                "datasetId": str(dataset_id),
                "epochs": 3,
                "learningRate": 0.001,
                "batchSize": 8,
            },
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    # base_model is typed UUID | str; the service helper handles coercion either way
    assert str(call_kwargs["model_id"]) == str(base_model_uuid)
    assert call_kwargs["namespace"] == NAMESPACE


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.run_finetune_model_workload", autospec=True)
def test_create_fine_tuning_job_with_canonical_name(mock_run: MagicMock) -> None:
    canonical_name = "meta-llama/Llama-3.1-8B"
    dataset_id = uuid4()
    mock_run.return_value = make_finetune_job_response()

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{NAMESPACE}/fine-tuning/jobs",
            json={
                "baseModel": canonical_name,
                "displayName": "my-finetune",
                "datasetId": str(dataset_id),
            },
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert mock_run.call_args.kwargs["model_id"] == canonical_name


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.run_finetune_model_workload", autospec=True)
def test_create_fine_tuning_job_with_multiple_datasets(mock_run: MagicMock) -> None:
    dataset_ids = [uuid4(), uuid4()]
    mock_run.return_value = make_finetune_job_response()

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{NAMESPACE}/fine-tuning/jobs",
            json={
                "baseModel": "meta-llama/Llama-3.1-8B",
                "displayName": "my-finetune",
                "datasetIds": [str(dataset_id) for dataset_id in dataset_ids],
            },
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    request = mock_run.call_args.kwargs["finetuning_data"]
    assert request.dataset_ids == dataset_ids


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.run_finetune_model_workload", autospec=True)
def test_create_fine_tuning_job_with_hf_token_secret(mock_run: MagicMock) -> None:
    dataset_id = uuid4()
    mock_run.return_value = make_finetune_job_response()

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{NAMESPACE}/fine-tuning/jobs",
            json={
                "baseModel": "meta-llama/Llama-3.1-8B",
                "displayName": "my-finetune",
                "datasetId": str(dataset_id),
                "hfTokenSecretName": "hf-token-secret",
            },
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert mock_run.call_args.kwargs["finetuning_data"].hf_token_secret_name == "hf-token-secret"


@override_dependencies(SESSION_OVERRIDES)
def test_create_fine_tuning_job_invalid_name_rejected() -> None:
    dataset_id = uuid4()

    # display_name accepts any characters (min_length=1 only); only empty string is invalid
    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{NAMESPACE}/fine-tuning/jobs",
            json={"baseModel": "meta-llama/Llama-3.1-8B", "displayName": "", "datasetId": str(dataset_id)},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected 422 for empty displayName"


@override_dependencies(SESSION_OVERRIDES)
def test_create_fine_tuning_job_missing_base_model_rejected() -> None:
    dataset_id = uuid4()

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{NAMESPACE}/fine-tuning/jobs",
            json={"displayName": "my-finetune", "datasetId": str(dataset_id)},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# DELETE /v1/projects/{project}/fine-tuning/jobs/{job_id}
# =============================================================================


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.delete_fine_tuning_job", new_callable=AsyncMock)
def test_cancel_fine_tuning_job(mock_delete: AsyncMock) -> None:
    job_id = uuid4()
    mock_delete.return_value = None

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{NAMESPACE}/fine-tuning/jobs/{job_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete.assert_awaited_once()
    call_kwargs = mock_delete.call_args.kwargs
    assert call_kwargs["workload_id"] == job_id
    assert call_kwargs["namespace"] == NAMESPACE


@override_dependencies(SESSION_OVERRIDES)
@patch("app.fine_tuning.router.delete_fine_tuning_job", new_callable=AsyncMock)
def test_cancel_fine_tuning_job_not_found(mock_delete: AsyncMock) -> None:
    job_id = uuid4()
    mock_delete.side_effect = NotFoundException(f"Fine-tuning job {job_id} not found")

    with TestClient(app) as client:
        response = client.delete(f"/v1/projects/{NAMESPACE}/fine-tuning/jobs/{job_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"]
