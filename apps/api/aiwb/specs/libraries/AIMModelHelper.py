# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Kubectl-based AIMModel CR helpers for AIWB E2E tests.

Keeps YAML construction and shell invocation out of .resource files, where
the project conventions require keyword bodies to delegate real logic to
Python libraries.
"""

import base64
import io
import json
import os
import socket
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import requests
from minio import Minio
from minio.error import S3Error
from robot.api import logger
from robot.api.deco import keyword
from robot.api.exceptions import SkipExecution
from robot.libraries.BuiltIn import BuiltIn


def _split_store_url(value: str) -> SplitResult:
    """Split an object-store address, tolerating a schemeless ``host:port``.

    ``urlsplit`` reads the host of a schemeless value as a scheme -- ``store:80`` parses to scheme
    ``store`` with no netloc at all -- so a bare address would otherwise yield an empty endpoint.

    Which parts a caller consumes is the caller's business: the bucket URL is read for its scheme,
    host and bucket path, while an endpoint override supplies only scheme and host.
    """
    return urlsplit(value if "//" in value else f"//{value}")


_KUBECTL_TIMEOUT = 60
_UPLOAD_TIMEOUT = 60
# Annotation the onboarding flow stamps with the upstream repo id; the models
# grid/detail responses carry it so a listed model can be located by source.
_CANONICAL_REPO_ID_ANNOTATION = "aiwb.apps.eai.amd.com/canonical-repo-id"
_MODEL_SOURCE_TYPE_LABEL = "aiwb.apps.eai.amd.com/model-source-type"
_CUSTOM_MODEL_SOURCE_TYPE = "custom"
_FINE_TUNING_WORKLOAD_TYPE_LABEL = "airm.silogen.ai/workload-type"
_FINE_TUNING_WORKLOAD_TYPE = "FINE_TUNING"
_ONBOARD_REVISION_ANNOTATION = "airm.silogen.ai/revision"
_ONBOARD_SOURCE_SHA_ANNOTATION = "aiwb.apps.eai.amd.com/source-sha"
_S3_BUCKET_URL_RAW = os.getenv(
    "AIWB_SPECS_S3_BUCKET_URL",
    "http://filer-s3.seaweedfs-instance.svc.cluster.local:80",
)


def _canonical_bucket_url(raw: str) -> SplitResult:
    """Split a bucket URL after adding a scheme, validating the host and at most one bucket segment.

    The value is written verbatim into the storage ConfigMap as ``BUCKET_URL``. The product reads
    only its endpoint origin (``AIWB_SPECS_MINIO_BUCKET`` names the bucket), but the direct client
    also derives the bucket from a path when one is given, and a trailing slash or a multi-segment
    path would yield an invalid bucket name (``bucket/`` or ``a/b``). Require the path to be empty
    or exactly one segment, and strip a trailing slash.
    """
    if "://" in raw:
        normalized = raw
    elif raw.startswith("//"):
        normalized = f"http:{raw}"
    else:
        normalized = f"http://{raw}"

    parts = urlsplit(normalized)
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError(f"AIWB_SPECS_S3_BUCKET_URL {raw!r} does not name a valid port") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"AIWB_SPECS_S3_BUCKET_URL {raw!r} must name an HTTP(S) host")
    if parts.username is not None or parts.password is not None:
        raise ValueError(
            # Deliberately omit the raw value: it carries the userinfo we are rejecting, and this
            # message reaches Robot/CI logs.
            "AIWB_SPECS_S3_BUCKET_URL must not contain embedded credentials (userinfo); use the project Secret instead"
        )
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) > 1:
        raise ValueError(f"AIWB_SPECS_S3_BUCKET_URL {raw!r} path must be empty or one bucket segment")
    if parts.query or parts.fragment:
        raise ValueError(f"AIWB_SPECS_S3_BUCKET_URL {raw!r} must not contain a query or fragment")
    return urlsplit(urlunsplit((parts.scheme, parts.netloc, f"/{segments[0]}" if segments else "", "", "")))


_S3_BUCKET_URL_PARTS = _canonical_bucket_url(_S3_BUCKET_URL_RAW)
_S3_BUCKET_URL = urlunsplit(_S3_BUCKET_URL_PARTS)
# AIWB_SPECS_MINIO_ENDPOINT still overrides on its own, for a runner reaching storage some other
# way. The scheme must then come from the override too: deriving TLS from the bucket URL while the
# endpoint points somewhere else addresses one store with the other's transport. A bare host:port
# override means plain HTTP, which is what a local port-forward is; prefix it with https:// for TLS.
# The override names only the endpoint origin. A path would be silently ignored while the bucket
# still came from AIWB_SPECS_MINIO_BUCKET or the bucket URL, so reject it rather than accepting a
# misleading configuration. Credentials belong in the project Secret, never in this URL.
_MINIO_ENDPOINT_OVERRIDE = os.getenv("AIWB_SPECS_MINIO_ENDPOINT")
if _MINIO_ENDPOINT_OVERRIDE:
    _OVERRIDE_PARTS = _split_store_url(_MINIO_ENDPOINT_OVERRIDE)
    try:
        _ = _OVERRIDE_PARTS.port
    except ValueError as exc:
        raise ValueError(f"AIWB_SPECS_MINIO_ENDPOINT {_MINIO_ENDPOINT_OVERRIDE!r} has an invalid port") from exc
    if _OVERRIDE_PARTS.scheme not in {"", "http", "https"} or not _OVERRIDE_PARTS.hostname:
        raise ValueError(f"AIWB_SPECS_MINIO_ENDPOINT {_MINIO_ENDPOINT_OVERRIDE!r} must name an HTTP(S) host")
    if _OVERRIDE_PARTS.username is not None or _OVERRIDE_PARTS.password is not None:
        # Deliberately omit the raw value: it carries the userinfo we are rejecting, and this
        # message reaches Robot/CI logs.
        raise ValueError(
            "AIWB_SPECS_MINIO_ENDPOINT must not contain embedded credentials (userinfo); use the project Secret instead"
        )
    if _OVERRIDE_PARTS.path not in {"", "/"}:
        raise ValueError(f"AIWB_SPECS_MINIO_ENDPOINT {_MINIO_ENDPOINT_OVERRIDE!r} must not contain a path")
    if _OVERRIDE_PARTS.query or _OVERRIDE_PARTS.fragment:
        raise ValueError(f"AIWB_SPECS_MINIO_ENDPOINT {_MINIO_ENDPOINT_OVERRIDE!r} must not contain a query or fragment")
    _MINIO_ENDPOINT = _OVERRIDE_PARTS.netloc
    _MINIO_SECURE = _OVERRIDE_PARTS.scheme == "https"
else:
    _MINIO_ENDPOINT = _S3_BUCKET_URL_PARTS.netloc
    _MINIO_SECURE = _S3_BUCKET_URL_PARTS.scheme == "https"
# The platform states endpoint and bucket separately (MINIO_URL plus MINIO_BUCKET), so the bucket
# URL normally carries no path. Honour one if an override supplies it, rather than addressing the
# overridden store while still reading and writing the default bucket — consumers handed this URL
# read the bucket off its path the same way.
_MINIO_BUCKET = os.getenv("AIWB_SPECS_MINIO_BUCKET") or _S3_BUCKET_URL_PARTS.path.strip("/") or "default-bucket"
_STORAGE_CONFIGMAP_LABEL = "airm.silogen.ai/storage"
_STORAGE_TYPE_LABEL = "airm.silogen.ai/storage-type"
_PREPARED_S3_PREFIXES: list[tuple[str, str]] = []
# Repository tail for the default Instinct/base family published as an AIMClusterModel.
_DEFAULT_BASE_FAMILY_ID = "aim-base"
_RADEON_BASE_FAMILY_ID = "aim-radeon-base"
_EPYC_BASE_FAMILY_ID = "aim-epyc-base"
_AIM_MODEL_API_VERSION = "aim.eai.amd.com/v1alpha2"


def _accelerator_categories(accelerators: list[dict[str, Any]]) -> tuple[bool, bool, bool]:
    """Classify detected accelerators the same way cluster.service does."""
    has_radeon_gpu = False
    has_other_gpu = False
    has_epyc_cpu = False

    for entry in accelerators:
        accel_type = str(entry.get("acceleratorType") or entry.get("accelerator_type") or "").lower()
        model = str(entry.get("acceleratorModel") or entry.get("accelerator_model") or "").strip()
        vendor = str(entry.get("acceleratorVendor") or entry.get("accelerator_vendor") or "").strip().lower()
        if accel_type == "gpu":
            normalized_model = model.upper()
            is_radeon_gpu = (
                normalized_model.startswith(("R", "W"))
                and not normalized_model.startswith("RTX")
                and vendor != "nvidia"
            )
            if is_radeon_gpu:
                has_radeon_gpu = True
            else:
                has_other_gpu = True
        elif accel_type == "cpu" and model.startswith("EPYC_"):
            has_epyc_cpu = True

    return has_radeon_gpu, has_other_gpu, has_epyc_cpu


def _catalog_family_ids(aim_image_families: list[dict[str, Any]]) -> set[str]:
    """Family ids from /cluster/aim-images (AIMClusterModel-backed, hardware-validated)."""
    family_ids: set[str] = set()
    for family in aim_image_families:
        family_id = str(family.get("familyId") or family.get("family_id") or "").strip()
        if family_id and family_id != "automatic":
            family_ids.add(family_id)
    return family_ids


def _preferred_base_family_ids(has_radeon_gpu: bool, has_other_gpu: bool, has_epyc_cpu: bool) -> list[str]:
    """Ordered family-id candidates mirroring ensure_namespace_aim_base_model priority."""
    family_ids: list[str] = []
    if has_other_gpu:
        family_ids.append(_DEFAULT_BASE_FAMILY_ID)
    if has_radeon_gpu:
        family_ids.append(_RADEON_BASE_FAMILY_ID)
    if has_epyc_cpu:
        family_ids.append(_EPYC_BASE_FAMILY_ID)
    if not family_ids:
        family_ids.append(_DEFAULT_BASE_FAMILY_ID)
    return family_ids


def _applicable_base_family_ids(
    aim_image_families: list[dict[str, Any]],
    accelerators: list[dict[str, Any]],
) -> list[str]:
    """All base-image families published on the cluster that match detected accelerators.

    Returns family ids in onboard priority order (Instinct/base, then Radeon, then EPYC).
    Clusters with multiple accelerator types may therefore expose more than one entry.
    """
    catalog_ids = _catalog_family_ids(aim_image_families)
    if not catalog_ids:
        raise AssertionError(
            "No base image families found in /cluster/aim-images; "
            "expected at least one hardware-validated AIMClusterModel base family"
        )

    has_radeon_gpu, has_other_gpu, has_epyc_cpu = _accelerator_categories(accelerators)
    preferred_ids = _preferred_base_family_ids(has_radeon_gpu, has_other_gpu, has_epyc_cpu)
    applicable = [family_id for family_id in preferred_ids if family_id in catalog_ids]
    if applicable:
        return applicable

    # No accelerator-matched family is published; fall back to the full catalog.
    return sorted(catalog_ids)


def _select_onboard_base_family_id(
    aim_image_families: list[dict[str, Any]],
    accelerators: list[dict[str, Any]],
) -> str:
    """Pick the single base family onboard provisions for a new custom model."""
    applicable = _applicable_base_family_ids(aim_image_families, accelerators)

    # ensure_namespace_aim_base_model prefers the default Instinct/base ref when present
    # in the candidate list; express that as preferring aim-base when it is applicable.
    if _DEFAULT_BASE_FAMILY_ID in applicable:
        return _DEFAULT_BASE_FAMILY_ID

    return applicable[0]


@keyword("Resolve Applicable Base Image Families From Cluster Discovery")
def resolve_applicable_base_image_families_from_cluster_discovery(
    aim_image_families: list[dict[str, Any]],
    accelerators: list[dict[str, Any]],
) -> list[str]:
    """Return all base-image family ids matching cluster AIMClusterModels and accelerators."""
    return _applicable_base_family_ids(aim_image_families, accelerators)


@keyword("Resolve Onboard Base Image Family From Cluster Discovery")
def resolve_onboard_base_image_family_from_cluster_discovery(
    aim_image_families: list[dict[str, Any]],
    accelerators: list[dict[str, Any]],
) -> str:
    """Return the base-image family id onboard provisions for custom-model derivation.

    When several families apply (mixed accelerator clusters), this is the prioritized
    choice onboard uses; see ``Resolve Applicable Base Image Families From Cluster Discovery``
    for the full applicable set.
    """
    return _select_onboard_base_family_id(aim_image_families, accelerators)


@keyword("Cluster Gpu Accelerator Model")
def cluster_gpu_accelerator_model(accelerators: list[dict[str, Any]], onboard_image: str = "") -> str:
    """First GPU ``acceleratorModel`` the onboard image's family can run on, or '' when none.

    The EPYC (CPU) family runs on no GPU, so it never gets an override.

    A mixed Instinct/Radeon cluster lists accelerators by device ID, so the first GPU can belong
    to a different family than the image onboard uses; an override for it would leave every
    derived profile unavailable. With no ``onboard_image`` any GPU qualifies.
    """
    family_id = _family_id_from_image_ref(onboard_image) if onboard_image else ""
    if family_id == _EPYC_BASE_FAMILY_ID:
        return ""
    for entry in accelerators:
        if str(entry.get("acceleratorType") or "").lower() != "gpu":
            continue
        model = str(entry.get("acceleratorModel") or "").strip()
        if not model:
            continue
        has_radeon_gpu, _, _ = _accelerator_categories([entry])
        if family_id == _RADEON_BASE_FAMILY_ID and not has_radeon_gpu:
            continue
        if family_id == _DEFAULT_BASE_FAMILY_ID and has_radeon_gpu:
            continue
        return model
    return ""


# Bookkeeping label the suite puts on custom models it creates, so a later run can tell its own
# models from a finished run's. It is test bookkeeping, not behavior under test.
_RUN_ID_LABEL = "e2e.silogen.ai/run-id"


@keyword("New E2E Run Id")
def new_e2e_run_id(ci_run_id: str = "") -> str:
    """An id unique to this Robot invocation, readable by the CI run it belongs to.

    The remote runner pod has no CI environment, so the workflow passes the CI run id in as a
    Robot variable and the caller hands it here; ``GITHUB_RUN_ID`` covers a runner that has it.

    Unique per invocation rather than per CI run so a re-run attempt of the same run does not
    mistake the earlier attempt's leftovers for its own.
    """
    return f"{ci_run_id or os.getenv('GITHUB_RUN_ID') or 'local'}-{uuid.uuid4().hex[:8]}"


@keyword("Stamp AIMModel With Run Id")
def stamp_aim_model_with_run_id(name: str, namespace: str, run_id: str) -> bool:
    """Label an AIMModel with ``run_id``; False when it could not be labeled.

    Best-effort on purpose: a model that was created but never labeled (the run died between the
    two, or kubectl failed) carries no stamp, and an unstamped model is only ever reported, never
    swept. Failing the test over bookkeeping would trade that safe outcome for a worse one.
    """
    try:
        result = subprocess.run(
            ["kubectl", "label", "aimmodels", name, "-n", namespace, f"{_RUN_ID_LABEL}={run_id}", "--overwrite"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as err:
        logger.warn(f"Could not stamp AIMModel {name} with the run id: {err}")
        return False
    if result.returncode != 0:
        logger.warn(f"Could not stamp AIMModel {name} with the run id: {result.stderr.strip()}")
        return False
    return True


def _run_stamp(model: dict[str, Any]) -> str:
    return str(((model.get("metadata") or {}).get("labels") or {}).get(_RUN_ID_LABEL) or "")


def _is_ci_run_id(run_id: str) -> bool:
    return run_id.partition("-")[0].isdigit()


def _other_stamps(custom_models: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    return [model for model in custom_models if _run_stamp(model) not in ("", run_id)]


@keyword("Models Stamped By Another Run")
def models_stamped_by_another_run(custom_models: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """The ``custom_models`` safe to sweep: stamped by a different CI run, swept by a CI run.

    Dispatched CI runs are serialized per runner, so another CI run's stamp names a run that has
    already finished. That guarantee does not cover a local invocation, which can run
    alongside anything, so a ``local`` stamp, or any sweep started from a local invocation, selects
    nothing; ``Models Stamped By An Unswept Run`` reports those instead. A model with no stamp
    proves nothing either way and is never returned.
    """
    if not _is_ci_run_id(run_id):
        return []
    return [model for model in _other_stamps(custom_models, run_id) if _is_ci_run_id(_run_stamp(model))]


@keyword("Models Stamped By An Unswept Run")
def models_stamped_by_an_unswept_run(custom_models: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """Other runs' models this run may not delete because it cannot prove their run finished."""
    swept = {id(model) for model in models_stamped_by_another_run(custom_models, run_id)}
    return [model for model in _other_stamps(custom_models, run_id) if id(model) not in swept]


