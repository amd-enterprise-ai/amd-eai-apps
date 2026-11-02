# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the adapter gate a deploy passes, and for changing adapters on a running service."""

import asyncio
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from kubernetes_asyncio.client import ApiException
from minio.error import S3Error

from api_common.exceptions import (
    ConflictException,
    ExternalServiceError,
    InconsistentStateException,
    NotFoundException,
    ValidationException,
)
from app.aims.constants import ADAPTER_PROFILE_FEATURE, AIM_PROFILE_SOURCE_MODEL_LABEL
from app.aims.crds import (
    AIMArtifactResource,
    AIMArtifactSpec,
    AIMModelResource,
    AIMModelSpec,
    AIMModelStatusFields,
    AIMProfileResource,
    AIMProfileSpec,
    AIMProfileStatus,
    AIMServiceResource,
    ResolvedRef,
)
from app.aims.enums import AdapterMode, AIMModelStatus
from app.aims.schemas import _MAX_ADAPTERS, AIMDeployRequest
from app.aims.service import ScalingPolicy, deploy_aim, update_aim_service_spec
from app.artifacts.readiness import OBJECT_MISSING_CODE, READINESS_ADAPTER_CONCURRENCY
from app.artifacts.schemas import REQUIRED_PEFT_FILENAMES, ReadinessState
from app.artifacts.service import MANAGED_BY_FINE_TUNING, MANAGED_BY_LABEL, MANAGED_BY_VALUE
from app.dispatch.crds import K8sMetadata
from app.dispatch.kube_client import KubernetesClient
from app.minio import MinioClient
from app.minio.config import MINIO_BUCKET
from tests.factory import make_aim_cluster_model, make_aim_service_k8s

NAMESPACE = "test-namespace"
BASE_AIM_ID = "meta-llama/llama3-8b"
# A weights identity distinct from the group one, so a test asserting on either cannot pass on the
# other: every quantised variant shares the group id but names its own model id.
BASE_MODEL_ID = "meta-llama/llama3-8b-fp8"
# A second quantisation sharing that group, so a test can tell "some profile in the group publishes
# these weights" apart from "a profile this deploy could actually resolve does".
SIBLING_MODEL_ID = "meta-llama/llama3-8b-bf16"
ADAPTER_NAME = "my-adapter"


@pytest.fixture
def kube_client() -> AsyncMock:
    """Kube client whose gateway calls are patched, kept spec'd to catch interface drift."""
    return AsyncMock(spec=KubernetesClient)


@pytest.fixture
def minio_client() -> MagicMock:
    """Storage client whose stats succeed, i.e. the adapter's weights are fully uploaded."""
    client = MagicMock(spec=MinioClient)
    client.stat_object.return_value = MagicMock()
    return client


def _s3_error(code: str) -> S3Error:
    """Build the S3Error minio-py would raise for the given error code."""
    return S3Error(
        code=code,
        message=code,
        resource="/bucket/object",
        request_id="request123",
        host_id="host123",
        response=MagicMock(status=404 if code == OBJECT_MISSING_CODE else 503),
    )


def _adapter(
    name: str = ADAPTER_NAME,
    *,
    compatible_with: Sequence[str] | None = (BASE_AIM_ID,),
    managed_by: str = MANAGED_BY_VALUE,
    artifact_type: str = "adapter",
    source_uri: str | None = f"s3://{MINIO_BUCKET}/{NAMESPACE}/adapters/{ADAPTER_NAME}/",
) -> AIMArtifactResource:
    return AIMArtifactResource(
        metadata=K8sMetadata(name=name, namespace=NAMESPACE, labels={MANAGED_BY_LABEL: managed_by}),
        spec=AIMArtifactSpec(
            type=artifact_type,
            source_uri=source_uri,
            compatible_with=None if compatible_with is None else list(compatible_with),
        ),
    )


def _namespace_model(*, aim_id: str | None = BASE_AIM_ID) -> AIMModelResource:
    return AIMModelResource(
        metadata=K8sMetadata(name="wb-finetune-job", namespace=NAMESPACE),
        spec=AIMModelSpec(),
        status=AIMModelStatusFields(**({"aimId": aim_id} if aim_id is not None else {})),
    )


def _published_profile(
    *,
    model_id: str = BASE_MODEL_ID,
    status: str = AIMModelStatus.READY,
    name: str = "published-profile",
    features: Sequence[str] = (ADAPTER_PROFILE_FEATURE,),
    precision: str | None = None,
    model_name: str | None = "llama3-8b",
) -> AIMProfileResource:
    """A profile of the base model, i.e. the model's own statement that it serves those weights.

    Adapter-capable by default because that is what makes the weights it names a place an adapter
    could actually land; a test proving the capability matters passes ``features=()``.

    ``model_name`` is the model this profile records as its source, stamped under the provenance
    key aim-engine itself writes and selects on, so these fixtures carry the metadata a real
    cluster would rather than whatever key the filter happens to read. It defaults to the model
    these tests deploy, so a test that cares about a sibling version says so explicitly; ``None``
    leaves the profile unstamped, as a profile predating that provenance is.
    """
    return AIMProfileResource(
        metadata=K8sMetadata(
            name=name,
            namespace=NAMESPACE,
            labels={} if model_name is None else {AIM_PROFILE_SOURCE_MODEL_LABEL: model_name},
        ),
        spec=AIMProfileSpec(model_id=model_id, aim_id=BASE_AIM_ID, features=list(features), precision=precision),
        status=AIMProfileStatus(status=status),
    )


def _adapters_profile(
    *, features: Sequence[str] = (ADAPTER_PROFILE_FEATURE,), model_id: str | None = None
) -> AIMProfileResource:
    """A profile a request pins by name. ``model_id`` is unset by default, as a profile predating
    the field states no weights and leaves the gate with nothing to read off it."""
    return AIMProfileResource(
        metadata=K8sMetadata(name="pinned-profile", namespace=NAMESPACE),
        spec=AIMProfileSpec(features=list(features), model_id=model_id),
        # Ready is what makes the namespace path pin this profile; the cluster path ignores status.
        status=AIMProfileStatus(status=AIMModelStatus.READY),
    )


