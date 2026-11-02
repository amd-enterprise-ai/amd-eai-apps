# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AIMs utils module."""

from collections.abc import Callable

import pytest

from api_common.exceptions import InconsistentStateException, ValidationException
from app.aims.crds import (
    AIMProfileResource,
    AIMProfileSetResource,
    AIMProfileSpec,
    AIMProfileStatus,
    HTTPRouteBackendRef,
    HTTPRouteMatch,
    HTTPRoutePathMatch,
    HTTPRouteResource,
    HTTPRouteRule,
    HTTPRouteSpec,
)
from app.aims.enums import AdapterMode, OptimizationMetric
from app.aims.schemas import AIMDeployRequest
from app.aims.utils import (
    agreed_adapter_weights,
    classify_default_profile_set,
    effective_profile_for_set,
    extract_endpoints,
    generate_aim_service_manifest,
    generate_aim_service_name,
    generate_fine_tuned_aim_service_manifest,
    generate_namespace_aim_service_manifest,
    is_default_profile_set,
    owning_profile_set_name,
    profiles_derived_from_set,
    profiles_without_owning_set,
    select_custom_deploy_profile,
)
from app.dispatch.crds import K8sMetadata
from app.workloads.constants import CANONICAL_NAME_LABEL, DISPLAY_NAME_ANNOTATION, MODEL_NAME_LABEL
from tests.factory import make_aim_cluster_model, make_aim_profile_set, make_aim_service_k8s, make_httproute


def test_generate_aim_service_name() -> None:
    """Test name generation is consistent and has correct format."""
    name1 = generate_aim_service_name("12345678-1234-5678-1234-567812345678")
    name2 = generate_aim_service_name("12345678-1234-5678-1234-567812345678")

    assert name1 == name2
    assert name1.startswith("wb-aim-")
    assert len(name1) == 15


def test_extract_endpoints_both_urls() -> None:
    """Test extraction of both internal and external URLs from HTTPRoute."""
    svc = make_aim_service_k8s(name="my-svc", namespace="my-ns", with_httproute=True)

    endpoints = extract_endpoints(svc, httproute=svc.httproute, cluster_host="https://cluster.example.com")
    assert "internal" in endpoints
    assert "external" in endpoints
    assert endpoints["internal"].startswith("http://my-svc-predictor.my-ns.svc.cluster.local")
    assert endpoints["external"].startswith("https://cluster.example.com/my-ns/")


def test_extract_endpoints_with_custom_port() -> None:
    """Test internal URL includes port when not 80."""
    svc = make_aim_service_k8s(name="my-svc", namespace="my-ns")
    httproute = make_httproute(namespace="my-ns", service_name="my-svc-predictor", port=8080)

    endpoints = extract_endpoints(svc, httproute=httproute)
    assert endpoints["internal"] == "http://my-svc-predictor.my-ns.svc.cluster.local:8080"


def test_extract_endpoints_adds_https_protocol() -> None:
    """Test adds https:// when cluster_host lacks protocol."""
    svc = make_aim_service_k8s(name="my-svc", namespace="my-ns", with_httproute=True)

    endpoints = extract_endpoints(svc, httproute=svc.httproute, cluster_host="cluster.example.com")
    assert endpoints["external"].startswith("https://")


def test_extract_endpoints_no_path_match() -> None:
    """Test returns only internal URL when no PathPrefix match found."""
    svc = make_aim_service_k8s(name="my-svc", namespace="my-ns")
    httproute = HTTPRouteResource(
        metadata=K8sMetadata(name="my-route", namespace="my-ns"),
        spec=HTTPRouteSpec(
            rules=[
                HTTPRouteRule(
                    backend_refs=[HTTPRouteBackendRef(kind="Service", name="my-svc-predictor", port=80)],
                    matches=[
                        HTTPRouteMatch(
                            path=HTTPRoutePathMatch(type="Exact", value="/my-ns/12345678-1234-5678-1234-567812345678")
                        )
                    ],
                )
            ]
        ),
    )

    endpoints = extract_endpoints(svc, httproute=httproute, cluster_host="https://cluster.example.com")
    assert endpoints["internal"] == "http://my-svc-predictor.my-ns.svc.cluster.local"
    assert "external" not in endpoints


def test_extract_endpoints_no_httproute_with_isvc() -> None:
    """Test derives internal URL from InferenceService name when HTTPRoute is missing."""
    svc = make_aim_service_k8s(name="my-svc", namespace="my-ns")
    endpoints = extract_endpoints(svc, httproute=None, inference_service_name="my-svc-a1b2c3")
    assert endpoints == {"internal": "http://my-svc-a1b2c3-predictor.my-ns.svc.cluster.local"}
    assert "external" not in endpoints


def test_extract_endpoints_no_httproute_no_isvc() -> None:
    """Test returns no internal URL when neither HTTPRoute nor InferenceService is available."""
    svc = make_aim_service_k8s(name="my-svc", namespace="my-ns")
    endpoints = extract_endpoints(svc, httproute=None, inference_service_name=None)
    assert "internal" not in endpoints
    assert "external" not in endpoints


def test_extract_endpoints_no_rules() -> None:
    """Test falls back to InferenceService name when HTTPRoute has no rules."""
    svc = make_aim_service_k8s(name="my-svc", namespace="my-ns")
    httproute = HTTPRouteResource(
        metadata=K8sMetadata(name="my-route", namespace="my-ns"), spec=HTTPRouteSpec(rules=[])
    )

    endpoints = extract_endpoints(svc, httproute=httproute, inference_service_name="my-svc-x9y8z7")
    assert endpoints["internal"] == "http://my-svc-x9y8z7-predictor.my-ns.svc.cluster.local"
    assert "external" not in endpoints


