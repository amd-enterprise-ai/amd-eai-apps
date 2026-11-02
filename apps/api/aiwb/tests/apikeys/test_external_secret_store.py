# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the per-key ExternalSecret store."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from kubernetes_asyncio.client import ApiException

from app.apikeys import external_secret_store as es


def _patch_labels(call_args: Any) -> dict:
    """Extract the labels from a template-labels JSON Patch and assert the body shape.

    patch_namespaced_custom_object defaults to application/json-patch+json, so the body MUST be a
    list of ops — a merge-patch object is rejected by the API server. This guards that regression.
    """
    body = call_args.kwargs["body"]
    assert isinstance(body, list), f"patch body must be a JSON Patch list, got {type(body).__name__}"
    op = body[0]
    assert op["op"] in ("replace", "add") and op["path"] == "/spec/target/template/metadata/labels"
    return op["value"]


def _kube() -> MagicMock:
    mock = MagicMock()
    mock.custom_objects = MagicMock()
    mock.custom_objects.get_namespaced_custom_object = AsyncMock()
    mock.custom_objects.create_namespaced_custom_object = AsyncMock()
    mock.custom_objects.patch_namespaced_custom_object = AsyncMock()
    mock.custom_objects.delete_namespaced_custom_object = AsyncMock()
    return mock


def _es_bound_to(workload_ids: set[str]) -> dict:
    """An ExternalSecret as returned by get, bound (template labels) to the given workloads."""
    labels = {es.API_KEY_LABEL: "true", es.MANAGED_BY_LABEL: es.MANAGED_BY_VALUE}
    for wid in workload_ids:
        labels[es.bound_label(wid)] = "true"
    return {
        "metadata": {"name": es.key_secret_name("kid")},
        "spec": {"target": {"template": {"metadata": {"labels": labels}}}},
    }


def test_key_secret_name() -> None:
    assert es.key_secret_name("kid-123") == "apikey-kid-123"


def test_bound_label() -> None:
    assert es.bound_label("wid-1") == "apikey.eai.amd.com/bound-wid-1"


def test_compute_client_id_is_token_ns_key() -> None:
    # x-api-key-id format token-<ns>-<key>, sanitized to [a-z0-9-]
    assert es.compute_client_id("Team NS", "My Key!") == "token-team-ns-my-key-"


@pytest.mark.asyncio
async def test_create_makes_external_secret_with_single_entry() -> None:
    kube = _kube()

    await es.create_key_secret(kube, "ns", "kid", "token-ns-k", "My Key")

    kube.custom_objects.create_namespaced_custom_object.assert_awaited_once()
    body = kube.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
    assert body["metadata"]["name"] == "apikey-kid"
    data = body["spec"]["data"]
    assert len(data) == 1
    assert data[0]["secretKey"] == "token-ns-k"
    assert data[0]["remoteRef"] == {"key": "apikeys/kid", "property": "token"}
    labels = body["spec"]["target"]["template"]["metadata"]["labels"]
    assert labels[es.API_KEY_LABEL] == "true"
    # deletionPolicy: Merge is required so native OpenBao expiry prunes the key (not Retain, which errors).
    assert body["spec"]["target"]["creationPolicy"] == "Owner"
    assert body["spec"]["target"]["deletionPolicy"] == "Merge"
    # Display name propagated as an annotation on both the ExternalSecret and the materialized Secret.
    assert body["metadata"]["annotations"][es.DISPLAY_NAME_ANNOTATION] == "My Key"
    assert body["spec"]["target"]["template"]["metadata"]["annotations"][es.DISPLAY_NAME_ANNOTATION] == "My Key"


@pytest.mark.asyncio
async def test_create_stamps_bound_labels() -> None:
    kube = _kube()

    await es.create_key_secret(kube, "ns", "kid", "token-ns-k", "My Key", {"A", "B"})

    body = kube.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
    labels = body["spec"]["target"]["template"]["metadata"]["labels"]
    assert labels[es.bound_label("A")] == "true"
    assert labels[es.bound_label("B")] == "true"


@pytest.mark.asyncio
async def test_create_conflict_converges_bindings() -> None:
    # Already exists → create raises 409 → converge on the requested bindings via a label patch.
    kube = _kube()
    kube.custom_objects.create_namespaced_custom_object.side_effect = ApiException(status=409)
    kube.custom_objects.get_namespaced_custom_object.return_value = _es_bound_to(set())

    await es.create_key_secret(kube, "ns", "kid", "token-ns-k", "My Key", {"A"})

    labels = _patch_labels(kube.custom_objects.patch_namespaced_custom_object.call_args)
    assert labels[es.bound_label("A")] == "true"


@pytest.mark.asyncio
async def test_set_bindings_patches_template_labels() -> None:
    kube = _kube()
    kube.custom_objects.get_namespaced_custom_object.return_value = _es_bound_to({"A", "B"})

    await es.set_key_bindings(kube, "ns", "kid", {"A", "C"})

    labels = _patch_labels(kube.custom_objects.patch_namespaced_custom_object.call_args)
    bound = {k[len(es.BOUND_LABEL_PREFIX) :] for k in labels if k.startswith(es.BOUND_LABEL_PREFIX)}
    assert bound == {"A", "C"}
    # Contract label preserved.
    assert labels[es.API_KEY_LABEL] == "true"


@pytest.mark.asyncio
async def test_set_bindings_noop_when_already_matching() -> None:
    kube = _kube()
    kube.custom_objects.get_namespaced_custom_object.return_value = _es_bound_to({"A"})

    await es.set_key_bindings(kube, "ns", "kid", {"A"})

    kube.custom_objects.patch_namespaced_custom_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_bindings_raises_when_missing() -> None:
    kube = _kube()
    kube.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    with pytest.raises(es.NotFoundKeySecret):
        await es.set_key_bindings(kube, "ns", "kid", {"A"})


@pytest.mark.asyncio
async def test_list_workload_ids_reads_bound_labels() -> None:
    kube = _kube()
    kube.custom_objects.get_namespaced_custom_object.return_value = _es_bound_to({"A", "C", "B"})

    assert await es.list_workload_ids_for_key(kube, "ns", "kid") == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_list_workload_ids_empty_when_absent() -> None:
    kube = _kube()
    kube.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)

    assert await es.list_workload_ids_for_key(kube, "ns", "kid") == []


@pytest.mark.asyncio
async def test_delete_key_secret() -> None:
    kube = _kube()

    await es.delete_key_secret(kube, "ns", "kid")

    kube.custom_objects.delete_namespaced_custom_object.assert_awaited_once()
    assert kube.custom_objects.delete_namespaced_custom_object.call_args.kwargs["name"] == "apikey-kid"


@pytest.mark.asyncio
async def test_delete_key_secret_tolerates_404() -> None:
    kube = _kube()
    kube.custom_objects.delete_namespaced_custom_object.side_effect = ApiException(status=404)

    await es.delete_key_secret(kube, "ns", "kid")  # no raise