@keyword("Models Without A Run Stamp")
def models_without_a_run_stamp(custom_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ``custom_models`` no run claimed; these are reported, not swept."""
    return [model for model in custom_models if not _run_stamp(model)]


@keyword("Deployment Ids Pinning Custom Models")
def deployment_ids_pinning_custom_models(
    deployments: list[dict[str, Any]], custom_models: list[dict[str, Any]]
) -> list[str]:
    """Ids of the deployments whose target AIM is one of ``custom_models``.

    Scopes a stale-state sweep to what Custom Models tests create, so deployments other suites
    own in the shared project are left alone.
    """
    names = {str((model.get("metadata") or {}).get("name") or "") for model in custom_models}
    names.discard("")
    return [
        str(deployment["id"])
        for deployment in deployments
        if deployment.get("id") and str(((deployment.get("spec") or {}).get("model") or {}).get("name") or "") in names
    ]


def _family_id_from_image_ref(image_ref: str) -> str:
    """Return the repository tail that onboard uses as the base-model name."""
    repository = image_ref.rsplit("@", 1)[0]
    return repository.rsplit("/", 1)[-1].rsplit(":", 1)[0].strip()


def _image_ref_from_repository_and_tag(repository: str, tag: str) -> str:
    """Rebuild a catalog image ref, preserving digest pins as ``repo@sha256:...``."""
    if tag.startswith("sha256:"):
        return f"{repository}@{tag}"
    return f"{repository}:{tag}"


@keyword("Build Catalog Image Ref")
def build_catalog_image_ref(repository: str, tag: str) -> str:
    """Join a catalog repository and tag, using ``@`` for digest-only tags."""
    return _image_ref_from_repository_and_tag(str(repository).strip(), str(tag).strip())


def _published_base_images(aim_image_families: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return ``(family_id, image_ref)`` pairs from the cluster catalog."""
    images: list[tuple[str, str]] = []
    for family in aim_image_families:
        family_id = str(family.get("familyId") or family.get("family_id") or "").strip()
        repository = str(family.get("repository") or "").strip()
        tags = family.get("tags") or []
        if not family_id or family_id == "automatic" or not repository:
            continue
        for tag in tags:
            tag_value = str(tag).strip()
            if tag_value:
                images.append((family_id, _image_ref_from_repository_and_tag(repository, tag_value)))
    return images


@keyword("Resolve Alternate Onboard Image From Cluster Discovery")
def resolve_alternate_onboard_image_from_cluster_discovery(
    aim_image_families: list[dict[str, Any]],
    accelerators: list[dict[str, Any]],
    current_image: str,
) -> str:
    """Return a published image that is not the hardware-default onboard image.

    Prefers a different family so selected-image onboarding cannot pass by
    matching the cluster default. Falls back to another tag of the default
    family. Skips when the catalog cannot provide a mismatch.
    """
    default_family = _select_onboard_base_family_id(aim_image_families, accelerators)
    published = _published_base_images(aim_image_families)
    for family_id, image_ref in published:
        if family_id != default_family and image_ref != current_image:
            return image_ref
    for family_id, image_ref in published:
        if family_id == default_family and image_ref != current_image:
            return image_ref
    raise SkipExecution(
        "Cluster catalog does not publish a second runtime image to distinguish selected-image onboarding"
    )


@keyword("Resolve Conflicting Tag Of Onboard Image")
def resolve_conflicting_tag_of_onboard_image(
    aim_image_families: list[dict[str, Any]],
    current_image: str,
) -> str:
    """Return another published tag of the same family as ``current_image``."""
    current_family = _family_id_from_image_ref(current_image)
    for family_id, image_ref in _published_base_images(aim_image_families):
        if family_id == current_family and image_ref != current_image:
            return image_ref
    raise SkipExecution("Cluster catalog does not publish a second tag of the selected runtime family")


@keyword("AIMModel Spec Image")
def aim_model_spec_image(name: str, namespace: str, scope: str = "Namespace") -> str:
    """Return ``spec.image`` of the named base model at ``scope``."""
    return _base_resource_spec_image(name, namespace, scope)


@keyword("AIMModel Should Use Runtime Family From Image")
def aim_model_should_use_runtime_family_from_image(name: str, namespace: str, expected_image: str) -> None:
    """Assert the named AIMModel derives from and runs ``expected_image``."""
    spec = _aim_model_spec(name, namespace)
    profiles = spec.get("profiles") or {}
    family, scope = _derived_from_model_ref(spec)
    actual_image = str((profiles.get("overrides") or {}).get("image") or "").strip()
    if actual_image != expected_image:
        raise AssertionError(f"AIMModel {name} should use image '{expected_image}', got '{actual_image}'")
    base_image = _base_resource_spec_image(family, namespace, scope)
    if base_image != expected_image:
        raise AssertionError(f"Base model {family} ({scope}) should use image '{expected_image}', got '{base_image}'")
    if scope.lower() != "cluster":
        expected_family = _family_id_from_image_ref(expected_image)
        if family != expected_family:
            raise AssertionError(f"AIMModel {name} should derive from '{expected_family}', got '{family}'")


def _derived_from_model_ref(spec: dict[str, Any]) -> tuple[str, str]:
    profiles = spec.get("profiles") or {}
    derived_from = profiles.get("derivedFrom") or {}
    selector = derived_from.get("selector") or {}
    model_ref = selector.get("modelRef") or {}
    family = str(model_ref.get("name") or "").strip()
    scope = str(model_ref.get("scope") or "Namespace").strip() or "Namespace"
    return family, scope


def _base_resource_spec_image(name: str, namespace: str, scope: str) -> str:
    if scope.lower() == "cluster":
        spec = _kubectl_custom_object_spec(["aimclustermodels", name], f"aimclustermodels/{name}")
    else:
        spec = _aim_model_spec(name, namespace)
    return str(spec.get("image") or "").strip()


def _aim_model_spec(name: str, namespace: str) -> dict[str, Any]:
    return _kubectl_custom_object_spec(["aimmodels", name, "-n", namespace], f"aimmodels/{name}")


def _kubectl_custom_object_spec(resource_args: list[str], error_label: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["kubectl", "get", *resource_args, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError(f"kubectl not found on PATH — cannot read {error_label}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for {error_label}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get {error_label} failed: {result.stderr}")
    return json.loads(result.stdout).get("spec") or {}


def _track_prepared_s3_prefix(namespace: str, prefix: str) -> None:
    """Record a generated S3 test prefix for suite-level cleanup."""
    entry = (namespace, prefix)
    if entry not in _PREPARED_S3_PREFIXES:
        _PREPARED_S3_PREFIXES.append(entry)


def _adapter_prefix(namespace: str, name: str) -> str:
    """The object-storage prefix the platform allocates for one adapter.

    Restated here rather than imported: these specs exercise the API as a black box, so the layout
    they write to has to be the one a client would infer, not the one the server computes.
    """
    return f"{namespace}/adapters/{name}/"


def _get_minio_credentials(namespace: str) -> tuple[str, str]:
    """Read MinIO access and secret keys from the minio-credentials secret."""
    result = subprocess.run(
        ["kubectl", "get", "secret", "minio-credentials", "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
        timeout=_KUBECTL_TIMEOUT,
    )
    data = json.loads(result.stdout)["data"]
    access = base64.b64decode(data["minio-access-key"]).decode().strip()
    secret = base64.b64decode(data["minio-secret-key"]).decode().strip()
    return access, secret


def _object_storage_reachable(timeout: float = 2.0) -> bool:
    """True when a TCP connection to the configured object-storage endpoint can be opened.

    False means the address did not answer -- refused, timed out, or its name did not resolve.
    Name resolution is included deliberately: an in-cluster service that no release deploys has no
    DNS record, so NXDOMAIN is exactly how genuinely-absent object storage presents itself here.

    A malformed endpoint raises instead of answering False, because False skips the test and a
    configuration error reported as "storage is absent" would be skipped over -- the failure this
    whole path exists to avoid. Parsed as a URL authority rather than split on ":" so a bracketed
    IPv6 endpoint resolves to its own host.
    """
    parts = urlsplit(f"//{_MINIO_ENDPOINT}")
    try:
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        raise ValueError(f"Object-storage endpoint {_MINIO_ENDPOINT!r} does not name a valid port") from exc
    if not host:
        raise ValueError(f"Object-storage endpoint {_MINIO_ENDPOINT!r} names no host")
    try:
        with socket.create_connection((host, port or (443 if _MINIO_SECURE else 80)), timeout=timeout):
            return True
    except OSError:
        return False


def _new_minio_client(namespace: str) -> Minio:
    """A client for the project's object storage, addressed as the platform addresses it."""
    access, secret = _get_minio_credentials(namespace)
    return Minio(_MINIO_ENDPOINT, access_key=access, secret_key=secret, secure=_MINIO_SECURE, cert_check=False)


def _minio_client(namespace: str) -> Minio:
    """As ``_new_minio_client``, but skipping the test when the store cannot be reached.

    Verifying stored objects directly needs a reachable object store. An install backed by
    storage the test runner cannot open a connection to leaves that precondition unmet, so the
    test is SKIPPED rather than failed; point AIWB_SPECS_S3_BUCKET_URL (or, on its own,
    AIWB_SPECS_MINIO_ENDPOINT) at a reachable address to run these tests there.
    """
    if not _object_storage_reachable():
        BuiltIn().skip(
            f"Object storage at {_MINIO_ENDPOINT} is not reachable from the test runner, so the "
            "stored objects this scenario inspects cannot be read directly."
        )
    return _new_minio_client(namespace)


def _prefix_from_storage_location(uri: str) -> str:
    """The object key prefix a storage location addresses inside the project's bucket."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an object-storage location: {uri!r}")
    bucket, _, prefix = uri[len("s3://") :].partition("/")
    if bucket != _MINIO_BUCKET or not prefix:
        raise ValueError(f"Storage location {uri!r} does not name a prefix in bucket {_MINIO_BUCKET}")
    return prefix


def _model_source_uris(model: dict[str, Any]) -> list[str]:
    """Return every declared model source URI across legacy and v1alpha2 shapes."""
    spec = model.get("spec") or {}
    uris: list[str] = []

    for source in spec.get("modelSources") or []:
        uri = source.get("sourceUri")
        if uri:
            uris.append(str(uri))

    profiles = spec.get("profiles") or {}
    overrides = profiles.get("overrides") or {}
    for source in overrides.get("modelSources") or []:
        uri = source.get("sourceUri")
        if uri:
            uris.append(str(uri))

    if uris:
        return uris

    raise AssertionError(
        "Fine-tuned model payload has no sourceUri in spec.modelSources or spec.profiles.overrides.modelSources"
    )


@keyword("Fine-Tuned Model Source And Parent Storage Locations")
def fine_tuned_model_source_and_parent_storage_locations(model: dict[str, Any]) -> list[str]:
    """Return sourceUri prefixes and their parent prefixes as verification locations.

    This intentionally assumes today's fine-tune producer shape where a source URI
    points at a terminal directory under a per-run path. If the producer starts
    emitting a different terminal layout, this check fails closed (extra leftovers)
    rather than silently asserting the wrong location.
    """
    locations: list[str] = []
    for source_uri in _model_source_uris(model):
        bucket, _, prefix = source_uri.removeprefix("s3://").partition("/")
        if bucket != _MINIO_BUCKET or not prefix:
            raise AssertionError(
                f"Fine-tuned model sourceUri {source_uri!r} does not point at bucket {_MINIO_BUCKET} "
                "with a non-empty prefix"
            )

        source_prefix = prefix if prefix.endswith("/") else f"{prefix}/"
        locations.append(f"s3://{_MINIO_BUCKET}/{source_prefix}")

        parent = source_prefix.rstrip("/").rpartition("/")[0]
        if parent:
            locations.append(f"s3://{_MINIO_BUCKET}/{parent}/")

    # Keep deterministic order while deduplicating when multiple sources share a parent.
    return list(dict.fromkeys(locations))


def _apply_yaml(yaml_body: str, namespace: str, error_label: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, prefix="aimmodel-") as tmp:
        tmp.write(yaml_body)
        tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(tmp_path), "-n", namespace],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError(f"kubectl not found on PATH — cannot apply YAML for {error_label}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl apply timed out after {_KUBECTL_TIMEOUT}s for {error_label}")
    finally:
        tmp_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create {error_label}: {result.stderr}")


@keyword("Apply Dummy AIMModel CR")
def apply_dummy_aim_model_cr(name: str, namespace: str) -> str:
    """Apply a minimal AIMModel CR that simulates a completed fine-tuned model.

    No GPU or actual fine-tuning needed — the CR exposes the same K8s shape
    the API surfaces for real models, so list/get tests can run on any cluster.
    """
    # airm.silogen.ai/workload-type=FINE_TUNING is the contract with
    # fine_tuning.service._is_fine_tuning_model; without it the dummy AIMModel
    # is invisible to GET /v1/projects/{p}/fine-tuning/models and the discovery
    # tests fail with 404 / empty list.
    #
    # Fine-tuning output shape only: deliberately omits model-source-type=custom and
    # onboard revision/source-sha stamps so copy/eligibility tests can distinguish
    # non-custom AIMModels from custom imports.
    yaml_body = (
        f"apiVersion: {_AIM_MODEL_API_VERSION}\n"
        "kind: AIMModel\n"
        "metadata:\n"
        f"  name: {name}\n"
        "  labels:\n"
        f'    aiwb.apps.eai.amd.com/model-name: "{name}"\n'
        '    airm.silogen.ai/workload-type: "FINE_TUNING"\n'
        "spec:\n"
        '  image: "fake-registry/dummy:latest"\n'
    )
    _apply_yaml(yaml_body, namespace, f"dummy AIMModel CR {name}")
    return name


@keyword("AIMModel Should Not Be Custom Import")
def aim_model_should_not_be_custom_import(name: str, namespace: str) -> None:
    """Assert an AIMModel CR is not stamped as a custom-model import.

    Matches the copy endpoint eligibility check: custom imports carry
    ``model-source-type=custom`` plus onboard revision and source-sha annotations.
    """
    try:
        result = subprocess.run(
            ["kubectl", "get", "aimmodels", name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot inspect AIMModel CR labels")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMModel {name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimmodels/{name} failed: {result.stderr}")

    resource = json.loads(result.stdout)
    metadata = resource.get("metadata") or {}
    labels = metadata.get("labels") or {}
    annotations = metadata.get("annotations") or {}

    if labels.get(_MODEL_SOURCE_TYPE_LABEL) == _CUSTOM_MODEL_SOURCE_TYPE:
        raise AssertionError(f"AIMModel {name} is stamped as a custom import ({_MODEL_SOURCE_TYPE_LABEL}=custom)")
    if _ONBOARD_REVISION_ANNOTATION in annotations and _ONBOARD_SOURCE_SHA_ANNOTATION in annotations:
        raise AssertionError(
            f"AIMModel {name} carries custom onboard stamps "
            f"({_ONBOARD_REVISION_ANNOTATION}, {_ONBOARD_SOURCE_SHA_ANNOTATION})"
        )
    if labels.get(_FINE_TUNING_WORKLOAD_TYPE_LABEL) != _FINE_TUNING_WORKLOAD_TYPE:
        raise AssertionError(
            f"AIMModel {name} should represent a fine-tuning output "
            f"({_FINE_TUNING_WORKLOAD_TYPE_LABEL}={_FINE_TUNING_WORKLOAD_TYPE}), "
            f"got {labels.get(_FINE_TUNING_WORKLOAD_TYPE_LABEL)!r}"
        )


@keyword("Apply AIMModel CR With Source")
def apply_aim_model_cr_with_source(name: str, namespace: str) -> str:
    """Apply a v1alpha2 AIMModel CR with an S3 weights URI on ``spec.profiles.overrides``.

    Used by tests that need a source-backed fine-tuned model shape. Most kubectl
    fixtures only need ``Apply Dummy AIMModel CR`` (image-only v1alpha2).
    """
    yaml_body = (
        f"apiVersion: {_AIM_MODEL_API_VERSION}\n"
        "kind: AIMModel\n"
        "metadata:\n"
        f"  name: {name}\n"
        "  labels:\n"
        '    airm.silogen.ai/workload-type: "FINE_TUNING"\n'
        "spec:\n"
        "  profiles:\n"
        "    derivedFrom:\n"
        "      selector:\n"
        '        role: "base"\n'
        "        modelRef:\n"
        '          name: "aim-base"\n'
        '          scope: "Namespace"\n'
        '    versionPolicy: "all"\n'
        "    overrides:\n"
        f"      aimId: test-aim-{name}\n"
        f"      modelId: test-org/{name}\n"
        "      modelSources:\n"
        f"        - modelId: test-org/{name}\n"
        f"          sourceUri: s3://test-bucket/{namespace}/models/{name}/\n"
    )
    _apply_yaml(yaml_body, namespace, f"AIMModel CR {name}")
    return name


# The three outcomes a single polled fine-tuning status can settle into.
_STATUS_REACHED = "reached"
_STATUS_FAILED = "failed"
_STATUS_WAITING = "waiting"


@keyword("Classify Finetuned Model Status")
def classify_finetuned_model_status(status: str, target_status: str) -> str:
    """Classify one polled AIMModel status against the status a caller is waiting for.

    Returns "reached" when status already matches, "failed" when the model entered a terminal
    Failed state while waiting for something else, or "waiting" otherwise so the caller's own Wait
    Until Keyword Succeeds retries. Shared by both poll paths in "Finetuned model status should be"
    (a targeted Get model once the CR name is known, and a list scan before it is) so a caching fix
    to one path cannot silently change the other's pass/fail semantics.
    """
    if status == target_status:
        return _STATUS_REACHED
    if status == "Failed" and target_status != "Failed":
        return _STATUS_FAILED
    return _STATUS_WAITING


@keyword("Apply Multiple Dummy AIMModel CRs")
def apply_multiple_dummy_aim_model_crs(
    namespace: str,
    count: int,
    name_prefix: str = "page-test-model",
) -> list[str]:
    """Apply ``count`` minimal AIMModel CRs in ``namespace``.

    Used by pagination tests that need more rows than fit on a single page
    without invoking real fine-tuning. Returns the list of names so callers
    can clean up explicitly if they're not relying on namespace cascade.
    """
    names: list[str] = []
    for i in range(int(count)):
        name = f"{name_prefix}-{i:03d}"
        apply_dummy_aim_model_cr(name, namespace)
        names.append(name)
    return names


@keyword("AIMModel CR Should Be Absent")
def aim_model_cr_should_be_absent(name: str, namespace: str) -> None:
    """Assert the AIMModel CR is no longer present in the namespace."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "aimmodels", name, "-n", namespace],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot verify AIMModel CR absence")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMModel {name}")
    if result.returncode == 0:
        raise AssertionError(f"AIMModel CR {name} still exists in namespace {namespace}")
    stderr_lower = result.stderr.lower()
    if "not found" not in stderr_lower and "notfound" not in stderr_lower:
        raise RuntimeError(f"kubectl get failed unexpectedly (not a 'not found' error): {result.stderr}")


@keyword("No Custom AIMModel CRs Should Remain")
def no_custom_aim_model_crs_should_remain(namespace: str) -> None:
    """Assert the namespace holds no custom AIMModel CRs, reading Kubernetes directly.

    The workbench list endpoint answers 200 with an empty ``data`` list when its
    Kubernetes read fails, so an empty API response cannot distinguish a clean
    project from an unreadable one. Callers that must know the project is
    genuinely empty before reusing it need this independent read, which raises
    rather than reporting emptiness when kubectl itself fails.

    Scoped to the custom source-type label the way the workbench's own list is:
    onboarding provisions a base-image AIMModel that legitimately stays in the
    namespace, and an unfiltered read would report that as leftover state.
    """
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimmodels",
                "-n",
                namespace,
                "-l",
                f"{_MODEL_SOURCE_TYPE_LABEL}={_CUSTOM_MODEL_SOURCE_TYPE}",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot verify the project holds no AIMModel CRs")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s listing AIMModels in {namespace}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimmodels failed unexpectedly: {result.stderr}")

    remaining = [
        item.get("metadata", {}).get("name", "<unnamed>") for item in json.loads(result.stdout).get("items", [])
    ]
    if remaining:
        raise AssertionError(
            f"Custom AIMModel CRs still present in namespace {namespace}: {', '.join(sorted(remaining))}"
        )


@keyword("No AIMService CRs Should Remain For Model")
def no_aim_service_crs_should_remain_for_model(model_name: str, namespace: str) -> None:
    """Assert no AIMService CR still references ``model_name``, reading Kubernetes directly.

    The services list endpoint answers 200 with an empty list when its Kubernetes
    read fails, so an empty API response cannot prove the previous round's
    service is gone - and a service that is merely unreported would be reused by
    the next deploy instead of a fresh one.
    """
    try:
        result = subprocess.run(
            ["kubectl", "get", "aimservices", "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot verify AIMService absence")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s listing AIMServices in {namespace}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimservices failed unexpectedly: {result.stderr}")

    referencing = [
        item.get("metadata", {}).get("name", "<unnamed>")
        for item in json.loads(result.stdout).get("items", [])
        if (item.get("spec", {}).get("model") or {}).get("name") == model_name
    ]
    if referencing:
        raise AssertionError(
            f"AIMService CRs still reference model {model_name} in namespace {namespace}: {', '.join(sorted(referencing))}"
        )


@keyword("No Base Role AIMProfile Should Declare A Precision")
def no_base_role_aim_profile_should_declare_a_precision(namespace: str) -> None:
    """Assert no base-role AIMProfile carries a precision, reading Kubernetes directly.

    The runtime-profile-options endpoint is fail-open: a Kubernetes or parse
    failure degrades to an empty profile list and a 200, which is
    indistinguishable from a template that genuinely offers nothing. Callers
    about to skip on an empty answer use this to tell the two apart, so a read
    outage fails loudly instead of silently retiring coverage.

    The endpoint counts only profiles whose ``spec.precision`` is set, and that
    field is optional - a CPU-only base template can emit profiles and still
    offer no precision target. So the question is whether any base profile
    declares one, not whether any base profile exists.
    """
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimprofiles",
                "-n",
                namespace,
                "-l",
                "aim.eai.amd.com/profile-role=base",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot verify base-role AIMProfile absence")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s listing base AIMProfiles in {namespace}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofiles failed unexpectedly: {result.stderr}")

    with_precision = [
        item.get("metadata", {}).get("name", "<unnamed>")
        for item in json.loads(result.stdout).get("items", [])
        if (item.get("spec", {}) or {}).get("precision")
    ]
    if with_precision:
        raise AssertionError(
            f"The runtime-profile-options endpoint reported no precisions, but namespace {namespace} "
            f"holds base-role AIMProfiles that declare one ({', '.join(sorted(with_precision))}) — the "
            "endpoint's profile read most likely failed rather than the template offering none"
        )


@keyword("Largest Accelerator Count For Precisions")
def largest_accelerator_count_for_precisions(precisions: list[str], namespace: str) -> int:
    """Return the largest accelerator count any of ``precisions`` needs, from Kubernetes.

    Precisions are not interchangeable across accelerator counts: a base template
    can emit fp16 at one accelerator and fp8 only at eight, so a run that must
    cover every offered precision needs quota for the largest of them.

    Sized from the base-role AIMProfiles rather than the options endpoint. That
    endpoint is fail-open, so a transient read failure would answer 200 with an
    empty matrix, and its ``combinations`` deliberately omit tuples that do not
    resolve to exactly one base profile - either would silently under-size the
    quota and fail a round for admission instead of covering its precision.
    Raises when a precision has no profile to size from, rather than guessing.
    """
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimprofiles",
                "-n",
                namespace,
                "-l",
                "aim.eai.amd.com/profile-role=base",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot size the project quota")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s sizing quota in {namespace}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofiles failed while sizing the project quota: {result.stderr}")

    counts_by_precision: dict[str, int] = {}
    for item in json.loads(result.stdout).get("items", []):
        spec = item.get("spec", {}) or {}
        precision = str(spec.get("precision") or "")
        if not precision:
            continue
        count = int(spec.get("acceleratorCount") or 0)
        counts_by_precision[precision] = max(counts_by_precision.get(precision, 0), count)

    unsized = sorted({str(p) for p in precisions} - counts_by_precision.keys())
    if unsized:
        raise AssertionError(
            f"No base-role AIMProfile in namespace {namespace} declares precision(s) "
            f"{', '.join(unsized)}, so the quota those rounds need cannot be sized"
        )

    needed = [counts_by_precision[str(p)] for p in precisions]
    return max([count for count in needed if count > 0], default=1)


@keyword("AIMProfile Precision")
def aim_profile_precision(profile_name: str, namespace: str) -> str:
    """Return ``spec.precision`` of the named AIMProfile.

    Reading the precision off the profile itself keeps assertions independent of
    how aim-engine happens to name derived profiles - that name is engine-owned
    and may change without the pinned precision changing.
    """
    try:
        result = subprocess.run(
            ["kubectl", "get", "aimprofile", profile_name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot read AIMProfile precision")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMProfile {profile_name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofile {profile_name} failed: {result.stderr}")

    precision = json.loads(result.stdout).get("spec", {}).get("precision")
    if not precision:
        raise AssertionError(f"AIMProfile {profile_name} in namespace {namespace} declares no spec.precision")
    return str(precision)


@keyword("Apply AIMService Referencing Model")
def apply_aim_service_referencing_model(name: str, model_name: str, namespace: str) -> str:
    """Apply a minimal v1alpha2 AIMService CR that references ``model_name``.

    Used by the delete active-deployment guard test. The service only needs to
    exist and carry ``spec.model.name`` — the workbench guard lists AIMServices
    and matches that field, so the service does not need to reach Ready (no GPU
    or real profile is required).
    """
    yaml_body = (
        "apiVersion: aim.eai.amd.com/v1alpha2\n"
        "kind: AIMService\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  namespace: {namespace}\n"
        "spec:\n"
        "  model:\n"
        f"    name: {model_name}\n"
    )
    _apply_yaml(yaml_body, namespace, f"AIMService CR {name}")
    return name


@keyword("Apply AIMService Pinning Profile")
def apply_aim_service_pinning_profile(name: str, model_name: str, profile_name: str, namespace: str) -> str:
    """Apply a minimal v1alpha2 AIMService CR that references ``model_name`` and pins ``profile_name``.

    Used by the Default-narrowing guard test: the workbench refuses a narrowing
    edit while a deployment pins a profile owned by the set being narrowed, and
    that reverse lookup keys on ``spec.profile.name``. The service only needs to
    exist and carry both fields, so it does not need to reach Ready (no GPU).
    """
    yaml_body = (
        "apiVersion: aim.eai.amd.com/v1alpha2\n"
        "kind: AIMService\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  namespace: {namespace}\n"
        "spec:\n"
        "  model:\n"
        f"    name: {model_name}\n"
        "  profile:\n"
        f"    name: {profile_name}\n"
    )
    _apply_yaml(yaml_body, namespace, f"AIMService CR {name}")
    return name


@keyword("Delete AIMService CR")
def delete_aim_service_cr(name: str, namespace: str) -> None:
    """Delete the named AIMService CR, tolerating one that is already gone.

    Used by the delete active-deployment guard test's teardown so the blocking
    service is removed and the referenced AIMModel can be cleaned up afterwards —
    without it the model stays pinned by the 409 guard and pollutes later tests.
    """
    try:
        result = subprocess.run(
            ["kubectl", "delete", "aimservice", name, "-n", namespace, "--ignore-not-found"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot delete AIMService CR")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl delete timed out after {_KUBECTL_TIMEOUT}s for AIMService {name}")
    if result.returncode != 0:
        raise RuntimeError(f"Failed to delete AIMService CR {name}: {result.stderr}")


@keyword("AIMProfile For Model Should Be Absent")
def aim_profile_for_model_should_be_absent(model_name: str, namespace: str) -> None:
    """Assert no AIMProfile derived from ``model_name`` remains in the namespace.

    aim-engine stamps the ``aim.eai.amd.com/model.name`` label on every
    AIMProfile it derives from an AIMModel; once the AIMModel is deleted the
    AIMProfile (and its AIMProfileSet) are garbage-collected via owner references.
    A label-filtered ``get`` returns exit 0 with empty output when nothing matches.
    """
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimprofiles",
                "-n",
                namespace,
                "-l",
                f"aim.eai.amd.com/model.name={model_name}",
                "-o",
                "name",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot verify AIMProfile absence")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMProfiles of {model_name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofiles failed unexpectedly: {result.stderr}")
    remaining = result.stdout.strip()
    if remaining:
        raise AssertionError(
            f"AIMProfile(s) derived from AIMModel {model_name} still present in namespace {namespace}: {remaining}"
        )


@keyword("AIMProfile For Model Should Exist")
def aim_profile_for_model_should_exist(model_name: str, namespace: str) -> None:
    """Assert at least one AIMProfile derived from ``model_name`` exists.

    Used to confirm aim-engine has derived the profile before the delete step,
    so the cascade-cleanup assertion is meaningful.
    """
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimprofiles",
                "-n",
                namespace,
                "-l",
                f"aim.eai.amd.com/model.name={model_name}",
                "-o",
                "name",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot verify AIMProfile presence")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMProfiles of {model_name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofiles failed unexpectedly: {result.stderr}")
    if not result.stdout.strip():
        raise AssertionError(f"No AIMProfile derived from AIMModel {model_name} found in namespace {namespace}")


@keyword("Get AIMProfile Name For Model")
def get_aim_profile_name_for_model(model_name: str, namespace: str) -> str:
    """Return ``metadata.name`` of the AIMProfile derived from ``model_name``.

    Matches the backend lookup keyed by ``aim.eai.amd.com/model.name``.
    """
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimprofiles",
                "-n",
                namespace,
                "-l",
                f"aim.eai.amd.com/model.name={model_name}",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot resolve AIMProfile name")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMProfiles of {model_name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofiles failed unexpectedly: {result.stderr}")

    items = json.loads(result.stdout).get("items", [])
    if not items:
        raise AssertionError(f"No AIMProfile derived from AIMModel {model_name} found in namespace {namespace}")
    return items[0]["metadata"]["name"]


