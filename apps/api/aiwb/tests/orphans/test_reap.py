# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.apikeys.models import ApiKey
from app.datasets.models import Dataset
from app.minio.client import MinioClient
from app.minio.config import MINIO_BUCKET
from app.openbao.client import OpenBaoClient
from app.orphans.reap import SKEW_MARGIN, reclaim
from app.projects.constants import NAMESPACE_ID_LABEL
from app.projects.crds import Namespace

NAMESPACE_CREATED = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
WELL_BEFORE = NAMESPACE_CREATED - SKEW_MARGIN - timedelta(days=7)
WELL_AFTER = NAMESPACE_CREATED + timedelta(days=7)


def namespace(name: str = "acme", created_at: datetime = NAMESPACE_CREATED) -> Namespace:
    return Namespace(
        name=name,
        labels={NAMESPACE_ID_LABEL: "3f2b1c4d-0000-4000-8000-000000000001"},
        created_at=created_at,
    )


def api_key(namespace_name: str = "acme", created_at: datetime = WELL_AFTER) -> ApiKey:
    return ApiKey(
        id=uuid4(),
        display_name="ci-token",
        truncated_key="amd_aim_api_key_••••••••1234",
        namespace=namespace_name,
        created_at=created_at,
    )


def dataset(namespace_name: str = "acme", created_at: datetime = WELL_AFTER) -> Dataset:
    return Dataset(
        id=uuid4(),
        name="training-set",
        description="",
        path="acme/datasets/x.jsonl",
        namespace=namespace_name,
        created_at=created_at,
    )


def stored_object(name: str, modified: datetime = WELL_AFTER, size: int = 1024) -> MagicMock:
    obj = MagicMock()
    obj.object_name = name
    obj.last_modified = modified
    obj.size = size
    return obj


def clients(
    live: list[Namespace] | None = None,
    objects: list[MagicMock] | None = None,
) -> tuple[AsyncMock, MagicMock, MagicMock, AsyncMock, list[Namespace]]:
    """Return (session, kube, minio, openbao) with the namespace list the reaper will use.

    `objects` is what the prefix holds when the reaper lists it.
    """
    session = AsyncMock(spec=AsyncSession)
    kube = MagicMock()
    minio = MagicMock(spec=MinioClient)
    minio.get_object_details.return_value = (
        objects if objects is not None else [stored_object("acme/a.txt"), stored_object("acme/b.txt")]
    )
    minio.list_top_level_prefixes.return_value = []
    openbao = AsyncMock(spec=OpenBaoClient)
    return session, kube, minio, openbao, live if live is not None else [namespace("unrelated")]


@pytest.fixture(autouse=True)
def no_database_candidates():
    with (
        patch("app.orphans.reap.get_all_api_keys", AsyncMock(return_value=[])),
        patch("app.orphans.reap.get_all_datasets", AsyncMock(return_value=[])),
    ):
        yield


@pytest.mark.asyncio
async def test_a_reused_name_loses_only_its_predecessors_keys() -> None:
    """The rule is per row, not per namespace — which is the reason it reads timestamps at all.

    A namespace that took a freed name holds its own keys and its predecessor's under the one name.
    Judging by name alone would either spare both or condemn both; only the older is orphaned.
    """
    session, kube, minio, openbao, _ = clients()
    successor = [namespace("acme", created_at=NAMESPACE_CREATED)]
    predecessors_key = api_key(created_at=WELL_BEFORE)
    successors_key = api_key(created_at=WELL_AFTER)

    with patch("app.orphans.reap.get_all_api_keys", AsyncMock(return_value=[predecessors_key, successors_key])):
        with patch("app.orphans.reap.delete_api_key_from_store", AsyncMock()) as delete_key:
            outcome = await reclaim(session, kube, minio, openbao, successor)

    assert outcome.credentials_revoked == 1
    assert [call.args[2] for call in delete_key.await_args_list] == [predecessors_key.id]


@pytest.mark.asyncio
async def test_a_dry_run_reaches_the_same_verdicts_and_deletes_nothing() -> None:
    """The preview has to come from the same traversal, or it is not a preview of this run."""
    session, kube, minio, openbao, live = clients()
    minio.list_top_level_prefixes.return_value = ["acme/"]

    with patch("app.orphans.reap.get_all_api_keys", AsyncMock(return_value=[api_key()])):
        with patch("app.orphans.reap.delete_api_key_from_store", AsyncMock()) as delete_key:
            outcome = await reclaim(session, kube, minio, openbao, live, dry_run=True)

    # Named as reclaimable, but nothing was touched and nothing was committed.
    assert outcome.prefixes_removed == 1
    assert outcome.credentials_revoked == 1
    minio.delete_object_keys.assert_not_called()
    delete_key.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_dry_run_does_not_need_the_credential_store() -> None:
    """Previewing revokes nothing, so an unreachable OpenBao must not block looking."""
    session, kube, minio, _, live = clients()

    outcome = await reclaim(session, kube, minio, None, live, dry_run=True)

    assert outcome.failed == 0


@pytest.mark.asyncio
async def test_reclaims_storage_of_a_deleted_project() -> None:
    session, kube, minio, openbao, live = clients()
    minio.list_top_level_prefixes.return_value = ["acme/"]

    outcome = await reclaim(session, kube, minio, openbao, live)

    minio.delete_object_keys.assert_called_once_with(MINIO_BUCKET, ["acme/a.txt", "acme/b.txt"])
    assert outcome.prefixes_removed == 1
    # From the listing used for deletion.
    assert outcome.bytes_removed == 2048


