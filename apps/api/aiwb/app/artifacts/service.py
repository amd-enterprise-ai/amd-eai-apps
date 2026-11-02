# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Business logic for artifact onboarding."""

import asyncio
import datetime
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from loguru import logger
from minio.error import S3Error

from api_common.collections import PaginationMetadata, paginate_list
from api_common.exceptions import (
    ConflictException,
    DeletionConflictException,
    ExternalServiceError,
    NotFoundException,
    UnhealthyException,
    ValidationException,
)
from api_common.slugs import slugify

from ..aims.constants import ADAPTER_PROFILE_FEATURE, AIM_API_GROUP, AIM_LEGACY_API_VERSION
from ..aims.crds import AIMArtifactResource, AIMArtifactSpec
from ..aims.gateway import (
    create_aim_artifact,
    delete_aim_artifact,
    get_aim_artifact,
    get_aim_service_by_id,
    list_aim_artifact_source_uris,
    list_aim_artifacts_by_label_selector,
    list_aim_services_referencing_artifact,
    resolve_recorded_profile,
)
from ..aims.utils import ServedWeights, adapter_serves
from ..config import AIWB_METADATA_PREFIX, SUBMITTER_ANNOTATION
from ..dispatch.kube_client import KubernetesClient
from ..minio import MinioClient
from ..minio.client import map_s3_error_to_domain_exception
from ..minio.config import MINIO_BUCKET
from ..minio.credentials import minio_credentials_env, verify_minio_credentials_secret
from ..models.utils import (
    delete_from_s3,
    delete_object_from_s3,
    get_adapter_artifact_prefix,
    get_adapter_artifacts_root,
)
from ..workloads.constants import DESCRIPTION_ANNOTATION, DISPLAY_NAME_ANNOTATION
from .manifest import ADAPTER_MANIFEST_FILENAME, AdapterManifest, read_adapter_manifest, write_adapter_manifest
from .readiness import OBJECT_MISSING_CODE, READINESS_ADAPTER_CONCURRENCY, split_s3_uri, stat_readiness
from .schemas import (
    MAX_ARTIFACT_FILES,
    MAX_ARTIFACT_LISTING_ENTRIES,
    REQUIRED_PEFT_FILENAMES,
    ArtifactDownloadResponse,
    ArtifactResponse,
    ArtifactS3Source,
    ArtifactsList,
    ArtifactStorage,
    ArtifactType,
    CreateArtifactRequest,
    CreateArtifactResponse,
    DownloadInstruction,
    ListArtifactsQuery,
    ReadinessState,
    UploadInstruction,
    path_escapes_prefix,
)

_PRESIGNED_URL_EXPIRY = datetime.timedelta(minutes=15)

MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
MANAGED_BY_VALUE = "aiwb"

# Records the prefix AIWB allocated and wrote to, and is stamped only where that happened — the
# upload path. Its presence is what makes deletion reclaim storage the platform owns without
# touching files a caller onboarded from storage they already owned, and it is carried here rather
# than read back off spec.sourceUri because the controller may rewrite that field.
#
# Presence is the signal; the recorded value is not trusted on its own. Deletion sweeps only the
# prefix the resource name derives to and treats any other value as tampering — sound only because
# the upload path mints the name and names the prefix after it. A future path that allocated a
# prefix named after something else would have to relax that equality check, not this annotation.
MANAGED_STORAGE_URI_ANNOTATION = f"{AIWB_METADATA_PREFIX}/managed-storage-uri"

# The only artifact type this API exposes; other types share the CRD but are out of its scope.
ADAPTER_ARTIFACT_TYPE = ArtifactType.ADAPTER.value

# The fine-tuning engine stamps adapters it produces with its own managed-by value. Both it and AIWB
# are platform authors, so the list view surfaces adapters from either — a user-facing "project
# adapter" is any adapter the platform created, not only ones onboarded through this API.
MANAGED_BY_FINE_TUNING = "fine-tuning"
PLATFORM_MANAGED_BY_VALUES = frozenset({MANAGED_BY_VALUE, MANAGED_BY_FINE_TUNING})

# Terminal directories the fine-tuning engine writes a LoRA adapter into, directly under its run folder.
_FINE_TUNED_ADAPTER_DIRS = frozenset({"checkpoint-final-adapter", "adapter"})

# Set-based selector so one list call returns adapters from every platform author. Sorted for a
# stable, testable selector string.
_PLATFORM_LABEL_SELECTOR = f"{MANAGED_BY_LABEL} in ({','.join(sorted(PLATFORM_MANAGED_BY_VALUES))})"


def _prefix_escapes_namespace(prefix: str) -> bool:
    """Whether a stored S3 key prefix fails to name a location inside the namespace tree it opens with.

    Object keys are literal, so what confines a prefix is the textual ``startswith`` test on the
    namespace prefix plus this: a segment that is empty or '..' makes the key name something other
    than where it reads as pointing. A '..' in particular clears ``startswith`` and then matches no
    object at all, so a prefix carrying one would surface as an artifact whose files went missing.

    Deliberately narrower than ``path_escapes_prefix``, which governs a path a client joins onto a
    local destination. Nothing joins a stored prefix, so a '.' segment, a backslash or a drive
    designator name a real, distinct prefix here, still inside the tree.
    """
    return any(segment in ("", "..") for segment in prefix.rstrip("/").split("/"))


