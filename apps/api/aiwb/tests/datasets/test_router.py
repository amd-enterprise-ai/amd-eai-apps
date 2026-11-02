# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from unittest.mock import patch
from uuid import uuid4

from fastapi import status
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from api_common.collections import PaginatedResult
from api_common.exceptions import NotFoundException
from app import app  # type: ignore[attr-defined]
from app.datasets.models import DatasetType
from tests.datasets.conftest import make_dataset_response
from tests.dependency_overrides import MINIO_OVERRIDES, override_dependencies


def _paginated(items: list, page: int = 1, page_size: int = 10) -> PaginatedResult:
    """Build a PaginatedResult mirroring what `list_paginated_datasets` returns."""
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size
    return PaginatedResult(
        items=items[start:end],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@override_dependencies(MINIO_OVERRIDES)
def test_upload_dataset_success():
    """Test uploading a new dataset."""
    expected_response = make_dataset_response(
        name="Test Dataset",
        description="Test Description",
    )

    with patch("app.datasets.router.create_and_upload_dataset", autospec=True) as mock_service:
        mock_service.return_value = expected_response

        test_file_content = b'{"text": "test"}\n{"text": "test2"}'
        files = {"jsonl": ("test.jsonl", test_file_content, "application/jsonlines")}
        data = {
            "name": "Test Dataset",
            "description": "Test Description",
            "type": DatasetType.FINETUNING.value,
        }

        with TestClient(app) as client:
            response = client.post("/v1/projects/test-namespace/datasets", files=files, data=data)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "Test Dataset"
    assert data["description"] == "Test Description"
    assert data["type"] == DatasetType.FINETUNING.value
    assert data["sizeBytes"] == len(test_file_content)


@override_dependencies(MINIO_OVERRIDES)
def test_list_datasets_success():
    """Test listing datasets in a namespace returns the nested envelope."""
    expected_datasets = [
        make_dataset_response(
            name="Dataset 1", description="Description 1", path="test-namespace/datasets/dataset-1.jsonl"
        ),
        make_dataset_response(
            name="Dataset 2", description="Description 2", path="test-namespace/datasets/dataset-2.jsonl"
        ),
    ]

    with patch("app.datasets.router.list_paginated_datasets", autospec=True) as mock_service:
        mock_service.return_value = _paginated(expected_datasets)

        with TestClient(app) as client:
            response = client.get("/v1/projects/test-namespace/datasets")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["name"] == "Dataset 1"
    assert body["data"][1]["name"] == "Dataset 2"
    assert body["data"][0]["sizeBytes"] is None
    assert body["pagination"] == {"page": 1, "pageSize": 10, "total": 2}
    # Nested pagination envelope must not leak loose top-level keys.
    assert "total" not in body
    assert "page" not in body
    assert "pageSize" not in body
    assert "totalPages" not in body
    assert "totalPages" not in body["pagination"]


@override_dependencies(MINIO_OVERRIDES)
def test_list_datasets_with_filters():
    """Test listing datasets with type and name filters."""
    expected_datasets = [
        make_dataset_response(
            name="Filtered Dataset", description="Description", path="test-namespace/datasets/filtered-dataset.jsonl"
        )
    ]

    with patch("app.datasets.router.list_paginated_datasets", autospec=True) as mock_service:
        mock_service.return_value = _paginated(expected_datasets)

        with TestClient(app) as client:
            response = client.get(
                f"/v1/projects/test-namespace/datasets?type={DatasetType.FINETUNING.value}&name=Filtered Dataset"
            )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["name"] == "Filtered Dataset"
    assert body["pagination"] == {"page": 1, "pageSize": 10, "total": 1}
    mock_service.assert_called_once()
    call_kwargs = mock_service.call_args.kwargs
    assert call_kwargs["type"] == DatasetType.FINETUNING
    assert call_kwargs["name"] == "Filtered Dataset"


@override_dependencies(MINIO_OVERRIDES)
def test_get_dataset_success():
    """Test getting a single dataset by ID."""
    dataset_id = uuid4()
    expected_dataset = make_dataset_response(id=dataset_id, description="Test Description")

    with patch("app.datasets.router.get_dataset_by_id", autospec=True) as mock_service:
        mock_service.return_value = expected_dataset

        with TestClient(app) as client:
            response = client.get(f"/v1/projects/test-namespace/datasets/{dataset_id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(dataset_id)
    assert data["name"] == "Test Dataset"
    assert data["sizeBytes"] is None


@override_dependencies(MINIO_OVERRIDES)
def test_get_dataset_not_found():
    """Test getting a non-existent dataset."""
    dataset_id = uuid4()

    with patch("app.datasets.router.get_dataset_by_id", autospec=True) as mock_service:
        mock_service.side_effect = NotFoundException(f"Dataset {dataset_id} not found")

        with TestClient(app) as client:
            response = client.get(f"/v1/projects/test-namespace/datasets/{dataset_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@override_dependencies(MINIO_OVERRIDES)
def test_download_dataset_success():
    """Test downloading a dataset file with streaming."""
    dataset_id = uuid4()

    # Mock streaming response
    def mock_stream():
        yield b'{"text": "test"}\n'

    mock_response = StreamingResponse(
        mock_stream(),
        media_type="application/jsonl; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="test-dataset.jsonl"'},
    )

    with patch("app.datasets.router.download_dataset_file", autospec=True) as mock_service:
        mock_service.return_value = mock_response

        with TestClient(app) as client:
            response = client.get(f"/v1/projects/test-namespace/datasets/{dataset_id}/download")

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/jsonl; charset=utf-8"
    assert "test-dataset.jsonl" in response.headers.get("content-disposition", "")


@override_dependencies(MINIO_OVERRIDES)
def test_delete_dataset_success():
    """Test deleting a single dataset."""
    dataset_id = uuid4()

    with patch("app.datasets.router.delete_dataset", autospec=True) as mock_service:
        mock_service.return_value = None

        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/test-namespace/datasets/{dataset_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT


@override_dependencies(MINIO_OVERRIDES)
def test_delete_dataset_not_found():
    """Test deleting a non-existent dataset - still returns 204."""
    dataset_id = uuid4()

    with patch("app.datasets.router.delete_dataset", autospec=True) as mock_service:
        mock_service.return_value = None

        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/test-namespace/datasets/{dataset_id}")

    # The endpoint returns 204 even if nothing was deleted (idempotent)
    assert response.status_code == status.HTTP_204_NO_CONTENT


@override_dependencies(MINIO_OVERRIDES)
def test_list_datasets_empty():
    """Test listing datasets when namespace has none."""
    with patch("app.datasets.router.list_paginated_datasets", autospec=True) as mock_service:
        mock_service.return_value = _paginated([])

        with TestClient(app) as client:
            response = client.get("/v1/projects/test-namespace/datasets")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["data"] == []
    assert body["pagination"] == {"page": 1, "pageSize": 10, "total": 0}
    assert "total" not in body
    assert "page" not in body
    assert "pageSize" not in body
    assert "totalPages" not in body
    assert "totalPages" not in body["pagination"]


@override_dependencies(MINIO_OVERRIDES)
def test_list_datasets_paginates_results():
    """Page slicing covers the right rows and pagination metadata is consistent."""
    all_datasets = [
        make_dataset_response(name=f"Dataset {i}", path=f"test-namespace/datasets/ds-{i}.jsonl") for i in range(15)
    ]

    with patch("app.datasets.router.list_paginated_datasets", autospec=True) as mock_service:
        mock_service.side_effect = lambda **kwargs: _paginated(
            all_datasets, page=kwargs["page"], page_size=kwargs["page_size"]
        )

        with TestClient(app) as client:
            first = client.get("/v1/projects/test-namespace/datasets")
            second = client.get(
                "/v1/projects/test-namespace/datasets",
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


@override_dependencies(MINIO_OVERRIDES)
def test_list_datasets_uses_default_page_size_of_10():
    """Without query params, the endpoint returns 10 items on page 1."""
    all_datasets = [
        make_dataset_response(name=f"Dataset {i}", path=f"test-namespace/datasets/ds-{i}.jsonl") for i in range(25)
    ]

    with patch("app.datasets.router.list_paginated_datasets", autospec=True) as mock_service:
        mock_service.side_effect = lambda **kwargs: _paginated(
            all_datasets, page=kwargs["page"], page_size=kwargs["page_size"]
        )

        with TestClient(app) as client:
            response = client.get("/v1/projects/test-namespace/datasets")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 10
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 25


@override_dependencies(MINIO_OVERRIDES)
def test_list_datasets_rejects_invalid_page_size():
    """`pageSize` must be in [1, 100]; values outside the bound are 422."""
    with TestClient(app) as client:
        too_small = client.get(
            "/v1/projects/test-namespace/datasets",
            params={"pageSize": 0},
        )
        too_large = client.get(
            "/v1/projects/test-namespace/datasets",
            params={"pageSize": 101},
        )

    assert too_small.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert too_large.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(MINIO_OVERRIDES)
def test_list_datasets_filter_applies_before_pagination():
    """When a name filter narrows the set, `total` reflects only the filtered rows."""
    filtered = [
        make_dataset_response(name="Foo", path="test-namespace/datasets/foo.jsonl"),
    ]

    with patch("app.datasets.router.list_paginated_datasets", autospec=True) as mock_service:
        mock_service.return_value = _paginated(filtered)

        with TestClient(app) as client:
            response = client.get(
                "/v1/projects/test-namespace/datasets",
                params={"name": "Foo"},
            )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["total"] == 1
    mock_service.assert_called_once()
    assert mock_service.call_args.kwargs["name"] == "Foo"