@pytest.mark.asyncio
async def test_revokes_the_credential_not_just_the_row() -> None:
    """The token outlives the project, so dropping the record alone leaves a working key."""
    key = api_key()
    session, kube, minio, openbao, live = clients()

    with (
        patch("app.orphans.reap.get_all_api_keys", AsyncMock(return_value=[key])),
        patch("app.orphans.reap.delete_api_key_from_store", AsyncMock()) as delete_key,
    ):
        outcome = await reclaim(session, kube, minio, openbao, live)

    assert outcome.credentials_revoked == 1
    # The store deletion is what revokes the token; passing openbao through is the whole point.
    assert delete_key.await_args_list[0].args[4] is openbao


@pytest.mark.asyncio
async def test_a_live_namespace_name_is_spared() -> None:
    """Data dated after the current namespace was created is not orphaned."""
    session, kube, minio, openbao, _ = clients()
    reappeared = [namespace("acme", created_at=WELL_BEFORE)]
    minio.list_top_level_prefixes.return_value = ["acme/"]

    with patch("app.orphans.reap.get_all_api_keys", AsyncMock(return_value=[api_key()])):
        outcome = await reclaim(session, kube, minio, openbao, reappeared)

    minio.delete_object_keys.assert_not_called()
    # The key and the prefix both, so a skip is visible wherever it happens.
    assert outcome.skipped == 2
    assert outcome.prefixes_removed == 0
    assert outcome.credentials_revoked == 0


@pytest.mark.asyncio
async def test_a_successor_writing_under_the_reused_name_is_spared() -> None:
    """A recent object keeps a reused storage prefix live."""
    successor_created = NAMESPACE_CREATED + timedelta(days=30)
    session, kube, minio, openbao, _ = clients(
        live=[namespace("acme", created_at=successor_created)],
        objects=[stored_object("acme/new.txt", modified=successor_created + timedelta(hours=1))],
    )
    minio.list_top_level_prefixes.return_value = ["acme/"]

    outcome = await reclaim(session, kube, minio, openbao, [namespace("acme", successor_created)])

    minio.delete_object_keys.assert_not_called()
    assert outcome.skipped == 1
    assert outcome.prefixes_removed == 0


@pytest.mark.asyncio
async def test_only_the_objects_that_were_judged_are_deleted() -> None:
    """Deleting by prefix would also take objects that were not listed."""
    session, kube, minio, openbao, live = clients(
        objects=[stored_object("acme/one.txt"), stored_object("acme/two.txt")]
    )
    minio.list_top_level_prefixes.return_value = ["acme/"]

    await reclaim(session, kube, minio, openbao, live)

    minio.delete_objects.assert_not_called()
    minio.delete_object_keys.assert_called_once_with(MINIO_BUCKET, ["acme/one.txt", "acme/two.txt"])


@pytest.mark.asyncio
async def test_an_empty_prefix_is_left_alone() -> None:
    session, kube, minio, openbao, live = clients(objects=[])
    minio.list_top_level_prefixes.return_value = ["acme/"]

    outcome = await reclaim(session, kube, minio, openbao, live)

    minio.delete_object_keys.assert_not_called()
    assert outcome.skipped == 1


@pytest.mark.asyncio
async def test_a_prefix_two_live_namespaces_answer_to_is_spared() -> None:
    """A prefix with multiple live holders cannot be attributed safely.

    `slugify` collapses runs of hyphens that namespace names may contain, so two live projects can
    write into one prefix. Resolving that prefix to a single arbitrary holder would judge the tree
    against a namespace that does not own it — and delete it while the other one does.
    """
    session, kube, minio, openbao, _ = clients()
    # One is younger than the data, which on its own would read as "a successor took the name".
    collided = [
        namespace("data--science", created_at=WELL_BEFORE),
        namespace("data-science", created_at=NAMESPACE_CREATED + timedelta(days=30)),
    ]
    minio.list_top_level_prefixes.return_value = ["data-science/"]

    outcome = await reclaim(session, kube, minio, openbao, collided)

    minio.delete_object_keys.assert_not_called()
    assert outcome.skipped == 1
    assert outcome.prefixes_removed == 0


@pytest.mark.asyncio
async def test_one_failure_does_not_strand_the_rest() -> None:
    """A prefix that cannot be removed must not stop the credentials from being revoked."""
    session, kube, minio, openbao, live = clients()
    minio.delete_object_keys.side_effect = RuntimeError("storage unavailable")
    minio.list_top_level_prefixes.return_value = ["acme/"]
    key = api_key()

    with (
        patch("app.orphans.reap.get_all_api_keys", AsyncMock(return_value=[key])),
        patch("app.orphans.reap.delete_api_key_from_store", AsyncMock()),
    ):
        outcome = await reclaim(session, kube, minio, openbao, live)

    assert outcome.failed == 1
    assert outcome.credentials_revoked == 1


@pytest.mark.asyncio
async def test_dataset_records_go_with_the_storage_they_describe() -> None:
    session, kube, minio, openbao, live = clients()
    data = dataset()

    with (
        patch("app.orphans.reap.get_all_datasets", AsyncMock(return_value=[data])),
        patch("app.orphans.reap.delete_dataset_by_id", AsyncMock(return_value=True)) as delete_dataset,
    ):
        outcome = await reclaim(session, kube, minio, openbao, live)

    assert outcome.datasets_removed == 1
    delete_dataset.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_orphaned_data_deletes_nothing() -> None:
    session, kube, minio, openbao, live = clients()

    outcome = await reclaim(session, kube, minio, openbao, live)

    minio.delete_object_keys.assert_not_called()
    assert outcome == type(outcome)()
