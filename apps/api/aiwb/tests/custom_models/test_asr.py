# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for speech-to-text detection and the ASR runtime preset.

Detection is table-driven off tag lists captured from the HuggingFace Hub for
the models in the STT support matrix, so the suite records which models the
platform actually recognises rather than which ones it is assumed to. That
includes the known gap: Voxtral-Mini-3B publishes nothing that identifies it as
a speech model, and the test pins that so widening the tag set cannot silently
change it.
"""

import importlib
import os
from typing import Any
from unittest.mock import patch

import pytest

from app.custom_models import constants
from app.custom_models.asr import (
    ASR_ENGINE_ARGS,
    apply_asr_preset,
    asr_engine_args,
    is_asr_source,
    is_audio_capable_base_image,
)
from app.custom_models.constants import AUDIO_CAPABLE_BASE_REPOSITORIES

# Built from the configured allowlist rather than a literal so the suite still
# means something when the audio base is repointed via the environment.
_AUDIO_BASE_REPOSITORY = min(AUDIO_CAPABLE_BASE_REPOSITORIES)
_AUDIO_IMAGE = f"amdenterpriseai/{_AUDIO_BASE_REPOSITORY}:1.0"
_CHAT_IMAGE = "amdenterpriseai/aim-base:0.13.1"

# Tags as the Hub returns them, trimmed to the entries that carry signal:
# the pipeline/architecture tags plus a couple of the language and housekeeping
# tags that surround them.
_HUB_TAGS: dict[str, list[str]] = {
    "openai/whisper-large-v3": [
        "transformers",
        "pytorch",
        "whisper",
        "automatic-speech-recognition",
        "audio",
        "hf-asr-leaderboard",
        "en",
    ],
    "openai/whisper-large-v3-turbo": [
        "transformers",
        "whisper",
        "automatic-speech-recognition",
        "audio",
        "en",
    ],
    "Qwen/Qwen3-ASR-1.7B": [
        "safetensors",
        "qwen3_asr",
        "automatic-speech-recognition",
        "region:us",
    ],
    "mistralai/Voxtral-Small-24B-2507": [
        "vllm",
        "voxtral",
        "audio-text-to-text",
        "en",
    ],
    "nvidia/parakeet-tdt-0.6b-v2": [
        "nemo",
        "FastConformer",
        "automatic-speech-recognition",
        "audio",
        "speech",
    ],
    "nvidia/canary-1b-flash": [
        "nemo",
        "automatic-speech-recognition",
        "automatic-speech-translation",
        "audio",
        "speech",
    ],
    # No pipeline tag and no audio tag; nothing here identifies it as speech.
    "mistralai/Voxtral-Mini-3B-2507": [
        "mistral-common",
        "safetensors",
        "voxtral",
        "vllm",
        "en",
    ],
}


# --- is_asr_source ---


@pytest.mark.parametrize(
    "repo_id",
    [
        "openai/whisper-large-v3",
        "openai/whisper-large-v3-turbo",
        "Qwen/Qwen3-ASR-1.7B",
        "mistralai/Voxtral-Small-24B-2507",
        "nvidia/parakeet-tdt-0.6b-v2",
        "nvidia/canary-1b-flash",
    ],
)
def test_matrix_speech_models_are_detected(repo_id: str) -> None:
    assert is_asr_source(_HUB_TAGS[repo_id]) is True


def test_voxtral_mini_is_not_detected() -> None:
    """Pins the known gap so the tag set cannot widen to cover it unnoticed.

    Voxtral-Mini-3B onboards as an ordinary model with no preset and no
    rejection; its engine args are the user's to set.
    """
    assert is_asr_source(_HUB_TAGS["mistralai/Voxtral-Mini-3B-2507"]) is False


@pytest.mark.parametrize("tag", ["speech-to-text", "transcription"])
def test_freeform_speech_tags_are_detected(tag: str) -> None:
    """No matrix model publishes these, but they are common enough Hub-wide to match for BYO sources."""
    assert is_asr_source(["safetensors", tag, "en"]) is True


def test_audio_tag_alone_does_not_qualify() -> None:
    """`audio` also covers text-to-speech, classification and music generation."""
    assert is_asr_source(["audio", "text-to-speech", "en"]) is False


def test_audio_transcription_tag_alone_does_not_qualify() -> None:
    """Only 3 models Hub-wide use it; `transcription` is the tag that carries the signal."""
    assert is_asr_source(["audio-transcription", "en"]) is False


@pytest.mark.parametrize("tags", [None, [], ["text-generation", "llama"]])
def test_non_speech_sources_are_not_detected(tags: list[str] | None) -> None:
    assert is_asr_source(tags) is False


def test_detection_normalizes_case_and_whitespace() -> None:
    assert is_asr_source(["  Automatic-Speech-Recognition "]) is True


# --- is_audio_capable_base_image ---


@pytest.mark.parametrize(
    "image_ref",
    [
        _AUDIO_IMAGE,
        f"registry.example.com:5000/amd/{_AUDIO_BASE_REPOSITORY}:2026.8",
        f"amdenterpriseai/{_AUDIO_BASE_REPOSITORY.upper()}:1.0",
        f"amdenterpriseai/{_AUDIO_BASE_REPOSITORY}@sha256:{'a' * 64}",
    ],
)
def test_audio_capable_base_matches_repository_name(image_ref: str) -> None:
    assert is_audio_capable_base_image(image_ref) is True


@pytest.mark.parametrize(
    "image_ref",
    [
        _CHAT_IMAGE,
        # "audio" in the registry path or the tag must not qualify the image.
        "audio.example.com/amd/aim-base:1.0",
        "amdenterpriseai/aim-base:audio-preview",
    ],
)
def test_non_audio_base_images_do_not_match(image_ref: str) -> None:
    assert is_audio_capable_base_image(image_ref) is False


@pytest.mark.parametrize("image_ref", [None, "", "not a valid ref"])
def test_unidentifiable_image_is_not_audio_capable(image_ref: str | None) -> None:
    """An image we cannot parse must not be assumed to carry the audio runtime."""
    assert is_audio_capable_base_image(image_ref) is False


# --- asr_engine_args ---


@pytest.mark.parametrize(
    ("precision", "expected_dtype"),
    [("fp16", "float16"), ("bf16", "bfloat16"), ("BF16", "bfloat16")],
)
def test_dtype_follows_precision(precision: str, expected_dtype: str) -> None:
    """The shipped Whisper profiles disagree — Radeon runs fp16, EPYC bf16."""
    assert asr_engine_args(precision)["dtype"] == expected_dtype


@pytest.mark.parametrize("precision", [None, "", "fp8"])
def test_unmapped_precision_leaves_dtype_to_vllm(precision: str | None) -> None:
    assert "dtype" not in asr_engine_args(precision)


def test_engine_args_carry_the_audio_limit_and_decoder_context() -> None:
    args = asr_engine_args("fp16")

    assert args["limit-mm-per-prompt"] == {"audio": 1}
    assert args["max-model-len"] == 448


def test_engine_args_do_not_alias_the_module_constant() -> None:
    """Nested values are copied, so one onboard cannot mutate the next one's preset."""
    args = asr_engine_args("fp16")
    args["limit-mm-per-prompt"]["audio"] = 99

    assert ASR_ENGINE_ARGS["limit-mm-per-prompt"] == {"audio": 1}


