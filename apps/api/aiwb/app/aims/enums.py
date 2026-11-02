# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Enums for AIM CRD resources."""

from enum import StrEnum


class AIMModelStatus(StrEnum):
    """Status of an AIM(Cluster)Model resource.

    Shared between cluster-scoped and namespace-scoped AIMModel CRDs — the
    engine's Go status is `AIMModelStatus` for both.
    """

    NOT_AVAILABLE = "NotAvailable"
    PENDING = "Pending"
    PROGRESSING = "Progressing"
    READY = "Ready"
    DEGRADED = "Degraded"
    FAILED = "Failed"
    ERROR = "Error"
    DELETED = "Deleted"  # API-only status for AIMs removed from cluster


class AIMServiceStatus(StrEnum):
    """Status values for AIMService resources.

    CRD enum: Pending, Starting, Running, Degraded, Failed.
    DELETED is API-only (used by the AIM history syncer, never from K8s).
    """

    PENDING = "Pending"
    STARTING = "Starting"
    RUNNING = "Running"
    FAILED = "Failed"
    DEGRADED = "Degraded"
    DELETED = "Deleted"


class AIMArtifactStatus(StrEnum):
    """Status of an AIMArtifact resource.

    CRD enum: Pending, Progressing, Ready, Degraded, Failed, NotAvailable.
    """

    PENDING = "Pending"
    PROGRESSING = "Progressing"
    READY = "Ready"
    DEGRADED = "Degraded"
    FAILED = "Failed"
    NOT_AVAILABLE = "NotAvailable"


class OptimizationMetric(StrEnum):
    """Performance optimization metrics for AIM deployments."""

    LATENCY = "latency"
    THROUGHPUT = "throughput"


class AIMVersionPolicy(StrEnum):
    """Version-matching policy for custom AIMModels deriving profiles from a base.

    Mirrors aim-engine's `ProfileVersionPolicy`. Controls which versions of
    matching base profiles a custom model copies from.

    - PINNED: match profiles whose `status.version` equals the model's image tag.
    - LATEST: match only the latest available `status.version`.
    - ALL: match profiles at any version.
    - ANY: deprecated alias of ALL, kept for backward compatibility with the CRD.
    """

    PINNED = "pinned"
    LATEST = "latest"
    ALL = "all"
    ANY = "any"


class AcceleratorType(StrEnum):
    """Accelerator family for AIMs (matches v1alpha2 AIMProfile spec.acceleratorType).

    Lowercase to mirror aim-engine's wire values; the API filter is case-sensitive.
    """

    CPU = "cpu"
    GPU = "gpu"


class ResolutionScope(StrEnum):
    """Scope at which aim-engine resolved a reference.

    CRD enum shared by `status.resolvedModel` / `status.resolvedProfile`
    (AIMService) and `status.resolvedParent` (AIMArtifact).
    """

    NAMESPACE = "Namespace"
    CLUSTER = "Cluster"
    MERGED = "Merged"
    UNKNOWN = "Unknown"


class AdapterMode(StrEnum):
    """How an AIMService admits LoRA adapters (`spec.adapterMode`).

    STATIC pins the service to the adapters declared at creation; DYNAMIC lets
    the engine load and unload them while the service runs. The CRD defaults to
    STATIC and makes the field immutable once set, so a deployment created
    without it can never move to DYNAMIC.
    """

    STATIC = "static"
    DYNAMIC = "dynamic"


class AdapterState(StrEnum):
    """Per-adapter lifecycle state on `AIMService.status.adapters[]`.

    Mirrors the CRD enum exactly. AIWB reports these verbatim and derives
    nothing from them: the engine owns the progression, including whether an
    adapter the runtime refused (LOAD_REJECTED) is retried.
    """

    PENDING = "Pending"
    DOWNLOADING = "Downloading"
    DOWNLOADED = "Downloaded"
    DELETING = "Deleting"
    LOADED = "Loaded"
    LOAD_REJECTED = "LoadRejected"
