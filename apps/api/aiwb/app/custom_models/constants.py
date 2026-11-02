# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Constants for the custom models module."""

import os
import re

import httpx

from ..config import AIWB_METADATA_PREFIX, EAI_APPS_METADATA_PREFIX

# HuggingFace lives on a single host; the API base and the set of accepted
# source hostnames both derive from it, so the host string is defined in
# exactly one place.
HF_HOST = "huggingface.co"
HF_API_BASE = f"https://{HF_HOST}/api/models"

COMPONENT_ID_ANNOTATION = f"{EAI_APPS_METADATA_PREFIX}/component-id"
SOURCE_URI_ANNOTATION = f"{EAI_APPS_METADATA_PREFIX}/source-uri"
REVISION_ANNOTATION = f"{EAI_APPS_METADATA_PREFIX}/revision"

MODEL_DISPLAY_NAME_ANNOTATION = f"{AIWB_METADATA_PREFIX}/model-display-name"
PROFILE_DISPLAY_NAME_ANNOTATION = f"{AIWB_METADATA_PREFIX}/profile-display-name"
CANONICAL_REPO_ID_ANNOTATION = f"{AIWB_METADATA_PREFIX}/canonical-repo-id"
SOURCE_SHA_ANNOTATION = f"{AIWB_METADATA_PREFIX}/source-sha"
SOURCE_DESCRIPTION_ANNOTATION = f"{AIWB_METADATA_PREFIX}/source-description"
SOURCE_TAGS_ANNOTATION = f"{AIWB_METADATA_PREFIX}/source-tags"

# Chosen precision; CRD prunes it from overrides.
MODEL_PRECISION_ANNOTATION = f"{AIWB_METADATA_PREFIX}/precision"

# Reserved profile identifier that resolves to a model's engine-created Default
# AIMProfileSet, so clients need not carry the generated `<model>-profiles-<hash>`
# name. The real resource name is always returned as `resourceName`.
DEFAULT_PROFILE_ALIAS = "default"

# Workbench-owned import annotations kept for backward compatibility with
# previously onboarded records. The active onboarding flow now points model
# sources directly at hf:// or user-provided s3:// URIs, but these fields are
# still read when present to preserve legacy phase/error semantics.
IMPORT_STATE_ANNOTATION = f"{AIWB_METADATA_PREFIX}/import-state"
IMPORT_ERROR_ANNOTATION = f"{AIWB_METADATA_PREFIX}/import-error"

HF_REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=25.0, write=10.0, pool=5.0)

HF_MAX_RESPONSE_BYTES = 1 * 1024 * 1024

_HF_HOSTS = frozenset({HF_HOST, f"www.{HF_HOST}"})

_REVISION_MARKERS = frozenset({"tree", "blob", "resolve"})

_REPO_PART_PATTERN = re.compile(r"^(?!\.+$)[A-Za-z0-9._-]+$")

_WEIGHT_EXTENSIONS = frozenset({".safetensors", ".gguf"})
_CONFIG_EXTENSIONS = frozenset({".json", ".txt", ".md", ".model", ".tiktoken", ".py", ".yaml", ".yml"})
_CONFIG_FILENAMES = frozenset({"merges.txt", "vocab.txt", "special_tokens_map.json"})

_INDEX_PATTERN = re.compile(r"\.safetensors\.index\.json$")

# S3 preview/onboard content expectations. Credential key aliases (S3_REQUIRED_CREDENTIAL_KEYS,
# S3_ENDPOINT_KEYS) are shared with AIWB secret creation and live in api_common.secrets.
# The MinIO credentials Secret name and key names live in ..minio.config, threaded in from the chart.
S3_EXPECTED_LAYOUT_FILES = ("config.json",)
S3_EXPECTED_TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json")

# The model card filename tag discovery reads. Held lowercase and matched against
# the lowercased path relative to the source prefix.
MODEL_CARD_FILENAME = "readme.md"