@keyword("Get Different AIMProfile Name For Model")
def get_different_aim_profile_name_for_model(
    model_name: str,
    excluded_name: str,
    profile_set_name: str,
    namespace: str,
) -> str:
    """Return another profile owned by the Default set, skipping when the set already derives one."""
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimprofiles",
                "-n",
                namespace,
                "-l",
                f"aim.eai.amd.com/model.name={model_name}",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot resolve AIMProfile name")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMProfiles of {model_name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofiles failed unexpectedly: {result.stderr}")

    names = []
    for item in json.loads(result.stdout).get("items", []):
        metadata = item.get("metadata", {})
        owned_by_default = any(
            owner.get("kind") == "AIMProfileSet" and owner.get("name") == profile_set_name
            for owner in metadata.get("ownerReferences", [])
        )
        if owned_by_default and metadata.get("name") != excluded_name:
            names.append(metadata["name"])
    if not names:
        BuiltIn().skip(f"Default for AIMModel {model_name} already derives only one profile")
    return sorted(names)[0]


@keyword("Get AIMProfile Name For Profile Set")
def get_aim_profile_name_for_profile_set(model_name: str, profile_set_name: str, namespace: str) -> str:
    """Return an AIMProfile ``metadata.name`` owned by ``profile_set_name``.

    A named AIMProfileSet emits its own derived AIMProfiles owner-referenced back
    to it; the in-use guard keys the reverse lookup on ``spec.profile.name``, so a
    test that pins one of those profiles needs its concrete name. Raises (rather
    than skips) when none is present yet so a ``Wait Until Keyword Succeeds`` can
    poll for aim-engine to derive it.
    """
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimprofiles",
                "-n",
                namespace,
                "-l",
                f"aim.eai.amd.com/model.name={model_name}",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot resolve AIMProfile name")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMProfiles of {model_name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofiles failed unexpectedly: {result.stderr}")

    for item in json.loads(result.stdout).get("items", []):
        metadata = item.get("metadata", {})
        owned = any(
            owner.get("kind") == "AIMProfileSet" and owner.get("name") == profile_set_name
            for owner in metadata.get("ownerReferences", [])
        )
        if owned:
            return metadata["name"]
    raise AssertionError(f"No AIMProfile owned by AIMProfileSet {profile_set_name} found in namespace {namespace} yet")


