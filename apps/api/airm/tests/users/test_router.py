# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from api_common.exceptions import ConflictException
from app import app  # type: ignore
from app.users.schemas import InvitedUser, InviteUser, UserResponse, UserRoleEnum
from app.utilities.security import Roles
from tests.dependency_overrides import (
    ADMIN_EMAIL_WITH_KC_ADMIN_OVERRIDES,
    ADMIN_FORBIDDEN_OVERRIDES,
    ADMIN_SESSION_OVERRIDES,
    override_dependencies,
)


@pytest.mark.asyncio
@patch(
    "app.users.router.get_users_from_db",
    return_value=[
        UserResponse(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            id="0aa18e92-002c-45b7-a06e-dcdb0277974c",
            role=Roles.TEAM_MEMBER.value,
            created_at="2023-01-01T00:00:00Z",
            updated_at="2023-01-01T00:00:00Z",
            created_by="test@example.com",
            updated_by="test@example.com",
        )
    ],
)
@override_dependencies(ADMIN_SESSION_OVERRIDES)
async def test_get_users_success(_: MagicMock) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/users")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "data": [
            {
                "firstName": "John",
                "lastName": "Doe",
                "email": "john.doe@example.com",
                "id": "0aa18e92-002c-45b7-a06e-dcdb0277974c",
                "role": "Team Member",
                "createdAt": "2023-01-01T00:00:00Z",
                "updatedAt": "2023-01-01T00:00:00Z",
                "createdBy": "test@example.com",
                "updatedBy": "test@example.com",
                "lastActiveAt": None,
            }
        ]
    }


@pytest.mark.asyncio
@override_dependencies(ADMIN_FORBIDDEN_OVERRIDES)
async def test_get_users_not_in_role() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/users")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch(
    "app.users.router.create_user",
    return_value=InvitedUser(
        id=UUID("0aa18e92-002c-45b7-a06e-dcdb0277974c"),
        email="newuser@example.com",
        role=Roles.TEAM_MEMBER.value,
        invited_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        invited_by="admin@example.com",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="admin@example.com",
        updated_by="admin@example.com",
    ),
)
@override_dependencies(ADMIN_EMAIL_WITH_KC_ADMIN_OVERRIDES)
async def test_create_user_success(mock_create_user: MagicMock) -> None:
    """Test that create_user endpoint returns 200 OK with InvitedUser response."""
    user_create = InviteUser(email="newuser@example.com", roles=[])

    with TestClient(app) as client:
        response = client.post("/v1/users", json=user_create.model_dump(by_alias=True))

    assert response.status_code == status.HTTP_200_OK

    response_data = response.json()
    assert response_data["id"] == "0aa18e92-002c-45b7-a06e-dcdb0277974c"
    assert response_data["email"] == "newuser@example.com"
    assert response_data["invitedBy"] == "admin@example.com"
    assert response_data["role"] == Roles.TEAM_MEMBER.value
    assert "invitedAt" in response_data

    mock_create_user.assert_called_once()


@pytest.mark.asyncio
@patch(
    "app.users.router.create_user",
    return_value=InvitedUser(
        id=UUID("0aa18e92-002c-45b7-a06e-dcdb0277974c"),
        email="newadmin@example.com",
        role=Roles.PLATFORM_ADMINISTRATOR.value,
        invited_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        invited_by="admin@example.com",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        created_by="admin@example.com",
        updated_by="admin@example.com",
    ),
)
@override_dependencies(ADMIN_EMAIL_WITH_KC_ADMIN_OVERRIDES)
async def test_create_user_as_platform_admin(mock_create_user: MagicMock) -> None:
    """Test that create_user correctly identifies platform admin role."""
    user_create = InviteUser(email="newadmin@example.com", roles=[UserRoleEnum.PLATFORM_ADMIN])

    with TestClient(app) as client:
        response = client.post("/v1/users", json=user_create.model_dump(by_alias=True))

    assert response.status_code == status.HTTP_200_OK

    response_data = response.json()
    assert response_data["email"] == "newadmin@example.com"
    assert response_data["role"] == Roles.PLATFORM_ADMINISTRATOR.value

    mock_create_user.assert_called_once()


@pytest.mark.asyncio
@override_dependencies(ADMIN_FORBIDDEN_OVERRIDES)
async def test_create_user_not_in_role() -> None:
    """Test that create_user returns 403 when user is not platform administrator."""
    user_create = InviteUser(email="newuser@example.com", roles=[UserRoleEnum.PLATFORM_ADMIN])

    with TestClient(app) as client:
        response = client.post("/v1/users", json=user_create.model_dump(by_alias=True))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@patch("app.users.router.create_user")
@override_dependencies(ADMIN_EMAIL_WITH_KC_ADMIN_OVERRIDES)
async def test_create_user_duplicate_email(mock_create_user: MagicMock) -> None:
    """Test that create_user returns 409 when user with email already exists."""
    mock_create_user.side_effect = ConflictException("User with this email already exists.")

    user_create = InviteUser(email="existing@example.com", roles=[UserRoleEnum.PLATFORM_ADMIN])

    with TestClient(app) as client:
        response = client.post("/v1/users", json=user_create.model_dump(by_alias=True))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": "User with this email already exists."}


@pytest.mark.asyncio
@override_dependencies(ADMIN_EMAIL_WITH_KC_ADMIN_OVERRIDES)
async def test_create_user_invalid_email() -> None:
    """Test that create_user returns 422 for invalid email format."""
    with TestClient(app) as client:
        response = client.post("/v1/users", json={"email": "invalid-email", "roles": []})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