def test_extract_endpoints_no_service_backend() -> None:
    """Test falls back to InferenceService name when no Service backend found."""
    svc = make_aim_service_k8s(name="my-svc", namespace="my-ns")
    httproute = HTTPRouteResource(
        metadata=K8sMetadata(name="my-route", namespace="my-ns"),
        spec=HTTPRouteSpec(rules=[HTTPRouteRule(backend_refs=[HTTPRouteBackendRef(kind="Other", name="other")])]),
    )

    endpoints = extract_endpoints(svc, httproute=httproute, inference_service_name="my-svc-x9y8z7")
    assert endpoints["internal"] == "http://my-svc-x9y8z7-predictor.my-ns.svc.cluster.local"
    assert "external" not in endpoints


def test_generate_aim_service_manifest_basic() -> None:
    """Test basic manifest generation."""
    aim = make_aim_cluster_model(name="llama3-8b")
    req = AIMDeployRequest(model="llama3-8b", replicas=2)

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="test-ns",
        service_name="wb-aim-12345678",
        api_version="aims.amd.com/v1alpha2",
        submitter="test@example.com",
    )

    assert manifest["apiVersion"] == "aims.amd.com/v1alpha2"
    assert manifest["kind"] == "AIMService"
    assert manifest["metadata"]["namespace"] == "test-ns"
    assert manifest["spec"]["replicas"] == 2
    assert manifest["spec"]["model"]["name"] == "llama3-8b"
    # caching.mode replaces the deprecated cacheModel boolean.
    assert manifest["spec"]["caching"]["mode"] == "Shared"
    assert "cacheModel" not in manifest["spec"]
    # Forces the v1alpha2 profile pipeline so status.resolvedProfile lands;
    # The annotation will be removed once aim-engine drops v1alpha1 dispatch.
    assert manifest["metadata"]["annotations"]["aim.eai.amd.com/reconciler-pipeline"] == "profile"


def test_generate_aim_service_manifest_with_metric() -> None:
    """Metric criteria flow into spec.profile.selector."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="img", metric=OptimizationMetric.LATENCY)

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert "overrides" not in manifest["spec"]
    assert manifest["spec"]["profile"]["selector"] == {"minimumType": "any", "metric": "latency"}


# One group identity spanning two quantisations, which is the shape that makes an
# unconstrained selector able to pick a variant the adapters cannot load.
_GROUP_ID = "example-org/base-model"
_FP8_WEIGHTS = "example-org/base-model-fp8"
_BF16_WEIGHTS = "example-org/base-model-bf16"


_BOTH_QUANTISATIONS = {_FP8_WEIGHTS, _BF16_WEIGHTS}
# An unquantised base states one identity twice: the BF16 profile's modelId is the group id its
# quantised sibling also carries, so the same string is both a family name and real weights.
_UNQUANTISED_BASE = {_GROUP_ID, _FP8_WEIGHTS}


@pytest.mark.parametrize(
    ("declarations", "published", "expected"),
    [
        pytest.param([[_GROUP_ID, _FP8_WEIGHTS]], _BOTH_QUANTISATIONS, _FP8_WEIGHTS, id="one-adapter-names-weights"),
        pytest.param(
            [[_GROUP_ID, _FP8_WEIGHTS], [_GROUP_ID, _FP8_WEIGHTS]],
            _BOTH_QUANTISATIONS,
            _FP8_WEIGHTS,
            id="adapters-agree-on-weights",
        ),
        pytest.param([[_GROUP_ID], [_GROUP_ID]], _BOTH_QUANTISATIONS, None, id="every-adapter-names-only-the-group"),
        pytest.param(
            [[_GROUP_ID], [_GROUP_ID, _FP8_WEIGHTS]], _BOTH_QUANTISATIONS, None, id="one-adapter-names-only-the-group"
        ),
        pytest.param(
            [[_GROUP_ID, _FP8_WEIGHTS], [_GROUP_ID, _BF16_WEIGHTS]], _BOTH_QUANTISATIONS, None, id="adapters-disagree"
        ),
        pytest.param(
            # Two servable answers are not an impasse: either one loads the adapter, and abstaining
            # would refuse a declaration that names no group id for the fallback arm to match.
            [[_GROUP_ID, _FP8_WEIGHTS, _BF16_WEIGHTS]],
            _BOTH_QUANTISATIONS,
            _BF16_WEIGHTS,
            id="one-adapter-names-two-servable-weights",
        ),
        pytest.param(
            [[_GROUP_ID, _FP8_WEIGHTS, _BF16_WEIGHTS]],
            {_FP8_WEIGHTS},
            _FP8_WEIGHTS,
            id="several-declared-but-one-servable",
        ),
        pytest.param([[_GROUP_ID]], _UNQUANTISED_BASE, _GROUP_ID, id="group-id-is-also-real-weights"),
        pytest.param([["example-org/other-model"]], _BOTH_QUANTISATIONS, None, id="weights-this-model-does-not-serve"),
        pytest.param([[_GROUP_ID, _FP8_WEIGHTS]], set(), None, id="model-publishes-nothing"),
        pytest.param([], _BOTH_QUANTISATIONS, None, id="no-adapters"),
    ],
)
def test_agreed_adapter_weights(declarations: list[list[str]], published: set[str], expected: str | None) -> None:
    """Only weights every adapter names and the model serves narrow anything; with several, one is picked.

    The pick is by sorted order so the same request pins the same weights on every retry; a caller
    that wants a narrower answer narrows what it publishes rather than relying on the tie-break.
    """
    assert agreed_adapter_weights(declarations, published) == expected


def test_generate_aim_service_manifest_pins_agreed_adapter_weights() -> None:
    """The weights the adapters need reach the selector, so the engine cannot resolve a sibling."""
    manifest = generate_aim_service_manifest(
        aim=make_aim_cluster_model(),
        deploy_request=AIMDeployRequest(model="img", metric=OptimizationMetric.LATENCY),
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
        pinned_model_id=_FP8_WEIGHTS,
        pinned_aim_id=_GROUP_ID,
    )

    assert manifest["spec"]["profile"]["selector"] == {
        "minimumType": "any",
        "metric": "latency",
        "modelId": _FP8_WEIGHTS,
        # Carried alongside because the engine indexes its candidate listing on the group identity.
        "aimId": _GROUP_ID,
    }


@pytest.mark.parametrize(
    ("pinned_model_id", "pinned_aim_id"),
    [
        pytest.param(None, None, id="no-adapters-to-pin"),
        pytest.param(None, _GROUP_ID, id="adapters-name-only-the-group"),
        pytest.param(_FP8_WEIGHTS, None, id="model-has-not-resolved-its-group"),
    ],
)
def test_generate_aim_service_manifest_leaves_selector_alone_without_both_identities(
    pinned_model_id: str | None, pinned_aim_id: str | None
) -> None:
    """Nothing to narrow with is a no-op, never a constraint the adapters did not ask for."""
    manifest = generate_aim_service_manifest(
        aim=make_aim_cluster_model(),
        deploy_request=AIMDeployRequest(model="img", metric=OptimizationMetric.LATENCY),
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
        pinned_model_id=pinned_model_id,
        pinned_aim_id=pinned_aim_id,
    )

    assert manifest["spec"]["profile"]["selector"] == {"minimumType": "any", "metric": "latency"}


def test_generate_aim_service_manifest_with_hf_token() -> None:
    """HF_TOKEN lands in spec.caching.env, not spec.env, so it reaches the download Job only."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="img", hf_token="my-hf-secret")

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["env"] == []
    caching_env = manifest["spec"]["caching"]["env"]
    assert len(caching_env) == 1
    assert caching_env[0]["name"] == "HF_TOKEN"
    assert caching_env[0]["valueFrom"]["secretKeyRef"]["name"] == "my-hf-secret"
    assert caching_env[0]["valueFrom"]["secretKeyRef"]["key"] == "token"