def _parse_s3_uri(uri: str, namespace: str) -> tuple[str, str]:
    """Parse an s3:// URI and confine it to the calling project's own storage.

    Every project shares one bucket, so an unconstrained URI would let a caller stat objects in
    another project's tree and learn whether they exist. The namespace prefix is the tenant
    boundary; anything outside it is rejected before a single storage call is made.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValidationException(f"Invalid S3 URI: expected s3://bucket/prefix/, got '{uri}'")

    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")
    if not prefix.endswith("/"):
        prefix += "/"

    if _prefix_escapes_namespace(prefix):
        raise ValidationException(
            f"Invalid S3 URI: prefix must not be empty or contain '..' or empty segments, got '{uri}'"
        )

    namespace_prefix = f"{slugify(namespace)}/"
    if bucket != MINIO_BUCKET or not prefix.startswith(namespace_prefix):
        raise ValidationException(
            f"source.uri must point inside this project's storage (s3://{MINIO_BUCKET}/{namespace_prefix}), got '{uri}'"
        )

    return bucket, prefix


async def _verify_s3_lora_source(minio_client: MinioClient, bucket: str, prefix: str, uri: str) -> None:
    """Verify required LoRA PEFT files exist at the given S3 prefix.

    Only a genuine not-found counts as missing. Timeouts, throttling and auth failures propagate as
    themselves, so an unreachable storage backend is never reported to the caller as an invalid
    request pointing at absent files.
    """
    results = await asyncio.gather(
        *(asyncio.to_thread(minio_client.stat_object, bucket, f"{prefix}{f}") for f in REQUIRED_PEFT_FILENAMES),
        return_exceptions=True,
    )

    missing = []
    for filename, result in zip(REQUIRED_PEFT_FILENAMES, results, strict=True):
        if not isinstance(result, BaseException):
            continue
        if not isinstance(result, S3Error):
            raise result
        if result.code != OBJECT_MISSING_CODE:
            raise map_s3_error_to_domain_exception(result, f"s3://{bucket}/{prefix}{filename}") from result
        missing.append(filename)
    if missing:
        raise ValidationException(f"Required LoRA files not found at {uri}: {', '.join(missing)}")


def _build_manifest(
    namespace: str,
    resource_name: str,
    source_uri: str,
    request: CreateArtifactRequest,
    submitter: str,
    model_id: str,
    rank: int | None,
    display_name: str | None,
    description: str | None,
    managed_storage_uri: str | None,
) -> dict[str, Any]:
    annotations: dict[str, str] = {SUBMITTER_ANNOTATION: submitter}
    if display_name is not None:
        annotations[DISPLAY_NAME_ANNOTATION] = display_name
    if description is not None:
        annotations[DESCRIPTION_ANNOTATION] = description
    if managed_storage_uri is not None:
        annotations[MANAGED_STORAGE_URI_ANNOTATION] = managed_storage_uri

    # Composed through the CR model rather than hand-written camelCase so the writer and the reader
    # cannot drift apart. model_id, rank, display_name and description are passed in because an
    # existing S3-side manifest can override what the request declared.
    spec = AIMArtifactSpec(
        type=request.type,
        source_uri=source_uri,
        model_id=model_id,
        compatible_with=request.compatible_with,
        rank=rank,
        env=minio_credentials_env(),
    )

    return {
        "apiVersion": f"{AIM_API_GROUP}/{AIM_LEGACY_API_VERSION}",
        "kind": "AIMArtifact",
        "metadata": {
            "name": resource_name,
            "namespace": namespace,
            "labels": {
                MANAGED_BY_LABEL: MANAGED_BY_VALUE,
            },
            "annotations": annotations,
        },
        "spec": spec.model_dump(by_alias=True, exclude_none=True),
    }


def _redact(artifact: AIMArtifactResource) -> AIMArtifactResource:
    """Strip the credential references AIWB writes into ``spec.env`` before the CR leaves the API.

    ``env`` names the secret holding the project's object-storage keys so aim-engine can read
    ``sourceUri``. It is infrastructure wiring, not artifact identity, and returning the resource
    verbatim would otherwise hand every reader a map of which secrets to go after.
    """
    if artifact.spec.env is None:
        return artifact
    return artifact.model_copy(update={"spec": artifact.spec.model_copy(update={"env": None})})


def _new_artifact_response(
    artifact: AIMArtifactResource,
    source_uri: str,
    readiness: ReadinessState,
    uploads: list[UploadInstruction] | None = None,
) -> CreateArtifactResponse:
    """Project a just-created artifact into the same shape the list returns, plus its upload URLs.

    Everything is already in hand from the create, so this adds no storage reads: the caller knows
    the readiness verdict by construction. ``source_uri`` is passed rather than read back from the
    spec so the response reports the prefix the presigned URLs point at even if the controller has
    since rewritten the field.
    """
    return CreateArtifactResponse(
        storage=ArtifactStorage(uri=source_uri, readiness=readiness),
        artifact=_redact(artifact),
        uploads=uploads or [],
    )


def _batch_signing_instant() -> datetime.datetime:
    """The instant a batch of presigned URLs is stamped with, so they share one true deadline.

    A signature is alive for a fixed span measured from a timestamp carried inside it, and the
    signing client otherwise takes that timestamp off its own clock at each call — so links minted
    one after another die one after another, each a little past the single instant the response
    advertises. Stamping every link in a batch with this one reading makes the advertised deadline
    the real one for all of them.

    Whole seconds because that is the resolution a signature carries: a sub-second remainder would
    be dropped from the signature while still counting in what the response promises.
    """
    return datetime.datetime.now(tz=datetime.UTC).replace(microsecond=0)


async def _create_with_upload(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    minio_external_client: MinioClient,
    namespace: str,
    request: CreateArtifactRequest,
    submitter: str,
) -> CreateArtifactResponse:
    """Allocate a prefix, sign an upload URL per file, and create the CR that claims them.

    Refused up front when the presigning endpoint is not externally addressable. SigV4 covers the
    Host header, so the caller cannot repair a URL signed against an unreachable host: a 201 there
    accepts an upload the platform has already made impossible, with nothing in the response, the
    logs, or the resource status to say so. Refusing before the name is minted also means the
    rejection leaves no artifact behind.
    """
    if not minio_external_client.is_externally_addressable():
        raise UnhealthyException(
            f"Object storage endpoint '{minio_external_client.host}' is not reachable from outside the cluster, "
            "so no usable upload URL can be issued. Contact your platform administrator to set "
            "'minio.externalUrl' to the address clients reach object storage on. Adapters whose weights are "
            "already in object storage can still be registered with an 's3' source."
        )

    resource_name = f"adapter-{uuid4().hex[:8]}"
    prefix = get_adapter_artifact_prefix(namespace, resource_name)
    source_uri = f"s3://{MINIO_BUCKET}/{prefix}"

    signed_at = _batch_signing_instant()
    expires_at = signed_at + _PRESIGNED_URL_EXPIRY

    def _make_upload(file_path: str) -> UploadInstruction:
        object_name = f"{prefix}{file_path}"
        url = minio_external_client.generate_presigned_upload_url(
            bucket=MINIO_BUCKET,
            object_name=object_name,
            expires=_PRESIGNED_URL_EXPIRY,
            request_date=signed_at,
        )
        return UploadInstruction(path=file_path, url=url, expires_at=expires_at)

    # AIWB is the sole author of the manifest, so drop any client-listed copy to keep the presigned
    # set from racing our own write for the same key.
    upload_files = [f for f in (request.files or []) if f != ADAPTER_MANIFEST_FILENAME]

    # Sign upload URLs before creating the CR: a signing failure then surfaces as a failed request
    # rather than leaving an accepted artifact pointing at a prefix the caller was never told how to
    # populate. The manifest is a recovery mirror and stays after the CR, which remains authority.
    uploads = await asyncio.to_thread(lambda: [_make_upload(f) for f in upload_files])

    manifest = _build_manifest(
        namespace,
        resource_name,
        source_uri,
        request,
        submitter,
        model_id=request.model_id,
        rank=request.rank,
        display_name=request.display_name,
        description=request.description,
        # AIWB allocated this prefix and is about to write to it, so deleting the artifact is what
        # reclaims it.
        managed_storage_uri=source_uri,
    )
    artifact = await create_aim_artifact(kube_client, namespace, manifest)

    # The CR is the authority; the manifest is only a recovery mirror. Once the CR exists the request
    # has succeeded, so any mirror-write failure (mapped domain error, raw minio ServerError, or a
    # connection drop) is logged and swallowed rather than failing the caller — which on this path
    # would also throw away the presigned URLs they need to upload the weights. The manifest is built
    # before the try so a construction bug still surfaces; only the storage write is best-effort.
    manifest_key = f"{prefix}{ADAPTER_MANIFEST_FILENAME}"
    adapter_manifest = AdapterManifest(
        model_id=request.model_id,
        compatible_with=request.compatible_with,
        rank=request.rank,
        display_name=request.display_name,
        description=request.description,
    )
    try:
        await write_adapter_manifest(minio_client, MINIO_BUCKET, manifest_key, adapter_manifest)
    except Exception as e:
        logger.warning(
            f"AIMArtifact '{resource_name}' created but recovery manifest write to "
            f"{MINIO_BUCKET}/{manifest_key} failed: {e}. The CR is authoritative; the mirror can be backfilled."
        )

    # NotReady by construction: the presigned URLs the caller is being handed are exactly what has
    # not been used yet, so a storage check here could only confirm what the response already says.
    return _new_artifact_response(artifact, source_uri, ReadinessState.NOT_READY, uploads)


async def _create_from_s3_source(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    namespace: str,
    request: CreateArtifactRequest,
    submitter: str,
) -> CreateArtifactResponse:
    bucket, prefix = _parse_s3_uri(request.source.uri, namespace)
    # Store the canonical bucket + normalized prefix rather than the raw request URI, so spec.sourceUri
    # points at exactly where verification confirmed the files (a slash-less request prefix is verified
    # with a trailing slash) and matches the canonical form the upload path writes.
    source_uri = f"s3://{bucket}/{prefix}"
    await _verify_s3_lora_source(minio_client, bucket, prefix, source_uri)

    # A manifest already sitting beside the weights (written by the fine-tuning engine or a prior
    # onboard) is ground truth for what those files are, so whatever it states wins over the request.
    manifest_key = f"{prefix}{ADAPTER_MANIFEST_FILENAME}"
    existing = await read_adapter_manifest(minio_client, bucket, manifest_key)

    if existing is not None:
        # Where the manifest and the request both state the adapter's compatibility they must agree,
        # or the adapter would be onboarded against a base it was not trained on. A manifest written
        # before the field existed states nothing and is not a conflict.
        if existing.compatible_with is not None and set(existing.compatible_with) != set(request.compatible_with):
            raise ValidationException(
                f"Recovery manifest at {source_uri} records compatibility with "
                f"{sorted(existing.compatible_with)}, but the request declares {sorted(request.compatible_with)}"
            )
        model_id = existing.model_id
        # A manifest silent on these has nothing to restore, so fall back to the request rather than
        # dropping what the caller supplied. Rank is checked against None because a stated rank of 0
        # is a value the manifest asserts, not a silence for the request to fill.
        rank = existing.rank if existing.rank is not None else request.rank
        display_name = existing.display_name or request.display_name
        description = existing.description or request.description
    else:
        model_id, rank = request.model_id, request.rank
        display_name, description = request.display_name, request.description

    resource_name = f"adapter-{uuid4().hex[:8]}"
    manifest = _build_manifest(
        namespace,
        resource_name,
        source_uri,
        request,
        submitter,
        model_id=model_id,
        rank=rank,
        display_name=display_name,
        description=description,
        # The files were already there and belong to the caller, so deletion must leave them alone.
        managed_storage_uri=None,
    )
    artifact = await create_aim_artifact(kube_client, namespace, manifest)

    if existing is None:
        # Best-effort recovery mirror: the CR already exists and is authoritative, so any mirror-write
        # failure is logged rather than failing an onboard whose files are already in place.
        adapter_manifest = AdapterManifest(
            model_id=model_id,
            compatible_with=request.compatible_with,
            rank=rank,
            display_name=display_name,
            description=description,
        )
        try:
            await write_adapter_manifest(minio_client, bucket, manifest_key, adapter_manifest)
        except Exception as e:
            logger.warning(
                f"AIMArtifact '{resource_name}' created but recovery manifest write to "
                f"{bucket}/{manifest_key} failed: {e}. The CR is authoritative; the mirror can be backfilled."
            )

    # Ready without re-checking: _verify_s3_lora_source already proved every required file is at the
    # prefix, and nothing since then could have removed them on this path.
    return _new_artifact_response(artifact, source_uri, ReadinessState.READY)


async def create_adapter_artifact(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    minio_external_client: MinioClient,
    namespace: str,
    request: CreateArtifactRequest,
    submitter: str,
) -> CreateArtifactResponse:
    """Create an adapter artifact, either from an existing S3 prefix or with upload URLs.

    Verification reads go through minio_client on the in-cluster endpoint, while upload URLs are
    signed by minio_external_client, whose endpoint has to resolve for callers outside the cluster.
    Where it does not, the upload path refuses; the S3 source path signs nothing and is unaffected.
    """
    await verify_minio_credentials_secret(kube_client, namespace)

    if isinstance(request.source, ArtifactS3Source):
        return await _create_from_s3_source(kube_client, minio_client, namespace, request, submitter)
    return await _create_with_upload(kube_client, minio_client, minio_external_client, namespace, request, submitter)


def _readiness_from_filenames(filenames: frozenset[str]) -> ReadinessState:
    """Readiness verdict from a prefix listing, with no further storage calls.

    A listing already enumerates every object under the prefix, so the answer is definite either
    way — never ``UNKNOWN``.
    """
    return ReadinessState.READY if all(f in filenames for f in REQUIRED_PEFT_FILENAMES) else ReadinessState.NOT_READY


def _as_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    """Attach UTC to a naive timestamp so mixed-awareness values remain comparable.

    Kubernetes stamps RFC 3339 and MinIO reports UTC, but either can arrive naive depending on the
    client, and comparing a naive against an aware datetime raises — which would fail a whole
    listing over one item.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=datetime.UTC)


