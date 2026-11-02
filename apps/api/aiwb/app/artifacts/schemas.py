# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Request/response schemas for the artifact onboarding endpoint."""

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from api_common.collections import BasePaginationList, PaginationConditions
from api_common.schemas import BaseModel

from ..aims.crds import AIMArtifactResource
from .manifest import ADAPTER_MANIFEST_FILENAME

# PEFT weights an adapter cannot be reconstructed without. An upload request must declare all of
# them, and an S3 source is verified to contain them; both paths share this set so they cannot drift.
REQUIRED_PEFT_FILENAMES = ("adapter_config.json", "adapter_model.safetensors")

# Cap on the files one artifact transfer covers, in either direction: each entry fans out into a
# presigned-URL signing call, so an unbounded set is a request-sized amplifier.
#
# On download it is applied as the listing is read rather than to what the read produced: reading an
# entry costs a page fetch, so a prefix holding more than this is refused on the file that passes the
# cap instead of after the whole prefix has been pulled. Entries that are not files are bounded
# separately, below.
#
# It counts the artifact's own files only. The adapter manifest AIWB writes into the same prefix is
# not one of them, on either side: an upload declaring the full complement of files must still be
# downloadable once that manifest sits beside them.
MAX_ARTIFACT_FILES = 256

# Bound on entries *read* at a prefix while assembling a download, as distinct from the files above.
# Directory markers are recognised and skipped before the file cap can count them, so without this a
# prefix of nothing but markers is read to exhaustion however large it grows.
#
# Set to the page size of the listing itself: storage hands keys over a thousand at a time and this
# listing does not narrow that. The entry that trips the bound is therefore the first key of the
# second page, and asking for it fetches that whole page — so the scan costs two pages at worst,
# never a walk to the end of the prefix, which is the cost that grows with whatever was put there.
# A servable prefix stays well under it, holding at most MAX_ARTIFACT_FILES files, the manifest, and
# markers for directories those files sit in.
MAX_ARTIFACT_LISTING_ENTRIES = 1000

# An adapter is trained against one base architecture; the list exists for id aliases and sibling
# sizes, not for an open-ended compatibility matrix.
_MAX_COMPATIBLE_WITH = 32

# The description rides on a k8s annotation, whose whole map is capped at 256KB.
_MAX_DESCRIPTION_LENGTH = 2048

# Mirrors the AIMArtifact CRD's own pattern for spec.compatibleWith items. Kept in sync deliberately:
# without it a bare 'gemma-3-1b' reaches the API server and comes back as an opaque failure instead
# of a field-level 422 naming the offending value.
_MODEL_ID_PATTERN = r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+$"

CanonicalModelId = Annotated[str, Field(pattern=_MODEL_ID_PATTERN)]

# DNS-1123-ish resource name of an AIMArtifact CR, bounded by the CRD's own 253-character limit.
# Constrained wherever a caller names an artifact — a path segment here, an adapter reference on a
# deploy request — so a malformed value is a clean 422 rather than a K8s API error deep in a gateway.
ARTIFACT_NAME_PATTERN = r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$"
ARTIFACT_NAME_MAX_LENGTH = 253

ArtifactName = Annotated[str, Field(pattern=ARTIFACT_NAME_PATTERN, max_length=ARTIFACT_NAME_MAX_LENGTH)]


