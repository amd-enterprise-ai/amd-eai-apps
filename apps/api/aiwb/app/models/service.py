# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import os
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from kubernetes_asyncio.client import ApiException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import (
    DeletionConflictException,
    ExternalServiceError,
    NotFoundException,
    ValidationException,
)

from ..aims import gateway as aims_gateway
from ..aims.constants import ADAPTER_PROFILE_FEATURE, AIM_PROFILE_SOURCE_MODEL_LABEL
from ..aims.crds import AIMModelResource, AIMModelSource, AIMProfileResource
from ..charts.config import FINETUNING_CHART_NAME, MLFLOW_CHART_NAME
from ..charts.service import get_chart
from ..charts.utils import render_helm_template
from ..cluster.service import get_cluster_gpu_device_info
from ..cluster.utils import normalize_gpu_device_id
from ..config import SUBMITTER_ANNOTATION
from ..custom_models.constants import SOURCE_DESCRIPTION_ANNOTATION
from ..datasets.repository import list_datasets
from ..dispatch.kube_client import KubernetesClient
from ..dispatch.utils import parse_uuid, sanitize_label_value
from ..minio.client import MinioClient
from ..minio.config import MINIO_BUCKET, MINIO_URL
from ..overlays.models import Overlay
from ..overlays.repository import list_overlays
from ..secrets.service import get_secret_details
from ..workloads.constants import (
    DESCRIPTION_ANNOTATION,
    DISPLAY_NAME_ANNOTATION,
    MODEL_ID_LABEL,
    MODEL_NAME_LABEL,
    MODEL_SOURCE_TYPE_LABEL,
    TRAINING_OUTPUT_ANNOTATION,
    WORKLOAD_ID_LABEL,
    WORKLOAD_TYPE_LABEL,
)
from ..workloads.enums import ModelSourceType, TrainingOutput, WorkloadStatus, WorkloadType
from ..workloads.repository import create_workload, get_workloads, update_workload_status
from ..workloads.schemas import WorkloadResponse
from ..workloads.utils import apply_manifest, pin_jobs_to_gpu_devices
from .hyperparameters import (
    BATCH_SIZE_PATH,
    EPOCHS_PATH,
    LEARNING_RATE_PATH,
    LORA_PEFT_KEYS,
    PEFT_KWARGS_PATH,
    TRAINING_ARGS_SECTION,
    merge_helm_values,
    resolve_hyperparameters,
)
from .schemas import (
    FinetunableModelResponse,
    FinetuneCreate,
    FinetuneJobResponse,
    FineTuningOutput,
    TrainingType,
)
from .utils import delete_from_s3, delete_object_from_s3, get_finetuned_model_weights_path

# The {org} half of a fine-tuned adapter's modelId fixes its cache path on the serving
# node and cannot practically change once adapters exist in the field. A platform constant
# is therefore the only safe choice — deriving it from a project or tenant would strand
# every existing adapter the first time one is renamed.
ADAPTER_ORGANISATION = "finetuned"


def _get_training_output(
    *,
    wants_adapter: bool,
    training_type: TrainingType | str | None,
) -> TrainingOutput | None:
    """Return the annotation value for a LoRA run; absence denotes full training."""
    if wants_adapter:
        return TrainingOutput.LORA
    if training_type == TrainingType.LORA:
        return TrainingOutput.MERGED
    return None


async def get_aim_model(
    kube_client: KubernetesClient,
    namespace: str,
    resource_name: str,
) -> AIMModelResource:
    aim_model = await aims_gateway.get_aim_model(kube_client, namespace, resource_name)
    if aim_model is not None:
        return aim_model

    # Fall back to label-based lookup (supports workload UUIDs as resource_name)
    workload_id_selector = f"{WORKLOAD_ID_LABEL}={resource_name}"
    aim_model = await aims_gateway.find_aim_model_by_label(kube_client, namespace, workload_id_selector)
    if aim_model is not None:
        return aim_model

    raise NotFoundException(f"Model {resource_name} not found")


def _declared_accelerators(overlay: Overlay) -> list | None:
    """Return the GPU device IDs a recipe declares, or None when it declares none and fits any GPU."""
    overlay_data = overlay.overlay if isinstance(overlay.overlay, dict) else {}
    metadata = overlay_data.get("metadata")
    return metadata.get("compatibleAccelerators") if isinstance(metadata, dict) else None


def _section(values: Mapping[str, Any], key: str) -> dict:
    """Return a mapping nested in overlay data, or an empty one when it is absent or malformed."""
    section = values.get(key)
    return section if isinstance(section, dict) else {}


def _fits_cluster(overlay: Overlay, cluster_gpu_ids: Collection[str]) -> bool:
    """Whether the overlay declares no GPUs or names one of the cluster's.

    `cluster_gpu_ids` are bare lowercase hex, and declared IDs are compared in that form so
    `0x75a8` matches a `75a8` node label.
    """
    declared = _declared_accelerators(overlay)
    return declared is None or not {normalize_gpu_device_id(acc_id) for acc_id in declared}.isdisjoint(cluster_gpu_ids)


def select_recipe(overlays: list[Overlay], canonical_name: str, cluster_gpu_ids: Collection[str]) -> Overlay | None:
    """Pick the recipe for `canonical_name` that fits the cluster's GPUs, or None when none does.

    A chart may ship one recipe per GPU family for the same model, each backed by a file. Overlays
    authored through the API carry no file and may be partial overrides, so they are candidates only
    when the model has no file-backed recipe; otherwise they layer over the choice, see
    `select_supplemental_overlays`. A recipe naming one of the cluster's GPUs beats one that declares
    none, since its settings were written for that hardware. When several still qualify, as on a
    cluster with more than one GPU family, the first by source path wins: listing and running a
    fine-tune both choose through here, so they must reach the same recipe.
    """
    model_overlays = [overlay for overlay in overlays if overlay.canonical_name == canonical_name]
    candidates = [overlay for overlay in model_overlays if overlay.source_path is not None] or model_overlays
    ranked = [
        (_declared_accelerators(overlay) is None, overlay.source_path or "", overlay)
        for overlay in candidates
        if _fits_cluster(overlay, cluster_gpu_ids)
    ]
    if not ranked:
        return None
    return min(ranked, key=lambda entry: entry[:2])[2]


def select_supplemental_overlays(
    overlays: list[Overlay], recipe: Overlay, cluster_gpu_ids: Collection[str]
) -> list[Overlay]:
    """Return the API-authored overlays for the recipe's model that layer over it on this cluster.

    The run may land on any of the cluster's GPUs the recipe fits, so an overlay applies only when
    it declares no GPUs or declares every one of them. One written for only some of that hardware
    would otherwise run its settings on GPUs they do not describe, so it is left out.
    """
    declared_by_recipe = _declared_accelerators(recipe)
    run_gpu_ids = set(cluster_gpu_ids)
    if declared_by_recipe is not None:
        run_gpu_ids &= {normalize_gpu_device_id(acc_id) for acc_id in declared_by_recipe}

    supplements = []
    for overlay in overlays:
        if overlay is recipe or overlay.canonical_name != recipe.canonical_name or overlay.source_path is not None:
            continue
        declared = _declared_accelerators(overlay)
        if declared is None or run_gpu_ids <= {normalize_gpu_device_id(acc_id) for acc_id in declared}:
            supplements.append(overlay)
    return supplements