async def _no_adapter_scan() -> dict[str, frozenset[str]]:
    """Stand-in for the scan when nothing asked for it, so the caller can still await both halves."""
    return {}


async def _scan_adapter_storage(minio_client: MinioClient | None, namespace: str) -> dict[str, frozenset[str]]:
    """Map each prefix under the project's platform-allocated adapter tree to the files it holds.

    One recursive listing settles readiness for every prefix at once, which is what a readiness
    filter needs: the verdict has to hold for the whole collection, and the alternative is a stat
    per CR against a thread pool the whole service shares.

    Only the tree the platform allocates is swept. An adapter whose source URI points elsewhere is
    still listed; it just falls back to a per-item stat. Storage failures degrade to an empty scan
    rather than failing the request: a listing that cannot see storage should still return the CRs
    it can see.
    """
    if minio_client is None:
        return {}
    root = get_adapter_artifacts_root(namespace)
    try:
        objects = await asyncio.to_thread(
            lambda: list(minio_client.client.list_objects(MINIO_BUCKET, prefix=root, recursive=True))
        )
    except Exception as e:
        logger.warning(f"Adapter storage scan under s3://{MINIO_BUCKET}/{root} failed: {e}. Reporting none found.")
        return {}

    scanned: dict[str, set[str]] = defaultdict(set)
    for obj in objects:
        relative = obj.object_name.removeprefix(root)
        segment, _, filename = relative.partition("/")
        # aim-engine reads the PEFT files at the top level of the adapter prefix, so a nested path
        # does not count towards readiness.
        if not segment or not filename or "/" in filename:
            continue
        scanned[f"{root}{segment}/"].add(filename)
    return {prefix: frozenset(filenames) for prefix, filenames in scanned.items()}


