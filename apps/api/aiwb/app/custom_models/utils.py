# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Pure helper functions for custom model operations."""

import json
from typing import Any
from urllib.parse import unquote, urlsplit

from api_common.exceptions import ExternalServiceError, ForbiddenException, NotFoundException, ValidationException

from ..aims.crds import AIMModelResource, ProfileOverrides
from ..aims.enums import AIMModelStatus
from ..dispatch.utils import sanitize_label_value
from ..workloads.constants import DISPLAY_NAME_ANNOTATION, MODEL_NAME_LABEL
from .constants import (
    _CONFIG_EXTENSIONS,
    _CONFIG_FILENAMES,
    _HF_HOSTS,
    _INDEX_PATTERN,
    _REPO_PART_PATTERN,
    _REVISION_MARKERS,
    _WEIGHT_EXTENSIONS,
    CANONICAL_REPO_ID_ANNOTATION,
    HF_API_BASE,
    MODEL_DISPLAY_NAME_ANNOTATION,
    MODEL_PRECISION_ANNOTATION,
    REVISION_ANNOTATION,
    SOURCE_DESCRIPTION_ANNOTATION,
    SOURCE_SHA_ANNOTATION,
    SOURCE_TAGS_ANNOTATION,
)
from .enums import OnboardPhase
from .schemas import CustomModelPatchResponse, OnboardRequest, WeightFile


def resolve_onboard_phase(
    aim_model_status: str,
    profile_ready: bool,
    artifact_phase: str | None,
) -> OnboardPhase:
    """Classify the onboard phase from the contributing signals.

    ``artifact_phase`` carries the weight-import signal (Importing/Ready/Failed).
    Evaluated in order; first match wins:
    * ``Failed``    — AIMModel status is an explicit failure-class variant (``Failed`` or ``Error``), or the import failed.
    * ``Importing`` — the import is in flight (non-terminal phase). This gates readiness even when aim-engine has already marked the AIMModel Ready and emitted a profile, because profiles derive from the base image, not from the presence of weights in S3.
    * ``Ready``     — AIMModel status is "Ready", at least one AIMProfile has been emitted, and the import is not still running (done, or never tracked).
    * ``Pending``   — default; the CR exists but is not yet ready (e.g. import finished but the engine has not yet emitted a profile).
    """
    if aim_model_status in {AIMModelStatus.FAILED, AIMModelStatus.ERROR} or artifact_phase == OnboardPhase.FAILED:
        return OnboardPhase.FAILED
    if artifact_phase and artifact_phase not in (OnboardPhase.READY, OnboardPhase.FAILED):
        return OnboardPhase.IMPORTING
    if aim_model_status == AIMModelStatus.READY and profile_ready:
        return OnboardPhase.READY
    return OnboardPhase.PENDING


def _extract_revision(path_segments: list[str]) -> tuple[list[str], str | None]:
    if len(path_segments) > 2 and path_segments[2] in _REVISION_MARKERS:
        revision = unquote(path_segments[3]) if len(path_segments) > 3 else None
        return path_segments[:2], revision
    return path_segments, None


def normalize_hf_source(source: str) -> tuple[str, str | None]:
    parts = urlsplit(source.strip())

    if parts.scheme:
        if parts.scheme.lower() not in {"http", "https"}:
            raise ValidationException(
                message=f"Invalid Hugging Face source '{source}'. Only bare repo ids or http(s)://huggingface.co URLs are supported."
            )
        if not parts.netloc:
            raise ValidationException(
                message=f"Invalid Hugging Face source '{source}'. URLs must include 'huggingface.co' as the host."
            )
    elif parts.netloc:
        raise ValidationException(
            message=f"Invalid Hugging Face source '{source}'. Only bare repo ids or http(s)://huggingface.co URLs are supported."
        )
    if parts.netloc and parts.netloc.lower() not in _HF_HOSTS:
        raise ValidationException(
            message=f"Invalid Hugging Face source '{source}'. Only huggingface.co URLs are supported."
        )

    path_segments = [s for s in parts.path.split("/") if s]
    path_segments, revision = _extract_revision(path_segments)

    if len(path_segments) != 2:
        raise ValidationException(
            message=f"Invalid Hugging Face source '{source}'. Expected format: 'owner/model' or a full huggingface.co URL."
        )

    owner, model = path_segments
    if not _REPO_PART_PATTERN.match(owner) or not _REPO_PART_PATTERN.match(model):
        raise ValidationException(
            message=f"Invalid Hugging Face source '{source}'. Repo id may only contain letters, digits, '.', '_', and '-'."
        )

    return f"{owner}/{model}", revision


