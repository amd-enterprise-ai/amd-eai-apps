# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient

from api_common.secrets import SecretUseCase
from app import app  # type: ignore[attr-defined]
from app.secrets.crds import K8sMetadata
from app.secrets.schemas import SecretResponse
from tests.dependency_overrides import BASE_OVERRIDES, override_dependencies


def _make_secret(name: str, namespace: str = "test-project") -> SecretResponse:
    return SecretResponse(
        metadata=K8sMetadata(
            name=name,
            namespace=namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
        ),
    )


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_success():
    """Test listing secrets for a project returns the nested envelope."""
    mock_project = "test-project"
    expected_secrets = [_make_secret("huggingface-token", mock_project)]

    with patch("app.secrets.router.list_secrets_for_namespace") as mock_service:
        mock_service.return_value = expected_secrets
        with TestClient(app) as client:
            response = client.get(f"/v1/projects/{mock_project}/secrets")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "data" in data
    assert "pagination" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["metadata"]["name"] == "huggingface-token"
    assert data["pagination"] == {"page": 1, "pageSize": 10, "total": 1}


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_envelope_shape():
    """Pagination envelope must not leak loose top-level keys."""
    mock_project = "test-project"

    with patch("app.secrets.router.list_secrets_for_namespace") as mock_service:
        mock_service.return_value = [_make_secret("s1", mock_project)]
        with TestClient(app) as client:
            response = client.get(f"/v1/projects/{mock_project}/secrets")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "total" not in body
    assert "page" not in body
    assert "pageSize" not in body
    assert "totalPages" not in body["pagination"]


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_with_use_case_filter():
    """Test listing secrets filtered by use case."""
    mock_project = "test-project"
    expected_secrets = [_make_secret("s3-credentials", mock_project)]

    with patch("app.secrets.router.list_secrets_for_namespace") as mock_service:
        mock_service.return_value = expected_secrets
        with TestClient(app) as client:
            response = client.get(f"/v1/projects/{mock_project}/secrets?useCase=S3")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["metadata"]["name"] == "s3-credentials"
    assert data["pagination"]["total"] == 1


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_default_page_1_page_size_10():
    """Without query params, endpoint returns page 1 with pageSize 10."""
    mock_project = "test-project"
    secrets = [_make_secret(f"secret-{i}", mock_project) for i in range(25)]

    with patch("app.secrets.router.list_secrets_for_namespace") as mock_service:
        mock_service.return_value = secrets
        with TestClient(app) as client:
            response = client.get(f"/v1/projects/{mock_project}/secrets")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 10
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 25


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_custom_page_navigation():
    """Page 2 returns the correct slice and consistent pagination metadata."""
    mock_project = "test-project"
    secrets = [_make_secret(f"secret-{i}", mock_project) for i in range(15)]

    with patch("app.secrets.router.list_secrets_for_namespace") as mock_service:
        mock_service.return_value = secrets
        with TestClient(app) as client:
            response = client.get(
                f"/v1/projects/{mock_project}/secrets",
                params={"page": 2, "pageSize": 10},
            )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 5
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["total"] == 15


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_rejects_page_size_zero():
    """`pageSize=0` must be rejected with 422."""
    mock_project = "test-project"
    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{mock_project}/secrets",
            params={"pageSize": 0},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_rejects_page_size_over_100():
    """`pageSize=101` must be rejected with 422."""
    mock_project = "test-project"
    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{mock_project}/secrets",
            params={"pageSize": 101},
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_filter_applies_before_pagination():
    """use_case filter narrows the set before pagination; total reflects filtered count."""
    mock_project = "test-project"
    # Service already returns filtered result (filtering happens in service layer)
    filtered_secrets = [_make_secret("hf-token", mock_project)]

    with patch("app.secrets.router.list_secrets_for_namespace") as mock_service:
        mock_service.return_value = filtered_secrets
        with TestClient(app) as client:
            response = client.get(
                f"/v1/projects/{mock_project}/secrets",
                params={"useCase": "HuggingFace"},
            )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["total"] == 1
    mock_service.assert_called_once()
    assert mock_service.call_args.kwargs["use_case"] == SecretUseCase.HUGGING_FACE


