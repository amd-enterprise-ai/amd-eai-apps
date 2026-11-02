# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Users service tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakPostError
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, ExternalServiceError, NotFoundException
from app.users.repository import get_user, get_user_by_email
from app.users.schemas import InviteUser, UserDetailsUpdate, UserResponse, UserRoleEnum, UserRolesUpdate
from app.users.service import (
    assign_roles_to_user,
    create_user,
    delete_user,
    edit_user_details,
    get_invited_users,
    get_user_details,
    get_users,
    resend_invitation,
)
from app.utilities.security import Roles
from tests import factory  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_user_details_handles_user_not_found_in_keycloak(db_session: AsyncSession) -> None:
    """Test handling when user exists in DB but not in Keycloak."""
    env = await factory.create_basic_test_environment(db_session)
    user = await factory.create_user(db_session, email="user@example.com", keycloak_user_id="kc_user_id")

    with (
        patch("app.users.service.get_user", return_value=None, autospec=True),
        patch("app.users.service.get_user_realm_roles", return_value=[], autospec=True),
        patch("app.users.service.get_user_groups", return_value=[], autospec=True),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        with pytest.raises(ExternalServiceError, match="User not found in Keycloak service"):
            await get_user_details(kc_admin, db_session, user)


@pytest.mark.asyncio
async def test_get_user_details_handles_no_user_roles(db_session: AsyncSession) -> None:
    """Test user details retrieval when user has no roles."""
    env = await factory.create_basic_test_environment(db_session)
    user = await factory.create_user(db_session, email="user@example.com", keycloak_user_id="kc_user_id")

    # Create a test project that the user should have access to via groups
    test_project = await factory.create_project(db_session, env.cluster, name="user-test-project")

    keycloak_user = {
        "firstName": "test",
        "lastName": "Test",
        "email": "user@example.com",
    }
    user_roles: list[str] = []
    user_groups = [
        {"name": "user-test-project", "id": "group-id-123", "path": "/org/user-test-project"},
        {"name": "other-group", "id": "group-id-456", "path": "/org/other-group"},
    ]

    with (
        patch("app.users.service.get_user", return_value=keycloak_user, autospec=True),
        patch("app.users.service.get_user_realm_roles", return_value=user_roles, autospec=True),
        patch("app.users.service.get_user_groups", return_value=user_groups, autospec=True),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await get_user_details(kc_admin, db_session, user)

    assert isinstance(result, UserResponse)
    assert result.email == "user@example.com"
    assert result.role == Roles.TEAM_MEMBER.value
    # Verify the user has access to the project matching the group name
    assert len(result.projects) == 1
    assert result.projects[0].name == "user-test-project"


@pytest.mark.asyncio
async def test_delete_user_success(db_session: AsyncSession) -> None:
    """Test successful user deletion from both DB and Keycloak."""
    env = await factory.create_basic_test_environment(db_session)
    user = await factory.create_user(
        db_session, email="user1@test.com", keycloak_user_id="03890db1-9627-4663-ae0b-6a74ef1ff638"
    )

    with patch("app.users.service.delete_user_from_keycloak", return_value=None, autospec=True) as mock_delete_keycloak:
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        await delete_user(kc_admin, db_session, user)

    mock_delete_keycloak.assert_called_once()

    deleted_user = await get_user(db_session, user.id)
    assert deleted_user is None


@pytest.mark.asyncio
async def test_assign_roles_to_user_success(db_session: AsyncSession) -> None:
    """Test successful role assignment to user."""
    env = await factory.create_basic_test_environment(db_session)
    target_user = await factory.create_user(
        db_session, email="user1@test.com", keycloak_user_id="03890db1-9627-4663-ae0b-6a74ef1ff638"
    )

    await factory.create_multiple_users(db_session, user_count=2, email_prefix="other_user")

    user_role_request = UserRolesUpdate(roles=[UserRoleEnum.PLATFORM_ADMIN])

    keycloak_roles = [
        {"id": "role-id-1", "name": "Platform Administrator"},
        {"id": "role-id-2", "name": "Team Member"},
    ]

    with (
        patch("app.users.service.assign_roles_to_user_keycloak", return_value=None) as mock_assign_roles,
        patch("app.users.service.unassign_roles_to_user", return_value=None),
        patch(
            "app.users.service.get_assigned_roles_to_user",
            return_value={
                "realmMappings": [
                    {
                        "id": "f527862a-af68-4191-986a-cbcb25f15c24",
                        "name": "default-roles-airm",
                    }
                ]
            },
        ),
        patch("app.users.service.get_all_available_realm_roles", return_value=keycloak_roles),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        await assign_roles_to_user(kc_admin, target_user, user_role_request, "admin")

    mock_assign_roles.assert_called_once_with(
        kc_admin=kc_admin,
        user_id="03890db1-9627-4663-ae0b-6a74ef1ff638",
        roles=[{"id": "role-id-1", "name": "Platform Administrator"}],
    )


@pytest.mark.asyncio
async def test_create_user_success(db_session: AsyncSession) -> None:
    """Test successful user creation with real database operations."""
    env = await factory.create_basic_test_environment(db_session)

    user_data = InviteUser(email="test@example.com", roles=[UserRoleEnum.PLATFORM_ADMIN])
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
        patch("app.users.service.create_user_in_keycloak", return_value="keycloak_user_id"),
        patch("app.users.service.assign_roles_to_user"),
        patch("app.users.service.send_verify_email"),
        patch("app.users.service.POST_REGISTRATION_REDIRECT_URL", "http://test-redirect-url.com"),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await create_user(kc_admin, db_session, user_data, creator)

    assert result.email == "test@example.com"
    assert result.created_by == creator

    db_user = await get_user_by_email(db_session, "test@example.com")
    assert db_user is not None
    assert db_user.email == "test@example.com"


@pytest.mark.asyncio
async def test_create_user_with_projects_success(db_session: AsyncSession) -> None:
    """Test successful user creation with real database operations."""
    env = await factory.create_basic_test_environment(db_session)

    user_data = InviteUser(email="test@example.com", roles=[UserRoleEnum.PLATFORM_ADMIN], project_ids=[env.project.id])
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
        patch("app.users.service.create_user_in_keycloak", return_value="keycloak_user_id"),
        patch("app.users.service.assign_roles_to_user"),
        patch("app.users.service.send_verify_email"),
        patch("app.users.service.assign_users_to_group") as mock_assign_users_to_group,
        patch("app.users.service.POST_REGISTRATION_REDIRECT_URL", "http://test-redirect-url.com"),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await create_user(kc_admin, db_session, user_data, creator)

    assert result.email == "test@example.com"
    assert result.created_by == creator

    mock_assign_users_to_group.assert_called_once()

    db_user = await get_user_by_email(db_session, "test@example.com")
    assert db_user is not None
    assert db_user.email == "test@example.com"


@pytest.mark.asyncio
async def test_create_user_duplicate_email_raises_conflict(db_session: AsyncSession) -> None:
    """Test that creating user with existing email raises ConflictException."""
    env = await factory.create_basic_test_environment(db_session)

    _ = await factory.create_user(db_session, email="existing@example.com")

    user_data = InviteUser(email="existing@example.com", roles=[UserRoleEnum.PLATFORM_ADMIN])
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)

        with pytest.raises(ConflictException, match="User with this email already exists"):
            await create_user(kc_admin, db_session, user_data, creator)


@pytest.mark.asyncio
async def test_get_users_with_real_data(db_session: AsyncSession) -> None:
    """Test retrieving users with real database data."""
    env = await factory.create_basic_test_environment(db_session)

    users = await factory.create_multiple_users(db_session, user_count=3)

    keycloak_users = [
        {
            "id": users[0].keycloak_user_id,
            "email": users[0].email,
            "firstName": "User",
            "lastName": "One",
            "enabled": True,
        },
        {
            "id": users[1].keycloak_user_id,
            "email": users[1].email,
            "firstName": "User",
            "lastName": "Two",
            "enabled": True,
        },
        {
            "id": users[2].keycloak_user_id,
            "email": users[2].email,
            "firstName": "User",
            "lastName": "Three",
            "enabled": False,
        },
    ]

    with (
        patch("app.users.service.get_users_from_keycloak", return_value=keycloak_users),
        patch("app.users.service.get_user_realm_roles", return_value=[]),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await get_users(kc_admin, db_session)

    assert len(result) == 3
    emails = [user.email for user in result]
    assert users[0].email in emails
    assert users[1].email in emails
    assert users[2].email in emails


@pytest.mark.asyncio
async def test_get_users_registers_keycloak_users_without_db_record(db_session: AsyncSession) -> None:
    """Federated users that exist only in Keycloak (e.g. logged in via AIWB/OKTA) get a local record."""
    await factory.create_basic_test_environment(db_session)
    db_user = await factory.create_user(db_session, email="db-user@example.com", keycloak_user_id=str(uuid4()))

    federated_keycloak_id = str(uuid4())
    keycloak_users = [
        {
            "id": db_user.keycloak_user_id,
            "email": db_user.email,
            "firstName": "Database",
            "lastName": "User",
        },
        {
            "id": federated_keycloak_id,
            "email": "federated@example.com",
            "firstName": "Federated",
            "lastName": "User",
        },
    ]
    with (
        patch("app.users.service.get_users_from_keycloak", return_value=keycloak_users),
        patch("app.users.service.get_users_in_role", return_value=[]),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await get_users(kc_admin, db_session)
    assert len(result) == 2
    result_by_email = {user.email: user for user in result}
    federated_user = result_by_email["federated@example.com"]
    assert federated_user.role == Roles.TEAM_MEMBER.value
    assert federated_user.last_active_at is None
    assert result_by_email["db-user@example.com"].id == db_user.id
    # A local record is created so the user is usable by every per-user / project flow.
    registered = await get_user_by_email(db_session, "federated@example.com")
    assert registered is not None
    assert registered.keycloak_user_id == federated_keycloak_id
    assert registered.created_by == "federated"
    assert federated_user.id == registered.id


@pytest.mark.asyncio
async def test_get_users_does_not_duplicate_existing_records(db_session: AsyncSession) -> None:
    """Listing twice must not create duplicate local records for the same Keycloak user."""
    await factory.create_basic_test_environment(db_session)
    federated_keycloak_id = str(uuid4())
    keycloak_users = [
        {
            "id": federated_keycloak_id,
            "email": "federated@example.com",
            "firstName": "Federated",
            "lastName": "User",
        },
    ]
    with (
        patch("app.users.service.get_users_from_keycloak", return_value=keycloak_users),
        patch("app.users.service.get_users_in_role", return_value=[]),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        first = await get_users(kc_admin, db_session)
        second = await get_users(kc_admin, db_session)
    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id == second[0].id


@pytest.mark.asyncio
async def test_get_users_reuses_existing_record_on_email_conflict(db_session: AsyncSession) -> None:
    """A Keycloak user whose email already belongs to another local record reuses that record."""
    await factory.create_basic_test_environment(db_session)
    existing = await factory.create_user(db_session, email="shared@example.com", keycloak_user_id=str(uuid4()))
    keycloak_users = [
        {
            "id": str(uuid4()),
            "email": "shared@example.com",
            "firstName": "Federated",
            "lastName": "User",
        },
    ]
    with (
        patch("app.users.service.get_users_from_keycloak", return_value=keycloak_users),
        patch("app.users.service.get_users_in_role", return_value=[]),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await get_users(kc_admin, db_session)
    assert len(result) == 1
    assert result[0].id == existing.id


@pytest.mark.asyncio
async def test_create_user_with_no_roles(db_session: AsyncSession) -> None:
    """Test successful user creation without roles."""
    env = await factory.create_basic_test_environment(db_session)

    user_data = InviteUser(email="test@example.com", roles=[])  # No roles
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
        patch("app.users.service.create_user_in_keycloak", return_value="keycloak_user_id"),
        patch("app.users.service.assign_roles_to_user") as mock_assign_roles,
        patch("app.users.service.send_verify_email"),
        patch("app.users.service.POST_REGISTRATION_REDIRECT_URL", "http://test-redirect-url.com"),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await create_user(kc_admin, db_session, user_data, creator)

    assert result.email == "test@example.com"
    mock_assign_roles.assert_not_called()


@pytest.mark.asyncio
async def test_create_user_keycloak_error(db_session: AsyncSession) -> None:
    """Test user creation when Keycloak user creation fails."""
    env = await factory.create_basic_test_environment(db_session)

    user_data = InviteUser(email="test@example.com", roles=[UserRoleEnum.PLATFORM_ADMIN])
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
        patch("app.users.service.create_user_in_keycloak", side_effect=KeycloakPostError("Keycloak error")),
        patch("app.users.service.assign_roles_to_user"),
        patch("app.users.service.send_verify_email"),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)

        with pytest.raises(KeycloakPostError, match="Keycloak error"):
            await create_user(kc_admin, db_session, user_data, creator)

    db_user = await get_user_by_email(db_session, "test@example.com")
    assert db_user is None


@pytest.mark.asyncio
async def test_create_user_with_invalid_project_ids(db_session: AsyncSession) -> None:
    """Test user creation fails with invalid project IDs."""
    env = await factory.create_basic_test_environment(db_session)

    valid_project = env.project

    invalid_project_id = uuid4()

    user_data = InviteUser(
        email="test@example.com",
        roles=[UserRoleEnum.PLATFORM_ADMIN],
        project_ids=[valid_project.id, invalid_project_id],  # Mix of valid and invalid
    )
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)

        with pytest.raises(NotFoundException, match="Projects not found"):
            await create_user(kc_admin, db_session, user_data, creator)


@pytest.mark.asyncio
async def test_create_user_with_project_memberships(db_session: AsyncSession) -> None:
    """Test user creation with project membership assignment."""
    env = await factory.create_basic_test_environment(db_session)

    project1 = env.project
    project2 = await factory.create_project(db_session, env.cluster, name="Project 2")

    user_data = InviteUser(
        email="test@example.com", roles=[UserRoleEnum.PLATFORM_ADMIN], project_ids=[project1.id, project2.id]
    )
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
        patch("app.users.service.create_user_in_keycloak", return_value="keycloak_user_id"),
        patch("app.users.service.assign_roles_to_user"),
        patch("app.users.service.send_verify_email"),
        patch("app.users.service.POST_REGISTRATION_REDIRECT_URL", "http://test-redirect-url.com"),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await create_user(kc_admin, db_session, user_data, creator)

    assert result.email == "test@example.com"


@pytest.mark.asyncio
async def test_assign_roles_to_user_remove_platform_admin_role(db_session: AsyncSession) -> None:
    """Test successful removal of Platform Administrator role when other admins exist."""
    env = await factory.create_basic_test_environment(db_session)

    target_user = await factory.create_user(db_session, email="admin1@test.com", keycloak_user_id="admin1-id")
    other_admin = await factory.create_user(db_session, email="admin2@test.com", keycloak_user_id="admin2-id")

    user_role_request = UserRolesUpdate(roles=[])  # Remove all roles

    # Mock Keycloak responses showing multiple users have PA role
    keycloak_roles = [
        {"id": "role-id-1", "name": "Platform Administrator"},
        {"id": "role-id-2", "name": "Team Member"},
    ]

    with (
        patch("app.users.service.assign_roles_to_user_keycloak", return_value=None),
        patch("app.users.service.unassign_roles_to_user", return_value=None) as mock_unassign,
        patch(
            "app.users.service.get_assigned_roles_to_user",
            return_value={
                "realmMappings": [
                    {
                        "id": "role-id-1",
                        "name": "Platform Administrator",
                    }
                ]
            },
        ),
        patch("app.users.service.get_all_available_realm_roles", return_value=keycloak_roles),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        await assign_roles_to_user(kc_admin, target_user, user_role_request, "admin")

    mock_unassign.assert_called_once()


@pytest.mark.asyncio
async def test_edit_user_details(db_session: AsyncSession) -> None:
    """Test updating user profile details."""
    env = await factory.create_basic_test_environment(db_session)
    user = await factory.create_user(db_session, email="user@example.com", keycloak_user_id="user-kc-id")

    user_details = UserDetailsUpdate(first_name="NewFirstName", last_name="NewLastName")
    new_user_details = {
        "firstName": "NewFirstName",
        "lastName": "NewLastName",
    }

    with patch("app.users.service.update_user_details", return_value=None) as mock_update:
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        await edit_user_details(kc_admin, user, user_details, "updater")

    mock_update.assert_called_once_with(kc_admin=kc_admin, user_id=user.keycloak_user_id, user_details=new_user_details)
    assert user.updated_by == "updater"


@pytest.mark.asyncio
async def test_resend_invitation_success(db_session: AsyncSession) -> None:
    """Test successful invitation resend."""
    env = await factory.create_basic_test_environment(db_session)
    user = await factory.create_user(db_session, email="user@example.com", keycloak_user_id="user-kc-id")

    logged_in_user = "admin@example.com"
    keycloak_user = {
        "id": "user-kc-id",
        "email": "user@example.com",
    }

    with (
        patch("app.users.service.get_user", return_value=keycloak_user) as mock_get_user,
        patch("app.users.service.is_keycloak_user_inactive", return_value=True) as mock_is_inactive,
        patch("app.users.service.send_verify_email") as mock_send_email,
        patch("app.users.service.POST_REGISTRATION_REDIRECT_URL", "http://test-redirect-url.com"),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        await resend_invitation(kc_admin, user, logged_in_user)

    mock_get_user.assert_called_once_with(kc_admin=kc_admin, user_id="user-kc-id")
    mock_is_inactive.assert_called_once_with(keycloak_user)
    mock_send_email.assert_called_once_with(
        kc_admin=kc_admin, keycloak_user_id="user-kc-id", redirect_uri="http://test-redirect-url.com"
    )
    assert user.invited_by == logged_in_user
    assert user.invited_at is not None


@pytest.mark.asyncio
async def test_resend_invitation_user_not_found_keycloak(db_session: AsyncSession) -> None:
    """Test resend invitation when user not found in Keycloak."""
    env = await factory.create_basic_test_environment(db_session)
    user = await factory.create_user(db_session, email="user@example.com", keycloak_user_id="user-kc-id")

    logged_in_user = "admin@example.com"

    with (
        patch("app.users.service.get_user", return_value=None),
        patch("app.users.service.is_keycloak_user_inactive", return_value=True),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        with pytest.raises(ExternalServiceError, match="User lookup failed"):
            await resend_invitation(kc_admin, user, logged_in_user)


@pytest.mark.asyncio
async def test_resend_invitation_user_already_active(db_session: AsyncSession) -> None:
    """Test resend invitation when user is already active."""
    env = await factory.create_basic_test_environment(db_session)
    user = await factory.create_user(db_session, email="user@example.com", keycloak_user_id="user-kc-id")

    logged_in_user = "admin@example.com"
    keycloak_user = {
        "id": "user-kc-id",
        "email": "user@example.com",
        "firstName": "Test",
        "lastName": "User",
    }

    with (
        patch("app.users.service.get_user", return_value=keycloak_user),
        patch("app.users.service.is_keycloak_user_inactive", return_value=False),
        patch("app.users.service.send_verify_email"),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        with pytest.raises(ConflictException, match="User is already active"):
            await resend_invitation(kc_admin, user, logged_in_user)


@pytest.mark.asyncio
async def test_get_invited_users(db_session: AsyncSession) -> None:
    """Test getting invited users."""
    env = await factory.create_basic_test_environment(db_session)

    users = await factory.create_multiple_users(db_session, user_count=2)

    users[0].invited_at = datetime(2025, 1, 1, tzinfo=UTC)
    users[0].invited_by = "admin@example.com"
    users[1].invited_at = datetime(2025, 2, 1, tzinfo=UTC)
    users[1].invited_by = "admin@example.com"

    keycloak_users = [
        {"id": users[0].keycloak_user_id, "email": users[0].email},
        {"id": users[1].keycloak_user_id, "email": users[1].email},
    ]

    with (
        patch("app.users.service.get_users_in_role", return_value=[{"id": users[0].keycloak_user_id}]),
        patch("app.users.service.get_users_from_keycloak", return_value=keycloak_users),
        patch("app.users.service.is_keycloak_user_active", side_effect=lambda u: False),
        patch("app.users.service.is_keycloak_user_inactive", side_effect=lambda u: True),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await get_invited_users(kc_admin, db_session)

    assert len(result) == 2
    assert result[0].email == users[0].email
    assert result[0].invited_at == datetime(2025, 1, 1, tzinfo=UTC)
    assert result[1].email == users[1].email


@pytest.mark.asyncio
async def test_get_users_filters_inactive_users(db_session: AsyncSession) -> None:
    """Test that get_users only returns active users."""
    env = await factory.create_basic_test_environment(db_session)

    users = await factory.create_multiple_users(db_session, user_count=3)

    keycloak_users = [
        {
            "id": users[0].keycloak_user_id,
            "email": users[0].email,
            "firstName": "Active",
            "lastName": "User",
            "enabled": True,
        },
        {
            "id": users[1].keycloak_user_id,
            "email": users[1].email,
            "firstName": "Inactive",
            "lastName": "User",
            "enabled": False,
        },
        {
            "id": users[2].keycloak_user_id,
            "email": users[2].email,
            "firstName": "Another",
            "lastName": "Active",
            "enabled": True,
        },
    ]

    with (
        patch("app.users.service.get_users_from_keycloak", return_value=keycloak_users),
        patch("app.users.service.get_users_in_role", return_value=[]),
        patch("app.users.service.is_keycloak_user_active", side_effect=lambda u: u.get("enabled", False)),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await get_users(kc_admin, db_session)

    # Should only return 2 active users
    assert len(result) == 2
    emails = [user.email for user in result]
    assert users[0].email in emails
    assert users[1].email not in emails  # Inactive user should not be included
    assert users[2].email in emails


@pytest.mark.asyncio
async def test_get_user_details_with_platform_admin_role(db_session: AsyncSession) -> None:
    """Test user details retrieval when user is a Platform Administrator."""
    env = await factory.create_basic_test_environment(db_session)
    user = await factory.create_user(db_session, email="admin@example.com", keycloak_user_id="admin-kc-id")

    keycloak_user = {
        "id": "admin-kc-id",
        "firstName": "Admin",
        "lastName": "User",
        "email": "admin@example.com",
    }

    user_roles = [
        {"name": "Platform Administrator", "id": "role-id-1"},
    ]

    with (
        patch("app.users.service.get_user", return_value=keycloak_user),
        patch("app.users.service.get_user_realm_roles", return_value=user_roles),
        patch("app.users.service.get_user_groups", return_value=[]),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await get_user_details(kc_admin, db_session, user)

    assert result.email == "admin@example.com"
    assert result.role == Roles.PLATFORM_ADMINISTRATOR.value
    assert result.first_name == "Admin"
    assert result.last_name == "User"


@pytest.mark.asyncio
async def test_create_user_with_multiple_projects(db_session: AsyncSession) -> None:
    """Test user creation with assignment to multiple projects."""
    env = await factory.create_basic_test_environment(db_session)

    project1 = env.project
    project2 = await factory.create_project(db_session, env.cluster, name="Project 2")
    project3 = await factory.create_project(db_session, env.cluster, name="Project 3")

    user_data = InviteUser(
        email="multiproject@example.com", roles=[], project_ids=[project1.id, project2.id, project3.id]
    )
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
        patch("app.users.service.create_user_in_keycloak", return_value="keycloak_user_id"),
        patch("app.users.service.assign_users_to_group") as mock_assign_to_group,
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await create_user(kc_admin, db_session, user_data, creator)

    assert result.email == "multiproject@example.com"
    # Should be called 3 times, once for each project
    assert mock_assign_to_group.call_count == 3


@pytest.mark.asyncio
async def test_create_user_with_empty_project_ids_list(db_session: AsyncSession) -> None:
    """Test user creation with empty project_ids list doesn't assign to groups."""
    env = await factory.create_basic_test_environment(db_session)

    user_data = InviteUser(email="noprojects@example.com", roles=[], project_ids=[])
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
        patch("app.users.service.create_user_in_keycloak", return_value="keycloak_user_id"),
        patch("app.users.service.assign_users_to_group") as mock_assign_to_group,
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await create_user(kc_admin, db_session, user_data, creator)

    assert result.email == "noprojects@example.com"
    mock_assign_to_group.assert_not_called()


@pytest.mark.asyncio
async def test_create_user_sets_invited_fields(db_session: AsyncSession) -> None:
    """Test that created user has invited_at and invited_by fields set."""
    env = await factory.create_basic_test_environment(db_session)

    user_data = InviteUser(email="invited@example.com", roles=[])
    creator = "admin@example.com"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=None),
        patch("app.users.service.create_user_in_keycloak", return_value="keycloak_user_id"),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await create_user(kc_admin, db_session, user_data, creator)

    assert result.invited_by == creator
    assert result.invited_at is not None

    # Verify in database as well
    db_user = await get_user_by_email(db_session, "invited@example.com")
    assert db_user.invited_by == creator
    assert db_user.invited_at is not None


@pytest.mark.asyncio
async def test_create_user_with_existing_keycloak_user_uses_existing_id(db_session: AsyncSession) -> None:
    """Test that when Keycloak user exists, we use their existing ID."""
    env = await factory.create_basic_test_environment(db_session)

    existing_kc_user = {"id": "existing-kc-user-id", "email": "existing@example.com"}
    user_data = InviteUser(email="existing@example.com", roles=[])
    creator = "test_creator"

    with (
        patch("app.users.service.get_user_by_username_from_keycloak", return_value=existing_kc_user),
        patch("app.users.service.create_user_in_keycloak") as mock_create_kc_user,
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        result = await create_user(kc_admin, db_session, user_data, creator)

    # Should not create new user in Keycloak
    mock_create_kc_user.assert_not_called()

    # Should return InvitedUser response
    assert result.email == "existing@example.com"

    # Should use existing Keycloak user ID in database
    db_user = await get_user_by_email(db_session, "existing@example.com")
    assert db_user.keycloak_user_id == "existing-kc-user-id"


@pytest.mark.asyncio
async def test_assign_roles_when_platform_admin_role_not_found(db_session: AsyncSession) -> None:
    """Test role assignment when Platform Administrator role doesn't exist in Keycloak."""
    env = await factory.create_basic_test_environment(db_session)
    target_user = await factory.create_user(db_session, email="user@test.com", keycloak_user_id="user-id")

    user_role_request = UserRolesUpdate(roles=[UserRoleEnum.PLATFORM_ADMIN])

    # No Platform Administrator role in Keycloak
    keycloak_roles = [
        {"id": "role-id-1", "name": "Team Member"},
    ]

    with (
        patch("app.users.service.assign_roles_to_user_keycloak", return_value=None) as mock_assign_roles,
        patch("app.users.service.unassign_roles_to_user", return_value=None),
        patch("app.users.service.get_assigned_roles_to_user", return_value={"realmMappings": []}),
        patch("app.users.service.get_all_available_realm_roles", return_value=keycloak_roles),
    ):
        kc_admin = AsyncMock(spec=KeycloakAdmin)
        await assign_roles_to_user(kc_admin, target_user, user_role_request, "admin")

    # Should not call assign_roles since the role doesn't exist
    mock_assign_roles.assert_not_called()