async def get_finetunable_models(
    session: AsyncSession, kube_client: KubernetesClient, chart_name: str = FINETUNING_CHART_NAME
) -> list[FinetunableModelResponse]:
    """Get models that can be finetuned on the cluster's current AIM and GPU profile.

    Each model is offered once, through the recipe `select_recipe` picks for the cluster's GPUs.
    It is returned only when both:
    - that recipe exists: its `metadata.compatibleAccelerators` intersect the cluster's GPU device
      IDs, or it declares none and is treated as compatible with all hardware, and
    - its `aimManifest.aimId` matches an AIMClusterProfile present on the cluster
      (via `spec.aimId`).

    Both sides of the join use `modelId` (the base-weights / artifact identity) rather than
    `aimId` (the family identity that is shared across packagings like FP8 inference
    variants). A fine-tuning recipe targets a specific set of weights, so matching on the
    family would let incompatible packagings appear as finetunable. In current overlays
    `aimManifest.modelId == aimManifest.aimId`, so this read is behavior-neutral today; it
    expresses the intended join semantics for when the two diverge.
    """
    cluster_aim_ids = await _get_cluster_profile_aim_ids(kube_client)
    if not cluster_aim_ids:
        return []

    chart = await get_chart(session, chart_name=chart_name)
    overlays = await list_overlays(session, chart_id=chart.id, include_generic=True)
    cluster_gpu_names = {
        normalize_gpu_device_id(device_id): name
        for device_id, name in (await get_cluster_gpu_device_info(kube_client)).items()
    }
    signature = chart.signature if isinstance(chart.signature, dict) else {}
    generic_values = [overlay.overlay for overlay in overlays if overlay.canonical_name is None]

    model_names = dict.fromkeys(overlay.canonical_name for overlay in overlays if overlay.canonical_name is not None)
    result = []
    for model_name in model_names:
        overlay = select_recipe(overlays, model_name, cluster_gpu_names.keys())
        if overlay is None:
            continue
        supplements = select_supplemental_overlays(overlays, overlay, cluster_gpu_names.keys())
        overlay_data = overlay.overlay if isinstance(overlay.overlay, dict) else {}
        aim_manifest = overlay_data.get("aimManifest")
        aim_id = aim_manifest.get("aimId") if isinstance(aim_manifest, dict) else None
        if not aim_id or aim_id not in cluster_aim_ids:
            continue
        # Layered as a launch layers them, so what is advertised is what a run gets.
        launch_values = merge_helm_values(
            [signature, *generic_values, overlay_data, *(supplement.overlay for supplement in supplements)]
        )
        metadata = _section(launch_values, "metadata")
        # The GPUs come from the recipe alone: an override that applies may name more hardware than
        # the recipe's settings were written for.
        compatible_accelerators = _section(overlay_data, "metadata").get("compatibleAccelerators")
        normalized_accelerators = [normalize_gpu_device_id(acc_id) for acc_id in compatible_accelerators or []]
        # Resolve display names only for GPUs present in this cluster; deduplicate preserving order
        accelerator_names = list(
            dict.fromkeys(
                cluster_gpu_names[acc_id] for acc_id in normalized_accelerators if acc_id in cluster_gpu_names
            )
        )
        # Default to gated when the recipe omits the flag or declares a non-boolean. Reporting an
        # unreadable value as open costs the user a job that dies at weight download; reporting it
        # as gated costs them a token they may not need.
        hf_token_required = metadata.get("hfTokenRequired")
        # AIWB reads the overlay, never the chart's values.yaml, so the chart's own
        # `trainingType: "full"` default has to be applied here: a recipe that declares nothing
        # trains full-parameter. Anything unrecognised reads the same way rather than failing the
        # whole listing, since recipes are external data.
        training_type = metadata.get("trainingType")
        result.append(
            FinetunableModelResponse(
                canonical_name=overlay.canonical_name,
                # finetuningGpus is an integer in well-formed overlays; Pydantic coerces numeric strings
                gpu_count=launch_values.get("finetuningGpus"),
                # An unquoted YAML ID such as 7448 arrives as an int, which the str-typed field rejects
                compatible_accelerators=[str(acc_id) for acc_id in compatible_accelerators or []],
                compatible_accelerator_names=accelerator_names,
                hf_token_required=hf_token_required if isinstance(hf_token_required, bool) else True,
                training_type=training_type if training_type in TrainingType else TrainingType.FULL,
                hyperparameters=resolve_hyperparameters(launch_values),
            )
        )

    return sorted(result, key=lambda m: m.canonical_name)


async def _get_cluster_profile_aim_ids(kube_client: KubernetesClient) -> set[str]:
    """Collect aimIds advertised by Ready AIMClusterProfile resources on the cluster.

    Only profiles with `status.status == "Ready"` contribute their aimIds —
    Pending, Progressing, Degraded, Failed, and NotAvailable profiles describe
    a profile the cluster cannot currently serve.
    """
    profiles = await aims_gateway.list_aim_cluster_profiles_by_aim_ids(kube_client)
    aim_ids: set[str] = set()
    for profile in profiles:
        if profile.status.status != "Ready":
            continue
        if profile.spec.aim_id:
            aim_ids.add(profile.spec.aim_id)
    return aim_ids


async def list_aim_models(
    kube_client: KubernetesClient,
    namespace: str,
    label_selector: str | None = None,
) -> list[AIMModelResource]:
    exclude_custom = f"{MODEL_SOURCE_TYPE_LABEL}!={ModelSourceType.CUSTOM}"
    combined_selector = f"{label_selector},{exclude_custom}" if label_selector else exclude_custom
    return await aims_gateway.list_aim_models(kube_client, namespace, label_selector=combined_selector)