@keyword("Get AIMProfile Spec For Model")
def get_aim_profile_spec_for_model(model_name: str, namespace: str) -> dict:
    """Return the ``spec`` of the AIMProfile derived from ``model_name``.

    Lets pod-level assertions cross-check the running container against the
    profile aim-engine actually emitted (acceleratorModel, acceleratorCount,
    precision, engineArgs, engineEnv) rather than against hardcoded values that
    a given cluster may not schedule.
    """
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "aimprofiles",
                "-n",
                namespace,
                "-l",
                f"aim.eai.amd.com/model.name={model_name}",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot read AIMProfile spec")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMProfiles of {model_name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimprofiles failed unexpectedly: {result.stderr}")

    items = json.loads(result.stdout).get("items", [])
    if not items:
        raise AssertionError(f"No AIMProfile derived from AIMModel {model_name} found in namespace {namespace}")
    return items[0].get("spec", {})


def _seed_s3_model_source(namespace: str, label: str, files: dict[str, bytes]) -> str:
    """Upload ``files`` under a unique preview-test prefix and return its s3:// URI.

    A relative path of "" uploads a zero-byte prefix marker, which is how an
    otherwise empty folder is represented in object storage.
    """
    client = _minio_client(namespace)
    prefix = f"{namespace}/aiwb-custom-model-preview-e2e/{uuid.uuid4().hex}/{label}"

    for relative_path, payload in files.items():
        client.put_object(
            _MINIO_BUCKET,
            f"{prefix}/{relative_path}",
            io.BytesIO(payload),
            length=len(payload),
        )

    _track_prepared_s3_prefix(namespace, prefix)
    return f"s3://{_MINIO_BUCKET}/{prefix}"


