# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Constants for AIM resources."""

from typing import Final, Literal

from ..config import AIWB_METADATA_PREFIX

# CRD definitions
AIM_API_GROUP = "aim.eai.amd.com"
# All AIM kinds (AIMService, AIMClusterModel, AIMModel, AIMProfile, AIMClusterProfile) live under v1alpha2.
AIM_API_VERSION: Final[str] = "v1alpha2"
# Legacy AIM CRDs still served under v1alpha1 (e.g. AIMArtifact)
AIM_LEGACY_API_VERSION: Final[str] = "v1alpha1"
AIM_CLUSTER_MODEL_PLURAL = "aimclustermodels"
AIM_MODEL_PLURAL = "aimmodels"
AIM_SERVICE_RESOURCE = "AIMService"
AIM_SERVICE_PLURAL = "aimservices"
AIM_PROFILE_SET_RESOURCE = "AIMProfileSet"
AIM_CLUSTER_PROFILE_PLURAL = "aimclusterprofiles"
AIM_PROFILE_PLURAL = "aimprofiles"
AIM_PROFILE_SET_PLURAL = "aimprofilesets"
AIM_ARTIFACT_PLURAL = "aimartifacts"
AIM_CLUSTER_MODEL_LABEL = f"{AIM_API_GROUP}/cluster-model.name"
AIM_MODEL_LABEL = f"{AIM_API_GROUP}/model.name"
# Role aim-engine stamps on profiles it derives; base-role profiles emitted by the
# namespace base-image model define the runtime matrix any derived (BYOM) model inherits.
AIM_PROFILE_ROLE_LABEL = f"{AIM_API_GROUP}/profile-role"
AIM_PROFILE_ROLE_BASE = "base"

# Producing AIM(Cluster)Model of a profile. A namespace holds one base-image model
# per image family (aim-base, aim-audio-base, …), so the role label alone does not
# identify which base image a set of base profiles describes.
AIM_PROFILE_SOURCE_MODEL_LABEL = f"{AIM_API_GROUP}/source-model"

# Marks AIMProfileSets that AIWB authored, distinguishing them from the engine's
# implicit per-model Default set. Default classification keys on the ABSENCE of
# this label rather than the presence of the engine's managed-by label, which
# stops discriminating once AIWB creates its first set (see classify_default_profile_set).
PROFILE_ORIGIN_LABEL = f"{AIWB_METADATA_PREFIX}/profile-origin"
PROFILE_ORIGIN_AIWB = "aiwb"

# Entry in AIMProfile/AIMClusterProfile spec.features marking a profile whose runtime
# can serve LoRA adapters. aim-engine rejects an AIMService that declares spec.adapters
# unless its resolved profile lists this.
ADAPTER_PROFILE_FEATURE = "adapters"
# vLLM only accepts these discrete LoRA ranks.
LoraRank = Literal[1, 8, 16, 32, 64, 128, 256, 320, 512]
MAX_LORA_RANK_ENGINE_ARG: Final[str] = "max-lora-rank"

# HTTPRoute (Gateway API) definitions
HTTP_ROUTE_API_GROUP = "gateway.networking.k8s.io"
HTTP_ROUTE_PLURAL = "httproutes"

# KServe definitions
KSERVE_API_GROUP = "serving.kserve.io"
KSERVE_INFERENCE_SERVICE_PLURAL = "inferenceservices"

# Tag to identify chattable AIM deployments
CHAT_TAG_VALUE = "chat"

# Tags that identify a transcription- (speech-to-text) capable AIM deployment.
# Whisper-style images advertise one or more of these on their catalog metadata.
TRANSCRIPTION_TAG_VALUES = frozenset({"transcription", "speech-to-text", "automatic-speech-recognition"})

# Annotation key that forces aim-engine to route AIMService reconciliation through
# the v1alpha2 profile pipeline (which writes status.resolvedProfile) instead of
# the default v1alpha1 template pipeline. Without this, AIMServices that only set
# spec.model fall back to v1alpha1's `selectPipeline()` template path and never
# populate status.resolvedProfile — breaking the FE's profile join.
# TODO: drop once aim-engine removes v1alpha1 and the profile pipeline
# becomes the default.
RECONCILER_PIPELINE_ANNOTATION = f"{AIM_API_GROUP}/reconciler-pipeline"
RECONCILER_PIPELINE_PROFILE = "profile"

# Label stamped on AIMService CRs deployed from namespace-scoped fine-tuned models
FINE_TUNED_LABEL = f"{AIWB_METADATA_PREFIX}/fine-tuned"

# Label stamped on AIMService CRs deployed from namespace-scoped AIMModels
# (fine-tuned and custom-onboarded).
NAMESPACE_AIM_MODEL_LABEL = f"{AIWB_METADATA_PREFIX}/namespace-aim-model"

# AIMService condition types
AIM_COND_INFERENCE_SERVICE_READY = "InferenceServiceReady"
AIM_COND_HTTP_ROUTE_READY = "HTTPRouteReady"

# Serving-readiness conditions that must all be True before a service can expose
# any inference capability (endpoint reachable + routing configured). This gate is
# capability-neutral; the specific capability is read from the model's catalog tags.
AIM_SERVING_READY_CONDITIONS = (AIM_COND_INFERENCE_SERVICE_READY, AIM_COND_HTTP_ROUTE_READY)
