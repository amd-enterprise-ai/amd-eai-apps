# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
from datetime import UTC, datetime

from keycloak import KeycloakAdmin
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, ExternalServiceError, NotFoundException
from api_common.models import set_updated_fields

from ..projects.models import Project
from ..projects.repository import get_projects, get_projects_by_names
from ..users.repository import get_user_by_email
from ..utilities.config import POST_REGISTRATION_REDIRECT_URL
from ..utilities.keycloak_admin import assign_roles_to_user as assign_roles_to_user_keycloak
from ..utilities.keycloak_admin import (
    assign_users_to_group,
    get_all_available_realm_roles,
    get_assigned_roles_to_user,
    get_user,
    get_user_groups,
    get_user_realm_roles,
    get_users_in_role,
    send_verify_email,
    unassign_roles_to_user,
    update_user_details,
)
from ..utilities.keycloak_admin import delete_user as delete_user_from_keycloak
from ..utilities.keycloak_admin import get_user_by_username as get_user_by_username_from_keycloak
from ..utilities.keycloak_admin import get_users as get_users_from_keycloak
from ..utilities.security import Roles
from .models import User as UserModel
from .repository import create_user as create_user_in_db
from .repository import delete_user as delete_user_from_db
from .repository import get_users as get_users_from_db
from .repository import get_users_by_keycloak_ids
from .schemas import (
    InvitedUser,
    InviteUser,
    UserDetailsUpdate,
    UserResponse,
    UserRoleEnum,
    UserRolesUpdate,
    UserWithProjects,
)
from .utils import (
    create_user_in_keycloak,
    is_keycloak_user_active,
    is_keycloak_user_inactive,
    merge_invited_user_details,
    merge_user_details,
    merge_user_details_with_projects,
)


async def delete_user(kc_admin: KeycloakAdmin, session: AsyncSession, user: UserModel) -> None:
    await delete_user_from_keycloak(kc_admin=kc_admin, user_id=user.keycloak_user_id)
    await delete_user_from_db(session, user.id)


async def assign_roles_to_user(
    kc_admin: KeycloakAdmin,
    user: UserModel,
    user_role_request: UserRolesUpdate,
    updater: str,
) -> None:
    roles_assigned_to_user, all_realm_roles = await asyncio.gather(
        get_assigned_roles_to_user(kc_admin=kc_admin, user_id=user.keycloak_user_id),
        get_all_available_realm_roles(kc_admin=kc_admin, user_id=user.keycloak_user_id),
    )

    user_platform_admin_role = next(
        (
            role
            for role in roles_assigned_to_user["realmMappings"]
            if role["name"] == Roles.PLATFORM_ADMINISTRATOR.value
        ),
        None,
    )
    platform_admin_role = next(
        (role for role in all_realm_roles if role["name"] == Roles.PLATFORM_ADMINISTRATOR.value),
        None,
    )

    if Roles.PLATFORM_ADMINISTRATOR.value in user_role_request.roles and not user_platform_admin_role:
        if platform_admin_role:
            await assign_roles_to_user_keycloak(
                kc_admin=kc_admin, user_id=user.keycloak_user_id, roles=[platform_admin_role]
            )

    elif user_platform_admin_role and not user_role_request.roles:
        await unassign_roles_to_user(kc_admin=kc_admin, user_id=user.keycloak_user_id, roles=[user_platform_admin_role])

    set_updated_fields(user, updater)


async def edit_user_details(
    kc_admin: KeycloakAdmin, user: UserModel, user_details: UserDetailsUpdate, updater: str
) -> None:
    new_user_details = {
        "firstName": user_details.first_name,
        "lastName": user_details.last_name,
    }
    await update_user_details(kc_admin=kc_admin, user_id=user.keycloak_user_id, user_details=new_user_details)
    set_updated_fields(user, updater)


async def resend_invitation(kc_admin: KeycloakAdmin, user: UserModel, logged_in_user: str) -> None:
    keycloak_user = await get_user(kc_admin=kc_admin, user_id=user.keycloak_user_id)

    if keycloak_user:
        if is_keycloak_user_inactive(keycloak_user):
            await send_verify_email(
                kc_admin=kc_admin, keycloak_user_id=user.keycloak_user_id, redirect_uri=POST_REGISTRATION_REDIRECT_URL
            )
            user.invited_by = logged_in_user
            user.invited_at = datetime.now(UTC)
        else:
            raise ConflictException("User is already active.")
    else:
        raise ExternalServiceError("User lookup failed.")


