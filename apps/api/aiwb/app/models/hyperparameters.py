# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Reading the hyperparameters a fine-tuning recipe declares, for discovery."""

import math
from collections.abc import Iterable, Mapping
from typing import Any

from .schemas import FinetuningHyperparameters, LoraHyperparameters, TrainingType

# Where each hyperparameter sits inside the chart's `finetuning_config`. Job submission writes
# these paths and recipe discovery reads them back, so they live in one place: a drift between the
# two would pre-fill a form from one knob and submit to another, and both sides would look right.
BATCH_SIZE_PATH = ("batchsize_conf", "total_train_batch_size")
# Named separately because job submission also writes MLflow tracking keys into this section, and
# both writers must agree on the spelling for the merge to land in one place rather than two.
TRAINING_ARGS_SECTION = "training_args"
EPOCHS_PATH = (TRAINING_ARGS_SECTION, "num_train_epochs")
LEARNING_RATE_PATH = ("overrides", "lr_multiplier")
PEFT_KWARGS_PATH = ("peft_conf", "peft_kwargs")

# Request field names deliberately differ from the peft library's kwargs. Keep the mapping in one
# place so refusals can name what the caller actually sent rather than the library's spelling.
LORA_PEFT_KEYS = {"rank": "r", "alpha": "lora_alpha", "dropout": "lora_dropout"}


def merge_helm_values(layers: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge Helm values layers, lowest precedence first, the way Helm merges `--values` files."""
    merged: dict[str, Any] = {}
    for layer in layers:
        merged = _deep_merge(merged, layer)
    return merged


def resolve_hyperparameters(values: Mapping[str, Any]) -> FinetuningHyperparameters:
    """Read the defaults a recipe trains with from its fully merged Helm values.

    The paths read here must stay aligned with the ones job submission writes, or a recipe's
    advertised default and the value a caller overrides end up describing different knobs. A value
    that cannot be read as a finite number is reported as null rather than guessed at: a wrong
    default silently trains the wrong job for hours.
    """
    config = values.get("finetuning_config")
    peft = _read(config, *PEFT_KWARGS_PATH)

    return FinetuningHyperparameters(
        batch_size=_as_int(_read(config, *BATCH_SIZE_PATH)),
        epochs=_as_int(_read(config, *EPOCHS_PATH)),
        learning_rate=_as_float(_read(config, *LEARNING_RATE_PATH)),
        # A full-parameter recipe has no LoRA settings at all, and submission refuses them, so
        # advertising any would offer controls the job would reject.
        lora=(
            LoraHyperparameters(
                rank=_as_int(_read(peft, LORA_PEFT_KEYS["rank"])),
                alpha=_as_int(_read(peft, LORA_PEFT_KEYS["alpha"])),
                dropout=_as_float(_read(peft, LORA_PEFT_KEYS["dropout"])),
            )
            if _read(values, "metadata", "trainingType") == TrainingType.LORA
            else None
        ),
    )


def _read(node: Any, *keys: str) -> Any:
    """Walk a nested mapping, yielding None as soon as the path leaves one."""
    for key in keys:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def _deep_merge(base: dict[str, Any], layer: Mapping[str, Any]) -> dict[str, Any]:
    """Merge one Helm values layer over another: maps merge key-by-key, everything else replaces.

    Lists, scalars and explicit nulls replace wholesale, including replacing a map, because that
    is what Helm does — reviving the lower layer's value for a key a recipe deliberately blanked
    would report a default the job never uses.
    """
    merged = dict(base)
    for key, value in layer.items():
        current = merged.get(key)
        merged[key] = _deep_merge(current, value) if isinstance(current, dict) and isinstance(value, Mapping) else value
    return merged


def _as_int(value: Any) -> int | None:
    """Read a chart value as an integer, or None when it is not one.

    Recipes commonly spell integral values as floats (`lora_alpha: 16.0`), so those convert; a
    genuinely fractional value does not, since truncating it would advertise a default the recipe
    never uses. `bool` is rejected explicitly because Python counts it as an `int`.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        return None
    return int(value)


def _as_float(value: Any) -> float | None:
    """Read a chart value as a float, or None when it is not one.

    An integer too large for a float raises rather than comparing, so the conversion is guarded:
    one recipe carrying an absurd number must not fail the listing for every other recipe.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None