# --- apply_asr_preset ---


def test_preset_stamps_axes_and_engine_args_onto_empty_profile() -> None:
    result = apply_asr_preset(None, {"precision": "bf16", "metric": "latency", "type": "unoptimized"})

    assert result["precision"] == "bf16"
    assert result["metric"] == "latency"
    assert result["type"] == "unoptimized"
    assert result["engineArgs"]["dtype"] == "bfloat16"
    assert result["engineArgs"]["limit-mm-per-prompt"] == {"audio": 1}


def test_caller_axes_win_over_resolved_defaults() -> None:
    result = apply_asr_preset({"precision": "fp16"}, {"precision": "bf16", "metric": "latency"})

    assert result["precision"] == "fp16"
    assert result["metric"] == "latency"
    assert result["engineArgs"]["dtype"] == "float16"


def test_caller_engine_args_win_key_by_key() -> None:
    """A tuned value survives; the rest of the preset still lands alongside it."""
    result = apply_asr_preset({"engineArgs": {"max-model-len": 1024}}, {"precision": "fp16"})

    assert result["engineArgs"]["max-model-len"] == 1024
    assert result["engineArgs"]["limit-mm-per-prompt"] == {"audio": 1}
    assert result["engineArgs"]["dtype"] == "float16"


def test_absent_axis_default_is_not_stamped() -> None:
    """An axis the base profiles disagree on stays unset for the derived copy to fill."""
    result = apply_asr_preset(None, {"precision": "fp16", "metric": None})

    assert "metric" not in result


def test_non_dict_engine_args_are_left_for_admission_to_reject() -> None:
    result = apply_asr_preset({"engineArgs": "not-a-map"}, {})

    assert result["engineArgs"] == "not-a-map"


def test_preset_does_not_mutate_the_caller_profile() -> None:
    custom_profile: dict[str, Any] = {"engineArgs": {"max-model-len": 1024}}

    apply_asr_preset(custom_profile, {"precision": "fp16"})

    assert custom_profile == {"engineArgs": {"max-model-len": 1024}}


@pytest.mark.parametrize("override", ["", "   ", ",", " , "])
def test_allowlist_falls_back_when_the_override_parses_to_nothing(override: str) -> None:
    """An empty allowlist would disqualify every image, so speech onboarding would
    reject each model for lacking an audio runtime with nothing able to satisfy it.
    Falling back keeps a stray override from reading as a product bug."""
    with patch.dict(os.environ, {"AIM_AUDIO_CAPABLE_BASE_REPOSITORIES": override}):
        importlib.reload(constants)
        assert constants.AUDIO_CAPABLE_BASE_REPOSITORIES == frozenset({constants.DEFAULT_AUDIO_CAPABLE_BASE_REPOSITORY})

    importlib.reload(constants)


def test_allowlist_honors_a_populated_override() -> None:
    with patch.dict(os.environ, {"AIM_AUDIO_CAPABLE_BASE_REPOSITORIES": " Aim-Audio-Base , vendor-asr-base "}):
        importlib.reload(constants)
        assert constants.AUDIO_CAPABLE_BASE_REPOSITORIES == frozenset({"aim-audio-base", "vendor-asr-base"})

    importlib.reload(constants)
