# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AIMs Pydantic schemas."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.aims.constants import AIM_COND_HTTP_ROUTE_READY, AIM_COND_INFERENCE_SERVICE_READY
from app.aims.enums import AdapterMode, AIMServiceStatus, OptimizationMetric
from app.aims.schemas import (
    AIMDeployRequest,
    AIMServicePatchRequest,
)
from app.config import CLUSTER_HOST
from tests.factory import make_aim_service_k8s


def test_aim_deploy_request_defaults() -> None:
    """Test AIMDeployRequest defaults."""
    r = AIMDeployRequest(model="meta-llama-3-8b")
    assert r.replicas == 1
    assert r.metric is None
    assert r.min_replicas is None


def test_aim_deploy_request_with_resource_name() -> None:
    """Test AIMDeployRequest with model as resource_name."""
    r = AIMDeployRequest(model="my-aim-model")
    assert r.model == "my-aim-model"
    assert r.replicas == 1


def test_aim_deploy_request_with_all_fields() -> None:
    """Test AIMDeployRequest with all fields."""
    r = AIMDeployRequest(
        model="docker.io/amd/model:v1",
        replicas=4,
        metric=OptimizationMetric.LATENCY,
        image_pull_secrets=["secret1"],
        hf_token="hf_token",
    )
    assert r.replicas == 4
    assert r.metric == OptimizationMetric.LATENCY


def test_aim_deploy_request_parses_engine_override_camelcase_input() -> None:
    """Deploy-time engine override fields accept camelCase wire keys."""
    r = AIMDeployRequest(
        model="meta-llama-3-8b",
        engineArgs={"max-model-len": 8192},
        adapterMode="dynamic",
        engineEnv=[{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}],
        containerEnv=[{"name": "FOO", "value": "bar"}],
    )
    assert r.engine_args == {"max-model-len": 8192}
    assert r.engine_env == [{"name": "VLLM_LOGGING_LEVEL", "value": "DEBUG"}]
    assert r.container_env == [{"name": "FOO", "value": "bar"}]


@pytest.mark.parametrize("adapter_mode", [None, "static", "dynamic"])
@pytest.mark.parametrize("max_lora_rank", [32, 0, "32"])
def test_aim_deploy_request_rejects_max_lora_rank_engine_arg(adapter_mode: str | None, max_lora_rank: object) -> None:
    """The rank ceiling has a first-class field, so the engine-argument spelling is refused
    outright — accepting both would leave two ways to set one value, with no defined winner. The
    spelling is wrong under every adapter mode, and the refusal names the field, the ranks it
    takes and the mode it needs, so a caller moving the value across cannot earn a second 422."""
    with pytest.raises(ValidationError) as exc_info:
        AIMDeployRequest(
            model="meta-llama-3-8b",
            adapterMode=adapter_mode,
            engineArgs={"max-lora-rank": max_lora_rank},
        )

    assert "maxLoraRank" in str(exc_info.value)
    assert "512" in str(exc_info.value)
    assert "adapterMode 'dynamic'" in str(exc_info.value)


@pytest.mark.parametrize("max_lora_rank", [1, 512])
def test_aim_deploy_request_accepts_max_lora_rank_at_bounds(max_lora_rank: int) -> None:
    request = AIMDeployRequest(
        model="meta-llama-3-8b",
        adapterMode="dynamic",
        maxLoraRank=max_lora_rank,
    )

    assert request.max_lora_rank == max_lora_rank


@pytest.mark.parametrize("max_lora_rank", [0, 66, 513])
def test_aim_deploy_request_rejects_unsupported_max_lora_rank(max_lora_rank: object) -> None:
    """The engine only honors vLLM's fixed set of LoRA ranks; anything else, even within 1-512, is
    rejected, and the refusal enumerates the ranks that would have been accepted."""
    with pytest.raises(ValidationError) as exc_info:
        AIMDeployRequest(
            model="meta-llama-3-8b",
            adapterMode="dynamic",
            maxLoraRank=max_lora_rank,
        )

    assert "maxLoraRank" in str(exc_info.value)
    assert "512" in str(exc_info.value)


@pytest.mark.parametrize("max_lora_rank", [True, False, 32.0, 32.5, "32", Decimal("32")])
def test_aim_deploy_request_rejects_non_integer_max_lora_rank(max_lora_rank: object) -> None:
    """Every one of these either equals a supported rank (``True`` is 1) or is coerced onto one
    (``32.0``), so without a type guard the deployment would quietly land at a rank the caller
    never asked for."""
    with pytest.raises(ValidationError) as exc_info:
        AIMDeployRequest(
            model="meta-llama-3-8b",
            adapterMode="dynamic",
            maxLoraRank=max_lora_rank,
        )

    assert "maxLoraRank" in str(exc_info.value)
    assert "must be an integer" in str(exc_info.value)


