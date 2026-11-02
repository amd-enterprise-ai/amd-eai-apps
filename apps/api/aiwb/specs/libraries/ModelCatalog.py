# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Robot Framework library for selecting models from the finetunable catalog."""

import math
import re
from collections.abc import Iterator

import yaml

# Model families known to require a HuggingFace account or license acceptance.
# Used to deprioritize gated models in test selection so E2E tests run without
# an HF token secret assigned to the project, and to catch a catalog that
# advertises one of these families as needing no token.
_GATED_PREFIXES = (
    "meta-llama/",
    "google/gemma",
    "CohereLabs/",
)

# Model families that require HuggingFace approval / license acceptance before
# their weights can be downloaded. On clusters where the artifact download pod
# does not receive an HF token, deploying any of these fails at
# weight download with "Access denied. This repository requires approval".
# Used by get_smallest_deployable_aim to prefer genuinely open models.
_APPROVAL_GATED_PREFIXES = (
    "meta-llama/",
    "google/",
    "CohereLabs/",
    "mistralai/",
)


# The capability a serving profile declares when its runtime can load LoRA adapters.
_ADAPTER_FEATURE = "adapters"

# EPYC accelerator models the vLLM OTel collector is pinned to via nodeAffinity
# (helm/aiwb/templates/vllm-otel-collector.yaml). The CPU/EPYC metrics selector restricts
# to these because the collector never schedules onto a generic aim-accelerator.CPU node,
# so a model placed elsewhere would report no scraped metrics for the wrong reason. The
# selector owns this policy; CollectorAffinityGuard imports the constant and lints it
# against the chart, rather than defining its own copy.
COLLECTOR_SUPPORTED_EPYC_MODELS = frozenset(
    {
        "EPYC_ZEN4",
        "EPYC_ZEN5",
        "EPYC_9175F",
        "EPYC_9575F",
        "EPYC_9655",
        "EPYC_9755",
        "EPYC_9965",
    }
)


def _aim_requires_approval(aim_id: str) -> bool:
    return any(aim_id.startswith(prefix) for prefix in _APPROVAL_GATED_PREFIXES)


def _ready_open_aims(aims: list) -> Iterator[tuple[str, str]]:
    for aim in aims:
        status = aim.get("status", {})
        aim_id = status.get("aimId", "")
        resource_name = aim.get("metadata", {}).get("name")
        if status.get("status") == "Ready" and resource_name and not _aim_requires_approval(aim_id):
            yield aim_id, resource_name


def _newest_first_key(resource_name: str) -> tuple:
    """Sort key placing the newest published version of a model family first.

    A catalog commonly publishes the same aimId at several release versions, all
    identical on GPU count and parameter count. Ordering those by resource name
    picks an arbitrary one — and string order puts ``0-10-0`` ahead of ``0-9-0``,
    so the pick is usually a stale release nobody deploys by hand. Anything only
    E2E ever deploys is also the least-exercised path on the cluster.

    The version is the trailing ``<major>-<minor>-<patch>-<hash>`` of the
    AIMClusterModel name, which is how aim-engine derives the name from the image
    tag; the API does not surface ``status.version``. Names that do not carry a
    parseable version sort last so a recognised version always wins.
    """
    match = re.search(r"-(\d+)-(\d+)-(\d+)-[0-9a-z]+$", resource_name)
    if not match:
        return (1,)
    return (0, *(-int(part) for part in match.groups()))


def _auto_deployable_profiles(profiles: list) -> dict[str, tuple[int, str]]:
    """Map aimId to its smallest pin-able automatic profile's GPU count and name."""
    result: dict[str, tuple[int, str]] = {}
    for profile in profiles:
        spec = profile.get("spec", {})
        status = profile.get("status", {})
        if status.get("status") != "Ready" or (status.get("matchingNodes") or 0) < 1:
            continue
        if spec.get("manualSelectionOnly"):
            continue
        aim_id = spec.get("aimId")
        gpu_count = spec.get("acceleratorCount")
        profile_name = profile.get("metadata", {}).get("name")
        if not aim_id or not gpu_count or not profile_name:
            continue
        candidate = (gpu_count, profile_name)
        if aim_id not in result or candidate < result[aim_id]:
            result[aim_id] = candidate
    return result


def _auto_deployable_gpu_counts(profiles: list) -> dict[str, int]:
    """Map aimId to the smallest pin-able automatic profile's GPU count."""
    return {aim_id: gpu_count for aim_id, (gpu_count, _) in _auto_deployable_profiles(profiles).items()}


def get_model_resource_quota(gpu_count: int | str) -> tuple[int, int, int]:
    """Return GPU, CPU-millicore, and memory-byte quota for one or more model workloads."""
    if isinstance(gpu_count, str):
        try:
            gpu_count = int(gpu_count)
        except ValueError as error:
            raise ValueError(f"Model GPU count must be a positive integer, got {gpu_count!r}") from error
    if not isinstance(gpu_count, int) or isinstance(gpu_count, bool) or gpu_count < 1:
        raise ValueError(f"Model GPU count must be a positive integer, got {gpu_count!r}")
    return gpu_count, gpu_count * 4_000, gpu_count * 32 * 1024**3