def validate_hf_repo_id(repo_id: str) -> None:
    """Raise ValidationException when `repo_id` is not a well-formed HF repo id.

    Onboard is fed canonical repo ids the FE got back from preview, but the API
    doesn't trust that contract — it re-checks here so a malformed `repo_id`
    fails at the service boundary rather than producing a malformed K8s label
    value downstream. Matches the validation `normalize_hf_source` performs
    for preview's URL/bare-id input — including the leading/trailing whitespace
    trim, so onboard does not 400 on a payload that preview would have accepted
    after stripping (avoids surprises from minor UI/transport whitespace).
    """
    repo_id = repo_id.strip()
    parts = repo_id.split("/")
    if len(parts) != 2 or not all(_REPO_PART_PATTERN.match(part) for part in parts):
        raise ValidationException(
            message=f"'{repo_id}' is not a valid Hugging Face repo id. Expected 'owner/model' "
            "with only letters, digits, '.', '_', and '-'."
        )


def _get_file_extension(path: str) -> str:
    lower = path.lower()
    dot = lower.rfind(".")
    return lower[dot:] if dot != -1 else ""


def classify_siblings(siblings: list[dict]) -> list[WeightFile]:
    weight_files: list[WeightFile] = []
    config_files: list[WeightFile] = []

    for sibling in siblings:
        path: str = sibling.get("rfilename", "")
        if not path:
            continue

        if _INDEX_PATTERN.search(path.lower()):
            continue

        lfs = sibling.get("lfs") or {}
        if "size" in lfs:
            size_bytes: int | None = lfs["size"]
        elif "size" in sibling:
            size_bytes = sibling["size"]
        else:
            size_bytes = None

        ext = _get_file_extension(path)
        filename = path.split("/")[-1].lower()

        if ext in _WEIGHT_EXTENSIONS:
            weight_files.append(WeightFile(path=path, size_bytes=size_bytes, role=None))
        elif filename in _CONFIG_FILENAMES or ext in _CONFIG_EXTENSIONS:
            config_files.append(WeightFile(path=path, size_bytes=size_bytes, role="config"))

    _assign_weight_roles(weight_files)

    return weight_files + config_files


def _assign_weight_roles(weight_files: list[WeightFile]) -> None:
    groups: dict[str, list[WeightFile]] = {
        "safetensors": [],
        "gguf": [],
    }
    for wf in weight_files:
        ext = _get_file_extension(wf.path)
        if ext == ".safetensors":
            groups["safetensors"].append(wf)
        elif ext == ".gguf":
            groups["gguf"].append(wf)

    for files in groups.values():
        role = "primary" if len(files) == 1 else "shard"
        for wf in files:
            wf.role = role


def get_layout_hint(weight_files: list[WeightFile]) -> str | None:
    has_safetensors = any(_get_file_extension(wf.path) == ".safetensors" for wf in weight_files)
    has_gguf = any(_get_file_extension(wf.path) == ".gguf" for wf in weight_files)

    if has_safetensors and has_gguf:
        return "mixed"
    if has_safetensors:
        return "safetensors"
    if has_gguf:
        return "gguf"
    return None


def hub_request_args(repo_id: str, revision: str | None, token: str | None) -> tuple[str, dict, dict]:
    url = f"{HF_API_BASE}/{repo_id}"
    params: dict = {"blobs": "true"}
    if revision is not None:
        params["revision"] = revision
    headers: dict = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return url, params, headers


def raise_for_hub_status(
    status_code: int,
    repo_id: str,
    revision: str | None,
    token: str | None,
    body: bytes | None = None,
) -> None:
    if status_code == 200:
        return
    if status_code == 401:
        # When the caller supplied a token, a 401 is a credential failure — even
        # though the Hub masks both private and nonexistent repos behind the same
        # "invalid username or password" body. The caller gave credentials, so the
        # actionable outcome is "fix your token" (403), not a misleading "model not
        # found" (404). Resolving token validity any other way would require an
        # extra Hub round-trip the preview does not make.
        if token:
            raise ForbiddenException(
                "The supplied Hugging Face token is invalid or expired, or does not grant access to this model."
            )
        # No token: the Hub returns 401 "invalid username or password" for both
        # private and nonexistent repos to avoid leaking existence. With no
        # credential to fault, surface it as a plain not-found.
        if body:
            try:
                error_msg = json.loads(body).get("error", "") or ""
                if "invalid username or password" in error_msg.lower():
                    if revision is not None:
                        raise NotFoundException(
                            f"Model '{repo_id}' (revision '{revision}') was not found on Hugging Face Hub."
                        )
                    raise NotFoundException(f"Model '{repo_id}' was not found on Hugging Face Hub.")
            except (ValueError, AttributeError):
                pass
        raise ForbiddenException(
            f"Model '{repo_id}' requires a Hugging Face token. Provide a token via 'hfTokenSecretName' to access it."
        )
    if status_code == 403:
        if token:
            raise ForbiddenException(f"The supplied Hugging Face token does not have access to '{repo_id}'.")
        raise ForbiddenException(
            f"Model '{repo_id}' requires a Hugging Face token. Provide a token via 'hfTokenSecretName' to access it."
        )
    if status_code == 404:
        if revision is not None:
            raise NotFoundException(f"Model '{repo_id}' (revision '{revision}') was not found on Hugging Face Hub.")
        raise NotFoundException(f"Model '{repo_id}' was not found on Hugging Face Hub.")
    if status_code >= 500:
        raise ExternalServiceError(f"Hugging Face Hub returned an error (HTTP {status_code}) for '{repo_id}'.")
    raise ExternalServiceError(f"Unexpected response from Hugging Face Hub (HTTP {status_code}) for '{repo_id}'.")


