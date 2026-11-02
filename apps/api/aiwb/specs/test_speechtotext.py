# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the SpeechToText Robot library: tag-based model selection and the
synthetic WAV upload fixture."""

import io
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

import SpeechToText


def _aim(name: str, tags: list[str] | None = None, labels: dict[str, str] | None = None) -> dict:
    """Build a catalog AIM entry shaped like GET /v1/inference/models."""
    return {
        "metadata": {"name": name, "labels": labels or {}},
        "status": {"imageMetadata": {"model": {"tags": tags or []}}},
    }


@pytest.mark.parametrize("tag", list(SpeechToText.TRANSCRIPTION_TAG_VALUES))
def test_selects_model_carrying_each_transcription_tag(tag):
    aims = [_aim("chat-model", tags=["chat"]), _aim("whisper", tags=[tag, "audio"])]
    assert SpeechToText.first_transcription_capable_aim_name(aims) == "whisper"


def test_returns_first_match_in_order():
    aims = [
        _aim("chat-model", tags=["chat"]),
        _aim("whisper-a", tags=["transcription"]),
        _aim("whisper-b", tags=["speech-to-text"]),
    ]
    assert SpeechToText.first_transcription_capable_aim_name(aims) == "whisper-a"


def test_returns_none_when_no_transcription_model():
    aims = [_aim("chat-model", tags=["chat"]), _aim("vision", tags=["image-text-to-text"])]
    assert SpeechToText.first_transcription_capable_aim_name(aims) is None


def test_ignores_tags_present_only_on_legacy_metadata_label():
    # Tags must come from status.imageMetadata.model.tags (the backend-matching field).
    # A model that only carries the old metadata label is deliberately not selected.
    aims = [_aim("legacy", tags=[], labels={"org.amd.silogen.model.tags": "transcription"})]
    assert SpeechToText.first_transcription_capable_aim_name(aims) is None


def test_tolerates_missing_or_malformed_status():
    aims = [{"metadata": {"name": "no-status"}}, {"metadata": {"name": "empty"}, "status": {}}]
    assert SpeechToText.first_transcription_capable_aim_name(aims) is None


def test_synthetic_audio_upload_is_a_valid_wav():
    files = SpeechToText.synthetic_audio_upload(seconds=0.5, sample_rate=16000)
    assert set(files) == {"file"}
    filename, payload, content_type = files["file"]
    assert filename == "audio.wav"
    assert content_type == "audio/wav"

    with wave.open(io.BytesIO(payload), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2  # 16-bit PCM
        assert wav.getframerate() == 16000
        assert wav.getnframes() == 8000  # 0.5s * 16 kHz