# Byte cap for reading an untrusted model card. Cards are usually a few KiB;
# anything larger is either not what it claims to be or not worth
# streaming during a synchronous preview. Reads are truncated at this bound
# rather than rejected, since a truncated card still yields frontmatter (which
# sits at the top of the file).
SOURCE_METADATA_MAX_BYTES = 256 * 1024

# Bounds applied to every tag list assembled from untrusted source content.
# Tags land in a K8s annotation (1MiB total per object) and render in the UI, so
# a card advertising thousands of tags must not become an unbounded payload.
MAX_DISCOVERED_TAGS = 32
MAX_DISCOVERED_TAG_LENGTH = 64

S3_REGION_KEYS = (
    "AWS_DEFAULT_REGION",
    "awsDefaultRegion",
    "aws_default_region",
    "AWS_REGION",
    "aws_region",
    "region",
)

# BYOM image override; aim-engine prefers this over ``spec.image`` on AIMProfile.
AIM_DEPLOYMENT_IMAGE_REF_ANNOTATION = "aim.eai.amd.com/deployment-image-ref"

DEFAULT_AIM_DEPLOYMENT_IMAGE_REF = os.getenv("AIM_DEFAULT_DEPLOYMENT_IMAGE_REF", "amdenterpriseai/aim-base:0.13.1")
RADEON_AIM_DEPLOYMENT_IMAGE_REF = os.getenv("AIM_RADEON_DEPLOYMENT_IMAGE_REF", "amdenterpriseai/aim-radeon-base:0.12")
EPYC_AIM_DEPLOYMENT_IMAGE_REF = os.getenv("EPYC_AIM_DEPLOYMENT_IMAGE_REF", "amdenterpriseai/aim-epyc-base:0.13")

# Repository names (the final path segment of an image reference) of the base
# images whose vLLM build ships the audio runtime (librosa / soundfile /
# ffmpeg). Speech models only transcribe on one of these, so the list gates the
# speech-to-text onboard path. An allowlist of repository names rather than a
# substring scan of the whole reference keeps a chat image that merely mentions
# "audio" in its registry path or tag from qualifying.
#
# An override that parses to nothing falls back to the default instead of being
# honored: an empty allowlist disqualifies every image, so speech onboarding
# would reject each model as lacking an audio runtime with no image able to
# satisfy it. That reads as a product bug rather than the misconfiguration it is.
DEFAULT_AUDIO_CAPABLE_BASE_REPOSITORY = "aim-audio-base"
AUDIO_CAPABLE_BASE_REPOSITORIES = frozenset(
    repository.strip().lower()
    for repository in os.getenv("AIM_AUDIO_CAPABLE_BASE_REPOSITORIES", "").split(",")
    if repository.strip()
) or frozenset({DEFAULT_AUDIO_CAPABLE_BASE_REPOSITORY})

# Base-image AIMModel that custom-model onboards derive their profiles from.
# In v1alpha2 a BYOM AIMModel does not carry its own runtime profiles; it
# selects the base profiles emitted by a base-image AIMModel (spec.image points
# at an AIM base image) and overlays identity + weights via spec.profiles.
# That base-image AIMModel is provisioned once by the platform and reused, so
# its name/scope are configuration here, not part of the onboard request.
AIM_BASE_MODEL_NAME = os.getenv("AIM_BASE_MODEL_NAME", "aim-base")
AIM_BASE_MODEL_SCOPE = os.getenv("AIM_BASE_MODEL_SCOPE", "Namespace")

# Poll bounds for waiting on aim-engine to emit the AIMProfile after AIMModel apply.
AIM_PROFILE_WAIT_TIMEOUT_SECONDS = float(os.getenv("AIM_PROFILE_WAIT_TIMEOUT_SECONDS", "60"))
AIM_PROFILE_POLL_INTERVAL_SECONDS = float(os.getenv("AIM_PROFILE_POLL_INTERVAL_SECONDS", "2"))