def is_platform_managed(artifact: AIMArtifactResource) -> bool:
    """Membership test for the collection the list view exposes.

    The list selects on managed-by and filters to the adapter type, so an artifact the platform did
    not author — or a platform-managed artifact of a different type, e.g. a model — is not part of
    this API's resource set. The by-name endpoints apply the same two-part test: without it a
    guessed name reaches — and deletes — CRs that never appear in a listing and that this API does
    not own or does not expose.
    """
    return (
        artifact.spec.type == ADAPTER_ARTIFACT_TYPE
        and artifact.metadata.labels.get(MANAGED_BY_LABEL) in PLATFORM_MANAGED_BY_VALUES
    )


@dataclass(frozen=True)
class _Candidate:
    """One row of the list before the storage read that fills in its readiness has been made.

    ``readiness`` is pre-filled when the storage scan already answered it; ``None`` means the answer
    still costs a stat.
    """

    artifact: AIMArtifactResource
    location: tuple[str, str] | None
    readiness: ReadinessState | None = None


def _candidate(artifact: AIMArtifactResource, scan: dict[str, frozenset[str]]) -> _Candidate:
    location = split_s3_uri(artifact.spec.source_uri)
    stored = scan.get(location[1]) if location is not None and location[0] == MINIO_BUCKET else None
    return _Candidate(
        artifact=artifact,
        location=location,
        readiness=_readiness_from_filenames(stored) if stored is not None else None,
    )


async def _resolve_readiness(minio_client: MinioClient | None, candidate: _Candidate) -> ReadinessState:
    """The candidate's readiness, stat-ing storage only when the scan did not already answer it."""
    if candidate.readiness is not None:
        return candidate.readiness
    return await stat_readiness(minio_client, candidate.location)


async def _to_artifact_response(
    minio_client: MinioClient | None,
    candidate: _Candidate,
    namespace: str,
    served: ServedWeights | None = None,
) -> ArtifactResponse:
    """Project a candidate into the response, reading its readiness from storage if still needed."""
    readiness = await _resolve_readiness(minio_client, candidate)
    return ArtifactResponse(
        storage=ArtifactStorage(uri=candidate.artifact.spec.source_uri, readiness=readiness),
        artifact=_redact(candidate.artifact),
        # The deploy and attach gates judge the same question with this same function, so a row
        # reported servable is one those gates accept.
        servable=(
            None
            if served is None
            else adapter_serves(
                candidate.artifact.spec.compatible_with or [],
                served,
                adapter_name=candidate.artifact.metadata.name,
                namespace=namespace,
            )
        ),
    )