def _param_count_billions(canonical_name: str) -> float:
    """Extract parameter count in billions from a model canonical name.

    Handles patterns like 1B, 3B, 8x7B (MoE — uses active params heuristic),
    27b, 32B. Returns 999 when no match is found so unknown models sort last.
    """
    # MoE pattern: NxMB → use N*M (total parameters) as the size proxy.
    # Total params matter for finetuning memory, not active params per token.
    moe = re.search(r"(\d+)x(\d+)[Bb]", canonical_name)
    if moe:
        return float(moe.group(1)) * float(moe.group(2))
    # Standard pattern: NB or Nb
    match = re.search(r"(\d+(?:\.\d+)?)[Bb](?:\b|-)", canonical_name)
    if match:
        return float(match.group(1))
    return 999.0


def _is_gated(canonical_name: str) -> bool:
    return any(canonical_name.startswith(prefix) for prefix in _GATED_PREFIXES)


def get_smallest_aim_for_runtime_profile_overrides(
    aims: list,
    profiles: list,
    accelerator_model: str,
    accelerator_count: int,
    precision: str,
) -> str:
    """Return the smallest open AIM compatible with deploy-time profile overrides.

    The deployment fixture supplies selector fields and then overrides the selected
    profile's accelerator count. A generic catalog choice is not sufficient: the
    chosen model must own a Ready profile whose selector matches on available
    hardware. Prefer profiles for the exact image, but accept an omitted profile
    image because that field is optional in the API contract.
    """
    if not aims:
        raise ValueError("No AIMs provided")

    compatible_profiles = {
        (spec.get("aimId"), spec.get("image"))
        for profile in profiles
        if (spec := profile.get("spec", {})).get("acceleratorModel") == accelerator_model
        and spec.get("acceleratorCount") == accelerator_count
        and spec.get("precision") == precision
        and not spec.get("manualSelectionOnly")
        and profile.get("status", {}).get("status") == "Ready"
        and (profile.get("status", {}).get("matchingNodes") or 0) >= 1
        and spec.get("aimId")
    }
    candidates = [
        (_param_count_billions(aim_id), resource_name)
        for aim in aims
        if (status := aim.get("status", {})).get("status") == "Ready"
        and (aim_id := status.get("aimId", ""))
        and not _aim_requires_approval(aim_id)
        and (resource_name := aim.get("metadata", {}).get("name"))
        and ((aim_id, aim.get("spec", {}).get("image")) in compatible_profiles or (aim_id, None) in compatible_profiles)
    ]
    if not candidates:
        raise ValueError(
            "No open, Ready AIM has a Ready, auto-selectable profile matching "
            f"{accelerator_model}/{accelerator_count}/{precision} on available hardware"
        )
    candidates.sort()
    return candidates[0][1]


def _deployable_candidates_in_order(aims: list, profiles: list) -> list[str]:
    """Resource names of the open, auto-deployable AIMs, best candidate first.

    Two orderings apply at different scopes, and keeping them separate is the point:

    * Within one aimId, the newest published release wins, so a model is represented
      by the version a user would actually deploy.
    * Across models, ordering is fewest GPUs, then smallest parameter count, then
      resource name. Version deliberately plays no part here — release numbers of
      different models are not comparable, and letting one leak into cross-model
      ordering means publishing a new release of an unrelated model silently
      reshuffles which models the dual-AIM scenario picks.

    Both the smallest and second-smallest selectors read this one order. Ranking
    twice invites the two from drifting apart, and when they disagree the
    second-smallest can name the model the smallest already returned — handing a
    dual-AIM test the same model for both slots.
    """
    auto_gpu = _auto_deployable_gpu_counts(profiles)
    if not auto_gpu:
        raise ValueError("No auto-selectable deployable profiles found in catalog")
    # One deploy candidate per logical model. A catalog commonly carries several
    # releases of one aimId; without this dedupe the first two entries are usually
    # version N and N-1 of the *same* model, so the dual-AIM auth scenario silently
    # deploys one model twice despite receiving two distinct resource names.
    best_by_aim_id: dict[str, str] = {}
    for aim_id, resource_name in _ready_open_aims(aims):
        if aim_id not in auto_gpu:
            continue
        incumbent = best_by_aim_id.get(aim_id)
        # Name breaks a version tie so the winner does not depend on catalog order.
        if incumbent is None or (_newest_first_key(resource_name), resource_name) < (
            _newest_first_key(incumbent),
            incumbent,
        ):
            best_by_aim_id[aim_id] = resource_name
    return [
        resource_name
        for _, _, resource_name in sorted(
            (auto_gpu[aim_id], _param_count_billions(aim_id), resource_name)
            for aim_id, resource_name in best_by_aim_id.items()
        )
    ]


def get_smallest_deployable_aim_with_profile(aims: list, profiles: list) -> tuple[str, str, int]:
    """Return resource name, exact profile name, and GPU count for the smallest AIM.

    Selection reads the one shared deduped order, so quota sizing pins the same
    release that ``get_smallest_deployable_aim`` deploys. Ranking the raw catalog
    instead would ignore the per-aimId dedupe and could size quota for an older
    release of the model actually deployed.
    """
    ordered = _deployable_candidates_in_order(aims, profiles)
    if not ordered:
        raise ValueError(
            "No open AIM with an auto-selectable deployable profile found "
            "(checked Ready models against Ready, matchingNodes>=1, "
            "manualSelectionOnly=False profiles for non-approval-gated families)"
        )
    resource_name = ordered[0]
    profile_name, gpu_count = get_deployable_aim_profile(aims, profiles, resource_name)
    return resource_name, profile_name, gpu_count


