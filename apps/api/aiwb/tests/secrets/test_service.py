# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AIWB secrets service layer - pure Kubernetes secret management."""

import base64
from unittest.mock import AsyncMock, patch

import pytest
from kubernetes_asyncio.client import ApiException

from api_common.exceptions import ConflictException, NotFoundException, ValidationException
from api_common.secrets import SecretUseCase
from app.secrets import service
from app.secrets.constants import AIRM_USE_CASE_LABEL, DISPLAY_NAME_ANNOTATION, USE_CASE_LABEL
from app.secrets.crds import K8sMetadata, KubernetesSecretResource
from app.secrets.schemas import SecretCreate


@pytest.mark.asyncio
async def test_list_secrets_for_namespace(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test listing secrets for a namespace."""
    # Mock gateway response
    mock_secrets = [
        KubernetesSecretResource(
            metadata=K8sMetadata(
                name="secret-1",
                namespace=test_namespace,
                creation_timestamp="2025-01-01T00:00:00Z",
            ),
        ),
        KubernetesSecretResource(
            metadata=K8sMetadata(
                name="secret-2",
                namespace=test_namespace,
                creation_timestamp="2025-01-01T00:00:00Z",
            ),
        ),
    ]

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=mock_secrets):
        result = await service.list_secrets_for_namespace(
            kube_client=mock_kube_client,
            namespace=test_namespace,
        )

    assert len(result) == 2
    assert result[0].metadata.name == "secret-1"
    assert result[1].metadata.name == "secret-2"


@pytest.mark.asyncio
async def test_list_secrets_with_use_case_filter(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test listing secrets filtered by use case."""
    # Mock secrets with different use cases
    mock_secrets = [
        KubernetesSecretResource(
            metadata=K8sMetadata(
                name="s3-secret",
                namespace=test_namespace,
                creation_timestamp="2025-01-01T00:00:00Z",
                labels={USE_CASE_LABEL: "S3"},
            ),
        ),
        KubernetesSecretResource(
            metadata=K8sMetadata(
                name="hf-secret",
                namespace=test_namespace,
                creation_timestamp="2025-01-01T00:00:00Z",
                labels={USE_CASE_LABEL: "HuggingFace"},
            ),
        ),
    ]

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=mock_secrets):
        result = await service.list_secrets_for_namespace(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            use_case=SecretUseCase.S3,
        )

    assert len(result) == 1
    assert result[0].metadata.name == "s3-secret"


@pytest.mark.asyncio
async def test_list_secrets_with_airm_use_case_label_fallback(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test that secrets with AIRM's mismatched use-case label prefix are still matched."""
    mock_secrets = [
        KubernetesSecretResource(
            metadata=K8sMetadata(
                name="airm-secret",
                namespace=test_namespace,
                creation_timestamp="2025-01-01T00:00:00Z",
                labels={AIRM_USE_CASE_LABEL: "huggingface"},
            ),
        ),
        KubernetesSecretResource(
            metadata=K8sMetadata(
                name="aiwb-secret",
                namespace=test_namespace,
                creation_timestamp="2025-01-01T00:00:00Z",
                labels={USE_CASE_LABEL: "HuggingFace"},
            ),
        ),
    ]

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=mock_secrets):
        result = await service.list_secrets_for_namespace(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            use_case=SecretUseCase.HUGGING_FACE,
        )

    assert len(result) == 2
    assert all(s.use_case == SecretUseCase.HUGGING_FACE for s in result)