async def _served_weights(
    kube_client: KubernetesClient,
    namespace: str,
    deployment_id: UUID,
) -> ServedWeights | None:
    """The weights a deployment runs, or None when nothing can be said about them.

    Only the profile the deployment actually resolved decides what it can load, and this is the
    same read the attach gate performs before accepting a change, so the flag and the gate cannot
    answer from different profiles. Until aim-engine records that profile there is no answer to
    give, and a profile whose runtime cannot host adapters at all can serve none of them --
    reported as weights nothing matches rather than as unknown, because that is a settled answer
    the caller should act on.

    A deployment that does not exist is refused rather than answered with "unknown": the caller
    asked what a specific deployment can serve, and reporting every row as unevaluated reads to it
    as a page of adapters none of which are servable.
    """
    service = await get_aim_service_by_id(kube_client, namespace, deployment_id)
    if service is None:
        raise NotFoundException(f"AIM service {deployment_id} not found in namespace '{namespace}'")
    profile = await resolve_recorded_profile(kube_client, namespace, service.status.resolved_profile)
    if profile is None:
        return None
    if ADAPTER_PROFILE_FEATURE not in profile.spec.features:
        return ServedWeights(model_id=None, aim_id=None)
    return ServedWeights(model_id=profile.spec.model_id or None, aim_id=profile.spec.aim_id or None)


async def list_project_adapter_artifacts(
    kube_client: KubernetesClient,
    minio_client: MinioClient | None,
    namespace: str,
    query: ListArtifactsQuery,
) -> ArtifactsList:
    """List a project's adapters, newest first, one page at a time.

    Rows come from the AIMArtifact CRs the platform authored. Weights sitting in the project's
    adapter tree that no CR claims are not artifacts and are not reported: there is no record to
    name, address or delete them by.

    A readiness filter reads storage for every candidate rather than only the ones on the requested
    page: the verdict has to hold for the whole collection before it can be paginated. That is why
    it pulls in the recursive sweep -- one listing answers readiness for every prefix in the tree at
    once, where the alternative is a stat per CR against a thread pool the whole service shares.
    Plain browsing skips the sweep and pays only for the per-page stats of the page it asked for.
    """
    scan, artifacts = await asyncio.gather(
        _scan_adapter_storage(minio_client, namespace) if query.readiness is not None else _no_adapter_scan(),
        list_aim_artifacts_by_label_selector(kube_client, namespace, _PLATFORM_LABEL_SELECTOR),
    )

    # The full membership test rather than just the type filter, so list, get and delete share one
    # definition of the exposed collection.
    artifacts = [a for a in artifacts if is_platform_managed(a)]
    if query.type is not None:
        wanted_types = {t.value for t in query.type}
        artifacts = [a for a in artifacts if a.spec.type in wanted_types]

    candidates = [_candidate(a, scan) for a in artifacts]

    # asyncio.to_thread shares one executor across the process, so every storage fan-out below is
    # capped: unbounded, a large project would monopolise the workers each other request queues on.
    # A page is bounded in rows but not in pool pressure -- 100 rows is already 200 stats.
    limit = asyncio.Semaphore(READINESS_ADAPTER_CONCURRENCY)

    if query.readiness is not None:
        wanted = set(query.readiness)

        async def _bounded_readiness(candidate: _Candidate) -> ReadinessState:
            async with limit:
                return await _resolve_readiness(minio_client, candidate)

        resolved = await asyncio.gather(*(_bounded_readiness(c) for c in candidates))
        # Carry the verdict onto the survivors so the projection does not stat them a second time.
        candidates = [replace(c, readiness=r) for c, r in zip(candidates, resolved, strict=True) if r in wanted]

    # Newest first so pagination is stable and the most recently onboarded adapter leads the list.
    # Undated rows sort last rather than raising against dated ones.
    candidates.sort(
        key=lambda c: (
            _as_utc(c.artifact.metadata.creation_timestamp) or datetime.datetime.min.replace(tzinfo=datetime.UTC)
        ),
        reverse=True,
    )

    # One resolution for the whole page: every row is measured against the same deployment, so the
    # profile lookup does not belong inside the per-row fan-out below.
    served = await _served_weights(kube_client, namespace, query.servable_by) if query.servable_by is not None else None

    async def _bounded_response(candidate: _Candidate) -> ArtifactResponse:
        async with limit:
            return await _to_artifact_response(minio_client, candidate, namespace, served)

    page = paginate_list(candidates, page=query.page, page_size=query.page_size)
    data = await asyncio.gather(*(_bounded_response(c) for c in page.items))
    return ArtifactsList(
        data=list(data),
        pagination=PaginationMetadata(page=page.page, page_size=page.page_size, total=page.total),
    )


async def get_project_adapter_artifact(
    kube_client: KubernetesClient,
    minio_client: MinioClient | None,
    namespace: str,
    name: str,
) -> ArtifactResponse:
    """Fetch one adapter by name, in the same shape the list returns."""
    artifact = await get_aim_artifact(kube_client, namespace, name)
    if artifact is None or not is_platform_managed(artifact):
        raise NotFoundException(f"Artifact '{name}' not found in namespace '{namespace}'")
    return await _to_artifact_response(minio_client, _candidate(artifact, {}), namespace)