def get_smallest_deployable_aim_with_gpu_count(aims: list, profiles: list) -> tuple[str, int]:
    """Return the resource name and GPU count for the smallest AIM's pinned profile."""
    resource_name, _, gpu_count = get_smallest_deployable_aim_with_profile(aims, profiles)
    return resource_name, gpu_count


def _aim_id_for_resource_name(aims: list, resource_name: str) -> str:
    """Return the aimId of the catalog entry named resource_name, or raise if unknown."""
    target_aim_id = next(
        (
            aim.get("status", {}).get("aimId", "")
            for aim in aims
            if aim.get("metadata", {}).get("name") == resource_name
        ),
        None,
    )
    if not target_aim_id:
        raise ValueError(f"AIM resource {resource_name!r} not found in catalog")
    return target_aim_id


# Fallback GPU count for get_deployable_aim_profile_or_none when the pinned AIM's aimId has
# no profile of ANY kind (auto-selectable or not) to size from. Matches the largest model size
# referenced elsewhere in this catalog's fixtures (aiwb_ai_gateway.resource's DeepSeek-R1
# 8-GPU example) so an unplaceable override with no profile data at all still gets a quota that
# is not undersized against an unknown accelerator need. Actual profile data for the aimId --
# even a non-auto-selectable one -- is always preferred over this constant.
OVERRIDE_FALLBACK_GPU_COUNT = 8


def get_deployable_aim_profile(aims: list, profiles: list, resource_name: str) -> tuple[str, int]:
    """Return exact profile name and GPU count for one deployable AIM resource.

    An unknown resource_name is a caller error and is distinguished from a real catalog entry
    that merely has no auto-selectable profile, so ``get_deployable_aim_profile_or_none`` can
    tolerate the latter without swallowing the former.
    """
    target_aim_id = _aim_id_for_resource_name(aims, resource_name)
    auto_profiles = _auto_deployable_profiles(profiles)
    if target_aim_id not in auto_profiles:
        raise ValueError(
            f"AIM {resource_name!r} (aimId {target_aim_id!r}) has no auto-selectable "
            "deployable profile in the current catalog"
        )
    gpu_count, profile_name = auto_profiles[target_aim_id]
    return profile_name, gpu_count


def get_deployable_aim_gpu_count(aims: list, profiles: list, resource_name: str) -> int:
    """Return the GPU count for one deployable AIM resource's pinned profile."""
    _, gpu_count = get_deployable_aim_profile(aims, profiles, resource_name)
    return gpu_count


def get_deployable_aim_profile_or_none(
    aims: list, profiles: list, resource_name: str
) -> tuple[str, int] | tuple[None, int]:
    """Like get_deployable_aim_profile, but a (None, gpu_count) fallback instead of raising when
    resource_name is a real catalog entry with no auto-selectable profile.

    An AIM pinned via AIM_RESOURCE_OVERRIDE is documented to work on clusters where catalog
    profile provisioning is incomplete, so that specific condition must not be fatal here --
    callers fall back to deploying without a pinned profileName. The GPU count must still be a
    real number: a caller that sums this AIM's count into a combined-quota calculation (e.g. the
    dual-AIM fixture) cannot tolerate None there without crashing on int(None). Since no
    auto-selectable profile exists to cost, gpu_count is the LARGEST acceleratorCount declared by
    any profile for the AIM's aimId -- Ready or not, auto-selectable or not, since a cluster with
    incomplete provisioning may simply not have marked the right profile Ready yet -- falling
    back to OVERRIDE_FALLBACK_GPU_COUNT only when the aimId has no profile data at all, so the
    combined quota is never undersized against an override whose real need is unknown.

    A resource_name that isn't in the catalog at all is still a genuine caller error and
    continues to raise.
    """
    # Resolved directly rather than by catching get_deployable_aim_profile's ValueError and
    # matching its message: an unknown resource_name must still raise, and distinguishing the
    # two failures by error text would break silently the moment that wording changed.
    target_aim_id = _aim_id_for_resource_name(aims, resource_name)
    auto_profiles = _auto_deployable_profiles(profiles)
    if target_aim_id in auto_profiles:
        gpu_count, profile_name = auto_profiles[target_aim_id]
        return profile_name, gpu_count

    known_counts = [
        gpus
        for profile in profiles
        if profile.get("spec", {}).get("aimId") == target_aim_id
        and (gpus := profile.get("spec", {}).get("acceleratorCount"))
    ]
    gpu_count = max(known_counts) if known_counts else OVERRIDE_FALLBACK_GPU_COUNT
    return None, gpu_count


def get_profile_gpu_count(profiles: list, profile_name: str) -> int:
    """Return the GPU count of the profile named profile_name.

    Used to cost an AIM that is already deployed and running by its actual
    status.resolvedProfile.name, instead of by whatever the current catalog considers the
    smallest auto-selectable profile for that AIM's aimId -- the two can diverge if profile
    availability or ranking changed after the AIM was deployed.
    """
    for profile in profiles:
        if profile.get("metadata", {}).get("name") != profile_name:
            continue
        gpus = profile.get("spec", {}).get("acceleratorCount")
        if not gpus:
            raise ValueError(f"Profile {profile_name!r} has no acceleratorCount")
        return gpus
    raise ValueError(f"Profile {profile_name!r} not found in catalog")


