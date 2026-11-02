# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from pydantic import Field, computed_field

from api_common.collections import BasePaginationList, PaginationConditions
from api_common.schemas import BaseModel
from api_common.secrets import SecretUseCase

from .constants import (
    AIRM_USE_CASE_LABEL,
    DISPLAY_NAME_ANNOTATION,
    DISPLAY_NAME_MAX_LENGTH,
    DISPLAY_NAME_MIN_LENGTH,
    USE_CASE_LABEL,
)
from .crds import KubernetesSecretResource


class SecretListQuery(PaginationConditions):
    page: int = Field(default=1, ge=1)
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100)
    use_case: SecretUseCase | None = Field(default=None, description="Filter by use case")


class SecretResponse(KubernetesSecretResource):
    """Schema for secret read from Kubernetes - extends CRD with computed fields."""

    @computed_field
    def display_name(self) -> str:
        """User-visible name sourced from the display-name annotation, falling back to the K8s resource name."""
        return self.metadata.annotations.get(DISPLAY_NAME_ANNOTATION) or self.metadata.name

    @computed_field
    def use_case(self) -> SecretUseCase | None:
        """Extract use_case from labels, checking both AIWB and AIRM label keys."""
        use_case_str = self.metadata.labels.get(USE_CASE_LABEL) or self.metadata.labels.get(AIRM_USE_CASE_LABEL)
        return SecretUseCase(use_case_str) if use_case_str else None


class SecretsList(BasePaginationList):
    """Paginated list of secrets."""

    data: list[SecretResponse]


class SecretCreate(BaseModel):
    """Schema for creating a new Kubernetes Secret."""

    display_name: str = Field(
        description="User-visible name for the secret. Any characters are allowed; the K8s resource name is auto-generated.",
        min_length=DISPLAY_NAME_MIN_LENGTH,
        max_length=DISPLAY_NAME_MAX_LENGTH,
        examples=["hf-token", "openai-api-key"],
    )
    data: dict[str, str] = Field(
        description=(
            "Secret data as key-value pairs; values must be valid for the Kubernetes Secret `data` field "
            "(for example, base64-encoded strings) and are passed through without modification. "
            "Keys follow the camelCase API convention. For an S3 use case, include an access key and a "
            "secret key under an accepted alias (e.g. accessKeyId / secretAccessKey), optionally an endpoint."
        ),
        examples=[{"token": "aGZfeHh4eHh4eHh4eHh4eA=="}],
    )
    use_case: SecretUseCase | None = Field(default=None, description="Optional use case classification for the secret")