async def _find_job_by_name(
    kube_client: KubernetesClient,
    namespace: str,
    name: str,
) -> Any | None:
    try:
        job = await kube_client.batch_v1.read_namespaced_job(name=name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return None
        raise

    labels = job.metadata.labels or {}
    if labels.get(WORKLOAD_TYPE_LABEL) != WorkloadType.FINE_TUNING:
        return None
    return job


async def _find_job_by_label(
    kube_client: KubernetesClient,
    namespace: str,
    label_selector: str,
) -> Any | None:
    fine_tuning_selector = f"{WORKLOAD_TYPE_LABEL}={WorkloadType.FINE_TUNING},{label_selector}"
    job_list = await kube_client.batch_v1.list_namespaced_job(
        namespace=namespace,
        label_selector=fine_tuning_selector,
    )
    if job_list and job_list.items:
        return job_list.items[0]
    return None


def _extract_s3_prefix(source_uri: str) -> str:
    # s3://bucket-name/path/to/weights/ → path/to/weights/
    without_scheme = source_uri.removeprefix("s3://")
    _, _, prefix = without_scheme.partition("/")
    return prefix


def _iter_model_sources_for_cleanup(model: AIMModelResource) -> list[AIMModelSource]:
    """Return every weights source location that delete_model should reclaim.

    Fine-tuned/custom v1alpha2 AIMModels can carry weights under
    ``spec.profiles.overrides.modelSources`` with an empty legacy flat
    ``spec.modelSources``. Deletion must inspect both shapes to avoid leaving
    orphaned S3 prefixes behind.
    """
    sources: list[AIMModelSource] = list(model.spec.model_sources or [])
    if model.spec.profiles and model.spec.profiles.overrides.model_sources:
        sources.extend(model.spec.profiles.overrides.model_sources)
    return sources


def _cleanup_prefix_for_source(source_uri: str) -> str:
    """Return the S3 prefix delete_model should sweep for one model source.

    Fine-tuning outputs commonly record the final artifact path
    (`.../<run-id>/checkpoint-final`, `.../<run-id>/checkpoint-final-merged`,
    or `.../<run-id>/adapter`).
    Run-level siblings (for example `aim-model-manifest.yaml`) sit one level up
    and become orphaned if only the checkpoint directory is removed.
    """
    prefix = _extract_s3_prefix(source_uri)
    trimmed = prefix.rstrip("/")
    parts = [part for part in trimmed.split("/") if part]
    # Current fine-tuning producers always stamp:
    # <project>/finetuned-models/<family>/<model>/<run-id>/<terminal-dir>.
    # Requiring at least five segments prevents broadening malformed paths.
    if (
        len(parts) >= 5
        and parts[1] == "finetuned-models"
        and parts[-1]
        in {
            "checkpoint-final",
            "checkpoint-final-merged",
            "adapter",
        }
    ):
        return f"{'/'.join(parts[:-1])}/"
    return prefix


async def delete_model(
    kube_client: KubernetesClient,
    resource_name: str,
    namespace: str,
    minio_client: MinioClient,
    force: bool = False,
    session: AsyncSession | None = None,
) -> None:
    aim_model = await aims_gateway.get_aim_model(kube_client, namespace, resource_name)

    if aim_model is None:
        job = await _find_job_by_name(kube_client, namespace, resource_name)
        if job is None:
            # resource_name may be a workload UUID (from the dashboard) — look up by label
            job = await _find_job_by_label(kube_client, namespace, f"{WORKLOAD_ID_LABEL}={resource_name}")
        if job is None:
            raise NotFoundException(f"Model {resource_name} not found in namespace {namespace}")

        job_labels = job.metadata.labels or {}
        workload_id = job_labels.get(WORKLOAD_ID_LABEL)
        associated_model = (
            await aims_gateway.find_aim_model_by_label(kube_client, namespace, f"{WORKLOAD_ID_LABEL}={workload_id}")
            if workload_id
            else None
        )
        if associated_model:
            active_services = await aims_gateway.list_aim_services_for_model(
                kube_client, namespace, associated_model.metadata.name
            )
            if active_services:
                if not force:
                    raise DeletionConflictException(
                        f"Model {resource_name} has {len(active_services)} active deployment(s). Use force=true to delete anyway."
                    )
                for svc in active_services:
                    logger.warning(
                        f"Force-deleting AIMService {svc.metadata.name} — cluster-auth group cleanup skipped"
                    )
                    await aims_gateway.delete_aim_service(kube_client, namespace, UUID(svc.id))

        await kube_client.batch_v1.delete_namespaced_job(name=job.metadata.name, namespace=namespace)

        workload_uuid = parse_uuid(job_labels.get(WORKLOAD_ID_LABEL))
        if workload_uuid and session:
            await update_workload_status(session, workload_uuid, WorkloadStatus.DELETED, "system")

        if associated_model:
            await aims_gateway.delete_aim_model(kube_client, namespace, associated_model.metadata.name)
            for source in _iter_model_sources_for_cleanup(associated_model):
                if not source.source_uri:
                    continue
                prefix = _cleanup_prefix_for_source(source.source_uri)
                if not prefix:
                    logger.warning(
                        f"Cannot determine S3 prefix from {source.source_uri} for model {resource_name}, skipping."
                    )
                    continue
                try:
                    await delete_from_s3(prefix, minio_client, resource_name)
                    marker_key = prefix if prefix.endswith("/") else f"{prefix}/"
                    # Recursive prefix delete can leave a zero-byte "directory marker"
                    # object behind for this exact key in some stores.
                    await delete_object_from_s3(marker_key, minio_client, resource_name)
                except NotFoundException:
                    logger.warning(
                        f"Model weights not found in S3 for model {resource_name} ({source.source_uri}), skipping."
                    )
        return

    active_services = await aims_gateway.list_aim_services_for_model(kube_client, namespace, resource_name)
    if active_services:
        if not force:
            raise DeletionConflictException(
                f"Model {resource_name} has {len(active_services)} active deployment(s). Use force=true to delete anyway."
            )
        for svc in active_services:
            logger.warning(f"Force-deleting AIMService {svc.metadata.name} — cluster-auth group cleanup skipped")
            await aims_gateway.delete_aim_service(kube_client, namespace, UUID(svc.id))

    await aims_gateway.delete_aim_model(kube_client, namespace, resource_name)

    aim_model_labels = aim_model.metadata.labels or {}
    workload_id = parse_uuid(aim_model_labels.get(WORKLOAD_ID_LABEL))
    if workload_id and session:
        await update_workload_status(session, workload_id, WorkloadStatus.DELETED, "system")

    for source in _iter_model_sources_for_cleanup(aim_model):
        if not source.source_uri:
            continue
        prefix = _cleanup_prefix_for_source(source.source_uri)
        if not prefix:
            logger.warning(f"Cannot determine S3 prefix from {source.source_uri} for model {resource_name}, skipping.")
            continue
        try:
            await delete_from_s3(prefix, minio_client, resource_name)
            marker_key = prefix if prefix.endswith("/") else f"{prefix}/"
            # Recursive prefix delete can leave a zero-byte "directory marker"
            # object behind for this exact key in some stores.
            await delete_object_from_s3(marker_key, minio_client, resource_name)
        except NotFoundException:
            logger.warning(f"Model weights not found in S3 for model {resource_name} ({source.source_uri}), skipping.")


def _resolve_base_model_source(aim_model: AIMModelResource) -> AIMModelSource | None:
    """Return the AIMModelSource carrying the base model's weights, or None.

    The legacy flat ``spec.modelSources`` is populated for official and
    fine-tuning-published models. v1alpha2 imported / re-finetuned models instead
    carry their weights under ``spec.profiles.overrides.modelSources``. Prefer the
    flat field and fall back to the profiles override so a fine-tuned model can be
    used as the base for another round of fine-tuning.

    TODO: drop the legacy flat ``spec.modelSources`` branch once all
    models carry weights under ``spec.profiles.overrides.modelSources``.
    """
    if aim_model.spec.model_sources:
        return aim_model.spec.model_sources[0]
    if aim_model.spec.profiles and aim_model.spec.profiles.overrides.model_sources:
        return aim_model.spec.profiles.overrides.model_sources[0]
    return None


def _newest_first(cluster_models: list[AIMModelResource]) -> list[AIMModelResource]:
    """Order AIMClusterModels newest-registered first, breaking ties by name.

    Several versions of one aimId can be equally good picks, and the cluster list arrives
    unordered, so without an imposed order two identical requests can derive from
    different versions. Registration time is the only field on the resource that orders
    reliably — nothing on it carries a comparable version, and ranking the free-form OCI
    version label would mean inventing a comparison scheme — and the newest registration
    is the one an administrator most recently chose to make available. Sorting by name
    underneath is for determinism where registration times are absent or shared, not a
    preference between names.
    """
    by_name = sorted(cluster_models, key=lambda model: model.metadata.name)
    return sorted(by_name, key=_registered_at, reverse=True)


def _registered_at(cluster_model: AIMModelResource) -> datetime:
    """Registration time of an AIMClusterModel, oldest-possible when the API server omits it."""
    created = cluster_model.metadata.creation_timestamp
    if created is None:
        return datetime.min.replace(tzinfo=UTC)
    return created if created.tzinfo else created.replace(tzinfo=UTC)


@dataclass(frozen=True)
class BaseModelSelection:
    """The AIMClusterModel a fine-tuned model derives from, and the weights identity that goes with it.

    ``weights_model_id`` is the single value behind both halves of the manifest: it filters the
    chosen source's profiles down to those built from these weights, and it is stamped on the
    copies as their identity. They describe the same intent from two directions, so one field
    feeds both — a filter that copies profiles built from other weights while the stamp relabels
    them as these is not a state this type can express. Choosing the version here and deciding
    either half again at the manifest is what let the pair diverge.

    Empty means neither half is written, which only happens where no identity is stamped either:
    a run with no weights id at all, or an adapter run, whose manifest carries no ``modelId``.
    """

    cluster_model_name: str
    weights_model_id: str


def _select_base_cluster_model(
    cluster_models: list[AIMModelResource],
    *,
    recipe_aim_id: str,
    cluster_profiles: list[AIMProfileResource],
    weights_model_id: str,
    wants_adapter: bool,
    model_canonical_name: str,
) -> BaseModelSelection:
    """Return the AIMClusterModel the fine-tuned model derives its profiles from, and its filter.

    One aimId can be registered several times over — one AIMClusterModel per published
    version — and the cluster list arrives unordered, so position in it carries no
    meaning. The version publishing the weights this run trains on is the one whose
    profiles survive the chart's own filter, so that is the primary key; adapter
    capability narrows it further inside that set, on either arm. A run producing a model
    copies the source profiles into a new AIMModel, so an incapable source leaves it unable
    to serve adapters for good; a run producing an adapter derives nothing, but an adapter
    built against a version publishing no capable profile is accepted at deploy time and
    then never starts. The model arm falls back within the weights-matched set when no
    capable version publishes these weights; the adapter arm refuses.

    ``cluster_profiles`` carries whatever the cluster published, on every run: this is the
    only place a profile decides anything, so a caller that filtered them first would be
    choosing a source on evidence the manifest then contradicts. An empty list means the
    cluster published nothing, never that the caller declined to look, and that case falls
    through to the ranked order below on missing evidence rather than on policy.
    """
    # The gateway returns every profile matching the aimId whatever its status, and a
    # profile that is not Ready has not finished telling us what it is. Treat it as
    # evidence of nothing: counting one as capable would accept a version whose
    # capability never materialised — the very failure this selection exists to prevent —
    # while counting it as incapable would refuse a run that succeeds once it settles.
    # The listing endpoint in aims.service deliberately wants the unfiltered set, so the
    # filter belongs here rather than in the shared gateway function.
    settled_profiles = [profile for profile in cluster_profiles if profile.status.status == "Ready"]
    candidates = [
        model for model in cluster_models if model.status.status == "Ready" and model.status.aim_id == recipe_aim_id
    ]
    if not candidates:
        raise ValidationException(
            f"No Ready AIMClusterModel found for aimId '{recipe_aim_id}'. "
            "The model must be deployed on the cluster before fine-tuning."
        )

    # aim-engine stamps the producing model on every profile it discovers, and that label
    # is the only route from a profile back to the version that published it — the aimId
    # the profiles are filtered by is shared across all of them.
    published: dict[str, list[AIMProfileResource]] = {}
    adapter_capable: dict[str, list[AIMProfileResource]] = {}
    for profile in settled_profiles:
        source = profile.metadata.labels.get(AIM_PROFILE_SOURCE_MODEL_LABEL)
        if not source:
            continue
        published.setdefault(source, []).append(profile)
        if ADAPTER_PROFILE_FEATURE in profile.spec.features:
            adapter_capable.setdefault(source, []).append(profile)

    def _on_trained_weights(profiles: list[AIMProfileResource]) -> bool:
        return any(profile.spec.model_id == weights_model_id for profile in profiles)

    def _derive_from(cluster_model_name: str) -> BaseModelSelection:
        """Pair a chosen version with the weights identity the manifest filters and stamps by.

        Every return below goes through here so neither half can be decided a second time
        against a different version than the one actually chosen.
        """
        source_profiles = published.get(cluster_model_name, [])
        if not weights_model_id or not source_profiles or _on_trained_weights(source_profiles):
            return BaseModelSelection(cluster_model_name, weights_model_id)
        # The version publishes settled profiles and not one of them is built from the weights this
        # run trains on. That is evidence saying no, not the missing evidence the fallback below
        # was written for, and on the model arm it leaves nothing truthful to derive: every copy
        # is built from other weights, so keeping the filter copies no profile at all while
        # dropping it copies those variants and stamps them with weights they never served. An
        # adapter trained against that result is declared compatible with a profile that cannot
        # load it. Refuse while the caller can still choose a base that publishes these weights.
        if not wants_adapter:
            raise ValidationException(
                f"No published profile of base model '{model_canonical_name}' is built from weights "
                f"'{weights_model_id}'. Deriving a fine-tuned model from it would copy profiles built "
                "from other weights and declare them as these, so adapters trained on the result "
                "could not be deployed. Choose a base model version that publishes these weights."
            )
        # An adapter run stamps no identity of its own, so there is nothing here to mislabel:
        # dropping the filter copies what the version does publish, which is what this path did
        # before the filter existed. Capability, not weights, is what the warning below covers.
        logger.warning(
            f"No Ready profile of AIMClusterModel '{cluster_model_name}' is built from weights "
            f"'{weights_model_id}'; deriving without the weights filter so the adapter inherits "
            "the profiles this version does publish."
        )
        return BaseModelSelection(cluster_model_name, "")

    # Ordering belongs to the selection below and nowhere else. It exists so that versions the
    # published profiles cannot separate still resolve the same way every run — the fallback at
    # the end included, where no profile separates the survivors and the order the cluster
    # happened to list them in would otherwise be what decided.
    ranked = _newest_first(candidates)

    # The weights decide first, whatever the run produces: the chart copies only the source
    # profiles built from the weights this run trains on, so a version publishing none of them
    # leaves the derived model with nothing to derive. Capability then narrows that set on either
    # arm, and it matters most on the model arm: the model arm is the one that enables the model
    # manifest, so it is the only path that creates a derived AIMModel and copies profiles into
    # it. A derived model built from an incapable source can never serve an adapter, and no later
    # run can repair it — the profiles are copied once, at creation. An adapter run enables the
    # adapter manifest instead and disables the model manifest, so it derives nothing; capability
    # is checked there because the deploy gate matches it, not because profiles are inherited.
    chosen: AIMModelResource | None = None
    if weights_model_id:
        on_trained_weights = [model for model in ranked if _on_trained_weights(published.get(model.metadata.name, []))]
        # One profile has to carry both the capability and the trained weights. A version
        # satisfying them with two different profiles publishes nothing the derived model can
        # use: the chart copies only the profiles built from the weights this run trains on, so
        # the capable one is left behind and only the incapable copy survives.
        chosen = next(
            (
                model
                for model in on_trained_weights
                if _on_trained_weights(adapter_capable.get(model.metadata.name, []))
            ),
            None,
        )
        # Capability is a tiebreak inside the weights-matched pool and never a way out of it, so
        # the fallback stays within that pool rather than reaching for a capable version built
        # from other weights. Only the adapter arm declines to fall back here: it goes on to the
        # refusal below, because an adapter derived from an incapable version is accepted at
        # deploy time and then never starts.
        if chosen is None and not wants_adapter:
            chosen = next(iter(on_trained_weights), None)
    elif wants_adapter:
        # Nothing names the weights, so capability is the only evidence there is to rank on.
        chosen = next((model for model in ranked if adapter_capable.get(model.metadata.name)), None)
    if chosen is not None:
        return _derive_from(chosen.metadata.name)

    # No settled profile means the capability is unknown, not absent — aim-engine may simply
    # not have discovered them yet, and refusing on missing evidence would block fine-tuning
    # that works. Refuse only where the profiles exist and say the capability is not there.
    # A version whose profiles all exist but are none of them Ready lands here too, and
    # deliberately: an unsettled profile is missing evidence rather than negative evidence,
    # and the two outcomes are not symmetric — falling back logs a warning and may produce an
    # adapter that fails to deploy, whereas refusing hard-stops a run that would have worked
    # once the profile settled.
    capability_is_known = published.keys() & {model.metadata.name for model in candidates}
    if wants_adapter and capability_is_known:
        # Capability on a variant the run does not train on is not capability the run can use, so
        # the refusal names the weights when they are known rather than claiming the cluster
        # publishes no adapter-capable profiles at all.
        unusable_variants = " built from the weights this run trains on" if weights_model_id else ""
        raise ValidationException(
            f"No version of base model '{model_canonical_name}' on this cluster publishes "
            f"adapter-capable serving profiles{unusable_variants}, so an adapter trained against it "
            "could never be deployed. Ask an administrator to register a version that supports "
            "adapters, or request a model instead of an adapter."
        )

    # Which version this lands on is a decision about the whole set, not a property of
    # whichever one the API server listed first. _derive_from refuses when the version handed
    # to it publishes settled profiles and not one of them is built from these weights, so
    # picking a candidate by list position would put accept-versus-refuse in the gift of the
    # listing: a version publishing profiles for other weights only (evidence saying no) and
    # one publishing no profiles at all (no evidence yet) give opposite answers depending on
    # nothing but which came back first. The distinction between the two kinds of evidence is
    # worth keeping and is kept — what changes is that it is read across the set. Refuse only
    # when every remaining candidate contradicts the trained weights; while one that does not
    # is sitting in the set, derive from the newest of those instead.
    def _contradicts_trained_weights(cluster_model_name: str) -> bool:
        source_profiles = published.get(cluster_model_name, [])
        return bool(weights_model_id) and bool(source_profiles) and not _on_trained_weights(source_profiles)

    fallback = next(
        (model for model in ranked if not _contradicts_trained_weights(model.metadata.name)),
        ranked[0],
    )
    # The model arm reaches here without ever having asked for an adapter, so naming one reads
    # as a warning about something the run does not do. Both arms lose the same evidence — no
    # settled profile separates the versions — but only the adapter arm has a consequence to
    # warn about.
    consequence = (
        "Adapters attached to the result may fail to deploy."
        if wants_adapter
        else "Adapter capability of the result is unknown."
    )
    logger.warning(
        f"No AIMClusterModel for aimId '{recipe_aim_id}' publishes settled profiles to select on; "
        f"deriving from '{fallback.metadata.name}'. {consequence}"
    )
    return _derive_from(fallback.metadata.name)


async def _list_cluster_profiles_for_selection(
    kube_client: KubernetesClient,
    aim_ids: list[str],
) -> list[AIMProfileResource]:
    """Published profiles for the base-model selection, empty when the listing itself fails.

    The gateway raises on an API-server error, and every other caller wants that: the
    listing endpoint and the finetunable-models join would both report "nothing matched"
    for "could not look", which is a different answer. Only here is the empty list already
    a meaning the caller handles — ``_select_base_cluster_model`` reads missing profiles as
    missing evidence and falls back, precisely so that absent evidence does not block a run
    that works. Letting the error through would defeat that: a transient API-server blip
    would refuse the submission outright, which is the one outcome the fallback exists to
    avoid. So the degradation is applied here, at the one call site whose contract it fits,
    rather than in the shared gateway.
    """
    try:
        return await aims_gateway.list_aim_cluster_profiles_by_aim_ids(kube_client, aim_ids)
    except ExternalServiceError as e:
        logger.warning(
            f"Failed to list AIMClusterProfiles for aimIds {aim_ids}: {e}. Selecting a base model "
            "without profile evidence; the derived model may not serve adapters."
        )
        return []


async def _select_recipe_for_cluster(
    kube_client: KubernetesClient, overlays: list[Overlay], model_canonical_name: str
) -> tuple[Overlay | None, list[Overlay], list[str]]:
    """Choose the model's recipe for this cluster, the overlays layered over it, and the GPU device
    labels its job must run on.

    No recipe is returned when the chart ships none for the model, leaving the run to the chart and
    its generic overlays; the run is refused when every recipe it ships targets GPUs the cluster
    lacks. The labels are empty when the recipe declares no GPUs. Otherwise they are
    the cluster's own label values for the GPUs the recipe names: on a cluster with more than one
    GPU family, a job left unpinned could land on hardware its settings were not written for.
    """
    candidates = [overlay for overlay in overlays if overlay.canonical_name == model_canonical_name]
    if not candidates:
        return None, [], []

    labels_by_gpu_id: dict[str, set[str]] = {}
    if any(_declared_accelerators(overlay) is not None for overlay in candidates):
        for label in await get_cluster_gpu_device_info(kube_client):
            labels_by_gpu_id.setdefault(normalize_gpu_device_id(label), set()).add(label)
    recipe = select_recipe(candidates, model_canonical_name, labels_by_gpu_id.keys())
    if recipe is None:
        raise ValidationException(
            f"No fine-tuning recipe for base model '{model_canonical_name}' supports this cluster's GPUs."
        )
    supplements = select_supplemental_overlays(candidates, recipe, labels_by_gpu_id.keys())
    declared = _declared_accelerators(recipe)
    if declared is None:
        return recipe, supplements, []
    declared_ids = {normalize_gpu_device_id(acc_id) for acc_id in declared}
    return (
        recipe,
        supplements,
        sorted(label for gpu_id in declared_ids & labels_by_gpu_id.keys() for label in labels_by_gpu_id[gpu_id]),
    )


async def run_finetune_model_workload(
    session: AsyncSession,
    kube_client: KubernetesClient,
    model_id: UUID | str,
    finetuning_data: FinetuneCreate,
    submitter: str,
    namespace: str,
) -> FinetuneJobResponse:
    try:
        model_id = UUID(model_id) if isinstance(model_id, str) else model_id
    except ValueError:
        pass

    hf_token_secret_name = None
    if finetuning_data.hf_token_secret_name:
        hf_secret = await get_secret_details(
            namespace=namespace,
            secret_name=finetuning_data.hf_token_secret_name,
            kube_client=kube_client,
        )
        hf_token_secret_name = hf_secret.metadata.name

    is_finetuned_basemodel = isinstance(model_id, UUID)
    aim_model: AIMModelResource | None = None
    base_model_source: AIMModelSource | None = None

    # Resolve base model: AIMModel CR (UUID or resource name) or HuggingFace canonical name (str with /)
    base_model_uri: str
    if is_finetuned_basemodel:
        aim_model = await get_aim_model(kube_client, namespace, str(model_id))

        model_canonical_name = (
            aim_model.status.image_metadata.model.canonical_name or aim_model.status.aim_id or str(model_id)
        )
        # Weights live under the legacy flat field for official/fine-tuning models, but
        # imported/re-finetuned v1alpha2 models carry them under
        # spec.profiles.overrides.modelSources instead. Prefer the flat field and fall
        # back to the profiles override so a fine-tuned model can itself be re-finetuned.
        base_model_source = _resolve_base_model_source(aim_model)
        if base_model_source is None or not base_model_source.source_uri:
            raise ValidationException(
                f"Base model '{model_id}' has no weights URI. The model must be fully onboarded before finetuning."
            )
        base_model_uri = base_model_source.source_uri.removeprefix("s3://")
    else:
        model_canonical_name = str(model_id)
        base_model_uri = f"hf://{model_canonical_name}"

    chart = await get_chart(session, chart_name=FINETUNING_CHART_NAME)

    overlays = await list_overlays(
        session, chart_id=chart.id, canonical_name=model_canonical_name, include_generic=True
    )
    recipe, supplements, recipe_gpu_labels = await _select_recipe_for_cluster(
        kube_client, overlays, model_canonical_name
    )
    # The recipe layers over the generic overlays, so its model-specific settings win, and the
    # model's API-authored overlays layer over the recipe, since they adjust what it ships.
    overlay_values = [chart.signature] + [overlay.overlay for overlay in overlays if overlay.canonical_name is None]
    if recipe is not None:
        overlay_values += [recipe.overlay, *(supplement.overlay for supplement in supplements)]

    # Extract the aimId needed to resolve the correct AIMClusterModel to use as the
    # derivation source for the fine-tuned model. The AIMClusterModel name is passed as
    # modelRef.name in the derivedFrom selector — the aim-engine controller resolves it
    # via the aim.eai.amd.com/source-model label stamped on profiles. Prefer the recipe
    # overlay's aimManifest (the authoritative source for string-based / HF models). For
    # UUID-based re-finetunes the overlay may not carry it, so fall back to the base
    # AIMModel's status.aim_id.
    recipe_overlay: dict = recipe.overlay if recipe is not None and isinstance(recipe.overlay, dict) else {}

    # A re-finetune's own identity wins over the recipe's: the overlay is matched on canonical
    # name, which for a fine-tuned model resolves to the base it was derived from rather than the
    # model being trained. This value both selects the AIMClusterModel to derive profiles from and
    # is stamped on the output manifest, so the two cannot be allowed to disagree.
    aim_manifest_data = recipe_overlay.get("aimManifest")
    aim_manifest_data = aim_manifest_data if isinstance(aim_manifest_data, dict) else {}
    recipe_model_id: str | None = aim_manifest_data.get("modelId")
    base_aim_id = aim_model.status.aim_id if is_finetuned_basemodel and aim_model else None
    recipe_aim_id: str | None = base_aim_id or aim_manifest_data.get("aimId")
    if recipe_aim_id is None:
        raise ValidationException(
            "Cannot determine aimId for fine-tuning recipe. The recipe overlay must include "
            "aimManifest.aimId, or the base AIMModel must have a known aimId in its status."
        )

    # The weights this run trains on. It names both the source profiles the fine-tuned model may
    # copy and, on the model arm below, the identity stamped onto the copies. A UUID re-finetune
    # carries its own weights identity; otherwise the recipe's is the authority.
    # Empty rather than None is the absent case — AIMModelSource.model_id defaults to "".
    weights_model_id: str = (
        (base_model_source.model_id if is_finetuned_basemodel and base_model_source else "") or recipe_model_id or ""
    )

    # Only the settings actually named by the caller travel onward, so an empty `lora` object is
    # indistinguishable from omitting it — its presence carries no meaning of its own.
    supplied_lora = finetuning_data.lora.model_dump(exclude_none=True) if finetuning_data.lora is not None else {}
    peft_kwargs = {LORA_PEFT_KEYS[name]: value for name, value in supplied_lora.items()}

    # A full-parameter run trains every weight and produces no adapter, so neither an adapter
    # request nor LoRA settings can be honoured. Refuse before the job starts rather than
    # training for hours and silently discarding what was asked for.
    wants_adapter = finetuning_data.output is FineTuningOutput.ADAPTER
    # Anything not explicitly declared lora trains full-parameter, matching the chart default.
    # Read from every layer the job renders with, so an override switching the recipe to LoRA is
    # judged as the run it launches.
    training_type = _section(merge_helm_values(overlay_values), "metadata").get("trainingType")
    training_output = _get_training_output(
        wants_adapter=wants_adapter,
        training_type=training_type,
    )
    if training_type != TrainingType.LORA:
        if wants_adapter:
            raise ValidationException(
                f"Base model '{model_canonical_name}' trains full-parameter and cannot produce an adapter. "
                "Choose a base model whose training type is 'lora', or request a model instead."
            )
        if supplied_lora:
            named = ", ".join(f"lora.{name}" for name in sorted(supplied_lora))
            raise ValidationException(
                f"Base model '{model_canonical_name}' trains full-parameter, which has no LoRA settings. "
                f"Remove {named} from the request, or choose a base model whose training type is 'lora'."
            )

    dataset_ids = finetuning_data.dataset_ids
    if not dataset_ids:
        raise ValidationException("One or more datasetIds are required")
    found = {
        dataset.id: dataset
        for dataset in await list_datasets(session, namespace=namespace, selected_datasets_ids=dataset_ids)
    }
    if missing := [dataset_id for dataset_id in dataset_ids if dataset_id not in found]:
        raise NotFoundException(f"Dataset not found: {', '.join(str(dataset_id) for dataset_id in missing)}")
    datasets = [found[dataset_id] for dataset_id in dataset_ids]

    # TODO: enforce model name uniqueness (currently FE-only, no race protection)
    # Use a UUID as the S3 path segment so display names with spaces or special chars
    # don't produce invalid or colliding object keys.
    finetune_job_id = str(uuid4())
    finetuning_path = get_finetuned_model_weights_path(model_canonical_name, finetune_job_id, namespace)

    # Build the finetuning configuration. The paths are shared with recipe discovery, which reads
    # these same values back to advertise a recipe's defaults.
    peft_section, peft_key = PEFT_KWARGS_PATH
    finetuning_config: dict[str, dict] = {
        "data_conf": {
            "training_data": {"datasets": [{"path": os.path.join(MINIO_BUCKET, dataset.path)} for dataset in datasets]}
        },
    }

    # This is the last values layer Helm merges, so a key written here beats the recipe's own.
    # Leaving an unsupplied hyperparameter out is what lets the recipe's layer win; writing a
    # platform-chosen default would override every recipe with the same number.
    for (section, key), value in (
        (BATCH_SIZE_PATH, finetuning_data.batch_size),
        (LEARNING_RATE_PATH, finetuning_data.learning_rate),
        (EPOCHS_PATH, finetuning_data.epochs),
    ):
        if value is not None:
            finetuning_config.setdefault(section, {})[key] = value

    # Helm deep-merges maps, so a partial peft_kwargs keeps the recipe's target_modules — those are
    # architecture-specific and deliberately not platform-chosen. Writing the whole peft_conf would
    # wipe them.
    if peft_kwargs:
        finetuning_config[peft_section] = {peft_key: peft_kwargs}

    # Fan out MLflow lookup and AIMClusterModel resolution in parallel — both are
    # independent I/O calls. The AIMClusterModel lookup resolves which model the
    # fine-tuned AIMModel should derive its serving profiles from. modelRef.name
    # in the derivedFrom selector must be an AIMClusterModel name (not an
    # AIMClusterProfile name) — the aim-engine controller resolves it via the
    # aim.eai.amd.com/source-model label on profiles.
    # The published profiles are fetched on every run, with no condition deciding whether the
    # selection gets to see them. That unconditionality is the point: the manifest below emits the
    # weights filter for whatever version the selection returns, so a path that withheld the
    # profiles would choose a source without reference to the weights and then narrow it by them.
    # Where the first Ready version publishes only another variant, that filters the derived model
    # down to no profile at all and it cannot serve. One rule covers every path only while there is
    # nothing for a second condition here to disagree with. The call rides this gather, so a run
    # that ends up consulting no profile costs one extra listing and no extra wall-clock time.
    mlflow_workloads, cluster_models, cluster_profiles = await asyncio.gather(
        get_workloads(
            session=session,
            namespace=namespace,
            workload_types=[WorkloadType.WORKSPACE],
            status_filter=[WorkloadStatus.RUNNING],
            chart_name=MLFLOW_CHART_NAME,
        ),
        aims_gateway.list_aims(kube_client),
        _list_cluster_profiles_for_selection(kube_client, [recipe_aim_id]),
    )

    base_model_selection = _select_base_cluster_model(
        cluster_models,
        recipe_aim_id=recipe_aim_id,
        cluster_profiles=cluster_profiles,
        weights_model_id=weights_model_id,
        wants_adapter=wants_adapter,
        model_canonical_name=model_canonical_name,
    )

    mlflow_response = WorkloadResponse.model_validate(mlflow_workloads[0]) if mlflow_workloads else None
    if mlflow_response and mlflow_response.endpoints and mlflow_response.endpoints.get("internal"):
        mlflow_uri = mlflow_response.endpoints["internal"]
        if not mlflow_uri.startswith(("http://", "https://")):
            mlflow_uri = f"http://{mlflow_uri}"
        tracking_config = {
            "mlflow_server_uri": mlflow_uri,
            "experiment_name": finetuning_data.display_name,
        }
        training_args = finetuning_config.setdefault(TRAINING_ARGS_SECTION, {})
        training_args["report_to"] = ["mlflow"]
        training_args["logging_steps"] = 10
        finetuning_config["tracking"] = tracking_config
        logger.info(f"Found running MLflow workspace for namespace {namespace} - URI: {mlflow_uri}")
    else:
        logger.info(f"No running MLflow workspace found for namespace {namespace} - skipping MLflow tracking")

    helm_overrides: dict[str, Any] = {
        "bucketStorageHost": MINIO_URL,
        "checkpointsRemote": os.path.join(MINIO_BUCKET, finetuning_path),
        "basemodel": base_model_uri,
        "finetuning_config": finetuning_config,
    }

    if hf_token_secret_name:
        helm_overrides["hfTokenSecret"] = {"name": hf_token_secret_name, "key": "token"}

    workload = await create_workload(
        session=session,
        display_name=finetuning_data.display_name,
        workload_type=WorkloadType.FINE_TUNING,
        chart_id=chart.id,
        namespace=namespace,
        submitter=submitter,
        status=WorkloadStatus.PENDING,
        dataset_id=dataset_ids[0],
        dataset_refs=[{"id": str(dataset.id), "name": dataset.name} for dataset in datasets],
    )

    # WORKLOAD_TYPE_LABEL is the contract with fine_tuning.service._is_fine_tuning_model, which
    # backs GET /v1/projects/{project}/fine-tuning/models. Stamped here so it ends up on both
    # the AIMModel CR (via aim_manifest["labels"]) and the rest of the workload's resources
    # (via apply_manifest's extra_labels). Omitting it makes the resulting AIMModel invisible
    # to the Custom Models page.
    finetuning_labels = {
        MODEL_NAME_LABEL: sanitize_label_value(finetuning_data.display_name),
        WORKLOAD_TYPE_LABEL: WorkloadType.FINE_TUNING.value,
    }

    # Wire up the manifest-applier sidecar so it creates the CR after training. workload.name
    # becomes the CR name — it's unique and already used as the K8s resource name.
    # Sanitize every label at this boundary: the values flow through yaml.dump → Helm template
    # render → kubectl apply, and any non-str (StrEnum, UUID) gets serialized as a YAML sequence
    # and quoted into an invalid label like "[FINE_TUNING]". This mirrors apply_manifest's
    # per-label sanitize for the same reason.
    manifest_labels = {
        key: sanitize_label_value(str(value))
        for key, value in {**finetuning_labels, WORKLOAD_ID_LABEL: str(workload.id)}.items()
    }
    # On the adapter arm this is the display-name annotation's only route onto the CR — the
    # chart's own displayName value goes to the archived S3 manifest, which nothing reads back
    # for an engine-created CR. The model arm reads the display name from a label instead, so
    # the display-name annotation is inert there.
    #
    # The submitter annotation has no such asymmetry: the engine's own manifest never carries
    # it, so both arms need it stamped here — the same way onboarding already stamps it for
    # artifacts it creates directly (artifacts/service.py).
    manifest_annotations = {
        DISPLAY_NAME_ANNOTATION: finetuning_data.display_name,
        SUBMITTER_ANNOTATION: submitter,
    }
    if training_output is not None:
        manifest_annotations[TRAINING_OUTPUT_ANNOTATION] = training_output.value
    model_annotations = dict(manifest_annotations)
    if not wants_adapter and finetuning_data.description is not None:
        model_annotations[SOURCE_DESCRIPTION_ANNOTATION] = finetuning_data.description

    model_manifest: dict[str, Any] = {
        "enabled": not wants_adapter,
        "modelName": workload.name,
        "labels": manifest_labels,
        "annotations": model_annotations,
    }
    # The chart refuses to render a model manifest from a LoRA run whose merge is skipped, and a
    # recipe may switch the merge off, so the requested output decides it rather than the recipe:
    # merged into a model, or kept as a separate adapter. Full-parameter runs never merge.
    helm_overrides["mergeAdapter"] = not wants_adapter

    # Identity has to be stamped here rather than left to the recipe: the chart reads it under
    # `modelManifest`, while the recipe overlays still declare it one level up, where nothing
    # reads it. Relying on the Helm merge produces a render failure naming a value the caller
    # never supplied. A UUID re-finetune carries its own weights identity; otherwise the recipe's
    # is the authority. aimId and modelId stay separate — they coincide in every recipe today,
    # but they are distinct join keys.
    # Identity is only rendered when the model manifest is enabled, so an adapter run needs
    # neither field and must not be refused for lacking them.
    if not wants_adapter:
        if not weights_model_id:
            raise ValidationException(
                f"Cannot determine the model identity for base model '{model_canonical_name}'. "
                "Its fine-tuning recipe declares none, and the base model carries no weights "
                "source that does."
            )
        model_manifest["aimId"] = recipe_aim_id
        model_manifest["modelId"] = base_model_selection.weights_model_id

    # `scope: Auto` resolves namespace-first with a cluster fallback, which is what a
    # cluster-scoped base needs.
    #
    # The nested modelId is a *filter*, not the identity above: it narrows the source profiles
    # the chart copies to the ones built from the weights this run trains on, instead of every
    # variant the base model publishes. Unset, the copies include variants an adapter trained
    # here could never load.
    #
    # Both read the one value the selection settled on, so the filter deciding which profiles are
    # copied and the identity stamped onto the copies cannot name different weights: the selection
    # refuses rather than hand back a source whose profiles this identity would misdescribe.
    model_manifest["baseModel"] = {"name": base_model_selection.cluster_model_name, "scope": "Auto"}
    if base_model_selection.weights_model_id:
        model_manifest["baseModel"]["modelId"] = base_model_selection.weights_model_id

    adapter_manifest: dict[str, Any] = {"enabled": wants_adapter}
    if wants_adapter:
        adapter_annotations = dict(manifest_annotations)
        if finetuning_data.description is not None:
            adapter_annotations[DESCRIPTION_ANNOTATION] = finetuning_data.description
        adapter_manifest |= {
            "adapterName": workload.name,
            "organisation": ADAPTER_ORGANISATION,
            "labels": manifest_labels,
            "annotations": adapter_annotations,
            "displayName": finetuning_data.display_name,
        }
        if finetuning_data.description is not None:
            adapter_manifest["description"] = finetuning_data.description

        # The deploy gate attaches an adapter only when compatibleWith matches the base model's own
        # aimId, and compatibleWith renders from `model` below — so the two identities have to agree.
        # For a re-finetune they can diverge: `model` also selects the training base and drives
        # overlay matching, so it cannot be repointed to recipe_aim_id here without risking training
        # against the wrong weights; the real fix is to render the resolved AIM identity through its
        # own chart value instead of overloading `model`. Refuse rather than ship an adapter that
        # reports Ready but can never attach.
        if model_canonical_name != recipe_aim_id:
            raise ValidationException(
                f"Base model '{model_canonical_name}' resolves to aimId '{recipe_aim_id}', which "
                "differs from its own canonical name. The resulting adapter's compatibleWith would "
                "not match the base model's aimId and could never attach. Request a model instead of "
                "an adapter, or choose a base model whose recipe aimId matches its canonical name."
            )

        # compatibleWith renders solely from `model`, which only per-model recipe overlays set and
        # which — alone among the adapter inputs — carries no `required` guard, so an unset one
        # silently yields [""]: an adapter that reports Ready but can never attach. Setting it is a
        # no-op when a recipe matched — overlay canonical names are derived from this same value —
        # and supplies the base model's aimId when none did, which is what the deploy gate matches.
        helm_overrides["model"] = model_canonical_name

    helm_overrides["aimManifest"] = {
        "modelManifest": model_manifest,
        "adapterManifest": adapter_manifest,
    }

    logger.info(f"Deploying finetuning workload {workload.id} to namespace {namespace}")

    try:
        overlay_values.append(helm_overrides)

        manifest = await render_helm_template(
            chart=chart,
            name=workload.name,
            namespace=namespace,
            overlays_values=overlay_values,
        )
        if recipe_gpu_labels:
            manifest = pin_jobs_to_gpu_devices(manifest, recipe_gpu_labels)
        workload.manifest = manifest
        await session.flush()
        # Stamp the description onto the workload's own Job/Deployment so it is readable from
        # GET /projects/{project}/workloads/{id}, which sources annotations from that resource
        # rather than from the produced AIMModel/adapter CR.
        workload_annotations: dict[str, str] = {}
        if training_output is not None:
            workload_annotations[TRAINING_OUTPUT_ANNOTATION] = training_output.value
        if finetuning_data.description is not None:
            workload_annotations[DESCRIPTION_ANNOTATION] = finetuning_data.description
        await apply_manifest(
            kube_client,
            manifest,
            workload,
            namespace,
            submitter,
            extra_labels={**finetuning_labels, MODEL_ID_LABEL: str(workload.id)},
            extra_annotations=workload_annotations or None,
        )
        logger.info(f"Successfully deployed finetuning workload {workload.id}")

    except Exception as e:
        if isinstance(e, ValidationException):
            error_message = f"{e.message}: {e.detail}"
        else:
            error_message = str(e)

        logger.error(f"Failed to deploy finetuning workload {workload.id}: {error_message}")
        workload.status = WorkloadStatus.FAILED
        await session.flush()
        raise

    return FinetuneJobResponse(
        workload_id=workload.id,
        display_name=finetuning_data.display_name,
        base_model=model_canonical_name,
        namespace=namespace,
    )