@pytest.mark.asyncio
async def test_get_secret_details(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test getting detailed secret information."""
    secret_name = "test-secret"
    mock_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name=secret_name,
            namespace=test_namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
        ),
    )

    with patch("app.secrets.service.get_kubernetes_secret", return_value=mock_secret):
        result = await service.get_secret_details(
            kube_client=mock_kube_client,
            namespace=test_namespace,
            secret_name=secret_name,
        )

    assert result.metadata.name == secret_name
    assert result.metadata.namespace == test_namespace


@pytest.mark.asyncio
async def test_get_secret_details_not_found(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test getting details for non-existent secret raises NotFoundException."""
    with patch("app.secrets.service.get_kubernetes_secret", return_value=None):
        with pytest.raises(NotFoundException, match="not found"):
            await service.get_secret_details(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_name="nonexistent",
            )


@pytest.mark.asyncio
async def test_create_secret(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test creating a new secret."""
    secret_data = SecretCreate(
        display_name="new-secret",
        data={"api_key": "abc123"},
        use_case=SecretUseCase.HUGGING_FACE,
    )

    mock_created_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name="new-secret",
            namespace=test_namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
            labels={USE_CASE_LABEL: "HuggingFace"},
        ),
    )

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=[]):
        with patch("app.secrets.service.create_kubernetes_secret", return_value=mock_created_secret):
            result = await service.create_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_in=secret_data,
            )

    assert result.metadata.name == "new-secret"
    assert result.metadata.namespace == test_namespace


@pytest.mark.asyncio
async def test_create_secret_duplicate_display_name_raises_conflict(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test that creating a secret with a display name already in use raises ConflictException."""
    secret_data = SecretCreate(
        display_name="my-secret",
        data={"key": "value"},
    )

    existing_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name="wb-secret-abcd1234",
            namespace=test_namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
            annotations={DISPLAY_NAME_ANNOTATION: "my-secret"},
        ),
    )

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=[existing_secret]):
        with pytest.raises(ConflictException, match="my-secret"):
            await service.create_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_in=secret_data,
            )


@pytest.mark.asyncio
async def test_create_secret_duplicate_via_metadata_name_raises_conflict(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Secrets without the display-name annotation surface displayName=metadata.name; the check covers that fallback."""
    secret_data = SecretCreate(
        display_name="legacy-secret",
        data={"key": "value"},
    )

    # Old secret has no display-name annotation; its displayName surfaces as metadata.name
    existing_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name="legacy-secret",
            namespace=test_namespace,
            creation_timestamp="2024-01-01T00:00:00Z",
        ),
    )

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=[existing_secret]):
        with pytest.raises(ConflictException, match="legacy-secret"):
            await service.create_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_in=secret_data,
            )


@pytest.mark.asyncio
async def test_create_secret_already_exists(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test creating a secret that already exists raises ConflictException."""
    secret_data = SecretCreate(
        display_name="existing-secret",
        data={"key": "value"},
    )

    # Mock 409 Conflict from K8s
    api_exception = ApiException(status=409)

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=[]):
        with patch("app.secrets.service.create_kubernetes_secret", side_effect=api_exception):
            with pytest.raises(ConflictException, match="already exists"):
                await service.create_secret(
                    kube_client=mock_kube_client,
                    namespace=test_namespace,
                    secret_in=secret_data,
                )


@pytest.mark.asyncio
async def test_create_secret_image_pull_invalid_json_raises_validation_exception(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test creating an image pull secret with non-JSON value raises ValidationException."""
    invalid_value_b64 = base64.b64encode(b"plain text not json").decode("ascii")
    secret_data = SecretCreate(
        display_name="image-pull-secret",
        data={".dockerconfigjson": invalid_value_b64},
        use_case=SecretUseCase.IMAGE_PULL_SECRET,
    )

    with patch("app.secrets.service.create_kubernetes_secret") as mock_create:
        with pytest.raises(ValidationException, match="valid Docker config JSON"):
            await service.create_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_in=secret_data,
            )
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_create_secret_image_pull_valid_json_succeeds(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test creating an image pull secret with valid JSON calls gateway and returns secret."""
    valid_json = b'{"auths":{"https://index.docker.io/v1/":{"username":"u","password":"p"}}}'
    valid_value_b64 = base64.b64encode(valid_json).decode("ascii")
    secret_data = SecretCreate(
        display_name="image-pull-secret",
        data={".dockerconfigjson": valid_value_b64},
        use_case=SecretUseCase.IMAGE_PULL_SECRET,
    )

    mock_created_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name="image-pull-secret",
            namespace=test_namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
            labels={USE_CASE_LABEL: "ImagePullSecret"},
        ),
    )

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=[]):
        with patch("app.secrets.service.create_kubernetes_secret", return_value=mock_created_secret):
            result = await service.create_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_in=secret_data,
            )

    assert result.metadata.name == "image-pull-secret"
    assert result.metadata.namespace == test_namespace