def get_smallest_deployable_aim(aims: list, profiles: list) -> str:
    """Return the metadata.name of the smallest open, auto-deployable AIM.

    Used by inference E2E tests that need to deploy *some* AIM without caring which —
    the goal is the smallest blast radius (fewest GPUs, smallest params) on a model
    that a default deploy will actually bring up.

    Deployability is decided by the published profile catalog, not by the model's
    discoveredProfiles: a model is only auto-deployable at N GPUs if an
    AIMClusterProfile exists for its aimId that is Ready, has a matching node, and
    is NOT manualSelectionOnly (the automatic selector ignores manual-only profiles,
    so a default deploy of such a model fails with ProfileNotFound).

    Selection:
        - exclude models whose family requires HF approval (meta-llama/, google/,
          CohereLabs/, mistralai/) — their weights can't be downloaded on clusters
          where the artifact pod has no HF token
        - represent each aimId by its newest published release (a catalog carries
          several releases of one model)
        - order those distinct models by smallest auto-selectable GPU count, then
          parameter count, then resource name — version plays no part here, because
          releases of different models are not comparable

    ``aims`` and ``profiles`` are the ``data`` lists of GET /v1/inference/models and
    GET /v1/inference/profiles. Returns the winner's metadata.name.
    """
    resource_name, _ = get_smallest_deployable_aim_with_gpu_count(aims, profiles)
    return resource_name


def _smallest_profile_per_aim_id(
    profiles: list, *, adapter_capable: bool, must_be_schedulable: bool = True
) -> dict[str, tuple[int, str]]:
    """Map aimId -> (GPU count, profile name) of its smallest Ready profile that does or does not
    declare adapter support.

    Unlike _auto_deployable_gpu_counts this keeps manualSelectionOnly profiles: callers pin the
    returned name explicitly at deploy time instead of relying on the automatic selector.

    Callers whose request is expected to be refused before anything is created pass
    must_be_schedulable=False: demanding a matching node and real accelerators of hardware that is
    never stood up would narrow the pool for no gain, and an empty pool fails the whole scenario.
    """
    best: dict[str, tuple[int, str]] = {}
    for p in profiles:
        spec = p.get("spec", {})
        status = p.get("status", {})
        if status.get("status") != "Ready":
            continue
        if (_ADAPTER_FEATURE in (spec.get("features") or [])) is not adapter_capable:
            continue
        gpus = spec.get("acceleratorCount") or 0
        if must_be_schedulable and ((status.get("matchingNodes") or 0) < 1 or not gpus):
            continue
        aim_id = spec.get("aimId")
        profile_name = p.get("metadata", {}).get("name")
        if not aim_id or not profile_name:
            continue
        if aim_id not in best or gpus < best[aim_id][0]:
            best[aim_id] = (gpus, profile_name)
    return best


def _smallest_open_aim_with_profile(
    aims: list, best_by_aim_id: dict[str, tuple[int, str]]
) -> tuple[str, str, int] | None:
    """Pick the smallest open, Ready AIM that owns one of the given profiles, or None if none does.

    Same two-scope ordering as ``_deployable_candidates_in_order``: the newest release
    represents each aimId, then distinct models are ordered by GPU count, parameter
    count and resource name. Version must not reach the cross-model comparison —
    releases of different models are not comparable, so letting it in means a new
    release of an unrelated model changes which model this returns.
    """
    newest_by_aim_id: dict[str, str] = {}
    for aim_id, resource_name in _ready_open_aims(aims):
        if aim_id not in best_by_aim_id:
            continue
        incumbent = newest_by_aim_id.get(aim_id)
        # Name breaks a version tie so the winner does not depend on catalog order.
        if incumbent is None or (_newest_first_key(resource_name), resource_name) < (
            _newest_first_key(incumbent),
            incumbent,
        ):
            newest_by_aim_id[aim_id] = resource_name
    if not newest_by_aim_id:
        return None
    candidates = [
        (best_by_aim_id[aim_id][0], _param_count_billions(aim_id), resource_name, best_by_aim_id[aim_id][1])
        for aim_id, resource_name in newest_by_aim_id.items()
    ]
    gpus, _, resource_name, profile_name = min(candidates)
    return resource_name, profile_name, gpus


def get_smallest_adapter_capable_aim(aims: list, profiles: list) -> tuple[str, str]:
    """Return (metadata.name, profile name) for the smallest open AIM with a Ready profile that
    declares adapter support.

    Unlike get_smallest_deployable_aim, this does not require the profile to be auto-selectable:
    the caller pins the returned profile name explicitly at deploy time, so manualSelectionOnly
    profiles are fair game too -- only Ready, feature-declaring, schedulable profiles matter.
    """
    resource_name, profile_name, _ = get_smallest_adapter_capable_aim_with_gpu_count(aims, profiles)
    return resource_name, profile_name


def get_smallest_adapter_capable_aim_with_gpu_count(aims: list, profiles: list) -> tuple[str, str, int]:
    """Return resource name, profile name, and GPU count for the smallest adapter-capable AIM."""
    if not aims:
        raise ValueError("No AIMs provided")
    best_by_aim_id = _smallest_profile_per_aim_id(profiles, adapter_capable=True)
    if not best_by_aim_id:
        raise ValueError("No Ready, adapter-capable profile with a matching node found in catalog")
    selected = _smallest_open_aim_with_profile(aims, best_by_aim_id)
    if selected is None:
        raise ValueError(
            "No open, Ready AIM has a Ready, adapter-capable profile with a matching node "
            '(checked profiles declaring "adapters" in features)'
        )
    return selected


