# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Whether an adapter's weights are actually present at its storage prefix.

A leaf module on purpose: the deploy path needs this signal too, and reaching it through
``artifacts.service`` would drag the whole artifact-listing machinery — cluster reads, pagination,
storage sweeps — into deploying an AIM.
"""

import asyncio
from collections.abc import Iterable
from urllib.parse import urlparse

from minio.error import S3Error

from ..minio import MinioClient
from .schemas import REQUIRED_PEFT_FILENAMES, ReadinessState

# HEAD responses carry no error body, so minio-py synthesises this code for a 404 on an object.
OBJECT_MISSING_CODE = "NoSuchKey"

# Ceiling on stat threads in flight, so one caller cannot monopolise the shared to_thread workers
# every other storage call in the service also queues on. Expressed in threads rather than adapters
# because an adapter is itself a fan-out of one thread per required PEFT file — bounding adapters
# would let the real thread count run to this times that file count.
READINESS_STAT_THREADS = 16

# What that ceiling permits in adapters, which is the unit both fan-outs actually gate on.
READINESS_ADAPTER_CONCURRENCY = max(1, READINESS_STAT_THREADS // len(REQUIRED_PEFT_FILENAMES))


def split_s3_uri(uri: str | None) -> tuple[str, str] | None:
    """Split an s3:// URI into (bucket, prefix) for a read-only stat, or None if it isn't one.

    Unlike the onboarding path's own URI parser this neither raises nor enforces the tenant
    boundary: it feeds a best-effort readiness probe over an already-stored artifact's own recorded
    URI, not a caller-supplied one, so a malformed value simply yields "readiness unknown" rather
    than a 4xx.
    """
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        return None
    # Dropping leading separators is deliberate: callers enforce confinement on the normalized prefix.
    prefix = parsed.path.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return parsed.netloc, prefix


async def stat_readiness(minio_client: MinioClient | None, location: tuple[str, str] | None) -> ReadinessState:
    """Best-effort check that an adapter's required PEFT weights are present at its S3 prefix.

    ``UNKNOWN`` means the check could not run: storage unconfigured or unreachable, or the recorded
    URI does not parse. Only a genuine not-found on a required file yields ``NOT_READY``; ``READY``
    requires every required file to stat successfully.

    Only ``NOT_READY`` is firm enough to act on — the deploy path refuses on it. ``UNKNOWN`` never
    blocks a caller, so a storage outage degrades this to a missing display signal rather than
    making deployment depend on object storage being up.
    """
    if minio_client is None or location is None:
        return ReadinessState.UNKNOWN
    bucket, prefix = location

    results = await asyncio.gather(
        *(asyncio.to_thread(minio_client.stat_object, bucket, f"{prefix}{f}") for f in REQUIRED_PEFT_FILENAMES),
        return_exceptions=True,
    )
    # A definite not-found on any file means the weights aren't all there yet, and takes priority
    # over an unrelated transient failure (throttle, auth, connection) on another file in the same
    # batch — the latter alone means we could not check, so it only wins when no file is confirmed
    # missing.
    if any(isinstance(r, S3Error) and r.code == OBJECT_MISSING_CODE for r in results):
        return ReadinessState.NOT_READY
    if any(isinstance(r, BaseException) for r in results):
        return ReadinessState.UNKNOWN
    return ReadinessState.READY


async def gather_readiness(
    minio_client: MinioClient | None, locations: Iterable[tuple[str, str] | None]
) -> list[ReadinessState]:
    """Readiness for a whole batch of adapters, holding to the ``READINESS_STAT_THREADS`` ceiling.

    Results are returned in the order the locations were given, so callers can zip them back onto
    whatever they derived the locations from.
    """
    limit = asyncio.Semaphore(READINESS_ADAPTER_CONCURRENCY)

    async def _bounded(location: tuple[str, str] | None) -> ReadinessState:
        async with limit:
            return await stat_readiness(minio_client, location)

    return list(await asyncio.gather(*(_bounded(location) for location in locations)))
