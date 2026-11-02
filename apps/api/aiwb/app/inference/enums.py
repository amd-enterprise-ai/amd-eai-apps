# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Inference capability enums."""

from enum import StrEnum


class InferenceCapability(StrEnum):
    """Capability filter values accepted by the inference list endpoint.

    Each value narrows the list to fully-ready deployments whose model
    advertises that capability via its catalog tags. Adding new capabilities
    here lets clients filter for them without endpoint proliferation.
    """

    CHAT = "chat"
    TRANSCRIPTION = "transcription"