def _download_location(source_uri: str | None, namespace: str, name: str) -> tuple[str, str]:
    """Where an artifact's files may be signed from, confining them to the namespace's storage prefix.

    One bucket is shared by every project, so signing whatever the CR happens to record would turn a
    tampered or mis-reconciled sourceUri into working links against unrelated data elsewhere in the
    bucket. What the check confines to is the namespace's slugified prefix, the same granularity the
    onboarding parser enforces, and deliberately no narrower: artifacts legitimately sit in more than
    one tree under it — the prefix AIWB allocates for uploads, and the separate tree the fine-tuning
    engine writes its output to — so pinning this to either one would silently make everything in the
    other undownloadable.
    """
    location = split_s3_uri(source_uri)
    namespace_prefix = f"{slugify(namespace)}/"
    # Two rules are in play across this endpoint, and the difference between them is what the value
    # is for. Here it is a key prefix the server uses as-is, so the prefix rule applies: the same one
    # onboarding parses an S3 source with. The listing below applies the stricter
    # path_escapes_prefix, because those paths are handed to a client to join onto a local
    # destination, and a segment that resolves away moves the file it names.
    if (
        location is None
        or location[0] != MINIO_BUCKET
        or not location[1].startswith(namespace_prefix)
        or _prefix_escapes_namespace(location[1])
    ):
        raise ConflictException(
            f"Artifact '{name}' records its files at '{source_uri}', which is not inside this project's "
            f"storage (s3://{MINIO_BUCKET}/{namespace_prefix}), so they cannot be handed out."
        )
    return location


async def download_project_artifact(
    kube_client: KubernetesClient,
    minio_client: MinioClient,
    minio_external_client: MinioClient,
    namespace: str,
    name: str,
) -> ArtifactDownloadResponse:
    """Hand back one time-limited direct link per file under the artifact's storage prefix.

    The bytes never pass through this API. Links are signed against the external endpoint so the
    transfer runs between the caller and object storage; the in-cluster client only lists the prefix.

    Dataset download streams through the API instead, and the difference is the shape of the thing:
    a dataset is one file the caller asked for by id, while an artifact is a directory that can run
    to several gigabytes. Proxying that through the API pod is what the links avoid.

    Refused up front when the presigning endpoint is not externally addressable, for the same reason
    upload is: SigV4 covers the Host header, so a link signed against an unreachable host cannot be
    repaired by the caller, and a 200 carrying such links reports a success nobody can act on. The
    check precedes the lookup and the listing because no artifact in the project can be handed out
    on such an install — the verdict is about the install, not about this name.
    """
    if not minio_external_client.is_externally_addressable():
        raise UnhealthyException(
            f"Object storage endpoint '{minio_external_client.host}' is not reachable from outside the cluster, "
            "so no usable download URL can be issued. Contact your platform administrator to set "
            "'minio.externalUrl' to the address clients reach object storage on."
        )

    artifact = await get_aim_artifact(kube_client, namespace, name)
    if artifact is None or not is_platform_managed(artifact):
        raise NotFoundException(f"Artifact '{name}' not found in namespace '{namespace}'")

    bucket, prefix = _download_location(artifact.spec.source_uri, namespace, name)

    def _list_contents() -> tuple[list[tuple[str, int | None]], str | None]:
        """The prefix's files, or nothing and the reason the artifact cannot be handed out.

        Recursive, so a download hands back exactly what an upload may register: onboarding permits
        nested extras, and every file under the prefix comes back keyed on its path relative to
        the prefix. A recursive listing reports stored objects only — a subdirectory is not an entry
        of its own — so the entries read but not served are directory markers, which exist only
        where something stored one.

        The listing is paged and lazy, so how much of it is read is how much this pod fetches. Both
        bounds are therefore applied as it is read: the entry the file cap refuses on, and the
        marker-heavy prefix the entry bound refuses on, each settle the verdict where they are met.
        """
        contents: list[tuple[str, int | None]] = []
        files = 0
        entries = 0
        for obj in minio_client.client.list_objects(bucket, prefix=prefix, recursive=True):
            entries += 1
            if entries > MAX_ARTIFACT_LISTING_ENTRIES:
                return [], (
                    f"Artifact '{name}' holds more than the {MAX_ARTIFACT_LISTING_ENTRIES} entries "
                    f"one download reads at s3://{bucket}/{prefix}. Files of its own stop at "
                    f"{MAX_ARTIFACT_FILES}, so a prefix that reaches this is most likely dense with "
                    f"directory markers, which this API does not create."
                )
            path = obj.object_name.removeprefix(prefix)
            # A key ending in "/" names a directory rather than a file. The prefix ends in one, so
            # its own key lands here as an empty path and is the same kind of object as a nested
            # marker — one rule covers both. Empty, it is a marker: an object a console's "create
            # folder" leaves behind, naming a directory a download rebuilds anyway from the files
            # under it, so it is passed over. Carrying bytes it is not a marker, and there is no file
            # path to write it at, so it is refused instead. The file cap is stated in files a
            # download covers, so markers are skipped before it counts rather than against it —
            # which is why they need the entry bound above, or a prefix of nothing but markers would
            # never reach any cutoff.
            if not path or path.endswith("/"):
                if obj.size:
                    return [], (
                        f"Artifact '{name}' holds an object at s3://{bucket}/{prefix}{path} whose key "
                        f"names a directory yet carries bytes, so there is no path to write it at and "
                        f"its files cannot be handed out."
                    )
                continue
            # What is left claims to be a file, and the response tells the caller to write it at its
            # own path, so a traversing or resolving-away segment would write outside the directory
            # being rebuilt or somewhere other than where the listing said. Onboarding rejects the
            # same shapes on the way in; a key that reached storage some other way is refused here
            # rather than dropped, because handing back less than the prefix holds yields an adapter
            # that looks complete and is not.
            if path_escapes_prefix(path):
                return [], (
                    f"Artifact '{name}' holds an object at s3://{bucket}/{prefix}{path} whose path "
                    f"relative to its prefix escapes it, so its files cannot be handed out."
                )
            # AIWB writes the manifest into the same prefix the caller's files go to, so counting
            # it against a cap the caller's own declaration is allowed to fill would make an upload
            # of exactly that many files permanently undownloadable. It is served like any other
            # object; only the count leaves it out. A nested copy is a file of the caller's and is
            # counted, matching the single root key AIWB writes and onboarding strips.
            if path != ADAPTER_MANIFEST_FILENAME:
                files += 1
                if files > MAX_ARTIFACT_FILES:
                    return [], (
                        f"Artifact '{name}' holds more than the {MAX_ARTIFACT_FILES} files one "
                        f"download covers at s3://{bucket}/{prefix}."
                    )
            contents.append((path, obj.size))
        return contents, None

    # The iterator fetches as it is consumed, so the storage calls happen inside the thread rather
    # than at the call that creates it, and the guard has to span the consumption to catch them.
    try:
        contents, refusal = await asyncio.to_thread(_list_contents)
    except Exception as exc:
        raise ExternalServiceError(
            message=f"Failed to read the files of artifact '{name}' at s3://{bucket}/{prefix}.",
            detail=str(exc),
        ) from exc

    if refusal is not None:
        raise ConflictException(refusal)

    # PEFT completeness is what an adapter means, not what an artifact means. Every other type this
    # API grows has to answer this question for itself; until one does, it has no such requirement
    # and whatever sits at its prefix is downloadable.
    if artifact.spec.type == ADAPTER_ARTIFACT_TYPE:
        # aim-engine and the readiness stats read the PEFT files at the top of the prefix, so a
        # nested copy of one does not make the adapter usable and must not satisfy the check.
        root_filenames = frozenset(path for path, _ in contents if "/" not in path)
        if _readiness_from_filenames(root_filenames) is not ReadinessState.READY:
            raise ConflictException(
                f"Artifact '{name}' cannot be downloaded: its weights are not present at "
                f"s3://{bucket}/{prefix}. A complete adapter holds {', '.join(REQUIRED_PEFT_FILENAMES)}."
            )

    signed_at = _batch_signing_instant()
    expires_at = signed_at + _PRESIGNED_URL_EXPIRY

    def _make_download(path: str, size: int | None) -> DownloadInstruction:
        url = minio_external_client.generate_presigned_download_url(
            bucket=bucket,
            object_name=f"{prefix}{path}",
            expires=_PRESIGNED_URL_EXPIRY,
            request_date=signed_at,
        )
        return DownloadInstruction(path=path, url=url, size_bytes=size)

    # Signing is not the offline computation it looks like: no region is configured, so the client
    # resolves the bucket's location over the network on its first presign against it. That call
    # reaches the same storage the listing above does and is reported the same way.
    try:
        files = await asyncio.to_thread(lambda: [_make_download(path, size) for path, size in contents])
    except Exception as exc:
        raise ExternalServiceError(
            message=f"Failed to sign download links for artifact '{name}' at s3://{bucket}/{prefix}.",
            detail=str(exc),
        ) from exc

    return ArtifactDownloadResponse(files=files, expires_at=expires_at)


