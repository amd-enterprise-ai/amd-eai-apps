# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AIMs CRD Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.aims.crds import (
    AIMArtifactResource,
    AIMArtifactStatusFields,
    AIMImageMetadata,
    AIMModelMetadata,
    AIMModelResource,
    AIMModelSource,
    AIMModelSourceEnvVar,
    AIMModelStatusFields,
    AIMProfileSetResource,
    AIMServiceAdapterRef,
    AIMServiceResource,
    AIMServiceSpec,
    AIMServiceStatusFields,
    CachingConfig,
    HTTPRouteResource,
    ResolvedRef,
)
from app.aims.enums import AdapterState, AIMModelStatus, AIMServiceStatus, ResolutionScope
from app.aims.enums import AIMArtifactStatus as AIMArtifactStatusEnum
from app.dispatch.crds import K8sMetadata
from tests.factory import make_aim_cluster_model, make_aim_cluster_profile, make_aim_service_k8s


def test_aim_model_metadata_defaults() -> None:
    """Test AIMModelMetadata defaults."""
    m = AIMModelMetadata()
    assert m.canonical_name is None
    assert m.tags == []


def test_aim_model_metadata_with_values() -> None:
    """Test AIMModelMetadata with values."""
    m = AIMModelMetadata.model_validate(
        {
            "canonicalName": "meta/llama",
            "tags": ["chat"],
            "hfTokenRequired": True,
        }
    )
    assert m.canonical_name == "meta/llama"
    assert m.hf_token_required is True


def test_aim_image_metadata() -> None:
    """Test AIMImageMetadata."""
    m = AIMImageMetadata.model_validate(
        {
            "model": {"canonicalName": "test", "descriptionFull": "A full description"},
            "oci": {"description": "Short desc", "version": "1.0"},
        }
    )
    assert m.model.canonical_name == "test"
    assert m.model.description_full == "A full description"
    assert m.oci.description == "Short desc"
    assert m.oci.version == "1.0"


def test_aim_model_status_defaults() -> None:
    """Test AIMModelStatusFields defaults."""
    s = AIMModelStatusFields()
    assert s.status == AIMModelStatus.NOT_AVAILABLE


def test_aim_cluster_model_resource_with_factory() -> None:
    """Test AIMModelResource using factory."""
    aim = make_aim_cluster_model(name="my-model", image="docker.io/test:v1")

    assert aim.metadata.name == "my-model"
    assert aim.spec.image == "docker.io/test:v1"
    assert aim.status.status == AIMModelStatus.READY


def test_aim_cluster_model_resource_minimal() -> None:
    """Test parsing minimal AIMModelResource."""
    aim = AIMModelResource.model_validate({"metadata": {"name": "minimal"}})
    assert aim.metadata.name == "minimal"
    assert aim.spec.image == ""
    assert aim.status.status == AIMModelStatus.NOT_AVAILABLE


def test_aim_model_status_includes_failure_class_variants() -> None:
    """Both ``Failed`` and ``Error`` are recognized failure-class statuses.

    The engine emits ``Failed`` for terminal failures. ``Error`` is a parallel
    failure-class status defensively recognized so Pydantic does not reject the
    whole CR if aim-engine ever emits it.
    """
    assert AIMModelStatus("Failed") is AIMModelStatus.FAILED
    assert AIMModelStatus("Error") is AIMModelStatus.ERROR


def test_aim_service_spec_defaults() -> None:
    """Test AIMServiceSpec defaults."""
    s = AIMServiceSpec()
    assert s.replicas == 1
    assert s.min_replicas is None
    assert s.max_replicas is None
    assert s.auto_scaling is None


def test_aim_service_spec_with_scaling() -> None:
    """Test AIMServiceSpec with scaling."""
    s = AIMServiceSpec.model_validate(
        {
            "minReplicas": 2,
            "maxReplicas": 10,
            "autoScaling": {"metrics": []},
        }
    )
    assert s.min_replicas == 2
    assert s.max_replicas == 10