def build_display_name(hub_data: dict, repo_id: str) -> str:
    card_data = hub_data.get("cardData") or {}
    if card_data.get("model_name"):
        return str(card_data["model_name"])
    return repo_id.split("/")[-1].replace("-", " ").replace("_", " ")


def build_description(hub_data: dict) -> str:
    card_data = hub_data.get("cardData") or {}
    return str(card_data.get("description") or "")


def _onboard_overrides(cr: AIMModelResource) -> ProfileOverrides | None:
    """Return the ``spec.profiles.overrides`` block of an onboard AIMModel.

    v1alpha2 custom-model AIMModels carry their identity, runtime image, and BYO
    weights under ``spec.profiles.overrides`` (the flat v1alpha1 ``spec.image`` /
    ``spec.modelSources`` / ``spec.env`` are forbidden alongside ``spec.profiles``
    by CEL). Returns ``None`` for any CR that is not profiles-shaped.
    """
    profiles = cr.spec.profiles
    return profiles.overrides if profiles else None


def extract_hf_token_secret_name(cr: AIMModelResource) -> str | None:
    """Return the K8s secret name supplying HF_TOKEN to the onboard AIMModel, or None.

    The token is attached to the weights source it authorizes, under
    ``spec.profiles.overrides.modelSources[].env``.
    """
    overrides = _onboard_overrides(cr)
    if overrides is None:
        return None
    for source in overrides.model_sources:
        for entry in source.env or []:
            if entry.name == "HF_TOKEN":
                value_from = (entry.model_extra or {}).get("valueFrom", {})
                return value_from.get("secretKeyRef", {}).get("name")
    return None


def extract_overrides_image(cr: AIMModelResource) -> str:
    """Return the runtime container image overridden on the onboard AIMModel, or "".

    Lives at ``spec.profiles.overrides.image`` in v1alpha2.
    """
    overrides = _onboard_overrides(cr)
    return (overrides.image or "") if overrides else ""


def extract_onboard_repo_id(cr: AIMModelResource) -> str:
    """Return the repo id (or S3 URI) the onboard AIMModel was derived from, or "".

    Prefer the canonical repo-id annotation, which preserves the user-entered
    source (including full S3 URIs). Fall back to profile overrides for older
    resources that predate the annotation.
    """
    annotations = cr.metadata.annotations or {}
    canonical_repo_id = annotations.get(CANONICAL_REPO_ID_ANNOTATION)
    if canonical_repo_id:
        return canonical_repo_id

    overrides = _onboard_overrides(cr)
    if overrides is None:
        return ""
    if overrides.model_id:
        return overrides.model_id
    if overrides.model_sources:
        return overrides.model_sources[0].model_id
    return ""


def parse_source_tags(raw: str | None) -> list[str]:
    """Decode the JSON-encoded ``source-tags`` annotation written at onboard time.

    The annotation lives on a CR and is therefore externally mutable, so a
    malformed value (non-JSON, a non-list, or a list with non-string elements)
    must not break response construction. Non-string elements are dropped so the
    return value always satisfies the declared ``list[str]`` and feeds a
    ``list[str]`` Pydantic field cleanly.
    """
    if not raw:
        return []
    try:
        tags = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if isinstance(tag, str)]


