# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Finds and reclaims data left behind by deleted projects. Everything here is irreversible."""

import asyncio
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.slugs import slugify

from ..apikeys.repository import get_all_api_keys
from ..apikeys.service import delete_api_key_from_store
from ..datasets.repository import delete_dataset_by_id, get_all_datasets
from ..dispatch.kube_client import KubernetesClient
from ..minio.client import MinioClient
from ..minio.config import MINIO_BUCKET
from ..openbao.client import OpenBaoClient
from ..projects.crds import Namespace
from .config import CLEANUP_SKEW_MARGIN_SECONDS

SKEW_MARGIN = timedelta(seconds=CLEANUP_SKEW_MARGIN_SECONDS)


@dataclass
class ReclaimOutcome:
    credentials_revoked: int = 0
    datasets_removed: int = 0
    prefixes_removed: int = 0
    bytes_removed: int = 0
    # Items that cannot be safely reclaimed under the current namespace view. Expected, not an error:
    # a name can be in use again by the time this cycle evaluates it.
    skipped: int = 0
    failed: int = 0


async def reclaim(
    session: AsyncSession,
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    openbao_client: OpenBaoClient | None,
    live_namespaces: list[Namespace],
    dry_run: bool = False,
) -> ReclaimOutcome:
    """Find and delete orphaned data using the current namespace view.

    Ordering within an item is a safety property. The database row goes last, because it carries
    the key id needed to revoke a credential and the path needed to find the objects: failing
    before the row is written off leaves something retryable, whereas failing after it would strand
    a live credential with nothing left pointing at it.

    `dry_run` reaches every verdict and reports it without acting on any of it. The same traversal
    decides both ways, so what it names is what a real run would remove — a separate preview could
    drift from the thing it claims to preview.
    """
    if openbao_client is None and not dry_run:
        # delete_api_key_from_store refuses each key without a client. Checked once here so a
        # run with the store disabled fails before it touches anything, instead of logging one
        # refusal per orphaned key and reporting a partial sweep.
        raise ValueError("Object storage credentials cannot be revoked without OpenBao")

    outcome = ReclaimOutcome()
    await _reclaim_keys(session, kube_client, openbao_client, live_namespaces, outcome, dry_run)
    await _reclaim_datasets(session, live_namespaces, outcome, dry_run)
    await _reclaim_storage(minio_client, live_namespaces, outcome, dry_run)
    if dry_run:
        # Nothing was deleted, but reads opened a transaction; end it without writing.
        await session.rollback()
    else:
        await session.commit()

    verb = "Would reclaim" if dry_run else "Reclaimed"
    logger.info(
        f"{verb} {outcome.credentials_revoked} credential(s), {outcome.datasets_removed} dataset record(s) "
        f"and {outcome.prefixes_removed} storage prefix(es) "
        f"({outcome.bytes_removed} bytes; {outcome.skipped} skipped, {outcome.failed} failed)"
    )
    return outcome


async def _reclaim_keys(
    session: AsyncSession,
    kube_client: KubernetesClient,
    openbao_client: OpenBaoClient | None,
    live_namespaces: list[Namespace],
    outcome: ReclaimOutcome,
    dry_run: bool,
) -> None:
    by_name = {namespace.name: namespace for namespace in live_namespaces}
    api_keys = await get_all_api_keys(session)

    for key in api_keys:
        if not _should_be_reclaimed(key.created_at, by_name.get(key.namespace)):
            outcome.skipped += 1
            continue
        try:
            if not dry_run:
                await delete_api_key_from_store(session, key.namespace, key.id, kube_client, openbao_client)
            outcome.credentials_revoked += 1
            verb = "Would revoke" if dry_run else "Revoked"
            logger.info(f"{verb} API key '{key.display_name}' from deleted project '{key.namespace}'")
        except Exception as e:
            # One unreclaimable item must not strand the rest; the next cycle retries it.
            outcome.failed += 1
            logger.error(f"Failed to revoke API key {key.id} in '{key.namespace}': {e}")