@contextmanager
def _deploy_env(
    *,
    cluster_model: AIMModelResource | None = None,
    namespace_model: AIMModelResource | None = None,
    artifacts: dict[str, AIMArtifactResource | None | Exception] | None = None,
    namespaced_profile: AIMProfileResource | None = None,
    cluster_profile: AIMProfileResource | None = None,
    model_profile: AIMProfileResource | None = None,
    published_profiles: Sequence[AIMProfileResource] = (),
) -> Iterator[SimpleNamespace]:
    """Patch every k8s read and write ``deploy_aim`` makes, exposing the mocks tests assert on.

    ``model_profile`` is the AIMProfile a namespace model derives and pins, as opposed to
    ``namespaced_profile``/``cluster_profile``, which resolve a name the request pinned.

    ``published_profiles`` are the profiles the base model publishes, which is where the weights it
    serves are named; a model seeded with none has said nothing about what it serves.
    """
    lookups = artifacts or {}

    def _lookup(_kube_client: object, _namespace: str, name: str) -> AIMArtifactResource | None:
        result = lookups[name]
        if isinstance(result, Exception):
            raise result
        return result

    mocks = SimpleNamespace(
        get_artifact=AsyncMock(side_effect=_lookup),
        get_namespaced_profile=AsyncMock(return_value=namespaced_profile),
        get_cluster_profile=AsyncMock(return_value=cluster_profile),
        create_cluster_service=AsyncMock(return_value=make_aim_service_k8s()),
        create_namespace_service=AsyncMock(return_value=make_aim_service_k8s()),
        list_cluster_profiles=AsyncMock(return_value=list(published_profiles)),
        list_namespace_profiles=AsyncMock(return_value=[]),
    )

    with (
        patch("app.aims.service.list_aim_cluster_profiles", mocks.list_cluster_profiles),
        patch("app.aims.service.list_aim_profiles", mocks.list_namespace_profiles),
        patch("app.aims.service.get_aim_by_name", AsyncMock(return_value=cluster_model)),
        patch("app.aims.service.get_aim_model_from_k8s", AsyncMock(return_value=namespace_model)),
        patch("app.aims.service.find_aim_profile_for_model", AsyncMock(return_value=model_profile)),
        patch("app.aims.service.get_aim_artifact", mocks.get_artifact),
        patch("app.aims.service.get_aim_profile_from_k8s", mocks.get_namespaced_profile),
        patch("app.aims.service.get_aim_cluster_profile_from_k8s", mocks.get_cluster_profile),
        patch("app.aims.gateway.get_aim_profile_by_name", mocks.get_namespaced_profile),
        patch("app.aims.gateway.get_aim_cluster_profile_by_name", mocks.get_cluster_profile),
        patch("app.aims.service.create_aim_service_in_k8s", mocks.create_cluster_service),
        patch("app.aims.service.create_namespace_aim_service_in_k8s", mocks.create_namespace_service),
    ):
        yield mocks


def _running_service(
    *,
    adapter_mode: AdapterMode | None = AdapterMode.DYNAMIC,
    model_ref: str = "llama3-8b",
    resolved_profile_name: str | None = None,
) -> AIMServiceResource:
    """A deployed AIMService as ``update_aim_service_spec`` reads it back from the cluster."""
    service = make_aim_service_k8s(namespace=NAMESPACE, model_ref=model_ref)
    service.spec.adapter_mode = adapter_mode
    if resolved_profile_name:
        service.status.resolved_profile = ResolvedRef(name=resolved_profile_name)
    return service


@contextmanager
def _patch_env(
    *,
    service: AIMServiceResource | None,
    cluster_model: AIMModelResource | None = None,
    namespace_model: AIMModelResource | None = None,
    artifacts: dict[str, AIMArtifactResource | None | Exception] | None = None,
    namespaced_profile: AIMProfileResource | None = None,
    patch_result: AIMServiceResource | Exception | None = None,
    published_profiles: Sequence[AIMProfileResource] = (),
) -> Iterator[SimpleNamespace]:
    """Patch every k8s read and write ``update_aim_service_spec`` makes, exposing the mocks tests assert on.

    The profile lookups are patched only so a test can prove the change path never reaches them;
    ``namespaced_profile`` seeds one that would refuse the change if it did.
    """
    lookups = artifacts or {}

    def _lookup(_kube_client: object, _namespace: str, name: str) -> AIMArtifactResource | None:
        result = lookups[name]
        if isinstance(result, Exception):
            raise result
        return result

    patch_outcome = patch_result if patch_result is not None else make_aim_service_k8s(namespace=NAMESPACE)
    mocks = SimpleNamespace(
        get_service=AsyncMock(return_value=service),
        get_artifact=AsyncMock(side_effect=_lookup),
        get_namespaced_profile=AsyncMock(return_value=namespaced_profile),
        get_cluster_profile=AsyncMock(return_value=None),
        patch_spec=AsyncMock(
            side_effect=patch_outcome if isinstance(patch_outcome, Exception) else None,
            return_value=None if isinstance(patch_outcome, Exception) else patch_outcome,
        ),
        list_cluster_profiles=AsyncMock(return_value=list(published_profiles)),
        list_namespace_profiles=AsyncMock(return_value=[]),
    )

    with (
        patch("app.aims.service.list_aim_cluster_profiles", mocks.list_cluster_profiles),
        patch("app.aims.service.list_aim_profiles", mocks.list_namespace_profiles),
        patch("app.aims.service.get_aim_service_from_k8s", mocks.get_service),
        patch("app.aims.service.get_aim_cluster_model_strict", AsyncMock(return_value=cluster_model)),
        patch("app.aims.service.get_aim_model_from_k8s", AsyncMock(return_value=namespace_model)),
        patch("app.aims.service.get_aim_artifact", mocks.get_artifact),
        patch("app.aims.service.get_aim_profile_from_k8s", mocks.get_namespaced_profile),
        patch("app.aims.service.get_aim_cluster_profile_from_k8s", mocks.get_cluster_profile),
        patch("app.aims.gateway.get_aim_profile_by_name", mocks.get_namespaced_profile),
        patch("app.aims.gateway.get_aim_cluster_profile_by_name", mocks.get_cluster_profile),
        patch("app.aims.service.patch_aim_service_spec_in_k8s", mocks.patch_spec),
    ):
        yield mocks