def path_escapes_prefix(path: str) -> bool:
    """Whether a path relative to an artifact's storage prefix fails to name one definite object
    inside it.

    The rule, which every accepted and refused shape follows from: the path must be a '/'-separated
    sequence of *plain* segments, and must not open with a drive designator. A segment is plain when
    it is non-empty, is neither '.' nor '..', and holds no backslash. A shape this has not been asked
    about before is decided by reading it against those two clauses, not by adding a third.

    They come from what a caller does with the path — join it onto a destination, a bucket prefix on
    upload or a directory on download, and expect exactly one object to land under that destination
    on whichever platform does the joining. Three ways that fails, and the clauses cover them. A
    segment that resolves ('', '.', '..') moves the object or erases it, so the path handed over is
    not the path used. A separator the joining platform honours but this rule does not — a backslash,
    on Windows — hides further segments from every clause, traversal among them. And a root marker
    discards the destination outright: an empty first segment on POSIX, a leading '<letter>:' on
    Windows, which is drive-absolute or drive-relative but never relative to what it was joined to.

    Both directions consult this, judging different things by the same resolution: an upload
    validates a *declaration* of where a file is to be written, as ``prefix + path`` against a bucket
    every project shares, while a download classifies an *observation* of a key storage already
    holds. Download refuses such a key outright rather than dropping it, which is what binds the two
    together: accepting one on upload would register an artifact that no later download can hand
    back.

    Outside the rule, and left there: a colon anywhere but the drive position, which on Windows names
    an alternate data stream rather than a location and so stays under the destination
    ('weights/a:b/file.bin'); and directory markers on read, which the download recognises and skips
    before it consults this.
    """
    segments = path.split("/")
    if any(segment in ("", ".", "..") or "\\" in segment for segment in segments):
        return True
    # Anchored at the start rather than matching the segment whole: 'C:' names the drive's current
    # directory and 'C:outside' a path relative to it, and both discard the destination they are
    # joined to. Exactly one letter before the colon — 'CC:' is no drive and stays relative.
    return re.match(r"[A-Za-z]:", segments[0]) is not None


class ArtifactUploadSource(BaseModel):
    type: Literal["upload"]


class ArtifactS3Source(BaseModel):
    type: Literal["s3"]
    uri: str