def test_generate_aim_service_manifest_with_image_pull_secrets() -> None:
    """Test manifest includes imagePullSecrets when image_pull_secrets is provided."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="meta-llama-3-8b", image_pull_secrets=["secret1", "secret2"])

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert "imagePullSecrets" in manifest["spec"]
    assert len(manifest["spec"]["imagePullSecrets"]) == 2
    assert manifest["spec"]["imagePullSecrets"][0]["name"] == "secret1"
    assert manifest["spec"]["imagePullSecrets"][1]["name"] == "secret2"


def test_generate_aim_service_manifest_with_scaling() -> None:
    """Test manifest with scaling policy."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(
        model="llama3-8b",
        min_replicas=2,
        max_replicas=10,
        auto_scaling={"metrics": [{"type": "PodMetric"}]},
    )

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["minReplicas"] == 2
    assert manifest["spec"]["maxReplicas"] == 10
    assert "autoScaling" in manifest["spec"]


def test_generate_aim_service_manifest_auto_via_model() -> None:
    """When profile_name is unset, the manifest emits spec.profile.selector with minimumType=any.

    This allows aim-engine to consider all profile tiers (optimized, preview,
    unoptimized) rather than enforcing the default optimized floor, which would
    fail on clusters that only have unoptimized or preview profiles.
    """
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b")

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["model"]["name"] == "llama3-8b"
    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any"}}
    assert "template" not in manifest["spec"]


def test_generate_aim_service_manifest_profile_name_wins_over_selector() -> None:
    """When profile_name is explicit, it takes the direct-reference path:
    spec.profile.name is set and the selector criteria (metric/precision/gpu_model)
    are skipped. gpu_count is independent of selector/profile_name resolution and
    still lands in spec.profileOverrides.acceleratorCount when supplied.
    """
    aim = make_aim_cluster_model(name="llama3-8b")
    req = AIMDeployRequest(
        model="llama3-8b",
        metric=OptimizationMetric.LATENCY,
        precision="fp8",
        gpu_model="MI300X",
        gpu_count=8,
        profile_name="my-explicit-profile",
    )

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    # Legacy spec.overrides shape must not be emitted by v1alpha2.
    assert "overrides" not in manifest["spec"]
    profile = manifest["spec"]["profile"]
    assert profile == {"name": "my-explicit-profile"}
    # gpu_count is layered on top of the named profile via profileOverrides.
    assert manifest["spec"]["profileOverrides"] == {"acceleratorCount": 8}