async def test_deploy_attaches_a_compatible_ready_adapter(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """A platform-managed adapter that lists the base model and has its weights uploaded deploys."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME], profile_name="pinned-profile")

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
        namespaced_profile=_adapters_profile(),
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    assert mocks.create_cluster_service.await_args.kwargs["deploy_request"].adapters == [ADAPTER_NAME]
    # The readiness probe really ran on this path rather than being skipped into a pass.
    assert minio_client.stat_object.call_count == len(REQUIRED_PEFT_FILENAMES)


async def test_deploy_admits_a_model_id_only_adapter_on_the_selector_path(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Naming only the weights is the correct declaration, and the selector path has no profile.

    Without a pinned ``profile_name`` aim-engine resolves the profile after the CR is written, so
    the gate has no profile to read a modelId off, and the model's own profiles are what confirm
    the adapter names weights this model serves. The deploy is then pinned to that identity, which
    is what makes the adapter loadable against whatever aim-engine picks.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID,))},
        published_profiles=[_published_profile()],
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    kwargs = mocks.create_cluster_service.await_args.kwargs
    assert kwargs["deploy_request"].adapters == [ADAPTER_NAME]
    # The weights that admitted the adapter are the weights the deploy is narrowed to; a gate that
    # admitted on one identity and pinned another would deploy something the adapter cannot load.
    assert kwargs["pinned_model_id"] == BASE_MODEL_ID
    # No profile was resolved, so nothing but the adapter's declaration could have supplied this.
    mocks.get_namespaced_profile.assert_not_awaited()
    mocks.get_cluster_profile.assert_not_awaited()


async def test_deploy_refuses_a_model_id_only_adapter_the_model_does_not_publish(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Weights the model does not serve are refused by name, however confidently declared.

    The adapter names one weights identity and nothing else, so it cannot be admitted on the model
    group either. Were its own declaration allowed to stand in for the profile's, it would agree
    with itself and pass — the model's profiles are what make the two cases distinguishable.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter(compatible_with=("org/some-other-model-fp8",))},
            published_profiles=[_published_profile()],
        ) as mocks,
        pytest.raises(ValidationException, match=f"'{ADAPTER_NAME}' does not list model 'llama3-8b'"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_ignores_weights_only_a_failed_profile_advertises(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A profile that never reconciled is not the model serving those weights."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID,))},
            published_profiles=[_published_profile(status="Failed")],
        ) as mocks,
        pytest.raises(ValidationException, match="among the models it can serve"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_falls_back_to_the_group_when_the_model_publishes_nothing(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A model with no Ready profile has said nothing, and nothing is not a mismatch.

    The adapter declares the group as well, which is what the gate asked for before weights entered
    it; refusing here would block a deploy that works on the strength of missing evidence.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_AIM_ID, BASE_MODEL_ID))},
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    # Unconfirmed weights narrow nothing: the selector is left as unconstrained as it is without
    # adapters rather than pinned to an identity the model never claimed.
    assert mocks.create_cluster_service.await_args.kwargs["pinned_model_id"] is None


async def test_deploy_does_not_pin_when_adapters_name_different_weights(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Disagreement narrows nothing and refuses nothing; the group arm still admits both."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME, "other-adapter"])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={
            ADAPTER_NAME: _adapter(compatible_with=(BASE_AIM_ID, BASE_MODEL_ID)),
            "other-adapter": _adapter(name="other-adapter", compatible_with=(BASE_AIM_ID, "meta-llama/llama3-8b-fp16")),
        },
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    assert mocks.create_cluster_service.await_args.kwargs["pinned_model_id"] is None


async def test_deploy_pins_weights_whose_id_is_also_the_group_id(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """An unquantised base states one string twice, and the profile catalog says which it is here.

    The BF16 profile's ``modelId`` is the group id its quantised sibling also carries, so an adapter
    declaring those weights — what a producer recording a modelId emits — is indistinguishable from
    one declaring only the family until the model is asked. Read as a family name it would narrow
    nothing, and the unconstrained selector could resolve to the FP8 sibling the adapter cannot
    load: precisely the runtime failure the pin exists to prevent.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_AIM_ID,))},
        published_profiles=[
            _published_profile(model_id=BASE_AIM_ID, name="unquantised"),
            _published_profile(model_id=BASE_MODEL_ID, name="quantised-sibling"),
        ],
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    pinned = mocks.create_cluster_service.await_args.kwargs["pinned_model_id"]
    assert pinned == BASE_AIM_ID
    # Named rather than implied: the sibling shares the group id, so a pin that landed on it would
    # still look like a match on every identity the gate compares.
    assert pinned != BASE_MODEL_ID


async def test_deploy_pins_the_one_declared_variant_the_model_serves(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Several declared weights are not disagreement when the model serves exactly one of them.

    Counted on their own they abstain, and abstaining leaves the adapter judged against the group
    alone — which it never declared, so the selector path refuses an adapter that pinning the same
    profile by name accepts. The catalog is what turns the declaration into the one servable answer.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID, "meta-llama/llama3-8b-fp16"))},
        published_profiles=[_published_profile(model_id=BASE_MODEL_ID)],
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    assert mocks.create_cluster_service.await_args.kwargs["pinned_model_id"] == BASE_MODEL_ID


async def test_deploy_refuses_weights_only_a_sibling_model_version_publishes(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Another version's profile is not this deploy's candidate, however the group id is shared.

    Two versions of a model share one aimId, so the group listing answers for both. Admitting on a
    profile belonging to the other version would pin weights this service can never resolve, and
    the deploy would be accepted only to fail minutes later with no candidate profile.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter(compatible_with=(SIBLING_MODEL_ID,))},
            published_profiles=[_published_profile(model_id=SIBLING_MODEL_ID, model_name="llama3-8b-v2")],
        ) as mocks,
        pytest.raises(ValidationException, match=f"'{ADAPTER_NAME}' does not list model 'llama3-8b'"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_does_not_pin_weights_of_a_precision_the_request_excludes(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A precision the request rules out cannot supply the pin, because the engine ANDs the two.

    The adapter names the BF16 weights and the group, and both quantisations are published and
    adapter-capable. Pinning the BF16 weights on a request asking for fp8 would emit a selector
    carrying both, which no profile satisfies; the adapter is instead admitted on the group, exactly
    as it was before weights entered the gate.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME], precision="fp8")

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_AIM_ID, SIBLING_MODEL_ID))},
        published_profiles=[
            _published_profile(model_id=SIBLING_MODEL_ID, name="bf16-profile", precision="bf16"),
            _published_profile(model_id=BASE_MODEL_ID, name="fp8-profile", precision="fp8"),
        ],
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    assert mocks.create_cluster_service.await_args.kwargs["pinned_model_id"] is None


async def test_deploy_pins_one_of_several_weights_the_model_publishes(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Several servable answers are a choice, not an impasse, and the adapter declares them all.

    Neither declared id is the group id, so abstaining here is a refusal rather than neutrality: the
    gate would fall back to an identity the adapter never named. One eligible candidate is pinned,
    picked by sorted order so a retry of the same request deploys the same weights.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID, SIBLING_MODEL_ID))},
        published_profiles=[
            _published_profile(model_id=BASE_MODEL_ID, name="fp8-profile"),
            _published_profile(model_id=SIBLING_MODEL_ID, name="bf16-profile"),
        ],
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    assert mocks.create_cluster_service.await_args.kwargs["pinned_model_id"] == SIBLING_MODEL_ID


