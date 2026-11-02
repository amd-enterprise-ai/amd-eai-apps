# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Pure helpers for deriving a speech-to-text runtime profile at onboard time.

A speech model needs different runtime defaults than a chat model, and it only
transcribes at all on a base image whose vLLM build ships the audio runtime.
This module answers the two questions the onboard path asks — "is this source a
speech model" and "can the selected base image serve audio" — and composes the
runtime preset that makes the derived profile deployable.

Everything here is pure: detection reads the tags and image reference already on
the request, and the identity axes are resolved by the caller from the
namespace's base profiles and passed in.
"""

from copy import deepcopy
from typing import Any

from ..cluster.utils import parse_container_image_repository_and_tag
from .constants import AUDIO_CAPABLE_BASE_REPOSITORIES

# Source tags that mark a model as speech-to-text, verified against the
# HuggingFace Hub for every model in the STT support matrix:
#
#   automatic-speech-recognition  whisper-large-v3(-turbo), Qwen3-ASR-1.7B,
#                                 parakeet-tdt-0.6b-v2, canary-1b-flash
#   audio-text-to-text            Voxtral-Small-24B-2507
#
# The remaining two are freeform tags rather than pipeline tags, so no matrix
# model carries them, but they are common enough Hub-wide to be worth matching
# for other BYO sources:
#
#   speech-to-text                ~900 models; also the tag AMD publishes on the
#                                 Whisper AIM, so the S3 model-card path can
#                                 discover it
#   transcription                 ~315 models
#
# Deliberately excluded, do not add:
#   audio                         missing from Qwen3-ASR and both Voxtral
#                                 models, and Hub-wide it also covers
#                                 text-to-speech, audio classification and
#                                 music generation — neither necessary nor
#                                 sufficient
#   audio-transcription           3 models Hub-wide; too rare to be a signal
#   automatic-speech-translation  only canary-1b-flash, already matched above
#
# Known gap: Voxtral-Mini-3B-2507 carries no pipeline tag and no audio tag at
# all, so it cannot be detected from tags and onboards unchanged.
ASR_SOURCE_TAGS = frozenset(
    {
        "automatic-speech-recognition",
        "audio-text-to-text",
        "speech-to-text",
        "transcription",
    }
)

# Identity axes worth carrying over from the base profiles being derived from.
# Leaving one unset is safe — the derivation selector stays broad and each copy
# keeps its source profile's value — so these are only stamped when the base
# profiles agree. `precision` additionally decides the vLLM dtype below.
ASR_IDENTITY_AXES = ("precision", "metric", "type")

# Engine args that hold for any ASR model on any accelerator. The benchmarked
# Whisper profiles in aim-build disagree on everything else — the Radeon profile
# sets gpu-memory-utilization / tensor-parallel-size, the EPYC one sets
# max-num-batched-tokens — so those stay with the base profile being copied.
# `max-model-len` is Whisper's 448-token decoder context, a property of the
# architecture rather than the hardware.
ASR_ENGINE_ARGS: dict[str, Any] = {
    "limit-mm-per-prompt": {"audio": 1},
    "max-model-len": 448,
}

# vLLM `dtype` per precision axis. Derived rather than fixed because the two
# shipped Whisper profiles disagree: Radeon runs fp16/float16, EPYC bf16/bfloat16.
# An unmapped precision yields no `dtype` at all, leaving vLLM to auto-detect.
_PRECISION_DTYPES = {
    "fp16": "float16",
    "bf16": "bfloat16",
}


def is_asr_source(tags: list[str] | None) -> bool:
    """Return True when the source's catalog tags mark it as speech-to-text."""
    if not tags:
        return False
    return any(tag.strip().lower() in ASR_SOURCE_TAGS for tag in tags)


def is_audio_capable_base_image(image_ref: str | None) -> bool:
    """Return True when the base image's repository ships the ASR audio runtime.

    Unparseable references are not audio-capable: an image we cannot identify
    must not be assumed to carry librosa / soundfile / ffmpeg.
    """
    if not image_ref:
        return False
    try:
        repository, _ = parse_container_image_repository_and_tag(image_ref)
    except ValueError:
        return False
    return repository.rsplit("/", 1)[-1].strip().lower() in AUDIO_CAPABLE_BASE_REPOSITORIES


def asr_engine_args(precision: Any = None) -> dict[str, Any]:
    """Compose the ASR engine args, adding a `dtype` when the precision maps to one."""
    engine_args = deepcopy(ASR_ENGINE_ARGS)
    dtype = _PRECISION_DTYPES.get(str(precision).strip().lower()) if precision else None
    if dtype:
        engine_args["dtype"] = dtype
    return engine_args


def apply_asr_preset(
    custom_profile: dict[str, Any] | None,
    axis_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Overlay the caller's ``customProfile`` on top of the ASR runtime preset.

    Identity axes are filled from ``axis_defaults`` only where the caller left
    them unset, and engine args merge key-by-key with caller precedence, so an
    explicitly tuned value is never replaced. ``dtype`` follows whichever
    precision survives that merge.
    """
    merged: dict[str, Any] = dict(custom_profile) if custom_profile else {}

    for axis, value in (axis_defaults or {}).items():
        if value is not None:
            merged.setdefault(axis, value)

    preset_args = asr_engine_args(merged.get("precision"))
    caller_args = merged.get("engineArgs")
    if caller_args is None:
        merged["engineArgs"] = preset_args
    elif isinstance(caller_args, dict):
        merged["engineArgs"] = {**preset_args, **caller_args}
    # A non-dict engineArgs is left as the caller sent it; aim-engine rejects the
    # shape at admission, which is a clearer failure than a silent rewrite here.

    return merged
