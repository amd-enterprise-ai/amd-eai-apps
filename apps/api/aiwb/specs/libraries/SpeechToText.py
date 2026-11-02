# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Python helpers for the AIWB catalog speech-to-text (STT) E2E flow.

Keeps two pieces of non-trivial logic out of the ``.resource`` layer, per the
repo convention that keyword bodies delegate real work to libraries:

- selecting a transcription-capable AIM from the catalog by its tags, and
- producing a valid audio upload in-memory so the audio-endpoint tests need no
  committed binary fixture.
"""

import io
import math
import struct
import wave
from typing import Any

from robot.api.deco import keyword

# Mirrors the backend TRANSCRIPTION_TAG_VALUES (apps/api/aiwb/app/aims/constants.py)
# and the UI's copy (apps/ui/aiwb/lib/app/aims.ts): a model advertising any of these
# tags is speech-to-text capable.
TRANSCRIPTION_TAG_VALUES = (
    "transcription",
    "speech-to-text",
    "automatic-speech-recognition",
)


def _entry_tags(aim: dict[str, Any]) -> set[str]:
    """Return a catalog entry's tags from ``status.imageMetadata.model.tags``.

    This is the same field the backend capability classifier reads
    (apps/api/aiwb/app/aims/gateway.py) and the tested precedent in
    ``ChatAssertions.py`` uses, so selection here agrees with what the inference
    list surfaces under ``capability=transcription``.
    """
    model = ((aim.get("status") or {}).get("imageMetadata") or {}).get("model") or {}
    return {tag.strip() for tag in (model.get("tags") or []) if isinstance(tag, str) and tag.strip()}


@keyword("First Transcription Capable Aim Name")
def first_transcription_capable_aim_name(aims: list[dict[str, Any]]) -> str | None:
    """Return the ``metadata.name`` of the first transcription-tagged AIM, or None.

    None (not an error) signals "no such model in this catalog" so the caller can
    skip rather than fail on clusters without a Whisper AIM image.
    """
    transcription = set(TRANSCRIPTION_TAG_VALUES)
    for aim in aims:
        if _entry_tags(aim) & transcription:
            name = (aim.get("metadata") or {}).get("name") or ""
            if name:
                return name
    return None


@keyword("Synthetic Audio Upload")
def synthetic_audio_upload(
    field: str = "file",
    filename: str = "audio.wav",
    seconds: float = 1.0,
    frequency: float = 440.0,
    sample_rate: int = 16000,
) -> dict[str, tuple[str, bytes, str]]:
    """Return a requests-style multipart ``files`` mapping carrying a synthetic WAV.

    The clip is a short mono sine tone. The audio endpoints are exercised for their
    contract (a 200 with a ``text`` field), not for exact recognized words — a
    synthetic tone yields no deterministic transcript, and committing a real speech
    sample would add a binary fixture for no extra coverage of the request path.
    """
    wav_bytes = _sine_wav(float(seconds), float(frequency), int(sample_rate))
    return {field: (filename, wav_bytes, "audio/wav")}


def _sine_wav(seconds: float, frequency: float, sample_rate: int) -> bytes:
    amplitude = 16000  # < int16 max, with headroom
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit PCM
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(int(seconds * sample_rate)):
            sample = int(amplitude * math.sin(2 * math.pi * frequency * (i / sample_rate)))
            frames += struct.pack("<h", sample)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()