def test_aim_service_spec_caching_default() -> None:
    """AIMServiceSpec defaults caching.mode to Shared (v1alpha2 baseline that replaces cacheModel=true)."""
    s = AIMServiceSpec()
    assert isinstance(s.caching, CachingConfig)
    assert s.caching.mode == "Shared"


def test_aim_service_spec_caching_explicit() -> None:
    """AIMServiceSpec accepts an explicit caching config and exposes it on the model."""
    s = AIMServiceSpec.model_validate({"caching": {"mode": "None"}})
    assert s.caching.mode == "None"


def test_aim_service_status_fields() -> None:
    """Test AIMServiceStatusFields."""
    s = AIMServiceStatusFields()
    assert s.status == AIMServiceStatus.PENDING

    s2 = AIMServiceStatusFields.model_validate(
        {
            "status": "Running",
            "routing": {"path": "/v1/chat"},
        }
    )
    assert s2.status == AIMServiceStatus.RUNNING
    assert s2.routing["path"] == "/v1/chat"


def test_aim_service_resource_with_factory() -> None:
    """Test AIMServiceResource using factory."""
    svc = make_aim_service_k8s(
        namespace="my-ns",
        model_ref="llama3-8b",
        replicas=2,
        status=AIMServiceStatus.RUNNING,
    )

    assert svc.metadata.namespace == "my-ns"
    assert svc.spec.model.name == "llama3-8b"
    assert svc.spec.replicas == 2
    assert svc.status.status == AIMServiceStatus.RUNNING
    assert svc.id is not None  # Computed from label


def test_aim_service_resource_with_scaling() -> None:
    """Test AIMServiceResource with scaling policy."""
    svc = make_aim_service_k8s(min_replicas=2, max_replicas=10, auto_scaling={"metrics": []})

    assert svc.spec.min_replicas == 2
    assert svc.spec.max_replicas == 10


def test_aim_service_resource_backfills_model_name_from_resolved_model() -> None:
    """Legacy v1alpha1 deploy-by-image services have spec.model.name empty;
    the engine resolves the image and writes the AIMClusterModel resource name
    to status.resolvedModel.name. The validator backfills spec.model.name so
    FE consumers can always read it directly. TODO — drop when
    v1alpha1 is removed."""
    svc = AIMServiceResource(
        metadata=K8sMetadata(name="svc", namespace="ns"),
        spec=AIMServiceSpec.model_validate({"model": {"image": "amd/aim:0.8.5"}}),
        status=AIMServiceStatusFields(
            resolved_model=ResolvedRef(name="amd-aim-resource-name", scope="Cluster"),
        ),
    )

    assert svc.spec.model.name == "amd-aim-resource-name"
    # status is left untouched so engine-written data remains diagnosable.
    assert svc.status.resolved_model is not None
    assert svc.status.resolved_model.name == "amd-aim-resource-name"


def test_aim_service_resource_backfill_no_op_when_spec_name_set() -> None:
    """When spec.model.name is already set the validator leaves it alone,
    even if status.resolvedModel.name differs (e.g. v1alpha2 profile pipeline
    writes the canonical model id there, not a resource name)."""
    svc = AIMServiceResource(
        metadata=K8sMetadata(name="svc", namespace="ns"),
        spec=AIMServiceSpec.model_validate({"model": {"name": "amd-aim-resource-name"}}),
        status=AIMServiceStatusFields(
            resolved_model=ResolvedRef(name="amd/Llama-3.1-8B", scope="Cluster"),
        ),
    )

    assert svc.spec.model.name == "amd-aim-resource-name"


def test_aim_service_resource_backfill_no_op_when_resolved_model_missing() -> None:
    """When neither spec.model.name nor status.resolvedModel is set (pending
    reconcile), the validator leaves spec.model.name unset."""
    svc = AIMServiceResource(
        metadata=K8sMetadata(name="svc", namespace="ns"),
        spec=AIMServiceSpec.model_validate({"model": {"image": "amd/aim:0.8.5"}}),
        status=AIMServiceStatusFields(resolved_model=None),
    )

    assert svc.spec.model.name is None