async def test_deploy_pins_the_requested_versions_weights_over_a_sibling_the_adapter_also_declares(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A sibling version's weights cannot win the pin merely because the adapter declares them too.

    Both versions share the group id, so one listing answers for both, and each publishes its own
    Ready adapter-capable profile. Only a profile of the version being deployed can satisfy the
    selector this request writes, so pinning the sibling's weights emits a conjunction no profile
    of that version matches and the service never resolves — while the requested version's own
    weights were published, declared by the adapter, and a valid answer all along.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID, SIBLING_MODEL_ID))},
        published_profiles=[
            _published_profile(model_id=SIBLING_MODEL_ID, name="v2-bf16-profile", model_name="llama3-8b-v2"),
            _published_profile(model_id=BASE_MODEL_ID, name="fp8-profile"),
        ],
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    assert mocks.create_cluster_service.await_args.kwargs["pinned_model_id"] == BASE_MODEL_ID


async def test_deploy_pins_weights_published_by_a_profile_carrying_no_provenance(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """An unstamped profile is a gap in provenance, not a statement that it belongs to a sibling.

    Nothing about it names another model, so excluding it would abstain from a pin this deploy can
    make and cost the user the weights the adapter was built for.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID,))},
        published_profiles=[_published_profile(model_id=BASE_MODEL_ID, model_name=None)],
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    assert mocks.create_cluster_service.await_args.kwargs["pinned_model_id"] == BASE_MODEL_ID


async def test_deploy_ignores_weights_only_an_adapter_incapable_profile_publishes(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A runtime that cannot host adapters is not somewhere an adapter can land, Ready or not."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID,))},
            published_profiles=[_published_profile(features=())],
        ) as mocks,
        pytest.raises(ValidationException, match="among the models it can serve"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_reads_no_profile_catalog_when_it_could_not_use_the_answer(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Resolving declarations against the catalog must not make listings the common case.

    The rule is narrower than "no profile is pinned": the listing is skipped wherever the weights
    are already known, which is a deploy naming no adapters and a pinned profile that states its
    modelId. A pinned profile predating that field states none, and there the listing is what admits
    a modelId-only adapter — so it is read, and its answer is used rather than wasted.
    """
    with _deploy_env(cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID)) as mocks:
        await deploy_aim(
            kube_client, AIMDeployRequest(model="llama3-8b"), NAMESPACE, "user@example.com", minio_client=minio_client
        )

    mocks.list_cluster_profiles.assert_not_awaited()
    mocks.list_namespace_profiles.assert_not_awaited()

    pinned = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME], profile_name="pinned-profile")

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID,))},
        namespaced_profile=_adapters_profile(model_id=BASE_MODEL_ID),
    ) as mocks:
        await deploy_aim(kube_client, pinned, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.list_cluster_profiles.assert_not_awaited()
    mocks.list_namespace_profiles.assert_not_awaited()

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(BASE_MODEL_ID,))},
        namespaced_profile=_adapters_profile(),
        published_profiles=[_published_profile()],
    ) as mocks:
        await deploy_aim(kube_client, pinned, NAMESPACE, "user@example.com", minio_client=minio_client)

    # Read, and load-bearing: without it this adapter names nothing the gate could match, since it
    # declares no group id and the pinned profile supplied no weights to compare against.
    mocks.list_cluster_profiles.assert_awaited_once()
    mocks.create_cluster_service.assert_awaited_once()