def get_smallest_aim_with_adapter_incapable_profile(aims: list, profiles: list) -> tuple[str, str]:
    """Return (metadata.name, profile name) for the smallest open AIM with a Ready profile that
    does NOT declare adapter support.

    The inverse of get_smallest_adapter_capable_aim, and the pairing matters: a caller pins the
    returned profile to prove a deploy asking for adapters is turned away before anything is
    created. Nothing is ever scheduled on it, so unlike the capable sibling -- whose caller
    actually stands the model up -- a matching node is not required.
    """
    if not aims:
        raise ValueError("No AIMs provided")
    best_by_aim_id = _smallest_profile_per_aim_id(profiles, adapter_capable=False, must_be_schedulable=False)
    if not best_by_aim_id:
        raise ValueError(
            'Every Ready profile in this catalog declares "adapters" in features, so no serving '
            "runtime here can be asked to refuse them. Publish a profile without the adapters "
            "feature, or the adapter capability refusal cannot be exercised on this cluster."
        )
    selected = _smallest_open_aim_with_profile(aims, best_by_aim_id)
    if selected is None:
        raise ValueError(
            "No open, Ready AIM has a Ready profile that lacks adapter support (profiles without "
            "the feature exist, but none belongs to a model these tests may use)"
        )
    resource_name, profile_name, _ = selected
    return resource_name, profile_name


def get_aim_with_only_unoptimized_profiles(aims: list, profiles: list) -> str:
    """Return a Ready AIM whose Ready profiles are all unoptimized."""
    if not aims:
        raise ValueError("No AIMs provided")

    for aim_id, resource_name in _ready_open_aims(aims):
        ready_profiles = [
            profile
            for profile in profiles
            if profile.get("status", {}).get("status") == "Ready" and profile.get("spec", {}).get("aimId") == aim_id
        ]
        if not ready_profiles:
            continue
        if any(p.get("spec", {}).get("type") == "optimized" for p in ready_profiles):
            continue
        return resource_name

    raise ValueError(
        "No Ready AIM with only non-optimized Ready profiles found in the catalog "
        "(needed to exercise the deploy wizard's unoptimized-profile warning)"
    )


def get_second_smallest_deployable_aim_with_profile(aims: list, profiles: list) -> tuple[str, str, int]:
    """Return resource name, exact profile name, and GPU count for the second-smallest AIM.

    Reads the shared deduped order, so the two dual-AIM slots are always different
    models rather than two releases of one model.
    """
    ordered = _deployable_candidates_in_order(aims, profiles)
    if len(ordered) < 2:
        raise ValueError(
            f"Need at least two open auto-deployable AIMs for dual-AIM regression tests; "
            f"found {len(ordered)}. Deploy a second distinct model on this cluster "
            "or reduce the profile quota requirements."
        )
    resource_name = ordered[1]
    profile_name, gpu_count = get_deployable_aim_profile(aims, profiles, resource_name)
    return resource_name, profile_name, gpu_count


def get_second_smallest_deployable_aim_with_gpu_count(aims: list, profiles: list) -> tuple[str, int]:
    """Return the resource name and GPU count of the second-smallest deployable AIM."""
    resource_name, _, gpu_count = get_second_smallest_deployable_aim_with_profile(aims, profiles)
    return resource_name, gpu_count


def get_second_smallest_deployable_aim(aims: list, profiles: list) -> str:
    """Return only the resource name of the second-smallest deployable AIM."""
    resource_name, _ = get_second_smallest_deployable_aim_with_gpu_count(aims, profiles)
    return resource_name


def assert_finetunable_models_report_gpu_compatibility(models: list) -> None:
    """Assert every finetunable model reports meaningful GPU hardware compatibility info.

    Each model must carry a canonical name, a positive required GPU count, and at least one
    compatible accelerator (both as IDs and human-readable names).
    """
    for model in models:
        canonical_name = model.get("canonicalName")
        if not canonical_name:
            raise AssertionError(f"Recipe is missing canonicalName: {model!r}")

        gpu_count = model.get("gpuCount")
        if gpu_count is None:
            raise AssertionError(f"Recipe {canonical_name} is missing required GPU count")
        if not gpu_count > 0:
            raise AssertionError(f"Recipe {canonical_name} reports a non-positive GPU count: {gpu_count}")

        if not model.get("compatibleAccelerators"):
            raise AssertionError(f"Recipe {canonical_name} has no compatible accelerator IDs")

        if not model.get("compatibleAcceleratorNames"):
            raise AssertionError(f"Recipe {canonical_name} has no compatible accelerator names")


def assert_finetunable_models_report_hf_token_gating(models: list) -> None:
    """Assert every finetunable model reports whether pulling its base weights needs a token.

    Gating is always a boolean: a recipe that declares nothing is reported as gated, so an absent
    or null value means a model reached the catalog with its gating undetermined. A model from a
    family known to be gated must never be reported as open — a user trusting that never supplies
    a token and the job fails on the weight pull.
    """
    for model in models:
        canonical_name = model.get("canonicalName")
        if "hfTokenRequired" not in model:
            raise AssertionError(f"Model {canonical_name} does not report Hugging Face token gating")

        hf_token_required = model["hfTokenRequired"]
        if not isinstance(hf_token_required, bool):
            raise AssertionError(
                f"Model {canonical_name} reports a non-boolean Hugging Face token requirement: {hf_token_required!r}"
            )

        if hf_token_required is False and _is_gated(canonical_name or ""):
            raise AssertionError(
                f"Model {canonical_name} belongs to a gated family but is reported as needing no Hugging Face token"
            )