def test_generate_aim_service_manifest_selector_only_precision() -> None:
    """Precision alone populates spec.profile.selector with precision and minimumType=any."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b", precision="bf16")

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert "overrides" not in manifest["spec"]
    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any", "precision": "bf16"}}


def test_generate_aim_service_manifest_gpu_count_alone_emits_minimum_type_selector() -> None:
    """gpu_count is not a selector field — it lives in spec.profileOverrides.

    With only gpu_count set, spec.profile.selector carries minimumType=any (so
    aim-engine considers all profile tiers) and spec.profileOverrides carries
    acceleratorCount as a per-service override on top of the resolved profile.
    """
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b", gpu_count=4)

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert "overrides" not in manifest["spec"]
    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any"}}
    assert manifest["spec"]["profileOverrides"] == {"acceleratorCount": 4}


def test_generate_aim_service_manifest_gpu_count_omitted_emits_no_overrides() -> None:
    """When gpu_count is not supplied, spec.profileOverrides is not emitted.

    The engine derives the count from the resolved profile, so
    AIWB must not stamp an empty/default override that would shadow it.
    """
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b")

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert "profileOverrides" not in manifest["spec"]


def test_generate_aim_service_manifest_gpu_count_with_profile_name() -> None:
    """gpu_count overrides apply on top of direct profile_name references too.

    profile_name picks the base profile; profileOverrides.acceleratorCount is
    then layered on top — both keys coexist in spec.
    """
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b", profile_name="mi300x-throughput-fp8", gpu_count=2)

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["profile"] == {"name": "mi300x-throughput-fp8"}
    assert manifest["spec"]["profileOverrides"] == {"acceleratorCount": 2}


def test_generate_aim_service_manifest_selector_only_gpu_model() -> None:
    """gpu_model alone sets spec.profile.selector.acceleratorModel only."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b", gpu_model="MI300X")

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert "overrides" not in manifest["spec"]
    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any", "acceleratorModel": "MI300X"}}


def test_generate_aim_service_manifest_selector_metric_precision_gpu_model() -> None:
    """All three selector fields combine into a single spec.profile.selector."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(
        model="llama3-8b",
        metric=OptimizationMetric.THROUGHPUT,
        precision="fp8",
        gpu_model="MI325X",
    )

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert "overrides" not in manifest["spec"]
    assert manifest["spec"]["profile"]["selector"] == {
        "minimumType": "any",
        "metric": "throughput",
        "precision": "fp8",
        "acceleratorModel": "MI325X",
    }


def test_generate_aim_service_manifest_gpu_count_with_selector() -> None:
    """gpu_count and selector criteria coexist on independent spec branches.

    Fences a future refactor from folding gpu_count back into the selector dict:
    the selector picks the profile by hardware model and
    gpu_count layers as profileOverrides.acceleratorCount on the resolved profile.
    """
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(
        model="llama3-8b",
        metric=OptimizationMetric.LATENCY,
        gpu_count=2,
    )

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any", "metric": "latency"}}
    assert manifest["spec"]["profileOverrides"] == {"acceleratorCount": 2}


def test_generate_aim_service_manifest_camelcase_keys_to_cluster() -> None:
    """Manifest sent to cluster uses camelCase keys."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(
        model="llama3-8b",
        image_pull_secrets=["s1"],
        profile_name="profile-x",
        min_replicas=1,
        max_replicas=5,
        auto_scaling={"metrics": []},
    )

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    spec = manifest["spec"]
    assert "imagePullSecrets" in spec
    assert spec["imagePullSecrets"][0]["name"] == "s1"
    assert spec["profile"]["name"] == "profile-x"
    assert "template" not in spec
    assert spec["minReplicas"] == 1
    assert spec["maxReplicas"] == 5
    assert "autoScaling" in spec


def test_generate_aim_service_manifest_omits_cluster_auth_group() -> None:
    """cluster-auth has been removed from the serving path; the manifest must not
    stamp cluster-auth/allowed-group in either metadata.annotations or
    spec.routing.annotations."""
    aim = make_aim_cluster_model(name="llama3-8b")
    req = AIMDeployRequest(model="llama3-8b")

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert "cluster-auth/allowed-group" not in manifest.get("metadata", {}).get("annotations", {})
    routing_annotations = manifest.get("spec", {}).get("routing", {}).get("annotations", {})
    assert "cluster-auth/allowed-group" not in routing_annotations


def test_generate_aim_service_manifest_includes_workload_type_label() -> None:
    """Test manifest includes workload-type label (but not workload-id or component-id)."""
    aim = make_aim_cluster_model(name="llama3-8b")
    req = AIMDeployRequest(model="llama3-8b")

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-12345678",
        api_version="v1",
        submitter="test@example.com",
    )

    assert "labels" in manifest["metadata"]
    assert manifest["metadata"]["labels"]["airm.silogen.ai/workload-type"] == "INFERENCE"
    # workload-id and component-id labels are NOT included as they added by Kyverno/AIRM when deployed to the cluster
    assert "airm.silogen.ai/workload-id" not in manifest["metadata"]["labels"]
    assert "airm.silogen.ai/component-id" not in manifest["metadata"]["labels"]


def test_generate_fine_tuned_aim_service_manifest_stamps_finetuned_metadata() -> None:
    """User-facing fine-tune identity (display name + canonical name) lives in annotations,
    not labels — so values can carry characters K8s label values forbid (e.g. `/`).
    Labels are reserved for selector-relevant flags (fine-tuned marker, workload type)."""
    req = AIMDeployRequest(model="wb-llm-finetune-abc123")

    manifest = generate_fine_tuned_aim_service_manifest(
        model_name="wb-llm-finetune-abc123",
        deploy_request=req,
        namespace="workbench",
        service_name="wb-aim-test",
        api_version="aim.eai.amd.com/v1alpha2",
        submitter="user@example.com",
        display_name="my-finetune",
        canonical_name="Qwen/Qwen2.5-0.5B-Instruct",
    )

    labels = manifest["metadata"]["labels"]
    assert labels["aiwb.apps.eai.amd.com/fine-tuned"] == "true"
    assert labels["aiwb.apps.eai.amd.com/namespace-aim-model"] == "true"
    # User-facing identity is intentionally NOT in labels.
    assert MODEL_NAME_LABEL not in labels
    assert CANONICAL_NAME_LABEL not in labels

    annotations = manifest["metadata"]["annotations"]
    assert annotations[MODEL_NAME_LABEL] == "my-finetune"
    # Annotation preserves slashes; the FE reads this for code samples.
    assert annotations[CANONICAL_NAME_LABEL] == "Qwen/Qwen2.5-0.5B-Instruct"
    # Forces the v1alpha2 profile pipeline so status.resolvedProfile lands;
    # The annotation will be removed once aim-engine drops v1alpha1 dispatch.
    assert annotations["aim.eai.amd.com/reconciler-pipeline"] == "profile"
    # cluster-auth has been removed from the serving path.
    assert "cluster-auth/allowed-group" not in annotations
    assert "cluster-auth/allowed-group" not in manifest["spec"].get("routing", {}).get("annotations", {})

    # caching.mode replaces the deprecated cacheModel boolean.
    assert manifest["spec"]["caching"]["mode"] == "Shared"
    assert "cacheModel" not in manifest["spec"]