@pytest.mark.parametrize("adapter_mode", [None, "static"])
def test_aim_deploy_request_rejects_max_lora_rank_outside_dynamic_mode(adapter_mode: str | None) -> None:
    """A static deployment's ceiling follows from the adapters it declares, so a hand-set one
    would be a second, silently ignored source of truth."""
    with pytest.raises(ValidationError) as exc_info:
        AIMDeployRequest(
            model="meta-llama-3-8b",
            adapterMode=adapter_mode,
            maxLoraRank=32,
        )

    assert "maxLoraRank" in str(exc_info.value)
    assert "dynamic" in str(exc_info.value)


def test_aim_deploy_request_reports_the_engine_arg_before_the_adapter_mode() -> None:
    """A request that breaks both rules is answered with the engine-argument refusal, which is the
    only one of the two that names a spelling the caller has to abandon; being told to switch mode
    first would leave them to discover the second refusal on the next attempt."""
    with pytest.raises(ValidationError) as exc_info:
        AIMDeployRequest(
            model="meta-llama-3-8b",
            adapterMode="static",
            maxLoraRank=32,
            engineArgs={"max-lora-rank": 32},
        )

    assert "engineArgs['max-lora-rank'] is not accepted" in str(exc_info.value)
    assert "requires adapterMode 'dynamic'" not in str(exc_info.value)


def test_aim_deploy_request_leaves_max_lora_rank_unset_by_default() -> None:
    assert AIMDeployRequest(model="meta-llama-3-8b").max_lora_rank is None


def test_aim_deploy_request_parses_camelcase_input() -> None:
    """Test AIMDeployRequest accepts camelCase keys from API/UI payload."""
    r = AIMDeployRequest(
        model="meta-llama-3-8b",
        imagePullSecrets=["secret1", "secret2"],
        hfToken="hf_secret_name",
        minReplicas=2,
        maxReplicas=10,
        autoScaling={"metrics": []},
    )
    assert r.image_pull_secrets == ["secret1", "secret2"]
    assert r.hf_token == "hf_secret_name"
    assert r.min_replicas == 2
    assert r.max_replicas == 10
    assert r.auto_scaling == {"metrics": []}


def test_aim_deploy_request_with_scaling() -> None:
    """Test AIMDeployRequest with scaling policy."""
    r = AIMDeployRequest(
        model="img",
        min_replicas=2,
        max_replicas=10,
        auto_scaling={"metrics": []},
    )
    assert r.min_replicas == 2
    assert r.max_replicas == 10


def test_aim_deploy_request_partial_scaling_fails() -> None:
    """Test partial scaling policy validation."""
    with pytest.raises(ValueError, match="Autoscaling requires all three fields"):
        AIMDeployRequest(model="img", min_replicas=2)

    with pytest.raises(ValueError, match="Autoscaling requires all three fields"):
        AIMDeployRequest(model="img", min_replicas=2, max_replicas=10)


def test_aim_deploy_request_max_gte_min() -> None:
    """Test max_replicas >= min_replicas validation."""
    with pytest.raises(ValueError, match="maxReplicas .* must be >= minReplicas"):
        AIMDeployRequest(model="img", min_replicas=10, max_replicas=5, auto_scaling={"metrics": []})
    with pytest.raises(ValueError, match="autoScaling cannot be empty"):
        AIMDeployRequest(model="img", min_replicas=1, max_replicas=5, auto_scaling={})


def test_aim_service_patch_request_empty() -> None:
    """Test empty patch request is valid."""
    r = AIMServicePatchRequest()
    assert r.min_replicas is None


def test_aim_service_patch_request_with_scaling() -> None:
    """Test patch request with scaling."""
    r = AIMServicePatchRequest(min_replicas=1, max_replicas=5, auto_scaling={"metrics": []})
    assert r.min_replicas == 1


def test_aim_service_patch_request_camelcase() -> None:
    """Test camelCase aliases."""
    r = AIMServicePatchRequest(**{"minReplicas": 3, "maxReplicas": 10, "autoScaling": {"metrics": []}})
    assert r.min_replicas == 3


def test_aim_service_patch_request_partial_fails() -> None:
    """Test partial scaling policy fails."""
    with pytest.raises(ValueError, match="Autoscaling requires all three fields"):
        AIMServicePatchRequest(min_replicas=2, max_replicas=10)


def test_aim_service_patch_request_min_replicas_validation() -> None:
    """Test min_replicas >= 1."""
    with pytest.raises(ValueError):
        AIMServicePatchRequest(min_replicas=0, max_replicas=10, auto_scaling={"metrics": []})


def test_aim_service_patch_request_max_gte_min() -> None:
    """Test max >= min validation."""
    with pytest.raises(ValueError, match="maxReplicas .* must be >= minReplicas"):
        AIMServicePatchRequest(min_replicas=10, max_replicas=5, auto_scaling={"metrics": []})