def get_smallest_finetunable_model_with_gpu_count(models: list) -> tuple[str, int]:
    """Return the canonical name and required GPU count of the smallest finetunable model."""
    if not models:
        raise ValueError("No finetunable models provided")
    selected = min(
        models,
        key=lambda m: (
            _is_gated(m.get("canonicalName", "")),
            m.get("gpuCount", 999),
            _param_count_billions(m.get("canonicalName", "")),
        ),
    )
    canonical_name = selected.get("canonicalName")
    if not canonical_name:
        raise ValueError(f"Finetunable model entry is missing canonicalName: {selected!r}")
    gpu_count = selected.get("gpuCount")
    if not isinstance(gpu_count, int) or gpu_count < 1:
        raise ValueError(f"Finetunable model {canonical_name!r} has invalid gpuCount: {gpu_count!r}")
    return canonical_name, gpu_count


def get_finetunable_model_training_type(models: list, canonical_name: str) -> str:
    """Return the training type for a finetunable model selected by canonical name."""
    for model in models:
        if model.get("canonicalName") != canonical_name:
            continue
        training_type = model.get("trainingType")
        if training_type is None:
            raise ValueError(f"Model {canonical_name!r} is missing trainingType")
        return training_type
    raise ValueError(f"Model {canonical_name!r} not found in the finetunable catalog")


def get_smallest_finetunable_model(models: list) -> str:
    """Return the canonicalName of the smallest open finetunable model.

    Primary sort: open models before gated (meta-llama/, google/gemma require HF token).
    Secondary sort: gpuCount ascending (explicit GPU requirement).
    Tertiary sort: parameter count parsed from canonicalName (B suffix).

    This means the test always picks the smallest open model first, avoiding
    the need for a HuggingFace token secret assigned to the test project.

    Args:
        models: List of model dicts from GET /v1/finetunable response data.

    Returns:
        canonicalName of the smallest open model (or smallest gated if all are gated).

    Raises:
        ValueError: If models list is empty.
    """
    name, _ = get_smallest_finetunable_model_with_gpu_count(models)
    return name


# The only training types the fine-tuning chart understands. Anything else reaching the catalog
# means a recipe declared something the platform cannot act on.
_TRAINING_TYPES = ("lora", "full")


def assert_finetunable_models_report_training_type(models: list) -> None:
    """Assert every offered base model says how it trains.

    A user choosing a base model has to know before committing GPU time whether the run can leave
    a reusable adapter behind. A model that says nothing, or reports a value the platform cannot
    act on, leaves them to guess.
    """
    for model in models:
        canonical_name = model.get("canonicalName")
        training_type = model.get("trainingType")
        if training_type is None:
            raise AssertionError(
                f"Base model {canonical_name} does not say how it trains, "
                "so a user cannot tell whether it can produce an adapter"
            )
        if training_type not in _TRAINING_TYPES:
            raise AssertionError(
                f"Base model {canonical_name} reports an unrecognised training type: {training_type!r}"
            )


def get_full_training_base_model(models: list) -> str:
    """Return the canonicalName of a base model whose recipe trains every weight.

    Returns an empty string when the catalog offers none, so the caller can skip: without such a
    model the adapter refusal cannot be provoked at all.
    """
    for model in models:
        if model.get("trainingType") == "full" and model.get("canonicalName"):
            return model["canonicalName"]
    return ""


# The training settings every offered base model reports, each with the range a value has to fall in
# to be trainable.
_RECIPE_SETTINGS = (
    ("batchSize", "batch size", "positive"),
    ("epochs", "number of epochs", "positive"),
    ("learningRate", "learning rate multiplier", "positive"),
)

# Settings every offered recipe actually declares, so a blank one is the listing failing to read the
# recipe rather than the recipe staying silent. Batch size is deliberately not among them: no recipe
# offered today declares one, which also means its range check below is never reached in practice —
# it stands guard for a recipe that starts declaring one, not as coverage of anything shipped.
_ALWAYS_DECLARED = frozenset({"epochs", "learningRate"})

_LORA_SETTINGS = (
    ("rank", "LoRA rank", "positive"),
    ("alpha", "LoRA alpha", "positive"),
    ("dropout", "LoRA dropout", "probability"),
)

# What a started run publishes its training configuration under.
_TRAINING_CONFIG_KEY = "finetuning_config.yaml"

# Where the started run records each reported setting in the training configuration it was launched
# with. The two spellings differ, so a run can only be checked against what the user was shown by
# translating here — the one place the test knows both.
_TRAINED_SETTING_LOCATIONS = {
    "batchSize": ("batchsize_conf", "total_train_batch_size"),
    "epochs": ("training_args", "num_train_epochs"),
    "learningRate": ("overrides", "lr_multiplier"),
}


def _reported_settings(model: dict) -> dict:
    """Return one base model's reported training settings, failing when it reports none at all."""
    canonical_name = model.get("canonicalName")
    settings = model.get("hyperparameters")
    if not isinstance(settings, dict):
        raise AssertionError(
            f"Base model {canonical_name} reports no training settings, so a user setting up a run "
            "against it is shown blank fields instead of what the recipe already trains with"
        )
    return settings