def build_display_metadata_patch(updates: dict[str, Any]) -> dict:
    """Build a merge-patch metadata body from display-metadata updates.

    Mirrors the label/annotation conventions used at onboard time: the display
    name is stored as both the platform-wide ``DISPLAY_NAME_ANNOTATION`` and the
    custom-models ``MODEL_DISPLAY_NAME_ANNOTATION``, plus a sanitized copy on
    ``MODEL_NAME_LABEL`` for label-selector lookups. Tags reuse the same
    JSON-encoded ``SOURCE_TAGS_ANNOTATION`` the onboard path writes. Only the
    keys present in ``updates`` are emitted, so unspecified fields are left
    untouched by the resulting merge patch.
    """
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}

    if "display_name" in updates:
        sanitized = sanitize_label_value(updates["display_name"])
        labels[MODEL_NAME_LABEL] = sanitized
        annotations[DISPLAY_NAME_ANNOTATION] = updates["display_name"]
        annotations[MODEL_DISPLAY_NAME_ANNOTATION] = updates["display_name"]

    if "description" in updates:
        annotations[SOURCE_DESCRIPTION_ANNOTATION] = updates["description"]

    if "tags" in updates:
        annotations[SOURCE_TAGS_ANNOTATION] = json.dumps(updates["tags"])

    metadata: dict[str, dict[str, str]] = {}
    if labels:
        metadata["labels"] = labels
    if annotations:
        metadata["annotations"] = annotations
    return {"metadata": metadata}


def resolve_custom_model_display_name(cr: AIMModelResource) -> str:
    annotations = cr.metadata.annotations or {}
    return (
        annotations.get(MODEL_DISPLAY_NAME_ANNOTATION) or annotations.get(DISPLAY_NAME_ANNOTATION) or cr.metadata.name
    )


def display_metadata_response_from_model(model: AIMModelResource) -> CustomModelPatchResponse:
    annotations = model.metadata.annotations or {}
    description = annotations.get(SOURCE_DESCRIPTION_ANNOTATION, "")
    tags = parse_source_tags(annotations.get(SOURCE_TAGS_ANNOTATION))
    return CustomModelPatchResponse(
        name=model.metadata.name,
        display_name=resolve_custom_model_display_name(model),
        description=description,
        tags=tags,
    )


def next_copy_display_name(source_display_name: str, existing_display_names: set[str]) -> str:
    normalized = source_display_name
    if normalized.endswith("-copy"):
        normalized = normalized[: -len("-copy")]
    else:
        head, sep, tail = normalized.rpartition("-copy-")
        if sep and tail.isdigit():
            normalized = head

    base = f"{normalized}-copy"
    if base not in existing_display_names:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing_display_names:
        suffix += 1
    return f"{base}-{suffix}"


def build_copy_onboard_request(source: AIMModelResource, copy_display_name: str) -> OnboardRequest:
    source_name = source.metadata.name
    source_annotations = source.metadata.annotations or {}
    source_repo_id = extract_onboard_repo_id(source)
    source_image = extract_overrides_image(source) or source.spec.image
    source_hf_secret = extract_hf_token_secret_name(source)
    source_revision = source_annotations.get(REVISION_ANNOTATION, "")
    source_sha = source_annotations.get(SOURCE_SHA_ANNOTATION, "")
    source_description = source_annotations.get(SOURCE_DESCRIPTION_ANNOTATION, "")
    source_tags_raw = source_annotations.get(SOURCE_TAGS_ANNOTATION, "[]")
    try:
        source_tags = json.loads(source_tags_raw)
        if not isinstance(source_tags, list):
            source_tags = []
    except ValueError:
        source_tags = []

    missing = [
        field
        for field, value in (
            ("repo_id", source_repo_id),
            ("revision", source_revision),
            ("sha", source_sha),
            ("image", source_image),
        )
        if not value
    ]
    if missing:
        raise ValidationException(
            message=(
                f"Cannot copy model '{source_name}': required fields are missing or empty "
                f"on the source CR: {', '.join(missing)}. "
                "The model may have been created by an incompatible workflow."
            )
        )

    custom_profile: dict[str, Any] | None = (
        source.spec.profiles.overrides.model_dump(by_alias=True, exclude_none=True)
        if source.spec.profiles and source.spec.profiles.overrides
        else None
    )
    # Precision is pruned from overrides, so it survives only on the annotation.
    # Re-inject it into the copy's customProfile so the copied model keeps the
    # source's chosen precision (which the onboard path re-stamps as an annotation).
    source_precision = source_annotations.get(MODEL_PRECISION_ANNOTATION)
    if source_precision:
        custom_profile = {**(custom_profile or {}), "precision": source_precision}

    return OnboardRequest(
        repo_id=source_repo_id,
        revision=source_revision,
        sha=source_sha,
        display_name=copy_display_name,
        description=source_description,
        tags=source_tags,
        image=source_image,
        hf_token_secret_name=source_hf_secret,
        custom_profile=custom_profile,
    )