def test_aim_service_response_endpoints_with_httproute() -> None:
    """Test that AIMServiceResponse.endpoints returns proper values when both required conditions are ready."""
    conditions = [
        {"type": AIM_COND_INFERENCE_SERVICE_READY, "status": "True"},
        {"type": AIM_COND_HTTP_ROUTE_READY, "status": "True"},
    ]
    svc = make_aim_service_k8s(
        name="test-aim",
        namespace="default",
        status=AIMServiceStatus.RUNNING,
        with_httproute=True,
        as_response=True,
        conditions=conditions,
    )

    # Check endpoints are populated
    assert svc.endpoints != {}
    assert "internal" in svc.endpoints
    assert "external" in svc.endpoints
    assert svc.endpoints["internal"] == "http://test-aim-predictor.default.svc.cluster.local"
    assert svc.endpoints["external"].startswith(f"{CLUSTER_HOST}/default/")


def test_aim_service_response_endpoints_empty_when_conditions_not_ready() -> None:
    """Test that endpoints are empty when required conditions are not ready."""
    svc = make_aim_service_k8s(
        name="test-aim",
        namespace="default",
        status=AIMServiceStatus.PENDING,
        with_httproute=True,
        as_response=True,
        # No conditions provided = conditions not ready
    )

    assert svc.endpoints == {}


def test_aim_deploy_request_accepts_adapters() -> None:
    """Adapters and their admission mode arrive camelCase on the wire like every other field."""
    r = AIMDeployRequest(model="llama3-8b", adapters=["my-adapter"], adapterMode="dynamic")

    assert r.adapters == ["my-adapter"]
    assert r.adapter_mode is AdapterMode.DYNAMIC


def test_aim_deploy_request_defaults_adapters_to_absent() -> None:
    """Unset stays None rather than an empty list: an empty spec.adapters is its own declaration."""
    r = AIMDeployRequest(model="llama3-8b")

    assert r.adapters is None
    assert r.adapter_mode is None


def test_aim_deploy_request_rejects_repeated_adapters() -> None:
    """spec.adapters is an atomic list, so a repeat would attach the same artifact twice."""
    with pytest.raises(ValidationError, match="repeated: my-adapter"):
        AIMDeployRequest(model="llama3-8b", adapters=["my-adapter", "other-adapter", "my-adapter"])


def test_aim_deploy_request_rejects_more_adapters_than_the_crd_allows() -> None:
    """The cap is the CRD's own, refused here as a field error instead of an opaque admission failure."""
    with pytest.raises(ValidationError):
        AIMDeployRequest(model="llama3-8b", adapters=[f"adapter-{i}" for i in range(65)])


def test_aim_deploy_request_accepts_the_maximum_number_of_adapters() -> None:
    names = [f"adapter-{i}" for i in range(64)]

    assert AIMDeployRequest(model="llama3-8b", adapters=names).adapters == names


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("My-Adapter", id="uppercase"),
        pytest.param("my_adapter", id="underscore"),
        pytest.param("-my-adapter", id="leading-dash"),
        pytest.param("my adapter", id="space"),
        pytest.param("", id="empty"),
        pytest.param("a" * 254, id="too-long"),
    ],
)
def test_aim_deploy_request_rejects_names_no_artifact_could_have(name: str) -> None:
    """A name outside the CRD's own pattern is a 422 here rather than a K8s error in a gateway."""
    with pytest.raises(ValidationError):
        AIMDeployRequest(model="llama3-8b", adapters=[name])


def test_aim_service_patch_request_accepts_adapters() -> None:
    """The patch request carries the same adapters field, so a running deployment can change it."""
    r = AIMServicePatchRequest(adapters=["my-adapter"])

    assert r.adapters == ["my-adapter"]


def test_aim_service_patch_request_distinguishes_detach_all_from_untouched() -> None:
    """An empty list detaches everything, while an absent field leaves the adapter set alone —
    the two must not collapse into one value."""
    assert AIMServicePatchRequest(adapters=[]).adapters == []
    assert AIMServicePatchRequest().adapters is None


def test_aim_service_patch_request_rejects_repeated_adapters() -> None:
    with pytest.raises(ValidationError, match="repeated: my-adapter"):
        AIMServicePatchRequest(adapters=["my-adapter", "other-adapter", "my-adapter"])


def test_aim_service_patch_request_rejects_more_adapters_than_the_crd_allows() -> None:
    with pytest.raises(ValidationError):
        AIMServicePatchRequest(adapters=[f"adapter-{i}" for i in range(65)])


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("My-Adapter", id="uppercase"),
        pytest.param("my_adapter", id="underscore"),
        pytest.param("-my-adapter", id="leading-dash"),
        pytest.param("my adapter", id="space"),
        pytest.param("", id="empty"),
        pytest.param("a" * 254, id="too-long"),
    ],
)
def test_aim_service_patch_request_rejects_names_no_artifact_could_have(name: str) -> None:
    with pytest.raises(ValidationError):
        AIMServicePatchRequest(adapters=[name])