def _assert_setting_is_usable(canonical_name: str | None, label: str, value: object, allowed: str) -> None:
    """Assert one reported setting is a number a run could actually train with.

    Callers decide whether a null setting is acceptable before reaching here.
    """
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise AssertionError(f"Base model {canonical_name} reports a {label} that is not a number: {value!r}")
    if allowed == "positive" and value <= 0:
        raise AssertionError(f"Base model {canonical_name} reports a {label} of {value}, which no run can train with")
    if allowed == "probability" and not 0 <= value < 1:
        raise AssertionError(f"Base model {canonical_name} reports a {label} of {value}, which is not a probability")


def models_that_train_with_lora(models: list) -> list:
    """Return the offered base models whose recipe trains with LoRA."""
    return [model for model in models if model.get("trainingType") == "lora"]


def models_that_train_full_parameter(models: list) -> list:
    """Return the offered base models whose recipe trains every weight."""
    return [model for model in models if model.get("trainingType") == "full"]


def assert_models_report_recipe_settings(models: list) -> None:
    """Assert every offered base model reports the training settings its own recipe defines.

    The epoch count and learning-rate multiplier every recipe declares must come back as numbers a
    run can train with; reporting them as null would show the user a blank field where the recipe
    has a value. A setting no recipe declares may be null — a stand-in there would be presented as
    the recipe's own and silently trained on for hours — but if reported it must still be usable.
    """
    for model in models:
        canonical_name = model.get("canonicalName")
        settings = _reported_settings(model)
        for field, label, allowed in _RECIPE_SETTINGS:
            if field not in settings:
                raise AssertionError(f"Base model {canonical_name} does not report a {label} either way")
            value = settings[field]
            if value is None:
                if field in _ALWAYS_DECLARED:
                    raise AssertionError(
                        f"Base model {canonical_name} reports no {label}, leaving a user setting up a run "
                        "against it with a blank field where its recipe has a value"
                    )
                continue
            _assert_setting_is_usable(canonical_name, label, value, allowed)
        if "lora" not in settings:
            raise AssertionError(f"Base model {canonical_name} does not say whether it has LoRA settings to offer")


def assert_lora_models_report_lora_settings(models: list) -> None:
    """Assert every base model that trains with LoRA offers the LoRA settings its recipe declares.

    A LoRA recipe declares rank, alpha and dropout together, so each one has to come back. Blanking
    any of them leaves the user inventing a value for a control the run is going to use either way.
    """
    for model in models_that_train_with_lora(models):
        canonical_name = model.get("canonicalName")
        lora = _reported_settings(model).get("lora")
        if not isinstance(lora, dict):
            raise AssertionError(
                f"Base model {canonical_name} trains with LoRA but offers no LoRA settings, "
                "leaving the user to invent them"
            )
        for field, label, allowed in _LORA_SETTINGS:
            value = lora.get(field)
            if value is None:
                raise AssertionError(
                    f"Base model {canonical_name} trains with LoRA but reports no {label}, leaving the user "
                    "to invent one for a run that will train with it"
                )
            _assert_setting_is_usable(canonical_name, label, value, allowed)


def assert_full_parameter_models_report_no_lora_settings(models: list) -> None:
    """Assert no base model that trains every weight offers LoRA settings.

    Such a run has no LoRA to tune and a submission tuning it is refused, so any LoRA setting shown
    against one of these models is a control the user cannot use.
    """
    for model in models_that_train_full_parameter(models):
        canonical_name = model.get("canonicalName")
        lora = _reported_settings(model).get("lora")
        if lora is not None:
            raise AssertionError(
                f"Base model {canonical_name} trains every weight, so it has no LoRA to tune, "
                f"yet it offers LoRA settings: {lora!r}"
            )


def job_settings_from_reported_settings(models: list, canonical_name: str) -> dict:
    """Return one base model's reported settings as fine-tuning job submission fields.

    Only the settings the recipe actually defines are carried over. Submitting a null one as an
    explicit null asks for something the recipe never said, which would test the wrong thing: the
    point of the round trip is that the numbers a user is shown are numbers they can submit.
    """
    for model in models:
        if model.get("canonicalName") != canonical_name:
            continue
        settings = _reported_settings(model)
        submission = {field: settings[field] for field, _, _ in _RECIPE_SETTINGS if settings.get(field) is not None}
        lora = settings.get("lora")
        if isinstance(lora, dict):
            declared = {field: lora[field] for field, _, _ in _LORA_SETTINGS if lora.get(field) is not None}
            if declared:
                submission["lora"] = declared
        return submission
    raise ValueError(f"Base model {canonical_name!r} is not offered in the finetunable catalog")


def _same_number(reported: object, trained: object) -> bool:
    """Compare a reported setting with the trained one, tolerating YAML/JSON float rounding."""
    if isinstance(reported, bool) or isinstance(trained, bool):
        return reported is trained
    if not isinstance(reported, int | float) or not isinstance(trained, int | float):
        return reported == trained
    return math.isclose(reported, trained, rel_tol=1e-9)


def training_configuration_of_run(published: list) -> str:
    """Return the training configuration a started run reads at startup, from what it published.

    Raises rather than returns nothing when it is absent, so a caller polling for it keeps waiting
    instead of asserting against an empty configuration.
    """
    for item in published:
        configuration = (item.get("data") or {}).get(_TRAINING_CONFIG_KEY)
        if configuration and configuration.strip():
            return configuration
    raise AssertionError(
        f"The fine-tuning run has published no {_TRAINING_CONFIG_KEY} yet, so there is nothing to check it against"
    )


