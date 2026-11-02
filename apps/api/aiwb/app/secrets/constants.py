# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Constants for secrets module."""

from ..config import AIWB_METADATA_PREFIX, EAI_APPS_METADATA_PREFIX

# Label used to identify the use case of a secret
USE_CASE_LABEL = f"{EAI_APPS_METADATA_PREFIX}/use-case"

# AIRM writes use-case labels with "airm.silogen.com" (a known typo, should be .ai).
# Until AIRM is fixed, we check this label as a fallback when reading secrets.
AIRM_USE_CASE_LABEL = "airm.silogen.com/use-case"

# Annotation used to identify which user submitted the secret (imported from config)
# Uses annotation (not label) so emails with @ and other special characters are stored as-is.

SECRET_NAME_MIN_LENGTH = 2
SECRET_NAME_MAX_LENGTH = 253
SECRET_NAME_PATTERN = "^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$"

# Display name constraints (user-visible, not K8s resource name constraints)
DISPLAY_NAME_MIN_LENGTH = 2
DISPLAY_NAME_MAX_LENGTH = 253

# Annotation used to store the human-readable display name of a secret
DISPLAY_NAME_ANNOTATION = f"{AIWB_METADATA_PREFIX}/display-name"