def _fine_tuned_manifest(req: AIMDeployRequest) -> dict:
    return generate_fine_tuned_aim_service_manifest(
        model_name="wb-llm-finetune-abc123",
        deploy_request=req,
        namespace="workbench",
        service_name="wb-aim-test",
        api_version="aim.eai.amd.com/v1alpha2",
        submitter="user@example.com",
        display_name="my-finetune",
        canonical_name="Qwen/Qwen2.5-0.5B-Instruct",
    )


def test_generate_fine_tuned_aim_service_manifest_auto_via_model() -> None:
    """Empty deploy request emits spec.profile.selector with minimumType=any."""
    manifest = _fine_tuned_manifest(AIMDeployRequest(model="wb-llm-finetune-abc123"))

    assert manifest["spec"]["model"]["name"] == "wb-llm-finetune-abc123"
    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any"}}
    assert "profileOverrides" not in manifest["spec"]
    assert "overrides" not in manifest["spec"]


def test_generate_namespace_aim_service_manifest_pins_resolved_profile_name() -> None:
    """Pinned profiles take precedence over deploy-time selectors and overrides."""
    manifest = generate_namespace_aim_service_manifest(
        model_name="custom-model",
        deploy_request=AIMDeployRequest(
            model="custom-model",
            metric=OptimizationMetric.LATENCY,
            precision="fp8",
            adapter_mode=AdapterMode.DYNAMIC,
            max_lora_rank=32,
        ),
        namespace="workbench",
        service_name="wb-aim-test",
        api_version="aim.eai.amd.com/v1alpha2",
        submitter="user@example.com",
        display_name="Custom Display",
        canonical_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        is_fine_tuned=False,
        resolved_profile_name="custom-profile",
    )

    assert manifest["spec"]["profile"] == {"name": "custom-profile"}
    assert "profileOverrides" not in manifest["spec"]
    assert "selector" not in manifest["spec"].get("profile", {})
    # adapterRuntime is a sibling of profile/profileOverrides, so a pinned profile doesn't suppress it.
    assert manifest["spec"]["adapterRuntime"] == {"maxRank": 32}


def test_generate_namespace_aim_service_manifest_uses_deploy_display_name() -> None:
    """A user-entered deploy display name wins for the display-name annotation,
    while the model identity stays on MODEL_NAME_LABEL."""
    manifest = generate_namespace_aim_service_manifest(
        model_name="custom-model",
        deploy_request=AIMDeployRequest(model="custom-model"),
        namespace="workbench",
        service_name="wb-aim-test",
        api_version="aim.eai.amd.com/v1alpha2",
        submitter="user@example.com",
        display_name="Custom Display",
        canonical_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        is_fine_tuned=False,
        resolved_profile_name="custom-profile",
        deploy_display_name="My TinyLlama",
    )

    annotations = manifest["metadata"]["annotations"]
    assert annotations[DISPLAY_NAME_ANNOTATION] == "My TinyLlama"
    assert annotations[MODEL_NAME_LABEL] == "Custom Display"


def test_generate_namespace_aim_service_manifest_falls_back_to_model_display_name() -> None:
    """Without a deploy display name, the display-name annotation falls back to
    the onboarded model's identity."""
    manifest = generate_namespace_aim_service_manifest(
        model_name="custom-model",
        deploy_request=AIMDeployRequest(model="custom-model"),
        namespace="workbench",
        service_name="wb-aim-test",
        api_version="aim.eai.amd.com/v1alpha2",
        submitter="user@example.com",
        display_name="Custom Display",
        canonical_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        is_fine_tuned=False,
        resolved_profile_name="custom-profile",
    )

    assert manifest["metadata"]["annotations"][DISPLAY_NAME_ANNOTATION] == "Custom Display"


def test_generate_namespace_aim_service_manifest_ignores_whitespace_deploy_display_name() -> None:
    """A whitespace-only deploy name is not a real name; fall back to model identity."""
    manifest = generate_namespace_aim_service_manifest(
        model_name="custom-model",
        deploy_request=AIMDeployRequest(model="custom-model"),
        namespace="workbench",
        service_name="wb-aim-test",
        api_version="aim.eai.amd.com/v1alpha2",
        submitter="user@example.com",
        display_name="Custom Display",
        canonical_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        is_fine_tuned=False,
        resolved_profile_name="custom-profile",
        deploy_display_name="   ",
    )

    assert manifest["metadata"]["annotations"][DISPLAY_NAME_ANNOTATION] == "Custom Display"


def test_generate_fine_tuned_aim_service_manifest_with_metric_selector() -> None:
    manifest = _fine_tuned_manifest(AIMDeployRequest(model="wb-llm-finetune-abc123", metric=OptimizationMetric.LATENCY))

    assert manifest["spec"]["profile"]["selector"] == {"minimumType": "any", "metric": "latency"}


def test_generate_fine_tuned_aim_service_manifest_with_precision_selector() -> None:
    manifest = _fine_tuned_manifest(AIMDeployRequest(model="wb-llm-finetune-abc123", precision="bf16"))

    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any", "precision": "bf16"}}


