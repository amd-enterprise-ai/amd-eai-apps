# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Multi-doc YAML manifest helpers for the custom-model DR mirror.

The S3 manifest is the durable mirror of the AIMModel + AIMProfile copy
CRs for an onboarded custom model. CR documents are addressed by
``(kind, metadata.name)`` so re-onboards replace in place rather than
duplicate.
"""

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

import yaml
from loguru import logger
from minio.error import S3Error
from tenacity import retry, stop_after_attempt, wait_exponential

from api_common.exceptions import ExternalServiceError

from ..minio import MinioClient
from ..minio.client import map_s3_error_to_domain_exception
from ..minio.config import MINIO_MAX_ATTEMPTS, MINIO_MAX_WAIT, MINIO_MIN_WAIT

ManifestDocument = dict


def _document_identity(document: ManifestDocument) -> tuple[str, str]:
    kind = document.get("kind")
    raw_metadata = document.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    name = metadata.get("name")
    # Require non-empty strings: truthy-but-unhashable shapes (``kind: [..]``,
    # ``name: {..}``) would otherwise crash the dict-key lookup downstream
    # with an opaque ``TypeError: unhashable type``.
    if not isinstance(kind, str) or not kind or not isinstance(name, str) or not name:
        raise ValueError(
            "Manifest document must carry both 'kind' and 'metadata.name' as non-empty strings to be addressable; "
            f"got kind={kind!r}, name={name!r}"
        )
    return kind, name


def serialize_manifest(documents: Iterable[ManifestDocument]) -> bytes:
    """Serialize CR documents to a multi-doc YAML payload.

    ``explicit_start=True`` keeps the output append-compatible: a later
    writer can stream a new document onto the end without rewriting,
    and ``kubectl apply -f`` sees the same document boundary regardless
    of how many CRs the manifest currently holds.
    """
    docs = list(documents)
    if not docs:
        raise ValueError("Cannot serialize an empty manifest")
    for doc in docs:
        # Validate up-front so we never emit a half-built manifest.
        _document_identity(doc)
    return yaml.safe_dump_all(docs, sort_keys=False, default_flow_style=False, explicit_start=True).encode("utf-8")


def parse_manifest(content: bytes) -> list[ManifestDocument]:
    """Parse a multi-doc YAML manifest into a list of CR documents.

    Parse-side failures (invalid YAML, non-mapping doc, missing or
    non-string identity) surface as ``ExternalServiceError`` to flag
    storage corruption distinctly from the producer-side ``ValueError``
    that ``serialize_manifest`` / ``upsert_manifest_documents`` raise on
    programmer bugs.
    """
    try:
        loaded = list(yaml.safe_load_all(content))
    except yaml.YAMLError as e:
        raise ExternalServiceError(f"Manifest is not valid YAML: {e}") from e

    documents: list[ManifestDocument] = []
    for doc in loaded:
        if doc is None:
            continue
        if not isinstance(doc, dict):
            raise ExternalServiceError(
                f"Manifest contains a non-mapping document of type {type(doc).__name__}; "
                "expected one Kubernetes CR per document."
            )
        try:
            _document_identity(doc)
        except ValueError as e:
            raise ExternalServiceError(f"Manifest from storage is malformed: {e}") from e
        documents.append(doc)
    return documents


def upsert_manifest_documents(
    existing: Iterable[ManifestDocument],
    new_documents: Iterable[ManifestDocument],
) -> list[ManifestDocument]:
    """Merge new CR documents into an existing manifest by (kind, name) identity.

    Order of first occurrence in ``existing`` is preserved; duplicates
    already in ``existing`` are collapsed (last-seen wins). Without
    deduping, a later upsert would only replace the *last* duplicate
    and leave older copies in place — breaking the "never duplicate by
    identity" contract on re-onboard.

    Returned documents share references with the inputs; callers that
    intend to mutate must ``copy.deepcopy`` first.
    """
    merged: list[ManifestDocument] = []
    index_by_identity: dict[tuple[str, str], int] = {}
    for doc in existing:
        identity = _document_identity(doc)
        if identity in index_by_identity:
            merged[index_by_identity[identity]] = doc
        else:
            index_by_identity[identity] = len(merged)
            merged.append(doc)

    for new_doc in new_documents:
        identity = _document_identity(new_doc)
        if identity in index_by_identity:
            merged[index_by_identity[identity]] = new_doc
        else:
            index_by_identity[identity] = len(merged)
            merged.append(new_doc)
    return merged


def remove_manifest_documents(
    existing: Iterable[ManifestDocument],
    identities: set[tuple[str, str]],
) -> list[ManifestDocument]:
    """Drop documents whose ``(kind, metadata.name)`` is in ``identities``; order preserved.

    The inverse of :func:`upsert_manifest_documents`: used when a CR is deleted
    so its stale mirror document does not linger in the manifest. Documents not
    named in ``identities`` (notably the AIMModel scaffold) are left untouched,
    so the returned list keeps the manifest reapplyable.
    """
    return [doc for doc in existing if _document_identity(doc) not in identities]


# A manifest update is a non-atomic read → upsert → write against a shared S3
# object. Without serialization, two concurrent writers can both read the same
# prior state and the later upload overwrites the earlier writer's documents.
# minio-py 7.2.x does not expose ``If-Match`` on ``put_object``, so true
# ETag-based optimistic concurrency would require bypassing the SDK; this
# in-process lock is the lighter alternative that closes the same-worker
# collision window. Cross-worker writers remain unserialized.
_manifest_write_locks: dict[tuple[str, str], asyncio.Lock] = {}
# Guards mutation of the registry so two coroutines racing for the same key
# get a single shared Lock instance rather than each creating their own.
_manifest_write_locks_registry_guard = asyncio.Lock()


@asynccontextmanager
async def manifest_write_lock(bucket: str, key: str) -> AsyncIterator[None]:
    """Serialize the read → upsert → write cycle of a manifest object within this process.

    Keyed on ``(bucket, key)`` so concurrent updates to *different*
    manifests proceed in parallel. Hold across the full read-modify-write
    span (including any cluster mutation that sits between read and
    write) — releasing earlier reintroduces the lost-update window.

    Process-local: multi-worker / multi-pod writers still race against
    each other on the underlying S3 object.
    """
    async with _manifest_write_locks_registry_guard:
        lock = _manifest_write_locks.get((bucket, key))
        if lock is None:
            lock = asyncio.Lock()
            _manifest_write_locks[(bucket, key)] = lock
    async with lock:
        yield


async def read_manifest_from_s3(
    minio_client: MinioClient,
    bucket: str,
    key: str,
) -> list[ManifestDocument]:
    """Read and parse an existing manifest from S3, returning ``[]`` if absent.

    ``NoSuchKey`` is swallowed here (rather than mapped to
    ``NotFoundException``) so first-write and re-onboard share one code
    path. Other S3 errors flow through ``map_s3_error_to_domain_exception``.
    """
    try:
        content = await asyncio.to_thread(minio_client.download_object, bucket, key)
    except S3Error as e:
        if e.code == "NoSuchKey":
            return []
        logger.error(f"Failed to read manifest at {bucket}/{key}: {e}")
        raise map_s3_error_to_domain_exception(e, f"custom-model manifest at {bucket}/{key}") from e
    return parse_manifest(content)


@retry(
    wait=wait_exponential(multiplier=1, min=MINIO_MIN_WAIT, max=MINIO_MAX_WAIT),
    stop=stop_after_attempt(MINIO_MAX_ATTEMPTS),
    reraise=True,
)
async def write_manifest_to_s3(
    minio_client: MinioClient,
    bucket: str,
    key: str,
    documents: Iterable[ManifestDocument],
) -> None:
    """Serialize ``documents`` and upload as a single manifest object.

    Both reads and writes dispatch through ``asyncio.to_thread`` because
    the underlying minio-py SDK calls are synchronous.
    """
    payload = serialize_manifest(documents)
    try:
        await asyncio.to_thread(minio_client.upload_object, bucket_name=bucket, object_name=key, data=payload)
    except S3Error as e:
        logger.error(f"Failed to write manifest at {bucket}/{key}: {e}")
        raise map_s3_error_to_domain_exception(e, f"custom-model manifest at {bucket}/{key}") from e


@retry(
    wait=wait_exponential(multiplier=1, min=MINIO_MIN_WAIT, max=MINIO_MAX_WAIT),
    stop=stop_after_attempt(MINIO_MAX_ATTEMPTS),
    reraise=True,
)
async def delete_manifest_from_s3(
    minio_client: MinioClient,
    bucket: str,
    key: str,
) -> None:
    """Remove the manifest object entirely.

    Needed because ``serialize_manifest`` refuses an empty document list: when
    the last document is dropped, deleting the object is the only way to clear
    the mirror rather than leave stale content behind.
    """
    try:
        await asyncio.to_thread(minio_client.delete_object, bucket_name=bucket, object_name=key)
    except S3Error as e:
        logger.error(f"Failed to delete manifest at {bucket}/{key}: {e}")
        raise map_s3_error_to_domain_exception(e, f"custom-model manifest at {bucket}/{key}") from e