def test_aim_service_model_ref_round_trips_extra_engine_keys() -> None:
    """spec.model carries engine-authored keys (selector/image) AIWB does not
    model; a read-modify-write round-trip must not silently drop them."""
    svc = AIMServiceResource.model_validate(
        {
            "metadata": {"name": "svc", "namespace": "ns"},
            "spec": {"model": {"name": "llama3-8b", "selector": {"metric": "throughput"}}},
        }
    )

    assert svc.spec.model.name == "llama3-8b"
    dumped = svc.model_dump(by_alias=True)
    assert dumped["spec"]["model"]["selector"] == {"metric": "throughput"}


def test_aim_model_source_env_typed_and_round_trips_extra_keys() -> None:
    """AIMModelSource.env parses into AIMModelSourceEnvVar with .name accessible,
    and preserves engine-authored keys (value/valueFrom) through a round-trip."""
    source = AIMModelSource.model_validate(
        {
            "modelId": "org/model",
            "sourceUri": "s3://bucket/model",
            "env": [
                {"name": "AWS_ENDPOINT_URL", "value": "http://minio.example.com"},
                {"name": "HF_TOKEN", "valueFrom": {"secretKeyRef": {"name": "hf", "key": "token"}}},
            ],
        }
    )

    assert source.env is not None
    assert [e.name for e in source.env] == ["AWS_ENDPOINT_URL", "HF_TOKEN"]
    assert isinstance(source.env[0], AIMModelSourceEnvVar)

    dumped = source.model_dump(by_alias=True, exclude_none=True)
    assert dumped["env"][0]["value"] == "http://minio.example.com"
    assert dumped["env"][1]["valueFrom"] == {"secretKeyRef": {"name": "hf", "key": "token"}}


def test_aim_profile_set_round_trips_extra_engine_keys() -> None:
    """The set carries selector at the top level (not under derivedFrom); unmodeled
    engine keys on the selector/overrides and top-level spec keys (image,
    sourceRef) must survive a read-modify-write round-trip."""
    profile_set = AIMProfileSetResource.model_validate(
        {
            "metadata": {"name": "m-profiles-abc", "namespace": "ns"},
            "spec": {
                "selector": {"role": "base", "precision": "fp8"},
                "overrides": {"aimId": "org/model", "engine": "vllm"},
                "versionPolicy": "all",
                "image": "amdenterpriseai/aim-base:0.11",
            },
        }
    )

    assert profile_set.spec.selector.role == "base"
    # versionPolicy populates the snake_case field via the global to_camel alias
    # generator (no explicit per-field alias needed) and re-emits camelCase.
    assert profile_set.spec.version_policy == "all"
    dumped = profile_set.spec.model_dump(by_alias=True, exclude_none=True)
    assert dumped["selector"]["precision"] == "fp8"
    assert dumped["overrides"]["engine"] == "vllm"
    assert dumped["image"] == "amdenterpriseai/aim-base:0.11"
    assert dumped["versionPolicy"] == "all"


def test_aim_cluster_profile_with_factory() -> None:
    """Test AIMProfileResource using factory (v1alpha2)."""
    profile = make_aim_cluster_profile(name="my-profile", aim_id="org/llama", metric="throughput")

    assert profile.metadata.name == "my-profile"
    assert profile.spec.aim_id == "org/llama"
    assert profile.spec.metric == "throughput"


def test_httproute_resource_from_dict() -> None:
    """Test HTTPRouteResource parsing from Kubernetes API dict."""
    route_dict = {
        "metadata": {"name": "my-route", "namespace": "test-ns"},
        "spec": {
            "rules": [
                {
                    "backendRefs": [{"kind": "Service", "name": "my-svc-predictor", "port": 80}],
                    "matches": [{"path": {"type": "PathPrefix", "value": "/v1/chat"}}],
                }
            ]
        },
    }
    route = HTTPRouteResource.model_validate(route_dict)
    assert route.metadata.name == "my-route"
    assert route.spec.rules[0].backend_refs[0].name == "my-svc-predictor"