# Minimal stand-ins for a real model tree. Preview only lists these and reads the
# card and config, so the weight blob's contents are irrelevant — but its
# extension is not, since that is what makes the folder look like a model.
_E2E_WEIGHT_FILE = b"not-real-weights"
_E2E_TOKENIZER_FILE = b'{"version":"1.0"}'


@keyword("Prepare Empty S3 Source For Custom Model Preview")
def prepare_empty_s3_source_for_custom_model_preview(namespace: str) -> str:
    """Create an empty S3 prefix for custom model preview tests."""
    return _seed_s3_model_source(namespace, "empty", {"": b""})


@keyword("Prepare Config-Only S3 Source For Custom Model Preview")
def prepare_config_only_s3_source_for_custom_model_preview(namespace: str) -> str:
    """Create an S3 prefix containing only config.json for custom model preview tests."""
    return _seed_s3_model_source(namespace, "config-only", {"config.json": b'{"model_type":"test"}'})


@keyword("Prepare Untagged S3 Source For Custom Model Preview")
def prepare_untagged_s3_source_for_custom_model_preview(namespace: str) -> str:
    """Create an S3 model folder that carries no tag signal whatsoever.

    No card, and a config stripped of the architecture fields tags are otherwise
    inferred from, so every discovery layer comes up empty.
    """
    return _seed_s3_model_source(
        namespace,
        "untagged",
        {
            "model.safetensors": _E2E_WEIGHT_FILE,
            "tokenizer.json": _E2E_TOKENIZER_FILE,
            "config.json": b'{"hidden_size": 8}',
        },
    )


@keyword("Prepare Card-Tagged S3 Source For Custom Model Preview")
def prepare_card_tagged_s3_source_for_custom_model_preview(namespace: str) -> str:
    """Create an S3 model folder whose card declares its own tags and no base model."""
    card = b"---\ntags:\n  - summarization\n  - experimental\n---\n\n# Test model\n"
    return _seed_s3_model_source(
        namespace,
        "card-tagged",
        {
            "model.safetensors": _E2E_WEIGHT_FILE,
            "tokenizer.json": _E2E_TOKENIZER_FILE,
            "config.json": b'{"hidden_size": 8}',
            "README.md": card,
        },
    )


@keyword("Prepare Base-Model-Derived S3 Source For Custom Model Preview")
def prepare_base_model_derived_s3_source_for_custom_model_preview(namespace: str, base_model: str) -> str:
    """Create an S3 model folder whose card declares ``base_model`` as its origin."""
    card = f"---\nbase_model: {base_model}\n---\n\n# Fine-tuned from {base_model}\n".encode()
    return _seed_s3_model_source(
        namespace,
        "derived",
        {
            "model.safetensors": _E2E_WEIGHT_FILE,
            "tokenizer.json": _E2E_TOKENIZER_FILE,
            "config.json": b'{"hidden_size": 8}',
            "README.md": card,
        },
    )


@keyword("Prepare Valid S3 Source For Custom Model Preview")
def prepare_valid_s3_source_for_custom_model_preview(namespace: str) -> str:
    """Create an S3 prefix with a minimal valid model layout for preview/onboard tests.

    Uploads config, tokenizer, and a safetensors weight file so validation
    passes without warnings, then returns the s3:// URI.
    """
    client = _minio_client(namespace)
    prefix = f"{namespace}/aiwb-custom-model-preview-e2e/{uuid.uuid4().hex}/valid-layout"

    config_payload = b'{"model_type":"test"}'
    tokenizer_payload = b'{"model_max_length":2048}'
    weight_payload = b"stub-weights"

    client.put_object(
        _MINIO_BUCKET,
        f"{prefix}/config.json",
        io.BytesIO(config_payload),
        length=len(config_payload),
        content_type="application/json",
    )
    client.put_object(
        _MINIO_BUCKET,
        f"{prefix}/tokenizer.json",
        io.BytesIO(tokenizer_payload),
        length=len(tokenizer_payload),
        content_type="application/json",
    )
    client.put_object(
        _MINIO_BUCKET,
        f"{prefix}/model.safetensors",
        io.BytesIO(weight_payload),
        length=len(weight_payload),
        content_type="application/octet-stream",
    )
    _track_prepared_s3_prefix(namespace, prefix)
    return f"s3://{_MINIO_BUCKET}/{prefix}"


@keyword("Minio Credentials Secret Exists In Project Namespace")
def minio_credentials_secret_exists_in_project_namespace(namespace: str) -> None:
    """Return once the platform-synced minio-credentials secret is present in the namespace."""
    _get_minio_credentials(namespace)


@keyword("Register AIWB S3 Storage ConfigMap Referencing Secret")
def register_aiwb_s3_storage_configmap(namespace: str, storage_name: str, secret_name: str) -> None:
    """Create an AIWB-labelled S3 storage ConfigMap that references an existing project secret.

    Used for negative preview scenarios where storage registration must reference a secret
    the storages API would reject at create time (for example a HuggingFace-labelled secret).
    """
    manifest = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": storage_name,
            "namespace": namespace,
            "labels": {
                _STORAGE_CONFIGMAP_LABEL: "true",
                _STORAGE_TYPE_LABEL: "S3",
            },
        },
        "data": {
            "TYPE": "S3",
            "SECRET_NAME": secret_name,
            "ACCESS_KEY_NAME": "token",
            "SECRET_KEY_NAME": "token",
            "BUCKET_URL": _S3_BUCKET_URL,
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, prefix="aiwb-storage-") as tmp:
        json.dump(manifest, tmp)
        tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(tmp_path), "-n", namespace],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to apply AIWB S3 storage ConfigMap '{storage_name}' in {namespace}: {result.stderr or result.stdout}"
            )
    finally:
        tmp_path.unlink(missing_ok=True)


@keyword("Clean Up Prepared S3 Sources For Custom Model Preview")
def clean_up_prepared_s3_sources_for_custom_model_preview() -> None:
    """Delete all S3 test prefixes created by preview fixture helpers."""
    if not _PREPARED_S3_PREFIXES:
        return

    failures: list[str] = []
    for namespace, prefix in list(_PREPARED_S3_PREFIXES):
        try:
            # Teardown must not raise a skip, so this deliberately uses the unguarded client:
            # nothing is tracked for cleanup unless a prepare step already reached the store.
            client = _new_minio_client(namespace)
            objects = list(client.list_objects(_MINIO_BUCKET, prefix=prefix, recursive=True))
            for obj in objects:
                client.remove_object(_MINIO_BUCKET, obj.object_name)
            _PREPARED_S3_PREFIXES.remove((namespace, prefix))
        except Exception as exc:
            failures.append(f"{namespace}:{prefix} -> {exc}")

    if failures:
        details = "; ".join(failures)
        raise RuntimeError(f"Failed to clean one or more prepared S3 preview prefixes: {details}")


def _as_combination_tuple(combination: dict) -> tuple:
    """Read the four narrowing axes off a combination object."""
    return (
        combination.get("acceleratorModel"),
        combination.get("acceleratorCount"),
        combination.get("precision"),
        combination.get("metric"),
    )


@keyword("Runtime Profile Options Combinations Should Be Consistent")
def runtime_profile_options_combinations_should_be_consistent(options: dict) -> None:
    """Assert the namespace runtime-options combinations are drawn from the per-axis lists.

    Each emitted combination must reuse values already present in the distinct
    per-axis lists — the point of the field is that these values coexist, not
    that new ones appear — and no combination may be advertised twice.
    """
    combinations = options.get("combinations")
    if not isinstance(combinations, list):
        raise AssertionError(f"Runtime profile options 'combinations' must be a list, got {type(combinations)}")

    models = options.get("acceleratorModels") or []
    counts = options.get("acceleratorCounts") or []
    precisions = options.get("precisions") or []
    metrics = options.get("metrics") or []

    seen: set[tuple] = set()
    for combination in combinations:
        model, count, precision, metric = _as_combination_tuple(combination)
        if model not in models:
            raise AssertionError(f"Combination acceleratorModel {model!r} is not in acceleratorModels {models}")
        if count not in counts:
            raise AssertionError(f"Combination acceleratorCount {count!r} is not in acceleratorCounts {counts}")
        if precision not in precisions:
            raise AssertionError(f"Combination precision {precision!r} is not in precisions {precisions}")
        if metric not in metrics:
            raise AssertionError(f"Combination metric {metric!r} is not in metrics {metrics}")
        key = (model, count, precision, metric)
        if key in seen:
            raise AssertionError(f"Combination {key} is advertised more than once")
        seen.add(key)


@keyword("Base Image Runtime Profile Options Combinations Should Be Consistent")
def base_image_runtime_profile_options_combinations_should_be_consistent(options: dict) -> None:
    """Assert the base-image combinations agree with the per-model discovered matrix.

    Every emitted tuple's count, precision and metric must belong to the same
    acceleratorModel's discovered sets, so the offered combinations never cross
    values that the base does not actually pair for that model.
    """
    combinations = options.get("combinations")
    if not isinstance(combinations, list):
        raise AssertionError(f"Base-image runtime options 'combinations' must be a list, got {type(combinations)}")

    models = options.get("acceleratorModels") or []
    counts_by_model = options.get("acceleratorCountsByModel") or {}
    precisions_by_model = options.get("precisionsByModel") or {}
    metrics_by_model = options.get("metricsByModel") or {}

    for combination in combinations:
        model, count, precision, metric = _as_combination_tuple(combination)
        if model not in models:
            raise AssertionError(f"Combination acceleratorModel {model!r} is not in acceleratorModels {models}")
        if count not in (counts_by_model.get(model) or []):
            raise AssertionError(f"Combination acceleratorCount {count!r} is not offered for model {model!r}")
        if precision not in (precisions_by_model.get(model) or []):
            raise AssertionError(f"Combination precision {precision!r} is not offered for model {model!r}")
        if metric not in (metrics_by_model.get(model) or []):
            raise AssertionError(f"Combination metric {metric!r} is not offered for model {model!r}")