def trained_settings_should_match_reported_settings(training_config: str, reported_settings: dict) -> None:
    """Assert a started run trains with the settings its base model reports.

    Only settings the base model actually reports are checked: a blank one is a value the recipe
    never stated, so there is nothing for the run to have honoured. The run's own configuration is
    the only place the effective values are visible — the API deliberately does not return them.
    """
    try:
        effective = yaml.safe_load(training_config)
    except yaml.YAMLError as error:
        raise AssertionError(f"The started run's training configuration is not valid YAML: {error}")
    if not isinstance(effective, dict):
        raise AssertionError(f"The started run's training configuration is not a mapping: {effective!r}")

    checked = 0
    for field, (section, key) in _TRAINED_SETTING_LOCATIONS.items():
        expected = reported_settings.get(field)
        if expected is None:
            continue
        actual = (effective.get(section) or {}).get(key)
        if not _same_number(expected, actual):
            raise AssertionError(
                f"The base model reports {field} {expected!r}, but the run it started trains with {actual!r}"
            )
        checked += 1
    if not checked:
        raise AssertionError(
            "The base model reports none of its training settings, so the run it started could not be "
            "checked against anything it advertises"
        )


def assert_no_adapter_attributable_to_workload(adapters: list, workload_id: str) -> None:
    """Assert no adapter in the project was left behind by the given fine-tuning run.

    Attribution is by the workload-id label the run stamps on everything it creates.
    """
    for adapter in adapters:
        labels = adapter.get("artifact", {}).get("metadata", {}).get("labels", {})
        if labels.get("airm.silogen.ai/workload-id") == workload_id:
            raise AssertionError(
                f"Fine-tuning run {workload_id} left an adapter behind although none was asked for: "
                f"{adapter.get('artifact', {}).get('metadata', {}).get('name')}"
            )


def _cpu_profiles_by_aim(profiles: list) -> dict[str, tuple[int, str, str]]:
    """Map aimId -> (acceleratorCount, profileName, acceleratorModel) per AIM.

    Restricted to profiles whose acceleratorType is "cpu" AND whose acceleratorModel is one of the
    EPYC labels the collector is pinned to (COLLECTOR_SUPPORTED_EPYC_MODELS). The collector never
    schedules onto generic ``aim-accelerator.CPU`` or unknown EPYC nodes, so accepting either would
    place the AIM on hardware the collector does not cover, making the metrics regression pass or
    fail for the wrong reason. manualSelectionOnly profiles ARE eligible: the caller pins the
    returned profileName at deploy time. A profile is NOT rejected on a falsy acceleratorCount — a
    CPU profile's count is a core count, not a GPU footprint.
    """
    result: dict[str, tuple[int, str, str]] = {}
    for p in profiles:
        spec = p.get("spec", {})
        status = p.get("status", {})
        if status.get("status") != "Ready" or (status.get("matchingNodes") or 0) < 1:
            continue
        if spec.get("acceleratorType") != "cpu":
            continue
        accelerator_model = (spec.get("acceleratorModel") or "").upper()
        if accelerator_model not in COLLECTOR_SUPPORTED_EPYC_MODELS:
            continue
        aim_id = spec.get("aimId")
        profile_name = p.get("metadata", {}).get("name")
        if not aim_id or not profile_name:
            continue
        count = spec.get("acceleratorCount") or 0
        if aim_id not in result or count < result[aim_id][0]:
            result[aim_id] = (count, profile_name, accelerator_model)
    return result


def get_smallest_cpu_servable_aim(aims: list, profiles: list, allow_gated: bool = False) -> tuple[str, str, str]:
    """Return (metadata.name, profileName, acceleratorModel) for a CPU/EPYC profile.

    The returned profileName MUST be pinned in the deploy request: selecting a CPU model is not
    enough, because a model that also publishes a GPU profile would otherwise have the engine
    auto-resolve the GPU profile. Selection is constrained to spec.acceleratorType == "cpu"
    profiles; manualSelectionOnly ones are eligible precisely because the caller pins them. Set
    ``allow_gated`` only when the project has an HF token: a CPU cluster's only servable model may
    belong to an HF-approval-gated family (e.g. meta-llama or gemma on an EPYC profile).
    """
    if not aims:
        raise ValueError("No AIMs provided")
    cpu_profiles = _cpu_profiles_by_aim(profiles)
    if not cpu_profiles:
        raise ValueError("No collector-supported EPYC profile (acceleratorType=cpu) found")
    candidates = []
    for aim in aims:
        status = aim.get("status", {})
        aim_id = status.get("aimId", "")
        resource_name = aim.get("metadata", {}).get("name")
        if status.get("status") != "Ready" or not resource_name:
            continue
        if not allow_gated and _aim_requires_approval(aim_id):
            continue
        if aim_id not in cpu_profiles:
            continue
        count, profile_name, accelerator_model = cpu_profiles[aim_id]
        # Sort by model size first: a CPU profile's acceleratorCount is a core count, not a
        # deployment footprint, so the smallest model (not the fewest cores) is the lightest AIM.
        candidates.append((_param_count_billions(aim_id), count, resource_name, profile_name, accelerator_model))
    if not candidates:
        gate_note = "" if allow_gated else " for non-approval-gated families"
        raise ValueError(f"No AIM with a CPU profile found (Ready, matchingNodes>=1, acceleratorType=cpu{gate_note})")
    candidates.sort()
    return candidates[0][2], candidates[0][3], candidates[0][4]