class CreateArtifactRequest(BaseModel):
    type: Literal["adapter"]
    source: Annotated[ArtifactUploadSource | ArtifactS3Source, Field(discriminator="type")]
    model_id: str = Field(
        description=(
            "HF-style identifier of the adapter itself (e.g. 'org/my-adapter'), stored as "
            "spec.modelId. This is the adapter's own id, not the base model — base-model "
            "compatibility is declared by compatibleWith."
        ),
    )
    compatible_with: list[CanonicalModelId] = Field(
        min_length=1,
        max_length=_MAX_COMPATIBLE_WITH,
        description=(
            "Canonical model IDs this adapter may attach to, stored as spec.compatibleWith. "
            "Declares compatibility without binding the adapter to a resource, so it survives "
            "deletion of any base model and is Ready even when no compatible base is in the "
            "cluster. Must be unique and org-prefixed. Immutable once created."
        ),
        examples=[["example-org/example-model"]],
    )
    rank: int | None = Field(default=None, ge=1)
    display_name: str | None = None
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION_LENGTH)
    files: list[str] | None = Field(
        default=None,
        max_length=MAX_ARTIFACT_FILES + 1,
        description=(
            "Paths to upload, relative to the artifact's storage prefix. At most "
            f"{MAX_ARTIFACT_FILES} files of your own, matching what one download covers; a listed "
            f"'{ADAPTER_MANIFEST_FILENAME}' at the root is not one of them and is dropped rather "
            "than signed, as AIWB writes that key itself."
        ),
    )

    @model_validator(mode="after")
    def _compatible_with_is_a_set(self) -> "CreateArtifactRequest":
        # spec.compatibleWith is x-kubernetes-list-type: set, so a repeat is rejected by the API
        # server. Named here instead, where the response can point at the value.
        duplicates = sorted({v for v in self.compatible_with if self.compatible_with.count(v) > 1})
        if duplicates:
            raise ValueError(f"compatibleWith entries must be unique, repeated: {', '.join(duplicates)}")
        return self

    @model_validator(mode="after")
    def _upload_requires_files(self) -> "CreateArtifactRequest":
        if not isinstance(self.source, ArtifactUploadSource):
            return self
        if not self.files:
            raise ValueError("files must be provided and non-empty when source.type is 'upload'")
        # Both readiness stats and aim-engine read the required PEFT files at the prefix root
        # (f"{prefix}{filename}"), so a required file nested under a subdirectory would upload
        # successfully but never be found — the artifact could never become Ready. Extra files are
        # free to nest.
        declared_at_root = set(self.files)
        missing = [name for name in REQUIRED_PEFT_FILENAMES if name not in declared_at_root]
        if missing:
            raise ValueError(f"upload files must include required PEFT files at the prefix root: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def _validate_files(self) -> "CreateArtifactRequest":
        declared = self.files or []
        # Two bounds, because the exemption alone does not bound anything. The manifest AIWB writes
        # at the prefix root is served by a download without being counted, so a declaration of
        # exactly the cap comes back one entry longer than it went in, and capping the declaration
        # at the cap itself would make the largest artifact this API can produce impossible to
        # re-onboard from its own download. Hence the field's max_length of one over the cap — the
        # longest list a download can produce, mirroring ArtifactDownloadResponse.files. The
        # exemption cannot be left to carry the bound on its own: storage holds one key at most per
        # path, so the download side counts at most one manifest whatever it meets, while a
        # declaration is a list and may repeat the name any number of times. Only the root key is
        # exempt, matching what the download skips; a nested copy is a file of the caller's.
        own_files = sum(1 for file_path in declared if file_path != ADAPTER_MANIFEST_FILENAME)
        if own_files > MAX_ARTIFACT_FILES:
            raise ValueError(
                f"declares {own_files} files, more than the {MAX_ARTIFACT_FILES} files one upload "
                f"covers; a '{ADAPTER_MANIFEST_FILENAME}' at the root does not count towards that"
            )
        # Keys are built as f"{prefix}{file_path}" against a bucket shared by every namespace, so a
        # path escaping the prefix would grant write access into another project's storage, and one
        # that resolves away would land a key the download side refuses, leaving an artifact that
        # cannot be handed back. Allow nested relative paths; reject both.
        for file_path in declared:
            if path_escapes_prefix(file_path):
                raise ValueError(
                    "file paths must be relative and must not contain '.', '..', empty segments, a "
                    f"backslash, or a leading drive designator (e.g. 'C:'): {file_path!r}"
                )
        return self


class UploadInstruction(BaseModel):
    path: str
    method: Literal["PUT"] = "PUT"
    url: str
    expires_at: datetime


class DownloadInstruction(BaseModel):
    """One object stored under the artifact's prefix, and a direct link to fetch it from.

    No expiry of its own: every link in one response is signed in a single batch against the same
    deadline, which the response carries once.
    """

    path: str = Field(
        description=(
            "Path of the object relative to the artifact's storage prefix. Contains '/' for an "
            "object nested below the prefix, so writing every entry to its own path rebuilds the "
            "prefix's contents as they stand."
        ),
    )
    method: Literal["GET"] = "GET"
    url: str
    size_bytes: int | None = Field(
        default=None,
        description="Size of the object in bytes, read from object storage. Null where storage reports no size for it.",
    )


class ArtifactDownloadResponse(BaseModel):
    """Where to fetch an artifact's files from, and until when.

    Not the bytes, and not a description of the artifact: ``files`` carries one time-limited direct
    link per file under the artifact's storage prefix — directory markers stored there are left out
    — so the transfer runs between the caller and object storage rather than through this API. A
    client that needs to know what the artifact is reads the artifact itself.
    """

    # One over the file cap, which is also the largest set onboarding accepts: the manifest AIWB
    # writes into the artifact's prefix is served but not counted against that cap, on this side and
    # on the way in, so a full complement of files comes back with the manifest on top and the
    # result can be handed straight back in as a new artifact.
    files: list[DownloadInstruction] = Field(max_length=MAX_ARTIFACT_FILES + 1)
    expires_at: datetime = Field(description="When every link in `files` stops working.")


class ArtifactType(StrEnum):
    """Values of ``AIMArtifact.spec.type`` this API exposes.

    Adapters are the whole collection today: readiness means the LoRA PEFT files, and the delete
    guard checks adapter references on AIMServices. Widening to another type means answering both
    for it, so the enum grows one value at a time rather than mirroring the CRD.
    """

    ADAPTER = "adapter"


class ReadinessState(StrEnum):
    """Whether the files the artifact's type requires are present at its storage prefix.

    ``Unknown`` is a distinct verdict from ``NotReady``: it means the check could not run
    (storage unconfigured or unreachable, or the recorded URI does not parse), not that a
    file is missing.
    """

    READY = "Ready"
    NOT_READY = "NotReady"
    UNKNOWN = "Unknown"


class ArtifactStorage(BaseModel):
    """Where the artifact's files live and what the API found there.

    Kept together, and apart from ``artifact``, so a reader can tell at a glance which half of a
    row came from the bucket and which from Kubernetes. It also keeps ``status`` unambiguous:
    ``artifact.status`` is what the controller reconciled, ``storage.readiness`` is what is actually
    on disk, and the two can legitimately disagree.

    Nothing here is stored, so nothing can go stale. Any future field has to clear the same bar:
    derived at read time from data already fetched (or one bounded extra call), with a named
    consumer, degrading to a defined value rather than failing the request.
    """

    uri: str | None = Field(
        default=None,
        description=(
            "Object-storage prefix holding the artifact's files, read off the resource. Null when "
            "the resource records no source."
        ),
    )
    readiness: ReadinessState


class ArtifactResponse(BaseModel):
    """An artifact as the API presents it.

    Two halves, one per source of truth: ``storage`` is what AIWB can see in the bucket, and
    ``artifact`` is the Kubernetes resource passed through verbatim. AIWB owns only what the CR
    cannot express, so nothing from the resource is renamed into a parallel AIWB model that would
    have to be revised every time the CRD moves.

    Every row is backed by an AIMArtifact. Files sitting in the project's storage that no resource
    claims are not artifacts and are not reported: without a record there is nothing to name,
    address, or delete.

    ``artifact.metadata.name`` is the identity clients key rows on, and the path segment for the
    by-name GET and DELETE.
    """

    storage: ArtifactStorage
    artifact: AIMArtifactResource = Field(
        description=(
            "The AIMArtifact resource claiming these files, verbatim, minus the credential references in `spec.env`."
        ),
    )
    servable: bool | None = Field(
        default=None,
        description=(
            "Whether the deployment named by `?servableBy=` can load this adapter: its resolved "
            "profile advertises the adapter capability, and the adapter declares either the "
            "weights that profile serves or the model group they belong to. The group is accepted "
            "only while adapter producers still record it instead of the weights; it is the "
            "coarser of the two. Null when the query did not ask, so a caller cannot mistake "
            "'not evaluated' for 'no'."
        ),
    )


class CreateArtifactResponse(ArtifactResponse):
    """The created adapter, in the same shape the list endpoint returns, plus its upload URLs.

    Inherits ``storage`` and ``artifact`` rather than nesting them, so a client can drop the
    response straight into the collection it is already rendering. ``uploads`` is empty for an
    S3 source, where the files already exist.
    """

    uploads: list[UploadInstruction] = Field(default_factory=list)


class ArtifactsList(BasePaginationList):
    data: list[ArtifactResponse]


class ListArtifactsQuery(PaginationConditions):
    page: int = Field(default=1, ge=1)
    # Bound page_size so a single client cannot fetch arbitrarily large pages.
    page_size: int = Field(default=10, ge=1, le=100)
    # Every filter is bounded by its own enum size: a repeatable param a caller controls must be
    # capped at the Pydantic boundary, and no request can meaningfully name a value twice.
    type: list[ArtifactType] | None = Field(
        default=None,
        max_length=len(ArtifactType),
        description="Filter by `AIMArtifact.spec.type` (repeatable). Omitted means every type this API exposes.",
        examples=[["adapter"]],
    )
    readiness: list[ReadinessState] | None = Field(
        default=None,
        max_length=len(ReadinessState),
        description=(
            "Filter by whether the artifact's files are all present (repeatable). Omitted means no "
            "readiness filter. Setting it reads storage for the whole collection rather than just "
            "the returned page, since the verdict decides which rows a page contains."
        ),
        examples=[["Ready"]],
    )
    servable_by: UUID | None = Field(
        default=None,
        description=(
            "Report, per row, whether this deployment can load the adapter. Answered from the "
            "profile the deployment resolved, by the same rule the deploy and attach endpoints "
            "apply, so a row reported servable is one they accept. Does not filter: a caller "
            "showing an existing selection still needs the rows it cannot serve. Omitted leaves "
            "`servable` null on every row; naming a deployment that does not exist is a 404."
        ),
    )