def test_generate_fine_tuned_aim_service_manifest_with_gpu_model_selector() -> None:
    manifest = _fine_tuned_manifest(AIMDeployRequest(model="wb-llm-finetune-abc123", gpu_model="MI300X"))

    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any", "acceleratorModel": "MI300X"}}


def test_generate_fine_tuned_aim_service_manifest_combined_selector() -> None:
    manifest = _fine_tuned_manifest(
        AIMDeployRequest(
            model="wb-llm-finetune-abc123",
            metric=OptimizationMetric.THROUGHPUT,
            precision="fp8",
            gpu_model="MI325X",
        )
    )

    assert manifest["spec"]["profile"]["selector"] == {
        "minimumType": "any",
        "metric": "throughput",
        "precision": "fp8",
        "acceleratorModel": "MI325X",
    }


def test_generate_fine_tuned_aim_service_manifest_with_profile_name() -> None:
    manifest = _fine_tuned_manifest(
        AIMDeployRequest(model="wb-llm-finetune-abc123", profile_name="my-namespace-profile")
    )

    assert manifest["spec"]["profile"] == {"name": "my-namespace-profile"}


def test_generate_fine_tuned_aim_service_manifest_with_gpu_count_profile_override() -> None:
    manifest = _fine_tuned_manifest(AIMDeployRequest(model="wb-llm-finetune-abc123", gpu_count=8))

    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any"}}
    assert manifest["spec"]["profileOverrides"] == {"acceleratorCount": 8}


def test_generate_fine_tuned_aim_service_manifest_with_engine_args_profile_override() -> None:
    manifest = _fine_tuned_manifest(
        AIMDeployRequest(model="wb-llm-finetune-abc123", engine_args={"max-model-len": 8192})
    )

    assert manifest["spec"]["profileOverrides"] == {"engineArgs": {"max-model-len": 8192}}


def test_generate_fine_tuned_aim_service_manifest_writes_max_lora_rank() -> None:
    manifest = _fine_tuned_manifest(
        AIMDeployRequest(
            model="wb-llm-finetune-abc123",
            adapter_mode=AdapterMode.DYNAMIC,
            max_lora_rank=32,
        )
    )

    assert manifest["spec"]["adapterRuntime"] == {"maxRank": 32}
    assert "profileOverrides" not in manifest["spec"]


def test_generate_fine_tuned_aim_service_manifest_with_engine_env_profile_override() -> None:
    manifest = _fine_tuned_manifest(
        AIMDeployRequest(model="wb-llm-finetune-abc123", engine_env=[{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}])
    )

    assert manifest["spec"]["profileOverrides"] == {"engineEnv": {"VLLM_LOGGING_LEVEL": "DEBUG"}}


@pytest.mark.parametrize(
    ("engine_env", "message"),
    [
        ([{"value": "DEBUG"}], "missing required field 'name'"),
        ([{"name": "VLLM_LOGGING_LEVEL"}], "missing required field 'value'"),
        ([{"name": "VLLM_LOGGING_LEVEL", "value": None}], "value must be a string"),
        (
            [{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}, {"name": "VLLM_LOGGING_LEVEL", "value": "INFO"}],
            "duplicates earlier entry",
        ),
    ],
)
def test_generate_aim_service_manifest_rejects_invalid_engine_env_entries(
    engine_env: list[dict[str, object]], message: str
) -> None:
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b", engine_env=engine_env)

    with pytest.raises(ValidationException, match=message):
        generate_aim_service_manifest(
            aim=aim,
            deploy_request=req,
            namespace="ns",
            service_name="wb-aim-test",
            api_version="v1",
            submitter="u",
        )


def test_generate_fine_tuned_aim_service_manifest_with_container_env_profile_override() -> None:
    container_env = [{"name": "FOO", "value": "bar"}]
    manifest = _fine_tuned_manifest(AIMDeployRequest(model="wb-llm-finetune-abc123", container_env=container_env))

    assert manifest["spec"]["profileOverrides"] == {"containerEnv": container_env}


def test_generate_fine_tuned_aim_service_manifest_selector_and_profile_overrides() -> None:
    manifest = _fine_tuned_manifest(
        AIMDeployRequest(
            model="wb-llm-finetune-abc123",
            precision="fp8",
            gpu_count=4,
            engine_args={"max-model-len": 4096},
        )
    )

    assert manifest["spec"]["profile"] == {"selector": {"minimumType": "any", "precision": "fp8"}}
    assert manifest["spec"]["profileOverrides"] == {
        "acceleratorCount": 4,
        "engineArgs": {"max-model-len": 4096},
    }


def test_generate_aim_service_manifest_with_engine_args_profile_override() -> None:
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b", engine_args={"max-model-len": 8192})

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["profileOverrides"] == {"engineArgs": {"max-model-len": 8192}}


def test_generate_aim_service_manifest_writes_max_lora_rank() -> None:
    """The rank ceiling lands on adapterRuntime, leaving other engine args untouched."""
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(
        model="llama3-8b",
        engine_args={"max-model-len": 8192},
        adapter_mode=AdapterMode.DYNAMIC,
        max_lora_rank=32,
    )

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["profileOverrides"] == {"engineArgs": {"max-model-len": 8192}}
    assert manifest["spec"]["adapterRuntime"] == {"maxRank": 32}


def test_generate_aim_service_manifest_with_engine_env_profile_override() -> None:
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b", engine_env=[{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}])

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["profileOverrides"] == {"engineEnv": {"VLLM_LOGGING_LEVEL": "DEBUG"}}