@override_dependencies(BASE_OVERRIDES)
def test_get_secrets_empty_namespace():
    """Test listing secrets for an empty project returns empty data with pagination."""
    mock_project = "empty-project"

    with patch("app.secrets.router.list_secrets_for_namespace") as mock_service:
        mock_service.return_value = []
        with TestClient(app) as client:
            response = client.get(f"/v1/projects/{mock_project}/secrets")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["data"] == []
    assert data["pagination"] == {"page": 1, "pageSize": 10, "total": 0}


@override_dependencies(BASE_OVERRIDES)
def test_create_secret_success():
    """Test creating a new secret."""
    mock_project = "test-project"

    expected_response = _make_secret("new-secret", mock_project)

    with patch("app.secrets.router.create_secret") as mock_service:
        mock_service.return_value = expected_response
        with TestClient(app) as client:
            response = client.post(
                f"/v1/projects/{mock_project}/secrets",
                json={
                    "displayName": "new-secret",
                    "type": "Opaque",
                    "data": {
                        "username": "admin",
                        "password": "secret123",
                    },
                },
            )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["metadata"]["name"] == "new-secret"


@override_dependencies(BASE_OVERRIDES)
def test_get_secret_details_success():
    """Test getting detailed secret information."""
    mock_project = "test-project"
    secret_name = "detailed-secret"

    expected_details = SecretResponse(
        metadata=K8sMetadata(
            name=secret_name,
            namespace=mock_project,
            creation_timestamp="2025-01-01T00:00:00Z",
            labels={"use-case": "HuggingFace"},
            annotations={"description": "Authentication token"},
        ),
    )

    with patch("app.secrets.router.get_secret_details") as mock_service:
        mock_service.return_value = expected_details
        with TestClient(app) as client:
            response = client.get(f"/v1/projects/{mock_project}/secrets/{secret_name}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["metadata"]["name"] == secret_name
    assert data["metadata"]["labels"]["use-case"] == "HuggingFace"


@override_dependencies(BASE_OVERRIDES)
def test_delete_secret_success():
    """Test deleting a secret."""
    mock_project = "test-project"
    secret_name = "old-secret"

    with patch("app.secrets.router.delete_secret") as mock_service:
        mock_service.return_value = None
        with TestClient(app) as client:
            response = client.delete(f"/v1/projects/{mock_project}/secrets/{secret_name}")

    assert response.status_code == status.HTTP_204_NO_CONTENT


@override_dependencies(BASE_OVERRIDES)
def test_create_secret_with_use_case():
    """Test creating a secret with a use case label."""
    mock_project = "test-project"

    expected_response = _make_secret("s3-secret", mock_project)

    with patch("app.secrets.router.create_secret") as mock_service:
        mock_service.return_value = expected_response
        with TestClient(app) as client:
            response = client.post(
                f"/v1/projects/{mock_project}/secrets",
                json={
                    "displayName": "s3-secret",
                    "type": "Opaque",
                    "useCase": "S3",
                    "data": {
                        "accessKeyId": "AKIAIOSFODNN7EXAMPLE",
                        "secretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    },
                },
            )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["metadata"]["name"] == "s3-secret"


@override_dependencies(BASE_OVERRIDES)
def test_create_s3_secret_missing_credentials_rejected():
    """An S3 secret without recognized credential keys is rejected before reaching Kubernetes."""
    mock_project = "test-project"

    with patch("app.secrets.service.create_kubernetes_secret") as mock_gateway:
        with TestClient(app) as client:
            response = client.post(
                f"/v1/projects/{mock_project}/secrets",
                json={
                    "displayName": "s3-secret",
                    "useCase": "S3",
                    "data": {"unrelated": "dmFsdWU="},
                },
            )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    mock_gateway.assert_not_called()