@pytest.mark.asyncio
async def test_create_secret_s3_missing_credentials_raises_validation_exception(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test creating an S3 secret without recognized credential keys raises ValidationException."""
    secret_data = SecretCreate(
        display_name="s3-secret",
        data={"unrelated": "dmFsdWU="},
        use_case=SecretUseCase.S3,
    )

    with patch("app.secrets.service.create_kubernetes_secret") as mock_create:
        with pytest.raises(ValidationException, match="missing required credential"):
            await service.create_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_in=secret_data,
            )
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_create_secret_s3_partial_credentials_raises_validation_exception(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test that an S3 secret with only an access key (no secret key) is rejected."""
    secret_data = SecretCreate(
        display_name="s3-secret",
        data={"AWS_ACCESS_KEY_ID": "dmFsdWU="},
        use_case=SecretUseCase.S3,
    )

    with patch("app.secrets.service.create_kubernetes_secret") as mock_create:
        with pytest.raises(ValidationException, match="secret key"):
            await service.create_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_in=secret_data,
            )
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_create_secret_s3_valid_credentials_succeeds(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test creating an S3 secret with access and secret keys (using aliased keys) calls the gateway."""
    secret_data = SecretCreate(
        display_name="s3-secret",
        data={
            "accessKeyId": "YWtpZA==",
            "secretAccessKey": "c2VjcmV0",
            "endpoint": "aHR0cHM6Ly9zMy5leGFtcGxlLmNvbQ==",
        },
        use_case=SecretUseCase.S3,
    )

    mock_created_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name="s3-secret",
            namespace=test_namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
            labels={USE_CASE_LABEL: "S3"},
        ),
    )

    with patch("app.secrets.service.list_kubernetes_secrets", return_value=[]):
        with patch("app.secrets.service.create_kubernetes_secret", return_value=mock_created_secret):
            result = await service.create_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_in=secret_data,
            )

    assert result.metadata.name == "s3-secret"
    assert result.use_case == SecretUseCase.S3


@pytest.mark.asyncio
async def test_delete_secret(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test deleting a secret."""
    secret_name = "delete-me"

    mock_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name=secret_name,
            namespace=test_namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
        ),
    )

    with patch("app.secrets.service.get_kubernetes_secret", return_value=mock_secret):
        with patch("app.secrets.service.delete_kubernetes_secret") as mock_delete:
            await service.delete_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_name=secret_name,
            )

            mock_delete.assert_called_once_with(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                name=secret_name,
            )


@pytest.mark.asyncio
async def test_delete_secret_not_found(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test deleting non-existent secret raises NotFoundException."""
    with patch("app.secrets.service.get_kubernetes_secret", return_value=None):
        with pytest.raises(NotFoundException, match="not found"):
            await service.delete_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_name="nonexistent",
            )


@pytest.mark.asyncio
async def test_delete_secret_with_owner_reference(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test deleting a secret with ownerReference raises ConflictException."""
    secret_name = "managed-secret"

    mock_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name=secret_name,
            namespace=test_namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
            owner_references=[{"kind": "Deployment", "name": "my-app"}],
        ),
    )

    with patch("app.secrets.service.get_kubernetes_secret", return_value=mock_secret):
        with pytest.raises(ConflictException, match="managed by another resource"):
            await service.delete_secret(
                kube_client=mock_kube_client,
                namespace=test_namespace,
                secret_name=secret_name,
            )


@pytest.mark.asyncio
async def test_delete_secret_k8s_404_ignored(
    test_namespace: str,
    mock_kube_client: AsyncMock,
) -> None:
    """Test deletion raises NotFoundException when K8s returns 404."""
    secret_name = "already-deleted"

    mock_secret = KubernetesSecretResource(
        metadata=K8sMetadata(
            name=secret_name,
            namespace=test_namespace,
            creation_timestamp="2025-01-01T00:00:00Z",
        ),
    )

    # Simulate 404 error during deletion
    api_exception = ApiException(status=404)

    with patch("app.secrets.service.get_kubernetes_secret", return_value=mock_secret):
        with patch("app.secrets.service.delete_kubernetes_secret", side_effect=api_exception):
            with pytest.raises(NotFoundException, match="not found"):
                await service.delete_secret(
                    kube_client=mock_kube_client,
                    namespace=test_namespace,
                    secret_name=secret_name,
                )