async def create_user(kc_admin: KeycloakAdmin, session: AsyncSession, user_in: InviteUser, creator: str) -> InvitedUser:
    all_projects = await get_projects(session)

    if user_in.project_ids:
        all_project_ids = {str(project.id) for project in all_projects}
        invalid_projects = [pid for pid in user_in.project_ids if str(pid) not in all_project_ids]

        if invalid_projects:
            raise NotFoundException(f"Projects not found: {', '.join(str(p) for p in invalid_projects)}")

    existing_user = await get_user_by_email(session, user_in.email)
    if existing_user:
        raise ConflictException("User with this email already exists.")

    keycloak_user = await get_user_by_username_from_keycloak(kc_admin=kc_admin, username=user_in.email)
    keycloak_user_id = keycloak_user["id"] if keycloak_user else None

    if not keycloak_user_id:
        keycloak_user_id = await create_user_in_keycloak(kc_admin=kc_admin, user_in=user_in)

    new_user = await create_user_in_db(session, user_in.email, keycloak_user_id, creator)

    new_user.invited_by = creator
    new_user.invited_at = datetime.now(UTC)

    if user_in.roles:
        await assign_roles_to_user(
            kc_admin,
            new_user,
            UserRolesUpdate(roles=user_in.roles),
            creator,
        )
    if user_in.project_ids:
        keycloak_group_ids = [
            project.keycloak_group_id for project in all_projects if project.id in user_in.project_ids
        ]
        for group_id in keycloak_group_ids:
            await assign_users_to_group(
                kc_admin=kc_admin,
                user_ids=[keycloak_user_id],
                group_id=group_id,
            )

    return merge_invited_user_details(
        new_user, {keycloak_user_id} if UserRoleEnum.PLATFORM_ADMIN in user_in.roles else set()
    )


async def get_users(kc_admin: KeycloakAdmin, session: AsyncSession) -> list[UserResponse]:
    platform_admin_users, keycloak_users, db_users = await asyncio.gather(
        get_users_in_role(kc_admin=kc_admin, role=Roles.PLATFORM_ADMINISTRATOR),
        get_users_from_keycloak(kc_admin=kc_admin),
        get_users_from_db(session),
    )

    db_users_by_keycloak_id = {user.keycloak_user_id: user for user in db_users}
    platform_admins = {pa["id"] for pa in platform_admin_users}

    active_keycloak_users = [user for user in keycloak_users if is_keycloak_user_active(user)]

    # Federated users (e.g. from OKTA) may exist only in Keycloak, so give them a local record
    # here; otherwise they are absent from the Users tab and cannot be assigned to projects.
    for keycloak_user in active_keycloak_users:
        if keycloak_user["id"] not in db_users_by_keycloak_id:
            if registered_user := await _register_federated_user(session, keycloak_user):
                db_users_by_keycloak_id[keycloak_user["id"]] = registered_user

    return [
        merge_user_details(
            keycloak_user=keycloak_user,
            user=db_user,
            platform_admins=platform_admins,
        )
        for keycloak_user in active_keycloak_users
        if (db_user := db_users_by_keycloak_id.get(keycloak_user["id"]))
    ]


async def _register_federated_user(session: AsyncSession, keycloak_user: dict) -> UserModel | None:
    """Create a local record for a Keycloak user that has no AIRM row yet.

    Returns the existing record instead when a concurrent request already created it or an
    invited user with the same email exists, and ``None`` when the Keycloak user has no email.
    """
    email = keycloak_user.get("email")
    keycloak_user_id = keycloak_user["id"]
    if not email:
        return None
    try:
        # SAVEPOINT so a unique-constraint conflict does not abort the surrounding transaction.
        async with session.begin_nested():
            return await create_user_in_db(session, email, keycloak_user_id, "federated")
    except ConflictException:
        # The conflict is on either keycloak_user_id (concurrent insert) or email (an existing
        # invited user); return whichever local record already claims this user.
        if existing := await get_users_by_keycloak_ids(session, [keycloak_user_id]):
            return existing[0]
        return await get_user_by_email(session, email)


async def get_invited_users(kc_admin: KeycloakAdmin, session: AsyncSession) -> list[InvitedUser]:
    platform_admin_users, keycloak_users, db_users = await asyncio.gather(
        get_users_in_role(kc_admin=kc_admin, role=Roles.PLATFORM_ADMINISTRATOR),
        get_users_from_keycloak(kc_admin=kc_admin),
        get_users_from_db(session),
    )

    keycloak_users_by_id = {user["id"]: user for user in keycloak_users}
    platform_admins = {pa["id"] for pa in platform_admin_users}
    return [
        merge_invited_user_details(
            user=user,
            platform_admins=platform_admins,
        )
        for user in db_users
        if (keycloak_user := keycloak_users_by_id.get(user.keycloak_user_id))
        and is_keycloak_user_inactive(keycloak_user)
    ]


async def get_user_details(kc_admin: KeycloakAdmin, session: AsyncSession, user: UserModel) -> UserWithProjects:
    keycloak_user = await get_user(kc_admin=kc_admin, user_id=user.keycloak_user_id)
    user_roles = await get_user_realm_roles(kc_admin=kc_admin, user_id=user.keycloak_user_id)

    if not keycloak_user:
        raise ExternalServiceError("User not found in Keycloak service")

    user_projects = await get_projects_for_user_groups(kc_admin, session, user.keycloak_user_id)

    return merge_user_details_with_projects(
        keycloak_user,
        user,
        (
            {user.keycloak_user_id}
            if any(role["name"] == Roles.PLATFORM_ADMINISTRATOR.value for role in user_roles)
            else set()
        ),
        user_projects,
    )


async def get_projects_for_user_groups(
    kc_admin: KeycloakAdmin, session: AsyncSession, keycloak_user_id: str
) -> list[Project]:
    user_groups = await get_user_groups(kc_admin=kc_admin, user_id=keycloak_user_id)
    group_names = [name for group in user_groups if (name := group.get("name"))]
    user_projects = await get_projects_by_names(session, group_names)
    return user_projects
