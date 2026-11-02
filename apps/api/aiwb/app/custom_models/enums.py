# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from enum import StrEnum


class CustomModelImportType(StrEnum):
    """Supported custom-model preview/onboard source families."""

    HUGGING_FACE = "huggingFace"
    S3 = "s3"


class OnboardPhase(StrEnum):
    """Derived onboarding phase for a custom (BYOM) model.

    Composed from the AIMModel CR status, AIMProfile presence, and the
    weight-import annotations on the CR into a single enum value the UI can
    switch on.
    """

    PENDING = "Pending"
    IMPORTING = "Importing"
    READY = "Ready"
    FAILED = "Failed"
