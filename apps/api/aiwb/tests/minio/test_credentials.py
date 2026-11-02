# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Unit tests for the MinIO credentials secret precondition."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from kubernetes_asyncio.client import ApiException

from api_common.exceptions import ExternalServiceError, ValidationException
from app.minio.config import MINIO_CREDENTIALS_SECRET_NAME
from app.minio.credentials import verify_minio_credentials_secret


@pytest.mark.asyncio
async def test_verify_minio_credentials_secret_passes_when_present(mock_kube_client: AsyncMock) -> None:
    """No exception is raised when the platform-provisioned secret exists."""
    mock_kube_client.core_v1.read_namespaced_secret = AsyncMock(return_value=MagicMock())

    await verify_minio_credentials_secret(mock_kube_client, "test-namespace")

    mock_kube_client.core_v1.read_namespaced_secret.assert_called_once_with(
        name=MINIO_CREDENTIALS_SECRET_NAME, namespace="test-namespace"
    )


@pytest.mark.asyncio
async def test_verify_minio_credentials_secret_raises_400_when_missing(mock_kube_client: AsyncMock) -> None:
    """A missing MinIO credentials secret raises ValidationException (400) with
    an actionable message so the caller knows exactly what to provision."""
    mock_kube_client.core_v1.read_namespaced_secret.side_effect = ApiException(status=404)

    with pytest.raises(ValidationException, match=MINIO_CREDENTIALS_SECRET_NAME):
        await verify_minio_credentials_secret(mock_kube_client, "test-namespace")


@pytest.mark.asyncio
async def test_verify_minio_credentials_secret_wraps_non_404_errors_as_external_service_error(
    mock_kube_client: AsyncMock,
) -> None:
    """Non-404 Kubernetes errors must surface as ExternalServiceError (502) so they
    are handled consistently at the service layer instead of leaking the async
    ApiException type that AIWB's exception handler does not recognise."""
    api_error = ApiException(status=403, reason="Forbidden")
    mock_kube_client.core_v1.read_namespaced_secret.side_effect = api_error

    with pytest.raises(ExternalServiceError) as exc_info:
        await verify_minio_credentials_secret(mock_kube_client, "test-namespace")

    assert exc_info.value.__cause__ is api_error