def _assert_default_profile_row(row: dict) -> None:
    """Assert one profile row is the Default: flagged, reserved name, real resourceName, effective profile.

    Centralises the "this is the Default row" contract so list and detail assertions agree and a
    consumer never mistakes an arbitrary row for the Default.
    """
    if not row.get("isDefault"):
        raise AssertionError(f"Profile row is not the Default (isDefault is not true): {row.get('name')!r}")
    if row.get("name") != "default":
        raise AssertionError(f"Default row name should be the reserved 'default' alias, got {row.get('name')!r}")
    if not row.get("resourceName"):
        raise AssertionError("Default row must carry its real resourceName")
    if not row.get("profile"):
        raise AssertionError("Default row must carry its effective profile once ready")


@keyword("Detail Response Should Present Default Profile First")
def detail_response_should_present_default_profile_first(response_json: dict) -> None:
    """Assert a custom-model detail response embeds the profile collection with the Default first.

    The detail endpoint carries the same rows as the dedicated profiles endpoint, so a client
    polling detail sees the Default (flagged, reserved 'default' name, real resourceName, effective
    profile) without a separate profiles request.
    """
    profiles = response_json.get("profiles") or []
    if not profiles:
        raise AssertionError("Detail response carries no profiles for the custom model")
    _assert_default_profile_row(profiles[0])


@keyword("Listed Model Should Present Default Profile First")
def listed_model_should_present_default_profile_first(response_json: dict, expected_repo_id: str) -> None:
    """Assert the listed model for ``expected_repo_id`` embeds its profile collection, Default first.

    Locates the model by its canonical-repo-id annotation, so the grid can render a count and the
    Default summary from the list response without a per-model profiles request.
    """
    for model in response_json.get("data", []):
        annotations = (model.get("metadata") or {}).get("annotations") or {}
        if annotations.get(_CANONICAL_REPO_ID_ANNOTATION) == expected_repo_id:
            profiles = model.get("profiles") or []
            if not profiles:
                raise AssertionError(f"Listed model '{expected_repo_id}' carries no profiles")
            _assert_default_profile_row(profiles[0])
            return
    raise AssertionError(f"No custom model with canonical-repo-id '{expected_repo_id}' found in list response")


@keyword("Detail Response Should Include Named Profile Alongside Default")
def detail_response_should_include_named_profile_alongside_default(response_json: dict, display_name: str) -> None:
    """Assert a detail response lists exactly the Default (first) and the named profile (second).

    After a named profile is created the collection carries both rows, so the grid reflects the new
    profile without a dedicated profiles request.
    """
    profiles = response_json.get("profiles") or []
    if len(profiles) != 2:
        raise AssertionError(
            f"Expected the Default and one named profile in the detail collection, got {len(profiles)}"
        )
    _assert_default_profile_row(profiles[0])
    named = profiles[1]
    if named.get("isDefault"):
        raise AssertionError("The second row must be the named (non-default) profile")
    if named.get("displayName") != display_name:
        raise AssertionError(
            f"Named profile row does not carry the expected display name {display_name!r}, "
            f"got {named.get('displayName')!r}"
        )


# A LoRA adapter small enough to plant in a few kilobytes and still a real one: the config carries
# the field set PEFT needs, and the weights are the factor pairs it names. Scenarios that carry an
# export out and back are then about an adapter rather than about arbitrary bytes. Shared by the
# fixture that writes the files directly and the one that uploads them.
# AIWB is the sole author of the adapter manifest: a client-listed copy is dropped from the upload
# set and a fresh one is written at the new prefix, so a round trip re-authors it rather than
# carrying it. Named here so the round-trip assertions can allow for exactly that and nothing else.
_ADAPTER_MANIFEST_FILENAME = "adapter-manifest.yaml"

_ADAPTER_BASE_MODEL = "example-org/e2e-base-model"
_ADAPTER_RANK = 4
_ADAPTER_TARGET_MODULES = ("q_proj", "v_proj")
_ADAPTER_HIDDEN_SIZE = 8
_PEFT_TYPE_LORA = "LORA"

# safetensors names its 32-bit float dtype F32 and stores it little-endian, four bytes per element.
_LORA_DTYPE = "F32"
_LORA_DTYPE_BYTES = 4

# PEFT initialises lora_A from a small random distribution and lora_B to zeros, so a freshly created
# adapter is a no-op until trained. A constant stands in for the randomness, which keeps the fixture
# byte-for-byte reproducible without making it any less loadable.
_LORA_A_INIT = 0.02


def _safetensors_bytes(tensors: dict[str, tuple[tuple[int, int], bytes]]) -> bytes:
    """Lay named float32 tensors out in the safetensors container format.

    Assembled by hand so planting a fixture needs no tensor framework. Nothing in the suite parses
    these bytes; the container is built for real so the scenarios carry a genuine adapter around
    rather than arbitrary bytes under adapter filenames.
    """
    header: dict[str, Any] = {}
    body = bytearray()
    for name, (shape, raw) in tensors.items():
        header[name] = {
            "dtype": _LORA_DTYPE,
            "shape": list(shape),
            "data_offsets": [len(body), len(body) + len(raw)],
        }
        body += raw
    encoded = json.dumps(header, separators=(",", ":")).encode()
    # The format requires the tensor body to start 8-byte aligned, and pads the header to get there.
    encoded += b" " * (-len(encoded) % 8)
    return struct.pack("<Q", len(encoded)) + encoded + bytes(body)


def _lora_adapter_weights() -> bytes:
    """Build one rank-r LoRA factor pair per targeted module, under the tensor names PEFT gives them.

    The names carry the base model's own module path, which is how a loader matches a factor pair to
    the layer it belongs to; the shapes mirror each other across the rank, because the pair is only
    meaningful as a product.
    """
    tensors: dict[str, tuple[tuple[int, int], bytes]] = {}
    for module in _ADAPTER_TARGET_MODULES:
        stem = f"base_model.model.model.layers.0.self_attn.{module}"
        element_count = _ADAPTER_RANK * _ADAPTER_HIDDEN_SIZE
        tensors[f"{stem}.lora_A.weight"] = (
            (_ADAPTER_RANK, _ADAPTER_HIDDEN_SIZE),
            struct.pack(f"<{element_count}f", *([_LORA_A_INIT] * element_count)),
        )
        tensors[f"{stem}.lora_B.weight"] = (
            (_ADAPTER_HIDDEN_SIZE, _ADAPTER_RANK),
            bytes(element_count * _LORA_DTYPE_BYTES),
        )
    return _safetensors_bytes(tensors)


_ADAPTER_WEIGHT_PAYLOADS = {
    "adapter_config.json": json.dumps(
        {
            "peft_type": _PEFT_TYPE_LORA,
            "task_type": "CAUSAL_LM",
            "base_model_name_or_path": _ADAPTER_BASE_MODEL,
            "r": _ADAPTER_RANK,
            "lora_alpha": _ADAPTER_RANK * 2,
            "lora_dropout": 0.0,
            "target_modules": list(_ADAPTER_TARGET_MODULES),
            "bias": "none",
            "fan_in_fan_out": False,
            "inference_mode": True,
        },
        indent=2,
    ).encode(),
    "adapter_model.safetensors": _lora_adapter_weights(),
}


@keyword("Write Adapter Weights To Project Storage")
def write_adapter_weights_to_project_storage(namespace: str, name: str) -> str:
    """Put adapter weight files into the project's adapter storage without creating any CR.

    This is what a deleted registration or an out-of-band training job leaves behind: files
    under the prefix the platform allocates for adapters that no record claims. Returns the storage
    URI of the prefix.
    """
    client = _minio_client(namespace)
    prefix = _adapter_prefix(namespace, name)
    for filename, payload in _ADAPTER_WEIGHT_PAYLOADS.items():
        client.put_object(_MINIO_BUCKET, f"{prefix}{filename}", io.BytesIO(payload), length=len(payload))
    return f"s3://{_MINIO_BUCKET}/{prefix}"


_FINE_TUNED_ADAPTER_DIR = "checkpoint-final-adapter"
# A run-level file standing in for what a run writes beside its checkpoints -- nothing registers
# it, so only reclaiming the whole run folder removes it.
_FINE_TUNING_RUN_LEVEL_FILES = {"run-metadata.json": b'{"produced_by": "aiwb-e2e"}\n'}


@keyword("Write Fine-Tuning Run Output To Project Storage")
def write_fine_tuning_run_output_to_project_storage(namespace: str, base_model: str) -> str:
    """Put a LoRA fine-tuning run's output into project storage the way a completed run leaves it.

    A run gets its own folder under the project's fine-tuned-models tree, named by a run id the
    workbench mints as a UUID. The adapter weights sit in their own directory inside it, beside
    run-level files. Returns the storage URI of the run folder; the adapter weights are under
    ``checkpoint-final-adapter`` inside it.
    """
    client = _minio_client(namespace)
    run_prefix = f"{namespace}/finetuned-models/{base_model}/{uuid.uuid4()}/"
    objects = {f"{_FINE_TUNED_ADAPTER_DIR}/{name}": payload for name, payload in _ADAPTER_WEIGHT_PAYLOADS.items()}
    objects.update(_FINE_TUNING_RUN_LEVEL_FILES)
    for path, payload in objects.items():
        client.put_object(_MINIO_BUCKET, f"{run_prefix}{path}", io.BytesIO(payload), length=len(payload))
    return f"s3://{_MINIO_BUCKET}/{run_prefix}"


@keyword("Fine-Tuned Adapter Location In Run")
def fine_tuned_adapter_location_in_run(run_uri: str) -> str:
    """The location a fine-tuning run records on the adapter it produces: its weights directory.

    Recorded without a trailing separator, as the fine-tuning engine writes it.
    """
    return f"{run_uri.rstrip('/')}/{_FINE_TUNED_ADAPTER_DIR}"


@keyword("Upload Adapter Weights To Provided Locations")
def upload_adapter_weights_to_provided_locations(uploads: list) -> None:
    """Write a file to each upload location the platform handed back on registration.

    A location whose name is one of the PEFT files gets that file's real content; any other gets
    content of its own, distinct from every sibling.

    Each location is a pre-signed URL, and the signature covers the host it was issued for, so it
    has to be used exactly as given -- an install that advertises an address the test runner cannot
    reach fails here rather than silently uploading somewhere else.
    """
    if not uploads:
        raise AssertionError("Registering the adapter for upload returned no upload locations")

    for upload in uploads:
        path = upload["path"]
        # Anything the PEFT set does not cover carries its own path in its bytes, so no two files
        # of one adapter ever hold the same content -- a comparison that swapped them would
        # otherwise pass while the adapter came back rearranged.
        payload = _ADAPTER_WEIGHT_PAYLOADS.get(path.rsplit("/", 1)[-1], f"e2e adapter file at {path}\n".encode())
        try:
            response = requests.put(upload["url"], data=payload, timeout=_UPLOAD_TIMEOUT, verify=False)
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Could not reach the upload location issued for {path}: {exc}. The install is advertising an "
                "object-storage address callers cannot reach -- check 'minio.externalUrl'."
            ) from exc
        if response.status_code >= 400:
            raise AssertionError(f"Uploading {path} failed with HTTP {response.status_code}: {response.text}")