def _fine_tuned_run_prefix(namespace: str, source_uri: str | None) -> str | None:
    """The run folder a fine-tuning job wrote this adapter into, or None if the source is not one.

    Fine-tuning writes each run under ``<project>/finetuned-models/<base model>/<run-id>/``, with the
    adapter weights in a terminal directory beside run-level files (manifest, metadata) that nothing
    else references. The whole run folder is the unit AIWB allocated, so it is what gets reclaimed.

    ``spec.sourceUri`` is patchable by anyone with RBAC on the CR, so only this project's tree, in
    the platform bucket, ending in a run segment AIWB mints as a UUID, qualifies — anything looser
    could widen the recursive sweep to other runs or the whole project.
    """
    parsed = urlparse(source_uri) if source_uri else None
    raw_parts = parsed.path.split("/") if parsed else []
    if any(part in {"", ".", ".."} for part in raw_parts[1:-1]):
        return None
    location = split_s3_uri(source_uri)
    if location is None or location[0] != MINIO_BUCKET:
        return None
    parts = location[1].rstrip("/").split("/")
    if (
        len(parts) < 5
        or parts[0] != slugify(namespace)
        or parts[1] != "finetuned-models"
        or parts[-1] not in _FINE_TUNED_ADAPTER_DIRS
        or any(part in {"", ".", ".."} for part in parts)
    ):
        return None
    try:
        if str(UUID(parts[-2])) != parts[-2]:
            return None
    except ValueError:
        return None
    return f"{'/'.join(parts[:-1])}/"


def _owned_storage_prefix(namespace: str, name: str, artifact: AIMArtifactResource) -> str | None:
    """The object-storage prefix AIWB allocated for this adapter, or None if it owns none.

    Two authors allocate storage: the upload path, which records it in a create-time annotation, and
    the fine-tuning engine, whose output lands in a run folder AIWB named. Anything else — onboarded
    from the caller's own storage, or created before the annotation existed — owns no files.
    """
    if artifact.metadata.labels.get(MANAGED_BY_LABEL) == MANAGED_BY_FINE_TUNING:
        return _fine_tuned_run_prefix(namespace, artifact.spec.source_uri)

    uri = artifact.metadata.annotations.get(MANAGED_STORAGE_URI_ANNOTATION)
    if not uri:
        return None

    # The annotation is patchable by anyone with RBAC on the CR, so the sweep target is the prefix
    # this artifact's own name derives to, and the recorded value only has to agree with it. Any
    # other value — another project's tree, the adapter root, a sibling adapter's prefix — is
    # tampering and is skipped with a warning rather than refused, so it cannot make the CR
    # undeletable through the API.
    #
    # Equality rather than a shape check, because shape alone admits any sibling adapters/<x>/. An
    # unclaimed one is reachable in practice: the upload path signs presigned URLs before creating
    # the CR, so a failed create leaves populated storage no artifact claims — the co-claimant scan
    # would find nothing to object, and caller-owned files would go with the sweep.
    prefix = get_adapter_artifact_prefix(namespace, name)
    if split_s3_uri(uri) != (MINIO_BUCKET, prefix):
        logger.warning(
            f"AIMArtifact '{name}' in namespace {namespace} records managed storage at '{uri}', which is not the "
            f"prefix allocated for it (s3://{MINIO_BUCKET}/{prefix}). Deleting the artifact without reclaiming it."
        )
        return None
    return prefix