def test_generate_aim_service_manifest_with_container_env_profile_override() -> None:
    container_env = [{"name": "FOO", "value": "bar"}]
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(model="llama3-8b", container_env=container_env)

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["profileOverrides"] == {"containerEnv": container_env}


def test_generate_aim_service_manifest_selector_and_profile_overrides() -> None:
    aim = make_aim_cluster_model()
    req = AIMDeployRequest(
        model="llama3-8b",
        metric=OptimizationMetric.LATENCY,
        gpu_count=2,
        engine_env=[{"name": "VLLM_LOGGING_LEVEL", "value": "INFO"}],
    )

    manifest = generate_aim_service_manifest(
        aim=aim,
        deploy_request=req,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="v1",
        submitter="u",
    )

    assert manifest["spec"]["profile"]["selector"] == {"minimumType": "any", "metric": "latency"}
    assert manifest["spec"]["profileOverrides"] == {
        "acceleratorCount": 2,
        "engineEnv": {"VLLM_LOGGING_LEVEL": "INFO"},
    }


def test_is_default_profile_set_by_absence_of_origin_label() -> None:
    default_set = make_aim_profile_set(is_aiwb_authored=False)
    aiwb_set = make_aim_profile_set(is_aiwb_authored=True)

    assert is_default_profile_set(default_set) is True
    assert is_default_profile_set(aiwb_set) is False


def test_is_default_profile_set_with_no_labels() -> None:
    """A set carrying no labels at all classifies as Default (unlabeled == engine)."""
    unlabeled = AIMProfileSetResource.model_validate({"metadata": {"name": "m-profiles-abc"}})

    assert unlabeled.metadata.labels == {}
    assert is_default_profile_set(unlabeled) is True


def test_classify_default_profile_set_returns_the_single_default() -> None:
    default_set = make_aim_profile_set(name="m-profiles-abc", is_aiwb_authored=False)
    aiwb_set = make_aim_profile_set(name="m-fast", is_aiwb_authored=True)

    result = classify_default_profile_set([aiwb_set, default_set])

    assert result.metadata.name == "m-profiles-abc"


def test_classify_default_profile_set_raises_on_zero_defaults() -> None:
    aiwb_only = [make_aim_profile_set(name="m-fast", is_aiwb_authored=True)]

    with pytest.raises(InconsistentStateException, match="found 0"):
        classify_default_profile_set(aiwb_only)


def test_classify_default_profile_set_raises_on_multiple_defaults() -> None:
    two_defaults = [
        make_aim_profile_set(name="m-profiles-abc", is_aiwb_authored=False),
        make_aim_profile_set(name="m-profiles-def", is_aiwb_authored=False),
    ]

    with pytest.raises(InconsistentStateException, match="found 2"):
        classify_default_profile_set(two_defaults)


def _make_derived_profile(
    *,
    name: str,
    owner_set: str | None = "m-profiles-abc",
    precision: str = "bf16",
    metric: str = "latency",
    status: str = "Ready",
    primary: bool = False,
    optimization_type: str = "general",
) -> AIMProfileResource:
    """A derived AIMProfile, owned by an AIMProfileSet the way aim-engine emits them."""
    owner_references = [{"kind": "AIMProfileSet", "name": owner_set, "controller": True}] if owner_set else []
    return AIMProfileResource(
        metadata=K8sMetadata(name=name, namespace="ns", owner_references=owner_references),
        spec=AIMProfileSpec(precision=precision, metric=metric, primary=primary, type=optimization_type),
        status=AIMProfileStatus(status=status),
    )


def test_owning_profile_set_name_reads_the_profile_set_owner_reference() -> None:
    profile = _make_derived_profile(name="m-bf16-latency", owner_set="m-profiles-abc")

    assert owning_profile_set_name(profile) == "m-profiles-abc"


def test_owning_profile_set_name_ignores_other_owner_kinds() -> None:
    """Profiles emitted before sets owned them are owned by the AIMModel, not a set."""
    profile = _make_derived_profile(name="m-legacy", owner_set=None)
    profile.metadata.owner_references = [{"kind": "AIMModel", "name": "m"}]

    assert owning_profile_set_name(profile) is None


def test_profiles_derived_from_set_selects_only_that_sets_profiles_in_order() -> None:
    profiles = [
        _make_derived_profile(name="authored-fp8", owner_set="m-fast"),
        _make_derived_profile(name="default-bf16", owner_set="m-profiles-abc"),
        _make_derived_profile(name="default-fp8", owner_set="m-profiles-abc"),
        _make_derived_profile(name="unowned", owner_set=None),
    ]

    derived = profiles_derived_from_set(profiles, "m-profiles-abc")

    assert [p.metadata.name for p in derived] == ["default-bf16", "default-fp8"]


def test_select_custom_deploy_profile_matches_engine_ranking() -> None:
    """Optimization tier wins first, then primary, then latency over throughput."""
    profiles = [
        _make_derived_profile(
            name="fp8-general-primary",
            precision="fp8",
            metric="throughput",
            primary=True,
            optimization_type="general",
        ),
        _make_derived_profile(
            name="fp8-optimized-throughput",
            precision="fp8",
            metric="throughput",
            optimization_type="optimized",
        ),
        _make_derived_profile(
            name="fp8-optimized-latency",
            precision="fp8",
            metric="latency",
            optimization_type="optimized",
        ),
        _make_derived_profile(name="bf16-latency", precision="bf16", metric="latency"),
    ]

    assert select_custom_deploy_profile(profiles, "fp8").metadata.name == "fp8-optimized-latency"
    # Drop the latency profile: optimized still wins over a general primary.
    assert select_custom_deploy_profile(profiles[:2] + profiles[3:], "fp8").metadata.name == (
        "fp8-optimized-throughput"
    )
    # No matching precision => None so the caller can fall back.
    assert select_custom_deploy_profile(profiles, "fp16") is None