@keyword("Fetch Downloaded Adapter Files")
def fetch_downloaded_adapter_files(files: list) -> dict:
    """Fetch every file a download offered, from the location it points at.

    Each location is a pre-signed URL, and the signature covers the host it was issued for, so it
    has to be used exactly as given -- an install that advertises an address the test runner cannot
    reach fails here rather than silently reading somewhere else. Returns the bytes that came back
    per path, so a scenario can weigh them against what the download promised or carry them
    somewhere else.
    """
    if not files:
        raise AssertionError("The download offered no files to fetch")

    fetched: dict[str, bytes] = {}
    for entry in files:
        path = entry["path"]
        try:
            response = requests.get(entry["url"], timeout=_UPLOAD_TIMEOUT, verify=False)
        except requests.RequestException as exc:
            raise RuntimeError(f"Could not reach the download location issued for {path}: {exc}") from exc
        if response.status_code >= 400:
            raise AssertionError(f"Fetching {path} failed with HTTP {response.status_code}: {response.text}")
        fetched[path] = response.content
    return fetched


@keyword("Fetched Adapter Files Should Be Whole")
def fetched_adapter_files_should_be_whole(files: list, fetched: dict) -> None:
    """Assert every offered file arrived, and in full wherever the download stated a size.

    A truncated body is the failure that matters here: a link that resolves but hands back part of a
    file produces an adapter that loads to garbage rather than one that visibly fails to load.

    A file whose size the download left unstated cannot be weighed, so only its arrival is checked.
    That concession is bounded: a download stating no size at all leaves nothing weighed, and a
    check that proved nothing is reported rather than passed.
    """
    weighed = 0
    for entry in files:
        path = entry["path"]
        if path not in fetched:
            raise AssertionError(f"The download offered {path} but nothing was fetched for it")
        size = entry.get("sizeBytes")
        if size is None:
            continue
        weighed += 1
        if len(fetched[path]) != size:
            raise AssertionError(f"{path} arrived as {len(fetched[path])} bytes, but the download said it holds {size}")
    if files and not weighed:
        raise AssertionError(
            "The download stated no size for any of its files, so nothing could be weighed against "
            "what arrived and this check proved nothing"
        )


@keyword("Downloaded Files Should Match What Storage Holds")
def downloaded_files_should_match_what_storage_holds(offered: list[str], stored: list[str], uri: str) -> None:
    """Assert the offered paths are exactly what storage holds, each relative to the adapter's prefix.

    Whole paths, not filenames: a download that dropped a file nested under the prefix, or offered
    it flattened onto the root, hands the receiver something they cannot rebuild the adapter from --
    and it would look complete on its own, so the loss surfaces only once the adapter fails to load.
    """
    prefix = _prefix_from_storage_location(uri)
    expected = {key.removeprefix(prefix) for key in stored}
    offered_set = set(offered)
    if offered_set != expected:
        missing = expected - offered_set
        extra = offered_set - expected
        raise AssertionError(f"Download is missing {sorted(missing)} and offers unexpected {sorted(extra)}")


@keyword("Every Downloaded File Should Have A Link And A Size")
def every_downloaded_file_should_have_a_link_and_a_size(files: list) -> None:
    """Assert every offered file carries a download link, and its size where storage reports one.

    The link is what makes the file fetchable, so no entry may lack it. The size lets a receiver
    tell whether what arrived is all of it, and is stated as null where storage reports none --
    unknown and zero are different answers, and zero is a legitimate size for an empty object.
    """
    if not files:
        raise AssertionError("The download offered no files")
    for entry in files:
        if not entry.get("url"):
            raise AssertionError(f"{entry['path']} is offered with no download link")
        if "sizeBytes" not in entry:
            raise AssertionError(f"{entry['path']} is offered without stating a size at all")
        size = entry["sizeBytes"]
        if size is None:
            continue
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise AssertionError(f"{entry['path']} is offered with {size!r} where a size was expected")


@keyword("Upload Fetched Adapter Files To Provided Locations")
def upload_fetched_adapter_files_to_provided_locations(uploads: list, fetched: dict) -> dict:
    """Send the bytes a download handed back to the upload locations a fresh registration issued.

    Nothing is invented and nothing is quietly left behind: every location has to be covered by a
    file the download offered, and every downloaded file has to have a location to go to. Either gap
    alone would still look like a round trip -- generated content substituted for what travelled, or
    a file dropped between the two adapters -- so both directions are checked. The manifest is the
    one permitted exception: the platform authors it at the new prefix itself, so it is deliberately
    absent from the locations handed out. Returns what was sent, keyed by path, so a scenario can
    hold the new storage to it.
    """
    if not uploads:
        raise AssertionError("Registering the new adapter for upload returned no upload locations")

    offered_locations = {upload["path"] for upload in uploads}
    unplaced = sorted(set(fetched) - offered_locations - {_ADAPTER_MANIFEST_FILENAME})
    if unplaced:
        raise AssertionError(
            f"The download handed over {unplaced}, but registering the new adapter issued no location "
            f"for them, so they would be lost in the round trip"
        )

    sent: dict[str, bytes] = {}
    for upload in uploads:
        path = upload["path"]
        if path not in fetched:
            raise AssertionError(f"The download offered no file for {path}, so there is nothing to carry back")
        payload = fetched[path]
        try:
            response = requests.put(upload["url"], data=payload, timeout=_UPLOAD_TIMEOUT, verify=False)
        except requests.RequestException as exc:
            raise RuntimeError(f"Could not reach the upload location issued for {path}: {exc}") from exc
        if response.status_code >= 400:
            raise AssertionError(f"Uploading {path} failed with HTTP {response.status_code}: {response.text}")
        sent[path] = payload
    return sent


@keyword("Adapter Location Should Hold Exactly")
def adapter_location_should_hold_exactly(namespace: str, uri: str, expected: dict) -> None:
    """Assert the location holds the named files, byte for byte, and nothing else.

    Read back from object storage rather than from the API, because what a receiver ends up with is
    the bytes at the prefix -- an API that reported the transfer as complete while storing something
    else would still be a broken import. Exactly, in both directions: a prefix carrying objects
    nobody sent is as wrong as one missing a file, and checking only the named ones would pass
    against either. The manifest is the one object allowed beyond what was sent, because the
    platform writes it at the prefix itself as part of registering the adapter.
    """
    if not expected:
        raise AssertionError("No files were named, so the location cannot be held to anything")

    client = _minio_client(namespace)
    prefix = _prefix_from_storage_location(uri)

    stored_paths = {key.removeprefix(prefix) for key in objects_stored_at_adapter_location(namespace, uri)}
    unexpected = sorted(stored_paths - set(expected) - {_ADAPTER_MANIFEST_FILENAME})
    absent = sorted(set(expected) - stored_paths)
    if unexpected or absent:
        raise AssertionError(f"{uri} is missing {absent} and holds unexpected {unexpected}")

    for path, payload in expected.items():
        response = client.get_object(_MINIO_BUCKET, f"{prefix}{path}")
        try:
            stored = response.read()
        finally:
            response.close()
            response.release_conn()
        if stored != payload:
            raise AssertionError(
                f"{path} at {uri} holds {len(stored)} bytes that differ from the {len(payload)} that were sent"
            )


@keyword("Objects Stored At Adapter Location")
def objects_stored_at_adapter_location(namespace: str, uri: str) -> list[str]:
    """Every object key currently held under an adapter's storage location, sorted.

    Returned rather than asserted on so a scenario can state its own expectation -- present,
    absent, or unchanged from what it recorded earlier.
    """
    return _objects_stored_at_storage_location(namespace, uri)


def _objects_stored_at_storage_location(namespace: str, uri: str) -> list[str]:
    """Return sorted object keys under one storage location."""
    client = _minio_client(namespace)
    prefix = _prefix_from_storage_location(uri)
    return sorted(obj.object_name for obj in client.list_objects(_MINIO_BUCKET, prefix=prefix, recursive=True))


@keyword("Objects Stored At Storage Locations")
def objects_stored_at_storage_locations(namespace: str, uris: list[str]) -> list[str]:
    """Every object key currently held under any provided storage location, sorted and unique."""
    object_keys: set[str] = set()
    for uri in uris:
        object_keys.update(_objects_stored_at_storage_location(namespace, uri))
    return sorted(object_keys)


@keyword("Stored Object Keys Should Be Removed")
def stored_object_keys_should_be_removed(namespace: str, object_keys: list[str]) -> None:
    """Assert all provided object keys are absent from project storage."""
    client = _minio_client(namespace)
    still_present: list[str] = []
    for object_key in object_keys:
        try:
            client.stat_object(_MINIO_BUCKET, object_key)
            still_present.append(object_key)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                continue
            raise RuntimeError(f"Failed to verify object absence for {object_key}: {exc}") from exc

    if still_present:
        raise AssertionError(f"Expected deleted objects are still present: {sorted(still_present)}")


@keyword("Storage Locations Should Be Empty")
def storage_locations_should_be_empty(namespace: str, uris: list[str]) -> None:
    """Assert every provided storage location currently has no objects."""
    for uri in uris:
        objects = _objects_stored_at_storage_location(namespace, uri)
        if objects:
            raise AssertionError(f"Storage location {uri} still holds objects: {objects}")


@keyword("Remove Adapter Weights At Storage Location")
def remove_adapter_weights_at_storage_location(namespace: str, uri: str) -> None:
    """Delete everything under a storage location, so the shared bucket does not outlive the project.

    Deleting the namespace does not reclaim object storage, and a prefix left behind would be
    discovered again by any later run that reuses the project name. A location the platform already
    reclaimed holds nothing, so this is a no-op there rather than an error.
    """
    client = _minio_client(namespace)
    prefix = _prefix_from_storage_location(uri)
    for obj in client.list_objects(_MINIO_BUCKET, prefix=prefix, recursive=True):
        client.remove_object(_MINIO_BUCKET, obj.object_name)


@keyword("Apply AIMArtifact CR")
def apply_aim_artifact_cr(
    name: str,
    namespace: str,
    managed_by: str = "fine-tuning",
    compatible_with: str = "example-org/e2e-base-model",
    workload_id: str = "",
    description: str = "",
    model_id: str = "",
    source_uri: str | None = None,
    display_name: str = "",
    rank: int | None = None,
    submitter: str = "",
) -> str:
    """Apply a minimal AIMArtifact CR standing in for a produced adapter artifact.

    ``managed_by`` sets the ``app.kubernetes.io/managed-by`` label the API treats as
    the platform-artifact membership rule — pass a foreign value to simulate an
    artifact authored outside the platform, which the API must not expose.

    ``compatible_with`` is the base model the adapter declares it may attach to. An adapter
    must carry exactly one lineage declaration, and a real fine-tuning run leaves this one:
    a canonical model id nothing has to resolve, rather than a binding to a concrete resource.

    ``model_id`` is the adapter's own canonical id, which the CRD requires of every adapter.
    It defaults to the same ``finetuned/<name>`` shape the fine-tuning engine stamps on the
    artifacts it leaves behind, so a stand-in built here is identified the way a real one is.

    The source URI defaults to the prefix the platform allocates for the project's adapters,
    so a CR built here claims the same storage a real registration would. ``source_uri`` overrides
    it, for scenarios that need a record pointing somewhere a real registration never would.
    The emitted CR's ``spec.env`` carries the same project-storage credential references as a real
    artifact, so a CR built here can be staged by aim-engine rather than only claiming storage it
    cannot read.

    ``workload_id``, when non-empty, stamps the ``airm.silogen.ai/workload-id`` label a
    fine-tuning run's own output carries — the label the adapter-attribution check matches
    on. Leave empty for an artifact that should not be attributable to any run.

    ``description``, ``display_name``, and ``submitter``, when non-empty, mirror the annotations
    produced by a fine-tuning job.

    ``rank`` stamps optional ``spec.rank`` when the producing run declares it.
    """
    if source_uri is None:
        source_uri = f"s3://{_MINIO_BUCKET}/{_adapter_prefix(namespace, name)}"
    labels = f"    app.kubernetes.io/managed-by: {managed_by}\n"
    if workload_id:
        labels += f"    airm.silogen.ai/workload-id: {workload_id}\n"
    annotation_values: dict[str, str] = {}
    if description:
        annotation_values["aiwb.apps.eai.amd.com/description"] = description
    if display_name:
        annotation_values["aiwb.apps.eai.amd.com/display-name"] = display_name
    if submitter:
        annotation_values["airm.silogen.ai/submitter"] = submitter
    annotations = ""
    if annotation_values:
        values = "".join(f"    {key}: {json.dumps(value)}\n" for key, value in annotation_values.items())
        annotations = f"  annotations:\n{values}"
    rank_line = f"  rank: {int(rank)}\n" if rank is not None else ""
    yaml_body = (
        "apiVersion: aim.eai.amd.com/v1alpha1\n"
        "kind: AIMArtifact\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  namespace: {namespace}\n"
        "  labels:\n"
        f"{labels}"
        f"{annotations}"
        "spec:\n"
        "  type: adapter\n"
        f"  sourceUri: {source_uri}\n"
        f"  modelId: {model_id or f'finetuned/{name}'}\n"
        f"{rank_line}"
        "  compatibleWith:\n"
        f"    - {compatible_with}\n"
        "  env:\n"
        "    - name: AWS_ACCESS_KEY_ID\n"
        "      valueFrom:\n"
        "        secretKeyRef:\n"
        "          name: minio-credentials\n"
        "          key: minio-access-key\n"
        "    - name: AWS_SECRET_ACCESS_KEY\n"
        "      valueFrom:\n"
        "        secretKeyRef:\n"
        "          name: minio-credentials\n"
        "          key: minio-secret-key\n"
        "    - name: AWS_ENDPOINT_URL\n"
        f"      value: {_S3_BUCKET_URL}\n"
    )
    _apply_yaml(yaml_body, namespace, f"AIMArtifact CR {name}")
    return name


