# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Robot Framework library for picking fine-tuning recipes by serving capability."""

# The capability a serving profile declares when its runtime can load a LoRA adapter.
# A profile that omits it can serve the base weights but can never mount an adapter,
# so an adapter trained against that base model has nowhere to be deployed.
_ADAPTER_FEATURE = "adapters"

# Only a Ready profile describes a configuration the cluster can actually serve today.
_READY = "Ready"


def _adapter_capable_aim_ids(cluster_profiles):
    """Collect the aimIds this cluster can actually mount an adapter onto.

    Both halves of the test matter: a Pending or Degraded profile describes serving the
    cluster cannot currently do, and a Ready profile without the feature describes a
    runtime that will refuse the adapter. Ids are casefolded so a catalog that differs
    only in the casing of a Hugging Face repository id still joins.
    """
    aim_ids = set()
    for profile in cluster_profiles or []:
        spec = profile.get("spec", {})
        status = profile.get("status", {})
        if status.get("status") != _READY:
            continue
        if _ADAPTER_FEATURE not in (spec.get("features") or []):
            continue
        aim_id = spec.get("aimId")
        if aim_id:
            aim_ids.add(aim_id.casefold())
    return aim_ids


def _published_aim_ids(cluster_profiles):
    """Collect the aimIds this cluster publishes any profile for, whatever it says.

    Status and features are deliberately not filtered here: this set answers "has the
    catalog said anything at all about this base model", which is a different question
    from whether what it said permits an adapter. Ids are casefolded to join the same
    way as elsewhere.
    """
    aim_ids = set()
    for profile in cluster_profiles or []:
        aim_id = profile.get("spec", {}).get("aimId")
        if aim_id:
            aim_ids.add(aim_id.casefold())
    return aim_ids


def _first_non_gated_lora_recipe(finetunable_models, cluster_profiles, want_adapter_support):
    """Return the canonicalName of the first LoRA recipe on the wanted side of the split.

    Gated recipes are excluded either way. The wizard disables its Next button on the model
    step until a gated model has a Hugging Face token selected, so a gated pick could never
    reach the training-settings step where the output options are shown.

    The negative side requires a published profile as well as the absence of an
    adapter-capable one. The wizard reads an empty profile listing as unknown rather than
    as a refusal and leaves the option offered, so a base model the catalog is silent about
    provokes none of the behaviour the negative scenario exists to observe: it would wait
    on an option that never becomes unavailable. Only a published "no" withdraws it, and
    only such a base model is a valid pick.
    """
    capable_aim_ids = _adapter_capable_aim_ids(cluster_profiles)
    published_aim_ids = _published_aim_ids(cluster_profiles)
    for model in finetunable_models or []:
        if model.get("trainingType") != "lora":
            continue
        if model.get("hfTokenRequired") is not False:
            continue
        canonical_name = model.get("canonicalName")
        if not canonical_name:
            continue
        aim_id = canonical_name.casefold()
        if want_adapter_support:
            if aim_id in capable_aim_ids:
                return canonical_name
        elif aim_id in published_aim_ids and aim_id not in capable_aim_ids:
            return canonical_name
    return ""


class FinetuneRecipeSelector:
    """Keyword library for selecting fine-tuning recipes by serving capability."""

    @staticmethod
    def find_lora_recipe_with_adapter_support(finetunable_models, cluster_profiles):
        """Return the canonicalName of a LoRA recipe whose base model can serve adapters.

        The positive counterpart of ``find_lora_recipe_without_adapter_support``, and the
        only safe pick for a scenario that goes on to choose LoRA output: taking the
        alphabetically first LoRA recipe instead would silently land on a base model whose
        adapters cannot be served, where the wizard now withholds the option and the
        scenario would wait for a radio that never becomes selectable.

        Takes the same two listings, joined the same way. Namespace-scoped profiles must
        not be passed in — see ``find_lora_recipe_without_adapter_support``.

        Returns:
            The canonicalName of the first matching recipe, or "" when no LoRA-capable base
            model on this cluster can serve adapters — letting the caller skip rather than
            fail, since there is then nothing here to exercise.
        """
        return _first_non_gated_lora_recipe(
            finetunable_models,
            cluster_profiles,
            want_adapter_support=True,
        )

    @staticmethod
    def find_lora_recipe_without_adapter_support(finetunable_models, cluster_profiles):
        """Return the canonicalName of a LoRA recipe whose base model cannot serve adapters.

        Args:
            finetunable_models: the ``data`` list of GET /v1/fine-tuning/models — recipe
                entries carrying ``canonicalName``, ``trainingType`` and ``hfTokenRequired``.
            cluster_profiles: the ``data`` list of GET /v1/inference/profiles, i.e.
                CLUSTER-scoped AIMClusterProfile resources. Namespace-scoped profiles must
                not be passed in: they currently publish an empty ``spec.features`` for
                unrelated engine-side reasons, so every base model would look
                adapter-incapable and the scenario would assert on a false positive.

        A base model counts as adapter-capable when at least one cluster profile for its
        aimId is Ready *and* declares ``adapters`` in ``spec.features``.

        The recipe list is joined to the profile list on ``canonicalName`` == ``spec.aimId``.
        These are separate fields — the recipe overlay's ``canonicalName`` and its
        ``aimManifest.aimId`` — that mirror each other in every published overlay; the
        fine-tuning listing does not expose the aimId, so this is the only join available to
        a caller. Comparison is case-insensitive so a catalog that differs only in the casing
        of a Hugging Face repository id still joins.

        Returns:
            The canonicalName of the first matching recipe, or "" when no LoRA-capable base
            model on this cluster publishes a profile that withholds adapter serving — letting
            the caller skip rather than fail, since the restriction cannot be provoked at all
            on such a cluster. A base model with no published profile at all does not count:
            the wizard treats catalog silence as unknown and keeps the option offered.
        """
        return _first_non_gated_lora_recipe(
            finetunable_models,
            cluster_profiles,
            want_adapter_support=False,
        )