async def test_deploy_without_adapters_never_looks_one_up(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """The gate is inert for a deployment that neither names adapters nor opens itself to them."""
    with _deploy_env(cluster_model=make_aim_cluster_model(name="llama3-8b")) as mocks:
        await deploy_aim(
            kube_client, AIMDeployRequest(model="llama3-8b"), NAMESPACE, "user@example.com", minio_client=minio_client
        )

    mocks.get_artifact.assert_not_awaited()
    minio_client.stat_object.assert_not_called()


async def test_deploy_rejects_an_adapter_that_does_not_exist(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """A name that resolves to nothing is refused by name, so the user knows which one."""
    request = AIMDeployRequest(model="llama3-8b", adapters=["ghost-adapter"])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={"ghost-adapter": None},
        ) as mocks,
        pytest.raises(ValidationException, match="'ghost-adapter' is not an adapter in this project"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


@pytest.mark.parametrize(
    "artifact",
    [
        pytest.param(_adapter(managed_by="someone-else"), id="foreign-author"),
        pytest.param(_adapter(managed_by=""), id="unlabelled"),
        pytest.param(_adapter(artifact_type="model"), id="not-an-adapter-type"),
    ],
)
async def test_deploy_rejects_an_artifact_this_api_does_not_own(
    kube_client: AsyncMock, minio_client: MagicMock, artifact: AIMArtifactResource
) -> None:
    """Only platform-authored adapters are attachable; anything else reads as absent."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: artifact},
        ) as mocks,
        pytest.raises(ValidationException, match=f"'{ADAPTER_NAME}' is not an adapter in this project"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


@pytest.mark.parametrize("compatible_with", [None, ()], ids=["null", "empty"])
async def test_deploy_rejects_an_adapter_declaring_no_base_models(
    kube_client: AsyncMock, minio_client: MagicMock, compatible_with: Sequence[str] | None
) -> None:
    """An adapter that names no base models is unattachable, and is not blamed on its parent."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter(compatible_with=compatible_with)},
        ),
        pytest.raises(ValidationException) as exc_info,
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    assert "does not declare which base models it can serve" in str(exc_info.value)
    # The absent declaration is the adapter's own, so pointing at a parent reference would send the
    # user looking at the wrong resource.
    assert "parentArtifact" not in str(exc_info.value)


async def test_deploy_rejects_an_adapter_trained_for_another_model(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Compatibility is decided against the model's own canonical id, not its resource name."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter(compatible_with=("org/some-other-model",))},
        ) as mocks,
        pytest.raises(ValidationException, match="does not list model 'llama3-8b' among the models it can serve"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_rejects_adapters_on_a_cluster_model_with_no_resolved_id(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A base model whose id the engine has not resolved cannot be matched, so nothing attaches.

    The refusal names the unresolved model rather than the adapter's declaration: no comparison
    happened, so telling the user their adapter does not list the model would send them to re-create
    a perfectly good adapter.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=None),
            artifacts={ADAPTER_NAME: _adapter()},
        ) as mocks,
        pytest.raises(ValidationException, match="model 'llama3-8b' has not resolved its identity yet"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_rejects_adapters_on_a_namespace_model_with_no_resolved_id(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Same verdict on the fine-tuned path, which resolves its base model through a different branch."""
    request = AIMDeployRequest(model="wb-finetune-job", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            namespace_model=_namespace_model(aim_id=None),
            artifacts={ADAPTER_NAME: _adapter()},
        ) as mocks,
        pytest.raises(ValidationException, match="model 'wb-finetune-job' has not resolved its identity yet"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_namespace_service.assert_not_awaited()


async def test_deploy_still_names_an_adapters_own_defect_when_the_model_is_unresolved(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """An adapter that names no base models is broken whatever the model resolves to.

    Reporting only the unresolved model would send the user off to wait for something that was never
    the blocker, then refuse again on the adapter once it cleared.
    """
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=None),
            artifacts={ADAPTER_NAME: _adapter(compatible_with=())},
        ),
        pytest.raises(ValidationException) as exc_info,
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    assert "does not declare which base models it can serve" in str(exc_info.value)
    assert "has not resolved its identity yet" not in str(exc_info.value)


async def test_deploy_attaches_an_adapter_to_a_namespace_model(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """The fine-tuned path admits adapters on the same terms as the cluster path."""
    request = AIMDeployRequest(model="wb-finetune-job", adapters=[ADAPTER_NAME])

    with _deploy_env(
        namespace_model=_namespace_model(),
        artifacts={ADAPTER_NAME: _adapter()},
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_namespace_service.assert_awaited_once()


async def test_deploy_rejects_an_adapter_whose_weights_are_not_uploaded(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A confirmed-missing weight file is the one storage verdict that refuses a deploy."""
    minio_client.stat_object.side_effect = _s3_error(OBJECT_MISSING_CODE)
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter()},
        ) as mocks,
        pytest.raises(ValidationException, match=f"'{ADAPTER_NAME}' has no uploaded weights yet"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_rejects_a_fine_tuning_adapter_whose_weights_are_not_uploaded(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Fine-tuning output is platform-hosted storage too, so a missing weight file refuses the
    deploy the same way an AIWB-uploaded adapter's would."""
    minio_client.stat_object.side_effect = _s3_error(OBJECT_MISSING_CODE)
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter(managed_by=MANAGED_BY_FINE_TUNING)},
        ) as mocks,
        pytest.raises(ValidationException, match=f"'{ADAPTER_NAME}' has no uploaded weights yet"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_proceeds_when_storage_cannot_answer(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """Unreachable storage leaves readiness unknown, which must not become a deploy gate."""
    minio_client.stat_object.side_effect = _s3_error("SlowDown")
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()


async def test_deploy_proceeds_when_storage_is_unconfigured(kube_client: AsyncMock) -> None:
    """Without a storage client there is no readiness check at all, and the deploy still lands."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=None)

    mocks.create_cluster_service.assert_awaited_once()


@pytest.mark.parametrize(
    "artifact",
    [
        pytest.param(_adapter(source_uri="hf://org/some-adapter"), id="fetched-from-hugging-face"),
        pytest.param(_adapter(source_uri=None), id="no-recorded-source"),
    ],
)
async def test_deploy_skips_readiness_for_weights_this_platform_does_not_host(
    kube_client: AsyncMock, minio_client: MagicMock, artifact: AIMArtifactResource
) -> None:
    """Only weights this platform hosts can be stat-ed; an externally sourced adapter is fetched
    and validated by aim-engine instead."""
    minio_client.stat_object.side_effect = AssertionError("storage must not be probed")
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: artifact},
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    minio_client.stat_object.assert_not_called()


async def test_deploy_rejects_adapters_on_a_profile_that_cannot_serve_them(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A pinned profile without the adapters capability is refused before the CR is written."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME], profile_name="pinned-profile")

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter()},
            namespaced_profile=_adapters_profile(features=()),
        ) as mocks,
        pytest.raises(ValidationException, match="profile 'pinned-profile' cannot serve adapters"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_accepts_a_cluster_profile_that_serves_adapters(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A pinned name absent from the project resolves cluster-wide rather than being refused."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME], profile_name="pinned-profile")

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
        namespaced_profile=None,
        cluster_profile=_adapters_profile(),
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()


async def test_deploy_defers_an_unresolvable_profile_name_to_the_engine(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A name in neither scope is aim-engine's to reject; guessing here would refuse valid deploys."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME], profile_name="unknown-profile")

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()


async def test_deploy_does_not_check_a_profile_it_did_not_pin(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """On the selector path the engine picks the profile after the CR is written, so nothing is read
    here — a capability check against a profile it may never pick would refuse valid deploys."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME], precision="fp8")

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.get_namespaced_profile.assert_not_awaited()
    mocks.get_cluster_profile.assert_not_awaited()
    mocks.create_cluster_service.assert_awaited_once()


async def test_deploy_rejects_adapters_on_a_namespace_model_profile_that_cannot_serve_them(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """The namespace path pins a profile it derives rather than one the request names, and that
    profile is held to the same capability requirement."""
    request = AIMDeployRequest(model="wb-finetune-job", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            namespace_model=_namespace_model(),
            artifacts={ADAPTER_NAME: _adapter()},
            model_profile=_adapters_profile(features=()),
        ) as mocks,
        pytest.raises(ValidationException, match="profile 'pinned-profile' cannot serve adapters"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_namespace_service.assert_not_awaited()


async def test_deploy_attaches_an_adapter_on_a_namespace_model_profile_that_serves_them(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A derived profile carrying the capability deploys, with that profile pinned on the manifest."""
    request = AIMDeployRequest(model="wb-finetune-job", adapters=[ADAPTER_NAME])

    with _deploy_env(
        namespace_model=_namespace_model(),
        artifacts={ADAPTER_NAME: _adapter()},
        model_profile=_adapters_profile(),
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_namespace_service.assert_awaited_once()
    assert mocks.create_namespace_service.await_args.kwargs["resolved_profile_name"] == "pinned-profile"


async def test_deploy_accepts_an_adapter_despite_criteria_the_pinned_manifest_ignores(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Criteria a pinned deploy never writes must not decide whether its adapters are accepted.

    The namespace path derives and pins a profile without the request naming one, and the manifest
    it writes carries that profile's name and no selector at all. The profile states no weights, so
    the gate reads the model's published catalog; narrowing that catalog by a precision the service
    will never carry would refuse a deploy over an option documented as ignored.
    """
    request = AIMDeployRequest(model="wb-finetune-job", adapters=[ADAPTER_NAME], precision="fp8")

    with _deploy_env(
        namespace_model=_namespace_model(),
        artifacts={ADAPTER_NAME: _adapter(compatible_with=(SIBLING_MODEL_ID,))},
        model_profile=_adapters_profile(),
        published_profiles=[
            _published_profile(
                model_id=SIBLING_MODEL_ID,
                name="bf16-profile",
                precision="bf16",
                model_name="wb-finetune-job",
            )
        ],
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_namespace_service.assert_awaited_once()
    assert mocks.create_namespace_service.await_args.kwargs["resolved_profile_name"] == "pinned-profile"


async def test_deploy_without_adapters_ignores_the_namespace_model_profile_capability(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Most profiles cannot serve adapters, so a deploy that requests none must not be refused."""
    request = AIMDeployRequest(model="wb-finetune-job")

    with _deploy_env(
        namespace_model=_namespace_model(),
        model_profile=_adapters_profile(features=()),
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_namespace_service.assert_awaited_once()


async def test_deploy_rejects_dynamic_adapters_on_a_profile_that_cannot_serve_them(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Asking for adapters to stay changeable needs the capability even before one is named: the
    mode is fixed at deploy time, so accepting it here would strand the deployment."""
    request = AIMDeployRequest(model="llama3-8b", profile_name="pinned-profile", adapter_mode=AdapterMode.DYNAMIC)

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            namespaced_profile=_adapters_profile(features=()),
        ) as mocks,
        pytest.raises(ValidationException, match="profile 'pinned-profile' cannot serve adapters") as exc_info,
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    # The refusal names the mode the user asked for rather than adapters they never listed.
    assert "adapterMode 'dynamic'" in str(exc_info.value)
    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_accepts_dynamic_adapters_on_a_profile_that_serves_them(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Starting with no adapters is a normal way to use a capable runtime and stays allowed."""
    request = AIMDeployRequest(model="llama3-8b", profile_name="pinned-profile", adapter_mode=AdapterMode.DYNAMIC)

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        namespaced_profile=_adapters_profile(),
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    mocks.get_artifact.assert_not_awaited()


async def test_deploy_leaves_dynamic_adapters_on_the_selector_path_to_the_engine(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Without a pinned profile there is nothing to hold to the capability, so the mode alone does
    not make the deploy read one — aim-engine still owns that rejection."""
    request = AIMDeployRequest(model="llama3-8b", adapter_mode=AdapterMode.DYNAMIC)

    with _deploy_env(cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID)) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.get_namespaced_profile.assert_not_awaited()
    mocks.get_cluster_profile.assert_not_awaited()
    mocks.create_cluster_service.assert_awaited_once()


async def test_deploy_rejects_dynamic_adapters_on_a_namespace_model_profile_that_cannot_serve_them(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """The namespace path always pins the profile it derives, so the mode is checked against it."""
    request = AIMDeployRequest(model="wb-finetune-job", adapter_mode=AdapterMode.DYNAMIC)

    with (
        _deploy_env(
            namespace_model=_namespace_model(),
            model_profile=_adapters_profile(features=()),
        ) as mocks,
        pytest.raises(ValidationException, match="profile 'pinned-profile' cannot serve adapters"),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_namespace_service.assert_not_awaited()


async def test_deploy_reports_every_unattachable_adapter_at_once(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """All adapters are evaluated before anything is raised, so several problems cost one retry."""
    request = AIMDeployRequest(model="llama3-8b", adapters=["ghost-adapter", "wrong-base"])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={
                "ghost-adapter": None,
                "wrong-base": _adapter(name="wrong-base", compatible_with=("org/some-other-model",)),
            },
        ) as mocks,
        pytest.raises(ValidationException) as exc_info,
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    message = str(exc_info.value)
    assert "ghost-adapter" in message
    assert "wrong-base" in message
    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_looks_up_a_repeated_adapter_once(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """The request schema rejects repeats; the gate dedupes anyway so a repeat that reaches it
    cannot double the cluster reads it fans out."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME]).model_copy(
        update={"adapters": [ADAPTER_NAME, ADAPTER_NAME]}
    )

    with _deploy_env(
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
    ) as mocks:
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    assert mocks.get_artifact.await_count == 1


async def test_deploy_surfaces_an_unreachable_cluster_as_itself(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A failed artifact read is not a verdict on the adapter, so it must not become a 400 telling
    the user their adapter is wrong."""
    request = AIMDeployRequest(model="llama3-8b", adapters=[ADAPTER_NAME])

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: ExternalServiceError("Failed to get AIMArtifact")},
        ) as mocks,
        pytest.raises(ExternalServiceError),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_not_awaited()


async def test_deploy_caps_how_many_adapters_it_probes_at_once(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """A deploy attaching the most adapters the request allows still probes storage a batch at a
    time, so one caller cannot claim the thread pool every other storage call queues on."""
    names = [f"adapter-{index:02d}" for index in range(_MAX_ADAPTERS)]
    request = AIMDeployRequest(model="llama3-8b", adapters=names)

    in_flight = 0
    peak = 0
    probed = 0

    async def _tracked_stat(*_args: object, **_kwargs: object) -> ReadinessState:
        nonlocal in_flight, peak, probed
        in_flight += 1
        peak = max(peak, in_flight)
        probed += 1
        # Yield so every probe the gate admits is counted before the first one retires; without it
        # the probes would run to completion one by one and never reveal the real peak.
        await asyncio.sleep(0)
        in_flight -= 1
        return ReadinessState.READY

    with (
        _deploy_env(
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={
                name: _adapter(name=name, source_uri=f"s3://{MINIO_BUCKET}/{NAMESPACE}/adapters/{name}/")
                for name in names
            },
        ) as mocks,
        patch("app.artifacts.readiness.stat_readiness", _tracked_stat),
    ):
        await deploy_aim(kube_client, request, NAMESPACE, "user@example.com", minio_client=minio_client)

    mocks.create_cluster_service.assert_awaited_once()
    # Every adapter is still probed, and the cap is genuinely reached rather than the batch simply
    # being smaller than it.
    assert probed == _MAX_ADAPTERS
    assert peak == READINESS_ADAPTER_CONCURRENCY


# ---------------------------------------------------------------------------
# Changing the adapter set of a running deployment
# ---------------------------------------------------------------------------


async def test_changing_adapters_writes_the_requested_set(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """The requested names replace whatever the deployment served, as AIMArtifact references."""
    with _patch_env(
        service=_running_service(),
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
    ) as mocks:
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], minio_client=minio_client)

    mocks.patch_spec.assert_awaited_once()
    assert mocks.patch_spec.await_args.args[3] == {"adapters": [{"kind": "AIMArtifact", "name": ADAPTER_NAME}]}


async def test_detaching_every_adapter_clears_the_field(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """An empty request clears spec.adapters rather than writing [], which the CRD reads as its own
    claim on the field; with nothing to attach, no adapter is looked up either."""
    with _patch_env(service=_running_service()) as mocks:
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [], minio_client=minio_client)

    assert mocks.patch_spec.await_args.args[3] == {"adapters": None}
    mocks.get_artifact.assert_not_awaited()


SCALING = ScalingPolicy(min_replicas=2, max_replicas=10, auto_scaling={"metrics": [{"type": "PodMetric"}]})


async def test_changing_adapters_and_scaling_together_is_one_atomic_write(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A merge patch is applied whole or not at all, so both changes belong in one. Splitting them
    across two calls is what would let a caller end up with half of what they asked for."""
    with _patch_env(
        service=_running_service(),
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
    ) as mocks:
        await update_aim_service_spec(
            kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], scaling=SCALING, minio_client=minio_client
        )

    mocks.patch_spec.assert_awaited_once()
    assert mocks.patch_spec.await_args.args[3] == {
        "adapters": [{"kind": "AIMArtifact", "name": ADAPTER_NAME}],
        "minReplicas": 2,
        "maxReplicas": 10,
        "autoScaling": {"metrics": [{"type": "PodMetric"}]},
    }


async def test_changing_scaling_alone_sends_the_trio_and_touches_nothing_else(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """The three scaling fields land together and nothing else moves — notably not spec.replicas,
    which KEDA owns, and not spec.adapters, which was not part of the request."""
    with _patch_env(service=_running_service()) as mocks:
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), scaling=SCALING, minio_client=minio_client)

    mocks.patch_spec.assert_awaited_once()
    assert mocks.patch_spec.await_args.args[3] == {
        "minReplicas": 2,
        "maxReplicas": 10,
        "autoScaling": {"metrics": [{"type": "PodMetric"}]},
    }


@pytest.mark.parametrize(
    "adapter_mode",
    [pytest.param(AdapterMode.STATIC, id="static"), pytest.param(None, id="mode-never-declared")],
)
async def test_changing_scaling_alone_is_allowed_on_a_deployment_that_cannot_take_adapters(
    kube_client: AsyncMock, minio_client: MagicMock, adapter_mode: AdapterMode | None
) -> None:
    """adapterMode governs adapter changes only. Letting it refuse a scaling change would take
    scaling away from every deployment that never opted into dynamic adapters."""
    with _patch_env(service=_running_service(adapter_mode=adapter_mode)) as mocks:
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), scaling=SCALING, minio_client=minio_client)

    mocks.patch_spec.assert_awaited_once()
    assert "adapters" not in mocks.patch_spec.await_args.args[3]
    mocks.get_artifact.assert_not_awaited()


async def test_changing_scaling_on_an_unknown_deployment_is_not_found(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """An id no deployment carries is a 404, not a gateway failure."""
    with (
        _patch_env(service=None) as mocks,
        pytest.raises(NotFoundException, match="not found in namespace"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), scaling=SCALING, minio_client=minio_client)

    mocks.patch_spec.assert_not_awaited()


async def test_a_request_that_changes_nothing_is_refused(kube_client: AsyncMock, minio_client: MagicMock) -> None:
    """Neither field supplied is a caller mistake, not an empty write to the cluster."""
    with (
        _patch_env(service=_running_service()) as mocks,
        pytest.raises(ValidationException, match="Nothing to update"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), minio_client=minio_client)

    mocks.get_service.assert_not_awaited()
    mocks.patch_spec.assert_not_awaited()


async def test_changing_scaling_alongside_adapters_still_answers_to_the_adapter_mode_gate(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Carrying a scaling change does not buy an adapter change past the gate it would otherwise
    fail, and the scaling half does not land on its own either."""
    with (
        _patch_env(service=_running_service(adapter_mode=AdapterMode.STATIC)) as mocks,
        pytest.raises(ValidationException, match="does not admit adapter changes"),
    ):
        await update_aim_service_spec(
            kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], scaling=SCALING, minio_client=minio_client
        )

    mocks.patch_spec.assert_not_awaited()


async def test_changing_scaling_alongside_adapters_still_checks_each_adapter(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """Same reasoning for the per-adapter checks: an unattachable adapter refuses the whole request
    before anything is written."""
    with (
        _patch_env(
            service=_running_service(),
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={"ghost-adapter": None},
        ) as mocks,
        pytest.raises(ValidationException, match="is not an adapter in this project"),
    ):
        await update_aim_service_spec(
            kube_client, NAMESPACE, uuid4(), ["ghost-adapter"], scaling=SCALING, minio_client=minio_client
        )

    mocks.patch_spec.assert_not_awaited()


@pytest.mark.parametrize(
    "adapter_mode",
    [pytest.param(AdapterMode.STATIC, id="static"), pytest.param(None, id="mode-never-declared")],
)
async def test_changing_adapters_is_refused_unless_the_deployment_is_dynamic(
    kube_client: AsyncMock, minio_client: MagicMock, adapter_mode: AdapterMode | None
) -> None:
    """adapterMode is fixed at deploy time, so a deployment that did not opt in never can."""
    with (
        _patch_env(service=_running_service(adapter_mode=adapter_mode)) as mocks,
        pytest.raises(ValidationException, match="does not admit adapter changes"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], minio_client=minio_client)

    mocks.patch_spec.assert_not_awaited()


async def test_changing_adapters_is_refused_when_the_resolved_profile_cannot_host_adapters(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A runtime advertising no adapter capability can host no adapter at all, so a direct PATCH
    cannot attach one to it either.

    This is not one of the deploy-time constraints a running deployment is entitled to revisit. A
    narrowing constraint such as precision is deliberately not re-litigated here, because refusing
    it would block a change the deployment may legitimately make; a profile that cannot host
    adapters refuses every adapter, so no legitimate change is being blocked.

    The artifacts listing reports these rows as not servable off this very same profile, so without
    the check the API tells a caller an adapter is not servable and then accepts it anyway.
    """
    with (
        _patch_env(
            service=_running_service(resolved_profile_name="pinned-profile"),
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={ADAPTER_NAME: _adapter()},
            namespaced_profile=_adapters_profile(features=()),
        ) as mocks,
        pytest.raises(ValidationException, match="cannot serve adapters"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], minio_client=minio_client)

    mocks.patch_spec.assert_not_awaited()


async def test_changing_adapters_is_allowed_when_the_resolved_profile_hosts_adapters(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """The capability check refuses a runtime that has the feature nowhere, not one that has it.

    Paired with the refusal above so the gate is shown to turn on the profile's capability rather
    than on the profile being read at all — the same read also names the running weights.
    """
    with _patch_env(
        service=_running_service(resolved_profile_name="pinned-profile"),
        cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
        artifacts={ADAPTER_NAME: _adapter()},
        namespaced_profile=_adapters_profile(),
    ) as mocks:
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], minio_client=minio_client)

    mocks.get_namespaced_profile.assert_awaited()
    mocks.patch_spec.assert_awaited_once()


@pytest.mark.parametrize(
    ("artifact", "base_aim_id", "weights_missing", "expected"),
    [
        pytest.param(None, BASE_AIM_ID, False, "is not an adapter in this project", id="unknown-name"),
        pytest.param(
            _adapter(managed_by="someone-else"),
            BASE_AIM_ID,
            False,
            "is not an adapter in this project",
            id="not-owned-by-this-api",
        ),
        pytest.param(
            _adapter(compatible_with=None),
            BASE_AIM_ID,
            False,
            "does not declare which base models it can serve",
            id="declares-no-base-models",
        ),
        pytest.param(
            _adapter(compatible_with=("org/some-other-model",)),
            BASE_AIM_ID,
            False,
            "among the models it can serve",
            id="trained-for-another-model",
        ),
        pytest.param(_adapter(), None, False, "has not resolved its identity yet", id="model-identity-unresolved"),
        pytest.param(_adapter(), BASE_AIM_ID, True, "has no uploaded weights yet", id="weights-not-uploaded"),
    ],
)
async def test_changing_adapters_enforces_every_gate_a_deploy_does(
    kube_client: AsyncMock,
    minio_client: MagicMock,
    artifact: AIMArtifactResource | None,
    base_aim_id: str | None,
    weights_missing: bool,
    expected: str,
) -> None:
    """Attaching to a running deployment is the same claim as attaching at deploy time, so it is
    held to the same gates rather than to a looser copy of them."""
    if weights_missing:
        minio_client.stat_object.side_effect = _s3_error(OBJECT_MISSING_CODE)

    with (
        _patch_env(
            service=_running_service(),
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=base_aim_id),
            artifacts={ADAPTER_NAME: artifact},
        ) as mocks,
        pytest.raises(ValidationException, match=expected),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], minio_client=minio_client)

    mocks.patch_spec.assert_not_awaited()


async def test_changing_adapters_reports_every_unattachable_adapter_at_once(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """All adapters are evaluated before anything is raised, so several problems cost one retry."""
    with (
        _patch_env(
            service=_running_service(),
            cluster_model=make_aim_cluster_model(name="llama3-8b", aim_id=BASE_AIM_ID),
            artifacts={
                "ghost-adapter": None,
                "wrong-base": _adapter(name="wrong-base", compatible_with=("org/some-other-model",)),
            },
        ),
        pytest.raises(ValidationException) as exc_info,
    ):
        await update_aim_service_spec(
            kube_client, NAMESPACE, uuid4(), ["ghost-adapter", "wrong-base"], minio_client=minio_client
        )

    message = str(exc_info.value)
    assert "ghost-adapter" in message
    assert "wrong-base" in message


async def test_changing_adapters_on_an_unknown_deployment_is_not_found(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    with (
        _patch_env(service=None) as mocks,
        pytest.raises(NotFoundException, match="not found in namespace"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [], minio_client=minio_client)

    mocks.patch_spec.assert_not_awaited()


async def test_changing_adapters_when_the_served_model_has_vanished_is_an_inconsistent_state(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """The model a running deployment serves disappearing from both scopes is a platform-side
    inconsistency, not something the caller's adapter request got wrong."""
    with (
        _patch_env(
            service=_running_service(),
            cluster_model=None,
            namespace_model=None,
            artifacts={ADAPTER_NAME: _adapter()},
        ) as mocks,
        pytest.raises(InconsistentStateException, match="is no longer available"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], minio_client=minio_client)

    mocks.patch_spec.assert_not_awaited()


_CLUSTER_ANSWERS = pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        pytest.param(422, ValidationException, id="admission-rejected"),
        pytest.param(400, ValidationException, id="bad-request"),
        pytest.param(409, ConflictException, id="concurrent-change"),
        pytest.param(500, ExternalServiceError, id="cluster-failure"),
    ],
)


@_CLUSTER_ANSWERS
async def test_changing_scaling_alone_maps_what_the_cluster_answered(
    kube_client: AsyncMock,
    minio_client: MagicMock,
    status_code: int,
    expected_exception: type[Exception],
) -> None:
    """A scaling-only change answers to the same contract as any other spec change: a rejected
    write carries the API server's own reason out rather than being flattened into an outage."""
    rejection = ApiException(status=status_code, reason="Rejected")
    rejection.body = '{"message": "maxReplicas must be >= minReplicas"}'

    with (
        _patch_env(service=_running_service(), patch_result=rejection),
        pytest.raises(expected_exception, match="maxReplicas must be >= minReplicas"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), scaling=SCALING, minio_client=minio_client)


@_CLUSTER_ANSWERS
async def test_changing_adapters_maps_what_the_cluster_answered(
    kube_client: AsyncMock,
    minio_client: MagicMock,
    status_code: int,
    expected_exception: type[Exception],
) -> None:
    """The API server's status decides the response, so a rejected write is not reported as an
    outage and an outage is not reported as the user's mistake."""
    rejection = ApiException(status=status_code, reason="Rejected")
    rejection.body = '{"message": "spec.adapters is immutable"}'

    with (
        _patch_env(service=_running_service(), patch_result=rejection),
        pytest.raises(expected_exception, match="spec.adapters is immutable"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [], minio_client=minio_client)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(None, id="no-body"),
        pytest.param("<html>gateway timeout</html>", id="not-json"),
        pytest.param('["rejected"]', id="json-but-not-an-object"),
    ],
)
async def test_a_rejection_without_a_usable_body_still_carries_a_reason_out(
    kube_client: AsyncMock, minio_client: MagicMock, body: str | None
) -> None:
    """Only the API server answers with its JSON status object; a proxy standing in front of it
    answers with whatever it likes. The status line has to reach the caller whatever the body
    turns out to be, rather than the body's shape deciding whether they learn anything at all."""
    rejection = ApiException(status=400, reason="Bad Request")
    rejection.body = body

    with (
        _patch_env(service=_running_service(), patch_result=rejection),
        pytest.raises(ValidationException, match="Bad Request"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), scaling=SCALING, minio_client=minio_client)


async def test_changing_scaling_alone_wraps_a_non_api_failure_as_an_external_service_error(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A connection drop or timeout talking to the cluster is not an ApiException, so without a
    catch-all it would reach the caller as a bare 500 instead of the same 502 every other cluster
    fault gets here."""
    with (
        _patch_env(service=_running_service(), patch_result=ConnectionError("connection reset")),
        pytest.raises(ExternalServiceError, match="connection reset"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), scaling=SCALING, minio_client=minio_client)


async def test_changing_adapters_reports_an_unreachable_model_lookup_as_a_cluster_fault(
    kube_client: AsyncMock, minio_client: MagicMock
) -> None:
    """A failed model lookup is a cluster fault, not evidence the model is gone, so it must not
    collapse into the ValidationException a genuinely missing model gets."""
    with (
        _patch_env(service=_running_service(), artifacts={ADAPTER_NAME: _adapter()}),
        patch(
            "app.aims.service.get_aim_model_from_k8s",
            AsyncMock(side_effect=ApiException(status=500, reason="boom")),
        ),
        pytest.raises(ExternalServiceError, match="Failed to look up AIM model .*: boom"),
    ):
        await update_aim_service_spec(kube_client, NAMESPACE, uuid4(), [ADAPTER_NAME], minio_client=minio_client)