@keyword("Apply AIMArtifact CR Recording Storage Outside The Project")
def apply_aim_artifact_cr_recording_storage_outside_the_project(name: str, namespace: str) -> str:
    """Apply an adapter CR whose recorded storage location sits in another project's tree.

    Every project shares one bucket, so a record pointing outside the project's own prefix is the
    shape a tampered or mis-reconciled artifact takes -- one that, if honoured, would sign working
    links against another tenant's files. No objects are written there: nothing may read the
    location in the first place. Returns the recorded location so a scenario can name it.
    """
    foreign_uri = f"s3://{_MINIO_BUCKET}/{_adapter_prefix(f'other-{namespace}', name)}"
    apply_aim_artifact_cr(name, namespace, source_uri=foreign_uri)
    return foreign_uri


@keyword("Apply Multiple AIMArtifact CRs")
def apply_multiple_aim_artifact_crs(
    namespace: str,
    count: int,
    name_prefix: str = "page-test-adapter",
    managed_by: str = "fine-tuning",
) -> list[str]:
    """Apply ``count`` AIMArtifact CRs so pagination has more than one page to return."""
    names: list[str] = []
    for index in range(int(count)):
        names.append(apply_aim_artifact_cr(f"{name_prefix}-{index:03d}", namespace, managed_by))
    return names


@keyword("Apply AIMService Referencing Artifact")
def apply_aim_service_referencing_artifact(name: str, artifact_name: str, namespace: str) -> str:
    """Apply an AIMService CR that attaches ``artifact_name`` via ``spec.adapters[]``.

    That list entry is the only thing the delete guard scans for, so the service must
    carry it to block deletion of the artifact.

    Two things the CRD insists on, without which the API server rejects the CR outright and
    the guard is never reached: every adapter entry carries ``kind``, restricted to
    ``AIMArtifact``, and a service declaring adapters must also select a profile. The profile
    named here resolves to nothing on purpose -- the service only has to exist, and one that
    could reconcile would schedule a real workload for a guard that reads a spec field.
    """
    yaml_body = (
        "apiVersion: aim.eai.amd.com/v1alpha2\n"
        "kind: AIMService\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  namespace: {namespace}\n"
        "spec:\n"
        "  profile:\n"
        "    name: e2e-unresolvable-profile\n"
        "  adapters:\n"
        "    - kind: AIMArtifact\n"
        f"      name: {artifact_name}\n"
    )
    _apply_yaml(yaml_body, namespace, f"AIMService CR {name}")
    return name


@keyword("Apply AIMService With Adapter Mode")
def apply_aim_service_with_adapter_mode(
    name: str,
    model_name: str,
    namespace: str,
    workload_id: str,
    adapter_mode: str = "dynamic",
    adapter_name: str = "",
) -> str:
    """Apply an AIMService CR standing in for a deployment whose adapters a test then changes.

    ``workload_id`` is the id the workbench addresses a deployment by, so without it as a label
    no request can reach this service.

    The pinned profile resolves to nothing deliberately: this keeps the service from scheduling,
    so no accelerator is held for a scenario that only reads and writes a spec.

    ``adapter_name`` seeds the service with one adapter already attached, for scenarios that
    start from a deployment that is serving something.
    """
    attached = ""
    if adapter_name:
        attached = f"  adapters:\n    - kind: AIMArtifact\n      name: {adapter_name}\n"
    yaml_body = (
        "apiVersion: aim.eai.amd.com/v1alpha2\n"
        "kind: AIMService\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  namespace: {namespace}\n"
        "  labels:\n"
        f"    airm.silogen.ai/workload-id: {workload_id}\n"
        "spec:\n"
        "  model:\n"
        f"    name: {model_name}\n"
        "  profile:\n"
        "    name: e2e-unresolvable-profile\n"
        f"  adapterMode: {adapter_mode}\n"
        f"{attached}"
    )
    _apply_yaml(yaml_body, namespace, f"AIMService CR {name}")
    return name


def _cr_exists(plural: str, name: str, namespace: str) -> tuple[bool, str]:
    """Whether the named CR is present, plus kubectl's stderr for the failure message.

    A non-zero exit that is not a "not found" is raised rather than reported as absent, so a
    misconfigured kubectl can never be mistaken for a resource that is gone.
    """
    try:
        result = subprocess.run(
            ["kubectl", "get", plural, name, "-n", namespace],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError(f"kubectl not found on PATH — cannot check {plural} {name}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for {plural} {name}")
    if result.returncode == 0:
        return True, ""
    stderr_lower = result.stderr.lower()
    if "not found" not in stderr_lower and "notfound" not in stderr_lower:
        raise RuntimeError(f"kubectl get failed unexpectedly (not a 'not found' error): {result.stderr}")
    return False, result.stderr


@keyword("AIMArtifact CR Should Be Absent")
def aim_artifact_cr_should_be_absent(name: str, namespace: str) -> None:
    """Assert the AIMArtifact CR is no longer present in the namespace."""
    exists, _ = _cr_exists("aimartifacts", name, namespace)
    if exists:
        raise AssertionError(f"AIMArtifact CR {name} still exists in namespace {namespace}")


@keyword("AIMArtifact CR Should Exist")
def aim_artifact_cr_should_exist(name: str, namespace: str) -> None:
    """Assert the AIMArtifact CR is still present in the namespace.

    Guards the foreign-artifact delete case: a 204 must mean "not yours, nothing done",
    never a silent removal of another operator's resource.
    """
    exists, stderr = _cr_exists("aimartifacts", name, namespace)
    if not exists:
        raise AssertionError(f"AIMArtifact CR {name} is absent from namespace {namespace}: {stderr}")


@keyword("AIMService CR Should Exist")
def aim_service_cr_should_exist(name: str, namespace: str) -> None:
    """Assert the AIMService CR is still present in the namespace.

    Backs the force-delete case: waiving the reference guard must remove only the artifact and
    leave the deployment that referenced it running.
    """
    exists, stderr = _cr_exists("aimservices", name, namespace)
    if not exists:
        raise AssertionError(f"AIMService CR {name} is absent from namespace {namespace}: {stderr}")


def _get_aim_service_cr(service_name: str, namespace: str) -> dict:
    """The AIMService CR as the engine sees it, for assertions the API's own echo cannot support."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "aimservices", service_name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl not found on PATH — cannot read AIMService spec")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl get timed out after {_KUBECTL_TIMEOUT}s for AIMService {service_name}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get aimservices failed unexpectedly: {result.stderr}")
    return json.loads(result.stdout)


@keyword("AIMService CR Should Record Adapter")
def aim_service_cr_should_record_adapter(service_name: str, namespace: str, expected_adapter_name: str) -> None:
    """Assert the AIMService CR's own manifest records the adapter it was asked to serve.

    Reads the resource the engine reconciles rather than the API's echo of the deploy request, so
    the adapter is proven to reach the manifest -- named, and typed as the artifact kind the engine
    resolves it against.
    """
    cr = _get_aim_service_cr(service_name, namespace)
    adapters = cr.get("spec", {}).get("adapters", [])
    if len(adapters) != 1:
        raise AssertionError(f"Deployment should record exactly the one adapter it was asked to serve, got: {adapters}")
    adapter = adapters[0]
    if adapter.get("name") != expected_adapter_name:
        raise AssertionError(f"Recorded adapter should be the one the deploy asked for, got: {adapter.get('name')}")
    if adapter.get("kind") != "AIMArtifact":
        raise AssertionError(
            f"Adapter reference must declare the artifact kind the engine resolves it against, "
            f"got: {adapter.get('kind')}"
        )


@keyword("AIMService CR Should Record Adapters")
def aim_service_cr_should_record_adapters(service_name: str, namespace: str, expected_adapter_names: list) -> None:
    """Assert the AIMService CR records exactly ``expected_adapter_names``, whatever their order.

    The adapter set is replaced wholesale, so the whole set is what has to be checked: an
    assertion on a single name would also pass a change that quietly left a detached adapter
    behind. An empty expectation means the field is gone, which is how a deployment serving no
    adapters is recorded.
    """
    cr = _get_aim_service_cr(service_name, namespace)
    adapters = cr.get("spec", {}).get("adapters") or []
    recorded = sorted(adapter.get("name") for adapter in adapters)
    expected = sorted(expected_adapter_names)
    if recorded != expected:
        raise AssertionError(f"Deployment should record adapters {expected}, got {recorded}")
    wrong_kind = [adapter.get("name") for adapter in adapters if adapter.get("kind") != "AIMArtifact"]
    if wrong_kind:
        raise AssertionError(
            f"Adapter references must declare the artifact kind the engine resolves them against, "
            f"got another kind for: {wrong_kind}"
        )


def _records_all_of(recorded: Any, expected: Any) -> bool:
    """Whether ``recorded`` carries every value in ``expected``, ignoring anything else it holds.

    Nested, because the interesting part of a scaling policy is the metric buried two levels
    down. Extra keys pass so that defaults the cluster fills in of its own accord are not read as
    the deployment recording something other than what it was asked for.
    """
    if isinstance(expected, dict):
        return isinstance(recorded, dict) and all(_records_all_of(recorded.get(k), v) for k, v in expected.items())
    if isinstance(expected, list):
        return (
            isinstance(recorded, list)
            and len(recorded) == len(expected)
            and all(_records_all_of(r, e) for r, e in zip(recorded, expected, strict=True))
        )
    return recorded == expected


@keyword("AIMService CR Should Record Scaling")
def aim_service_cr_should_record_scaling(service_name: str, namespace: str, expected_scaling: dict) -> None:
    """Assert the AIMService CR records the scaling policy the change asked for.

    Takes the request itself rather than a restatement of its values, so a fixture that asks for
    one thing cannot be checked against an assertion still expecting another. The metric shape is
    part of the claim: a policy the engine cannot read is not a policy the deployment recorded.
    """
    spec = _get_aim_service_cr(service_name, namespace).get("spec", {})
    wrong = {key: value for key, value in expected_scaling.items() if not _records_all_of(spec.get(key), value)}
    if wrong:
        recorded = {key: spec.get(key) for key in wrong}
        raise AssertionError(f"Deployment should record the scaling it was asked for: expected {wrong}, got {recorded}")


@keyword("AIMService CR Should Allow Adapters To Change")
def aim_service_cr_should_allow_adapters_to_change(service_name: str, namespace: str) -> None:
    """Assert the deployment was created free to gain and lose adapters while it runs.

    Checked on the manifest because the setting is fixed at creation: a deployment that did not
    carry the request cannot be corrected afterwards, only replaced.
    """
    cr = _get_aim_service_cr(service_name, namespace)
    mode = cr.get("spec", {}).get("adapterMode")
    if mode != "dynamic":
        raise AssertionError(
            f"Deployment should have been created free to change its adapters while running, got mode: {mode}"
        )