def test_aim_artifact_status_resolved_parent_parsed() -> None:
    """AIMArtifactResource.model_validate captures status.resolvedParent from camelCase K8s payload."""
    raw = {
        "metadata": {"name": "hf---google-gemma-3-1b-it-6fe1ff2eb8", "namespace": "workbench"},
        "status": {
            "resolvedParent": {
                "kind": "AIMArtifact",
                "name": "hf---google-gemma-3-1b-it-6fe1ff2eb8",
                "namespace": "workbench",
                "scope": "Namespace",
                "uid": "83269fe1-9163-4e8b-a3fe-f4c2f268e848",
            }
        },
    }
    resource = AIMArtifactResource.model_validate(raw)

    assert resource.status.resolved_parent is not None
    rp = resource.status.resolved_parent
    assert rp.kind == "AIMArtifact"
    assert rp.name == "hf---google-gemma-3-1b-it-6fe1ff2eb8"
    assert rp.namespace == "workbench"
    assert rp.scope == "Namespace"
    assert rp.uid == "83269fe1-9163-4e8b-a3fe-f4c2f268e848"


def test_aim_artifact_status_resolved_parent_emitted_camel_case() -> None:
    """model_dump(by_alias=True) emits resolvedParent in camelCase for K8s/API round-trips."""
    artifact = AIMArtifactResource(
        metadata=K8sMetadata(name="hf---google-gemma-3-1b-it-6fe1ff2eb8", namespace="workbench"),
        status=AIMArtifactStatusFields(
            resolved_parent=ResolvedRef(
                kind="AIMArtifact",
                name="hf---google-gemma-3-1b-it-6fe1ff2eb8",
                namespace="workbench",
                scope="Namespace",
                uid="83269fe1-9163-4e8b-a3fe-f4c2f268e848",
            )
        ),
    )

    dumped = artifact.model_dump(by_alias=True)
    assert "resolvedParent" in dumped["status"]
    rp = dumped["status"]["resolvedParent"]
    assert rp["kind"] == "AIMArtifact"
    assert rp["name"] == "hf---google-gemma-3-1b-it-6fe1ff2eb8"
    assert rp["namespace"] == "workbench"
    assert rp["scope"] == "Namespace"
    assert rp["uid"] == "83269fe1-9163-4e8b-a3fe-f4c2f268e848"


def test_aim_artifact_status_resolved_parent_absent_by_default() -> None:
    """resolvedParent is None when the K8s status does not include it."""
    resource = AIMArtifactResource.model_validate({"metadata": {"name": "minimal"}})
    assert resource.status.resolved_parent is None


def test_aim_artifact_preserves_unmodelled_controller_fields() -> None:
    """The controller reports more than we model, and it reaches clients through these objects. Keys
    we have not declared must survive a validate/dump round-trip rather than being silently dropped."""
    raw = {
        "metadata": {"name": "adapter-abcd1234", "namespace": "workbench"},
        "spec": {"type": "adapter", "sourceUri": "s3://bucket/ns/adapters/a/", "mode": "Cached"},
        "status": {
            "status": "Ready",
            "allocatedSize": "12Gi",
            "progress": 100,
            "persistentVolumeClaim": "pvc-adapter-abcd1234",
            "download": {"attempt": 2, "totalAttempts": 3, "protocol": "s3", "unexpectedKey": "kept"},
        },
    }

    dumped = AIMArtifactResource.model_validate(raw).model_dump(by_alias=True, exclude_none=True)

    assert dumped["spec"]["mode"] == "Cached"
    assert dumped["status"]["allocatedSize"] == "12Gi"
    assert dumped["status"]["progress"] == 100
    assert dumped["status"]["persistentVolumeClaim"] == "pvc-adapter-abcd1234"
    assert dumped["status"]["download"]["totalAttempts"] == 3
    assert dumped["status"]["download"]["unexpectedKey"] == "kept"


def test_aim_service_status_adapters_absent_by_default() -> None:
    """A service the engine reports no adapters for is distinguishable from one serving none."""
    assert AIMServiceStatusFields().adapters is None