async def _reclaim_datasets(
    session: AsyncSession,
    live_namespaces: list[Namespace],
    outcome: ReclaimOutcome,
    dry_run: bool,
) -> None:
    by_name = {namespace.name: namespace for namespace in live_namespaces}
    datasets = await get_all_datasets(session)

    for dataset in datasets:
        if not _should_be_reclaimed(dataset.created_at, by_name.get(dataset.namespace)):
            outcome.skipped += 1
            continue
        try:
            # The object itself sits under the namespace prefix and goes with it below; this
            # drops the record that would otherwise be left describing something absent.
            if dry_run or await delete_dataset_by_id(session, dataset.id, dataset.namespace):
                outcome.datasets_removed += 1
                verb = "Would remove" if dry_run else "Removed"
                logger.info(f"{verb} dataset record '{dataset.name}' from deleted project '{dataset.namespace}'")
        except Exception as e:
            outcome.failed += 1
            logger.error(f"Failed to remove dataset {dataset.id} in '{dataset.namespace}': {e}")


async def _reclaim_storage(
    minio_client: MinioClient,
    live_namespaces: list[Namespace],
    outcome: ReclaimOutcome,
    dry_run: bool,
) -> None:
    by_prefix = _index_by_prefix(live_namespaces)
    prefixes = await asyncio.to_thread(minio_client.list_top_level_prefixes, MINIO_BUCKET)

    for prefix in prefixes:
        # Resolved to every holder rather than one, because a prefix can answer to more than one
        # live namespace. Collapsing them to a single arbitrary holder would let a tree be judged
        # against a namespace that does not own it, and deleted while another one does.
        holders = by_prefix.get(prefix.rstrip("/"), [])
        if len(holders) > 1:
            outcome.skipped += 1
            continue
        try:
            objects = await asyncio.to_thread(minio_client.get_object_details, MINIO_BUCKET, prefix)
        except Exception as e:
            outcome.failed += 1
            logger.error(f"Failed to read storage prefix '{prefix}': {e}")
            continue

        dated = [obj for obj in objects if obj.last_modified is not None]
        if not dated:
            # Emptied since the listing, or carrying nothing to date it against; either way not ours
            # to condemn on this pass.
            outcome.skipped += 1
            continue

        newest = max(obj.last_modified for obj in dated)
        if not _should_be_reclaimed(newest, holders[0] if holders else None):
            outcome.skipped += 1
            continue

        # Only the objects just listed and judged. Deleting by prefix would also take whatever
        # landed while this ran, on the strength of a verdict reached before it existed.
        names = [obj.object_name for obj in objects if obj.object_name is not None]
        reclaimed_bytes = sum(obj.size or 0 for obj in objects)
        try:
            if not dry_run:
                await asyncio.to_thread(minio_client.delete_object_keys, MINIO_BUCKET, names)
            outcome.prefixes_removed += 1
            outcome.bytes_removed += reclaimed_bytes
            verb = "Would reclaim" if dry_run else "Reclaimed"
            logger.info(f"{verb} storage prefix '{prefix}' ({len(names)} object(s), {reclaimed_bytes} bytes)")
        except Exception as e:
            outcome.failed += 1
            logger.error(f"Failed to reclaim storage prefix '{prefix}': {e}")


def _index_by_prefix(namespaces: Iterable[Namespace]) -> dict[str, list[Namespace]]:
    """Group live namespaces by the storage prefix their writes land in.

    Keyed on the transform the write paths apply when they build a prefix, so the lookup follows
    that convention rather than assuming one. The transform collapses runs of hyphens, which
    namespace names are allowed to contain, so it is not injective: two live namespaces really can
    write into a single prefix.

    Project creation refuses a name whose storage prefix another namespace already holds, so a
    colliding pair can only be one that rule never got to vet: rows predating it, or namespaces
    the cluster agent reports rather than a user creating.
    """
    by_prefix: dict[str, list[Namespace]] = defaultdict(list)
    for namespace in namespaces:
        by_prefix[slugify(namespace.name)].append(namespace)
    return by_prefix


def _should_be_reclaimed(
    written_at: datetime,
    namespace: Namespace | None,
    margin: timedelta = SKEW_MARGIN,
) -> bool:
    """Whether data can be confidently attributed to a deleted project."""
    if namespace is None:
        return True

    if namespace.created_at is None:
        return False

    # Database, Kubernetes, and object-storage clients can return naive timestamps; interpret them
    # as UTC so a single mixed-awareness value cannot abort the reclamation pass.
    written_at_utc = written_at.replace(tzinfo=UTC) if written_at.tzinfo is None else written_at.astimezone(UTC)
    namespace_created_at_utc = (
        namespace.created_at.replace(tzinfo=UTC)
        if namespace.created_at.tzinfo is None
        else namespace.created_at.astimezone(UTC)
    )
    return written_at_utc < namespace_created_at_utc - margin