def test_select_custom_deploy_profile_ignores_non_ready_profiles() -> None:
    profiles = [_make_derived_profile(name="fp8-pending", precision="fp8", status="Pending")]

    assert select_custom_deploy_profile(profiles, "fp8") is None


def test_select_custom_deploy_profile_treats_an_unset_primary_as_not_primary() -> None:
    """``spec.primary`` is optional, and an unset flag must not be read as the engine
    having marked the profile primary — that would outrank a genuinely primary one."""
    unset = _make_derived_profile(name="fp8-primary-unset", precision="fp8")
    unset.spec.primary = None
    explicit = _make_derived_profile(name="fp8-primary", precision="fp8", primary=True)

    assert select_custom_deploy_profile([unset, explicit], "fp8").metadata.name == "fp8-primary"
    assert select_custom_deploy_profile([explicit, unset], "fp8").metadata.name == "fp8-primary"


def test_profiles_without_owning_set_selects_only_unowned_profiles() -> None:
    """Deploy falls back to these when the Default is unresolvable through the set
    layer, so a profile owned by an authored set must never appear here."""
    profiles = [
        _make_derived_profile(name="owned", owner_set="m-fast"),
        _make_derived_profile(name="legacy-bf16", owner_set=None),
        _make_derived_profile(name="legacy-fp8", owner_set=None),
    ]

    assert [p.metadata.name for p in profiles_without_owning_set(profiles)] == ["legacy-bf16", "legacy-fp8"]


def test_effective_profile_for_set_returns_the_single_profile_of_a_narrowed_set() -> None:
    """A narrowed set derives exactly one profile, so the precision annotation cannot override it."""
    only = _make_derived_profile(name="m-fast-fp8", precision="fp8")

    assert effective_profile_for_set([only], "bf16").metadata.name == "m-fast-fp8"


def test_effective_profile_for_set_prefers_the_annotated_precision() -> None:
    profiles = [
        _make_derived_profile(name="m-bf16-latency", precision="bf16"),
        _make_derived_profile(name="m-fp8-latency", precision="fp8"),
    ]

    assert effective_profile_for_set(profiles, "fp8").metadata.name == "m-fp8-latency"


def test_effective_profile_for_set_falls_back_to_the_first_profile() -> None:
    """Without an annotation, or with no Ready profile at that precision, the first
    derived profile is chosen — the answer deploy gave before profile sets existed."""
    profiles = [
        _make_derived_profile(name="m-bf16-latency", precision="bf16"),
        _make_derived_profile(name="m-fp8-latency", precision="fp8", status="Pending"),
    ]

    assert effective_profile_for_set(profiles, None).metadata.name == "m-bf16-latency"
    assert effective_profile_for_set(profiles, "fp8").metadata.name == "m-bf16-latency"


def test_effective_profile_for_set_returns_none_without_derived_profiles() -> None:
    assert effective_profile_for_set([], "fp8") is None


def _namespace_manifest(deploy_request: AIMDeployRequest) -> dict:
    return generate_namespace_aim_service_manifest(
        model_name="custom-model",
        deploy_request=deploy_request,
        namespace="workbench",
        service_name="wb-aim-test",
        api_version="aim.eai.amd.com/v1alpha2",
        submitter="user@example.com",
        display_name="Custom Display",
        canonical_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        is_fine_tuned=False,
        resolved_profile_name="custom-profile",
    )


def _cluster_manifest(deploy_request: AIMDeployRequest) -> dict:
    return generate_aim_service_manifest(
        aim=make_aim_cluster_model(name="llama3-8b"),
        deploy_request=deploy_request,
        namespace="ns",
        service_name="wb-aim-test",
        api_version="aim.eai.amd.com/v1alpha2",
        submitter="user@example.com",
    )


@pytest.mark.parametrize("build_manifest", [_cluster_manifest, _namespace_manifest], ids=["cluster", "namespace"])
def test_manifest_omits_adapter_fields_when_none_requested(build_manifest: Callable[[AIMDeployRequest], dict]) -> None:
    """An empty adapters array is still a declaration aim-engine acts on, and adapterMode is
    immutable once written, so a deploy that asked for neither writes neither."""
    spec = build_manifest(AIMDeployRequest(model="llama3-8b"))["spec"]

    assert "adapters" not in spec
    assert "adapterMode" not in spec
    assert "adapterRuntime" not in spec


@pytest.mark.parametrize("build_manifest", [_cluster_manifest, _namespace_manifest], ids=["cluster", "namespace"])
def test_manifest_writes_adapters_as_artifact_references(
    build_manifest: Callable[[AIMDeployRequest], dict],
) -> None:
    """Requested names become AIMArtifact references in the service's own namespace."""
    request = AIMDeployRequest(model="llama3-8b", adapters=["first-adapter", "second-adapter"])

    spec = build_manifest(request)["spec"]

    assert spec["adapters"] == [
        {"kind": "AIMArtifact", "name": "first-adapter"},
        {"kind": "AIMArtifact", "name": "second-adapter"},
    ]
    assert "adapterMode" not in spec


@pytest.mark.parametrize("build_manifest", [_cluster_manifest, _namespace_manifest], ids=["cluster", "namespace"])
def test_manifest_writes_adapter_mode_only_when_chosen(build_manifest: Callable[[AIMDeployRequest], dict]) -> None:
    request = AIMDeployRequest(model="llama3-8b", adapters=["first-adapter"], adapter_mode=AdapterMode.DYNAMIC)

    assert build_manifest(request)["spec"]["adapterMode"] == "dynamic"