async def _reclaim_managed_storage(
    kube_client: KubernetesClient,
    minio_client: MinioClient | None,
    namespace: str,
    name: str,
    artifact: AIMArtifactResource,
) -> None:
    """Delete the object-storage prefix AIWB allocated for an uploaded or fine-tuned adapter.

    Called before the CR is removed, so a failed sweep aborts the whole delete and leaves a visible,
    retryable artifact rather than a prefix nothing owns.
    """
    prefix = _owned_storage_prefix(namespace, name, artifact)
    if prefix is None:
        return
    uri = f"s3://{MINIO_BUCKET}/{prefix}"

    if minio_client is None:
        raise ExternalServiceError(
            f"Artifact '{name}' owns weights at {uri}, but object storage is not configured, so they cannot be "
            f"reclaimed. The artifact was left in place; retry once storage is reachable."
        )

    # Unselected and unvalidated: a foreign record claims a prefix as effectively as a platform one,
    # and an artifact the typed listing would drop for an unrelated shape problem claims it just as
    # effectively as one that parses. Sweeping storage another AIMArtifact still points at breaks it.
    #
    # Descendants count as claimants because the sweep is recursive: S3-source onboarding accepts any
    # prefix inside the project, so an artifact validly registered at .../a-1/checkpoint/ loses its
    # files when .../a-1/ goes. Ancestors deliberately do not — a claim on the adapters root keeps
    # its own files above the swept child, and honouring it would block reclamation project-wide.
    def _claims_swept_storage(source_uri: str) -> bool:
        claimed = split_s3_uri(source_uri)
        return claimed is not None and claimed[0] == MINIO_BUCKET and claimed[1].startswith(prefix)

    claimants = await list_aim_artifact_source_uris(kube_client, namespace)
    co_claimants = sorted(
        other for other, source_uri in claimants.items() if other != name and _claims_swept_storage(source_uri)
    )
    if co_claimants:
        logger.info(
            f"Deleting AIMArtifact '{name}' in namespace {namespace} without reclaiming {uri}: still claimed by "
            f"{', '.join(co_claimants)}."
        )
        return

    try:
        await delete_from_s3(prefix, minio_client, name, operation="deleting adapter weights")
        # Some stores keep a zero-byte directory marker at the prefix key itself, which the
        # recursive delete does not remove, leaving an empty folder visible in the bucket.
        await delete_object_from_s3(prefix, minio_client, name, operation="deleting adapter folder marker")
    except NotFoundException:
        # A prefix already gone is the end state the delete asks for, the same reading the endpoint
        # gives a missing artifact.
        logger.info(f"Adapter weights at {uri} were already absent when deleting AIMArtifact '{name}'.")
    except ExternalServiceError:
        raise
    except Exception as exc:
        # handle_s3_operation maps only S3Error and S3SyncError, so a transport failure would reach
        # the caller as a 500 and an AccessDenied on AIWB's own credentials as a 403 reading as
        # though the caller were forbidden. The route documents object-storage failure as 502.
        raise ExternalServiceError(
            message=f"Failed to reclaim adapter weights at {uri} while deleting artifact '{name}'.",
            detail=str(exc),
        ) from exc


async def delete_project_adapter_artifact(
    kube_client: KubernetesClient,
    minio_client: MinioClient | None,
    namespace: str,
    name: str,
    force: bool = False,
) -> bool:
    """Delete an adapter artifact unless an AIMService still references it.

    Returns True when a delete was accepted (caller maps to 202) and False when the artifact was
    already gone (204). Raises DeletionConflictException (409) if any AIMService lists it as an
    adapter — deleting live-referenced weights breaks those deployments on their next reload rather
    than while they run.

    Storage AIWB itself allocated — an uploaded adapter's prefix, or the whole run folder of an
    adapter a fine-tuning job produced — is reclaimed before the CR is removed. Files onboarded from
    storage the caller already owned are left alone.

    ``force`` overrides only the check for adapters in use by a running service, leaving the
    referencing services untouched: a running replica keeps serving the weights it already loaded
    and fails to reload them on restart. It deliberately does not delete or detach those services —
    an AIMService serves a base model and may carry several adapters, so tearing one down to remove
    a single adapter would take the whole deployment with it. Storage cleanup must succeed either
    way: when a sweep is required and fails, the artifact is not deleted, so a failed sweep never
    leaves a prefix nothing owns. Cases where no sweep is required — caller-owned files, or a prefix
    another artifact still claims — leave the files in place by design.

    ``force`` does not widen which artifacts are reachable. An artifact outside this API's
    collection is still reported as already gone rather than deleted: that is an ownership
    boundary, not a safety check, and it is indistinguishable from absent to every other endpoint
    here.
    """
    artifact = await get_aim_artifact(kube_client, namespace, name)
    if artifact is None or not is_platform_managed(artifact):
        return False

    referencing = await list_aim_services_referencing_artifact(kube_client, namespace, name)
    if referencing:
        blocking = ", ".join(sorted(referencing))
        if not force:
            raise DeletionConflictException(
                f"Artifact '{name}' is referenced by AIMService(s): {blocking}. Use force=true to delete anyway."
            )
        logger.warning(
            f"Force-deleting AIMArtifact '{name}' in namespace {namespace} while still referenced by "
            f"AIMService(s): {blocking}. Those deployments will fail to reload the adapter on restart."
        )

    # Storage first: reclaiming after the CR is gone would leave the prefix orphaned and invisible
    # whenever the sweep fails.
    await _reclaim_managed_storage(kube_client, minio_client, namespace, name, artifact)
    return await delete_aim_artifact(kube_client, namespace, name)