def test_aim_service_status_reports_every_adapter_state() -> None:
    """Every state in the CRD enum must survive the round-trip; an unparsed one would blank the row."""
    raw = {
        "adapters": [{"name": f"adapter-{i}", "state": state.value} for i, state in enumerate(AdapterState)],
    }

    status = AIMServiceStatusFields.model_validate(raw)

    assert [a.state for a in status.adapters or []] == list(AdapterState)
    # AdapterState is a str enum, so the equality above holds just as well for a plain string. The
    # union that lets unknown states through must not quietly degrade the known ones to that.
    assert all(type(a.state) is AdapterState for a in status.adapters or [])


def test_aim_service_status_keeps_a_state_the_engine_adds_later() -> None:
    """A state newer than this enum must not sink the whole service.

    Validation is all-or-nothing per resource: were the unknown value rejected, the deployment would
    vanish from the list and 404 on the get, over a status field nothing branches on.
    """
    raw = {"adapters": [{"name": "my-adapter", "state": "SomeFutureState"}]}

    adapter = AIMServiceStatusFields.model_validate(raw).adapters[0]

    assert adapter.state == "SomeFutureState"


def test_aim_service_status_adapter_round_trips_engine_detail() -> None:
    """The per-adapter row is passed through verbatim, including fields we have not modelled."""
    raw = {
        "adapters": [
            {
                "name": "my-adapter",
                "state": "Loaded",
                "adapterPath": "/adapters/my-adapter",
                "modelId": "org/my-adapter",
                "lastError": "",
                "lastObserved": "2026-08-12T10:30:00Z",
                "loadedReplicas": "3/3",
                "unexpectedKey": "kept",
            }
        ]
    }

    adapter = AIMServiceStatusFields.model_validate(raw).adapters[0]

    assert adapter.state is AdapterState.LOADED
    assert adapter.adapter_path == "/adapters/my-adapter"
    assert adapter.model_id == "org/my-adapter"
    assert adapter.loaded_replicas == "3/3"
    assert adapter.last_observed == datetime(2026, 8, 12, 10, 30, tzinfo=UTC)
    dumped = AIMServiceStatusFields.model_validate(raw).model_dump(by_alias=True, exclude_none=True)
    assert dumped["adapters"][0]["unexpectedKey"] == "kept"


def test_resolved_ref_scope_resolves_known_values_to_the_enum() -> None:
    """Known scopes must still resolve to the enum so they stay comparable and documented."""
    ref = ResolvedRef.model_validate({"name": "foo", "scope": "Cluster"})

    assert ref.scope is ResolutionScope.CLUSTER


def test_resolved_ref_keeps_a_scope_the_engine_adds_later() -> None:
    """A scope newer than this enum must not sink the whole resource carrying the reference."""
    ref = ResolvedRef.model_validate({"name": "foo", "scope": "SomeFutureScope"})

    assert ref.scope == "SomeFutureScope"


def test_aim_artifact_status_resolves_known_status_to_the_enum() -> None:
    """Known artifact statuses must still resolve to the enum so they stay comparable."""
    status = AIMArtifactStatusFields.model_validate({"status": "Ready"})

    assert status.status is AIMArtifactStatusEnum.READY


def test_aim_artifact_status_keeps_a_status_the_engine_adds_later() -> None:
    """A status newer than this enum must not sink the whole artifact over a field nothing branches on."""
    status = AIMArtifactStatusFields.model_validate({"status": "SomeFutureStatus"})

    assert status.status == "SomeFutureStatus"


def test_aim_service_adapter_ref_defaults_to_the_only_kind_the_engine_reads() -> None:
    ref = AIMServiceAdapterRef(name="my-adapter")

    assert ref.kind == "AIMArtifact"
    assert ref.model_dump(by_alias=True, exclude_none=True) == {"kind": "AIMArtifact", "name": "my-adapter"}


def test_aim_service_adapter_ref_rejects_another_kind() -> None:
    """The reference shape is the contract with aim-engine, not a free-form object reference."""
    with pytest.raises(ValidationError):
        AIMServiceAdapterRef.model_validate({"kind": "ConfigMap", "name": "my-adapter"})
