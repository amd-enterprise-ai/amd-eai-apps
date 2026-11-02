# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the custom-model multi-doc YAML manifest helpers."""

import asyncio
from unittest.mock import MagicMock

import pytest
import tenacity
import yaml
from minio.error import S3Error

from api_common.exceptions import ExternalServiceError, ForbiddenException, ValidationException
from app.custom_models.manifest import (
    manifest_write_lock,
    parse_manifest,
    read_manifest_from_s3,
    remove_manifest_documents,
    serialize_manifest,
    upsert_manifest_documents,
    write_manifest_to_s3,
)
from app.minio import MinioClient


@pytest.fixture(autouse=True)
def _disable_write_manifest_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable tenacity retry timing on ``write_manifest_to_s3`` for fast unit tests.

    The retry policy itself is covered by the shared MinIO retry tests
    (``tests/minio/``); here we only care that the error mapping and
    payload shape are correct, so retrying through the default
    exponential-backoff schedule would only slow the suite.
    """
    monkeypatch.setattr(write_manifest_to_s3.retry, "wait", tenacity.wait_none())
    monkeypatch.setattr(write_manifest_to_s3.retry, "stop", tenacity.stop_after_attempt(1))


def _aim_model_document(name: str = "llama-3-8b", namespace: str = "kw-test-project") -> dict:
    return {
        "apiVersion": "aim.eai.amd.com/v1alpha1",
        "kind": "AIMModel",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {"aimId": "meta-llama/Llama-3-8B"},
    }


def _aim_profile_document(
    name: str = "llama-3-8b-default",
    namespace: str = "kw-test-project",
    image_ref: str = "amdenterpriseai/aim-base:0.11",
) -> dict:
    return {
        "apiVersion": "aim.eai.amd.com/v1alpha2",
        "kind": "AIMProfile",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "annotations": {"aim.eai.amd.com/deployment-image-ref": image_ref},
        },
        "spec": {"aimId": "llama-3-8b", "image": image_ref},
    }


def test_serialize_and_parse_roundtrip_preserves_documents() -> None:
    documents = [_aim_model_document(), _aim_profile_document()]
    payload = serialize_manifest(documents)
    assert parse_manifest(payload) == documents


def test_serialize_manifest_emits_multi_doc_yaml() -> None:
    """The manifest format is multi-doc YAML — verify the boundary marker is
    present so consumers (e.g. ``kubectl apply -f``) split the documents."""
    payload = serialize_manifest([_aim_model_document(), _aim_profile_document()])
    text = payload.decode()
    assert text.count("\n---\n") >= 1


def test_serialize_manifest_rejects_empty_input() -> None:
    """An empty manifest is invalid — writing it would erase the durable
    record without anyone noticing."""
    with pytest.raises(ValueError, match="empty manifest"):
        serialize_manifest([])


def test_serialize_manifest_rejects_unaddressable_document() -> None:
    """Documents without (kind, metadata.name) cannot be replaced by identity
    on re-onboard; fail fast rather than emit a degenerate manifest."""
    with pytest.raises(ValueError, match="'kind'"):
        serialize_manifest([{"metadata": {"name": "x"}}])


@pytest.mark.parametrize(
    "broken_metadata",
    [
        pytest.param("not-a-mapping", id="string"),
        pytest.param(["name", "x"], id="list"),
        pytest.param(None, id="null"),
    ],
)
def test_serialize_manifest_rejects_non_mapping_metadata(broken_metadata: object) -> None:
    """A corrupted manifest with ``metadata`` set to a non-mapping must
    surface as a controlled ``ValueError`` rather than an opaque
    ``AttributeError`` from ``.get`` on a non-dict value."""
    with pytest.raises(ValueError, match="'kind'|'metadata.name'"):
        serialize_manifest([{"kind": "AIMModel", "metadata": broken_metadata}])


def test_parse_manifest_drops_trailing_empty_documents() -> None:
    """Trailing ``---`` is a valid YAML stream end and should not become a
    spurious document."""
    payload = b"apiVersion: v1\nkind: AIMModel\nmetadata:\n  name: m\n---\n"
    documents = parse_manifest(payload)
    assert len(documents) == 1
    assert documents[0]["kind"] == "AIMModel"


def test_parse_manifest_rejects_non_mapping_document() -> None:
    """The manifest is strictly a set of CR objects; anything else means a
    corrupted or hand-edited file."""
    payload = b"- not\n- a\n- mapping\n"
    with pytest.raises(ExternalServiceError, match="non-mapping document"):
        parse_manifest(payload)


def test_parse_manifest_rejects_invalid_yaml() -> None:
    """A YAML parse error from S3 content must surface as a domain
    ``ExternalServiceError``, not bubble up as a raw library exception."""
    with pytest.raises(ExternalServiceError, match="not valid YAML"):
        parse_manifest(b"key: [unterminated")


def test_parse_manifest_rejects_document_missing_identity() -> None:
    """A syntactically-valid YAML document without ``(kind, metadata.name)``
    is unaddressable for the upsert layer; treating that as storage
    corruption (502) rather than a producer-side programmer bug (400)
    keeps the failure consistent with the rest of the read path."""
    payload = b"apiVersion: v1\nkind: AIMModel\nmetadata:\n  namespace: ns\n"
    with pytest.raises(ExternalServiceError, match="malformed"):
        parse_manifest(payload)


@pytest.mark.parametrize(
    ("doc_yaml", "expected_field"),
    [
        pytest.param(
            b"apiVersion: v1\nkind:\n- AIMModel\nmetadata:\n  name: x\n",
            "kind",
            id="kind-as-list",
        ),
        pytest.param(
            b"apiVersion: v1\nkind:\n  inner: AIMModel\nmetadata:\n  name: x\n",
            "kind",
            id="kind-as-mapping",
        ),
        pytest.param(
            b"apiVersion: v1\nkind: AIMModel\nmetadata:\n  name:\n  - x\n",
            "name",
            id="name-as-list",
        ),
        pytest.param(
            b"apiVersion: v1\nkind: AIMModel\nmetadata:\n  name:\n    inner: x\n",
            "name",
            id="name-as-mapping",
        ),
    ],
)
def test_parse_manifest_rejects_non_string_identity_values(doc_yaml: bytes, expected_field: str) -> None:
    """Truthy-but-unhashable identity values (e.g. ``kind: [AIMModel]``
    or ``metadata.name: {...}``) would otherwise slip past the identity
    check and crash ``upsert_manifest_documents`` with an opaque
    ``TypeError: unhashable type`` when the identity tuple is used as a
    dict key. The corrupt-storage path must surface as
    ``ExternalServiceError`` regardless of whether the malformed value
    is missing, non-mapping, or wrong-typed."""
    del expected_field  # parametrize id only — both fields converge on the same error path
    with pytest.raises(ExternalServiceError, match="malformed"):
        parse_manifest(doc_yaml)


@pytest.mark.parametrize(
    "bad_document",
    [
        pytest.param({"kind": ["AIMModel"], "metadata": {"name": "x"}}, id="kind-as-list"),
        pytest.param({"kind": "AIMModel", "metadata": {"name": ["x"]}}, id="name-as-list"),
        pytest.param({"kind": {"inner": "AIMModel"}, "metadata": {"name": "x"}}, id="kind-as-mapping"),
    ],
)
def test_upsert_manifest_documents_rejects_non_string_identity_in_new_documents(
    bad_document: dict,
) -> None:
    """A caller bypassing ``parse_manifest`` (i.e. building the document
    in code) must still hit the controlled ``ValueError`` path before
    the identity tuple is used as a dict key — otherwise the failure
    surfaces as an opaque ``TypeError: unhashable type``."""
    with pytest.raises(ValueError, match="non-empty strings"):
        upsert_manifest_documents(existing=[], new_documents=[bad_document])


def test_upsert_manifest_documents_appends_new_document() -> None:
    """The AIMProfile document is appended when the manifest scaffold
    initially contains only the AIMModel — this is the first-time onboard
    path."""
    existing = [_aim_model_document()]
    template = _aim_profile_document()

    merged = upsert_manifest_documents(existing, [template])

    assert merged == [_aim_model_document(), template]


def test_upsert_manifest_documents_replaces_existing_document_by_identity() -> None:
    """Re-onboarding the same model must update the AIMProfile
    document in place rather than appending a duplicate — that's the
    idempotency requirement for onboarding."""
    initial_template = _aim_profile_document(image_ref="amdenterpriseai/aim-base:0.10")
    updated_template = _aim_profile_document(image_ref="amdenterpriseai/aim-base:0.11")

    merged = upsert_manifest_documents(
        existing=[_aim_model_document(), initial_template],
        new_documents=[updated_template],
    )

    assert len(merged) == 2
    assert merged[1]["metadata"]["annotations"]["aim.eai.amd.com/deployment-image-ref"] == (
        "amdenterpriseai/aim-base:0.11"
    )


def test_upsert_manifest_documents_preserves_existing_order() -> None:
    """The AIMModel should remain the first document so a manual ``kubectl
    apply -f manifest.yaml`` re-creates the model before the template that
    references it."""
    template = _aim_profile_document()
    aim_model = _aim_model_document()

    merged = upsert_manifest_documents(existing=[aim_model, template], new_documents=[template])

    assert merged[0]["kind"] == "AIMModel"
    assert merged[1]["kind"] == "AIMProfile"


def test_upsert_manifest_documents_collapses_duplicate_identities_in_existing() -> None:
    """A manifest produced by an older / buggy version (or hand-edited)
    can carry two documents with the same (kind, metadata.name). Upsert
    must collapse them — last-seen wins — so a subsequent re-onboard
    replaces *all* prior copies, not just the last one. Without this
    the durable record stays in violation of the "never duplicate by
    identity" contract."""
    initial_template = _aim_profile_document(image_ref="amdenterpriseai/aim-base:0.10")
    duplicate_template = _aim_profile_document(image_ref="amdenterpriseai/aim-base:0.10-dup")
    new_template = _aim_profile_document(image_ref="amdenterpriseai/aim-base:0.11")

    merged = upsert_manifest_documents(
        existing=[_aim_model_document(), initial_template, duplicate_template],
        new_documents=[new_template],
    )

    assert len(merged) == 2
    template_docs = [d for d in merged if d["kind"] == "AIMProfile"]
    assert len(template_docs) == 1
    assert template_docs[0]["metadata"]["annotations"]["aim.eai.amd.com/deployment-image-ref"] == (
        "amdenterpriseai/aim-base:0.11"
    )


def test_upsert_manifest_documents_collapses_duplicates_even_without_new_documents() -> None:
    """Idempotency edge case: passing an existing list with duplicates and
    an empty ``new_documents`` should still return a deduped list so
    that any read-modify-write loop converges on a clean manifest."""
    duplicate_template = _aim_profile_document(image_ref="amdenterpriseai/aim-base:0.10-dup")

    merged = upsert_manifest_documents(
        existing=[_aim_model_document(), _aim_profile_document(), duplicate_template],
        new_documents=[],
    )

    template_docs = [d for d in merged if d["kind"] == "AIMProfile"]
    assert len(template_docs) == 1
    # Last-seen wins for duplicates pre-existing in ``existing``.
    assert template_docs[0]["metadata"]["annotations"]["aim.eai.amd.com/deployment-image-ref"] == (
        "amdenterpriseai/aim-base:0.10-dup"
    )


def test_remove_manifest_documents_drops_matching_identity() -> None:
    """A deleted profile's mirror document is dropped while the AIMModel scaffold stays."""
    aim_model = _aim_model_document()
    profile = _aim_profile_document(name="llama-3-8b-named")

    remaining = remove_manifest_documents([aim_model, profile], identities={("AIMProfile", "llama-3-8b-named")})

    assert remaining == [aim_model]


def test_remove_manifest_documents_is_noop_when_identity_absent() -> None:
    """Removing an identity not present leaves the manifest unchanged."""
    aim_model = _aim_model_document()
    profile = _aim_profile_document()

    remaining = remove_manifest_documents([aim_model, profile], identities={("AIMProfile", "not-in-manifest")})

    assert remaining == [aim_model, profile]


def test_remove_manifest_documents_preserves_order_of_survivors() -> None:
    """Surviving documents keep their original order after a removal."""
    aim_model = _aim_model_document()
    keep = _aim_profile_document(name="keep-me")
    drop = _aim_profile_document(name="drop-me")

    remaining = remove_manifest_documents([aim_model, keep, drop], identities={("AIMProfile", "drop-me")})

    assert remaining == [aim_model, keep]


async def test_read_manifest_from_s3_returns_empty_list_when_object_missing() -> None:
    """``NoSuchKey`` is the steady-state ``no manifest yet`` signal — callers
    must be able to treat first-write and re-onboard symmetrically."""
    client = MagicMock(spec=MinioClient)
    client.download_object.side_effect = S3Error(
        code="NoSuchKey",
        message="missing",
        resource="key",
        request_id="r",
        host_id="h",
        response=MagicMock(status=404),
    )

    assert await read_manifest_from_s3(client, "bucket", "ns/custom-models/m/manifest.yaml") == []


@pytest.mark.parametrize(
    ("s3_code", "expected_exc"),
    [
        pytest.param("AccessDenied", ForbiddenException, id="access-denied-403"),
        pytest.param("InvalidRequest", ValidationException, id="invalid-request-400"),
        pytest.param("InternalError", ExternalServiceError, id="internal-error-502"),
    ],
)
async def test_read_manifest_from_s3_uses_shared_s3_error_mapping(s3_code: str, expected_exc: type) -> None:
    """Non-``NoSuchKey`` S3 errors must flow through the shared MinIO
    mapper so the resulting HTTP status code matches the rest of the
    API's storage surface (``AccessDenied`` → 403, ``InvalidRequest`` →
    400, transient/internal errors → 502)."""
    client = MagicMock(spec=MinioClient)
    client.download_object.side_effect = S3Error(
        code=s3_code,
        message="boom",
        resource="key",
        request_id="r",
        host_id="h",
        response=MagicMock(status=500),
    )

    with pytest.raises(expected_exc):
        await read_manifest_from_s3(client, "bucket", "ns/custom-models/m/manifest.yaml")


async def test_read_manifest_from_s3_rejects_malformed_stored_manifest() -> None:
    """A manifest that parses as YAML but contains an unaddressable
    document is a storage-corruption signal; the read path should turn
    that into an ``ExternalServiceError`` (502) so the caller doesn't see
    a misleading 400 from later upsert/serialize calls."""
    client = MagicMock(spec=MinioClient)
    client.download_object.return_value = b"apiVersion: v1\nkind: AIMModel\nmetadata:\n  namespace: ns\n"

    with pytest.raises(ExternalServiceError, match="malformed"):
        await read_manifest_from_s3(client, "bucket", "ns/custom-models/m/manifest.yaml")


async def test_read_manifest_from_s3_parses_existing_manifest() -> None:
    client = MagicMock(spec=MinioClient)
    payload = yaml.safe_dump_all([_aim_model_document()], sort_keys=False).encode()
    client.download_object.return_value = payload

    documents = await read_manifest_from_s3(client, "bucket", "key")

    assert documents == [_aim_model_document()]


async def test_write_manifest_to_s3_uploads_serialized_payload() -> None:
    client = MagicMock(spec=MinioClient)
    documents = [_aim_model_document(), _aim_profile_document()]

    await write_manifest_to_s3(client, "bucket", "key", documents)

    client.upload_object.assert_called_once()
    upload_kwargs = client.upload_object.call_args.kwargs
    assert upload_kwargs["bucket_name"] == "bucket"
    assert upload_kwargs["object_name"] == "key"
    assert list(yaml.safe_load_all(upload_kwargs["data"])) == documents


@pytest.mark.parametrize(
    ("s3_code", "expected_exc"),
    [
        pytest.param("AccessDenied", ForbiddenException, id="access-denied-403"),
        pytest.param("InvalidRequest", ValidationException, id="invalid-request-400"),
        pytest.param("InternalError", ExternalServiceError, id="internal-error-502"),
    ],
)
async def test_write_manifest_to_s3_uses_shared_s3_error_mapping(s3_code: str, expected_exc: type) -> None:
    """Upload failures must use the same shared MinIO error mapping as
    the read path so callers see a consistent HTTP status code for the
    same underlying S3 error code, regardless of which side of the
    manifest cycle hit the failure."""
    client = MagicMock(spec=MinioClient)
    client.upload_object.side_effect = S3Error(
        code=s3_code,
        message="boom",
        resource="key",
        request_id="r",
        host_id="h",
        response=MagicMock(status=500),
    )

    with pytest.raises(expected_exc):
        await write_manifest_to_s3(client, "bucket", "key", [_aim_model_document()])


async def test_manifest_write_lock_serializes_same_key() -> None:
    """Two coroutines contending for the same (bucket, key) must run
    their critical sections one after the other — that is the whole
    point of the lock. We assert by recording entry/exit timestamps and
    requiring the two intervals not to overlap.
    """
    events: list[tuple[str, str]] = []

    async def writer(tag: str) -> None:
        async with manifest_write_lock("bucket", "ns/m/manifest.yaml"):
            events.append(("enter", tag))
            # Yield to the scheduler so the *other* coroutine has a
            # chance to acquire the lock if it were unguarded; with the
            # lock held it must remain blocked.
            await asyncio.sleep(0)
            events.append(("exit", tag))

    await asyncio.gather(writer("a"), writer("b"))

    # Whichever tag entered first, its exit must precede the other's enter.
    first_enter = events.index(("enter", events[0][1]))
    first_exit = events.index(("exit", events[0][1]))
    second_enter_tag = "b" if events[0][1] == "a" else "a"
    second_enter = events.index(("enter", second_enter_tag))
    assert first_enter < first_exit < second_enter, f"intervals overlapped: {events}"


async def test_manifest_write_lock_allows_parallel_writes_to_different_keys() -> None:
    """The lock is keyed per (bucket, key), so unrelated manifests can
    be updated in parallel. Otherwise the per-process lock would become
    a global write bottleneck for every onboarded model in the
    namespace."""
    inside = asyncio.Event()
    proceed = asyncio.Event()

    async def writer_holding_lock(key: str) -> None:
        async with manifest_write_lock("bucket", key):
            inside.set()
            await proceed.wait()

    async def writer_takes_other_key(key: str) -> bool:
        # Wait until the first writer is inside its critical section,
        # then try to acquire the *different* key. If the lock were
        # global this would block until ``proceed`` is set.
        await inside.wait()
        async with manifest_write_lock("bucket", key):
            return True

    holder = asyncio.create_task(writer_holding_lock("ns/m-a/manifest.yaml"))
    contender = asyncio.create_task(writer_takes_other_key("ns/m-b/manifest.yaml"))

    # Give the scheduler a tick to start both tasks, then assert the
    # contender finished without us releasing the holder.
    result = await asyncio.wait_for(contender, timeout=1.0)
    assert result is True

    proceed.set()
    await holder


async def test_concurrent_writers_to_same_manifest_preserve_each_others_documents() -> None:
    """Regression for the lost-update window the lock is meant to close.

    Without the lock, two coroutines doing read → upsert → write
    against the same key can both read the same prior state and the
    later upload overwrites the earlier writer's document. Under the
    lock, the second writer reads the post-first-write state and
    upserts on top, so both documents survive in the final manifest.
    """
    storage: dict[tuple[str, str], bytes] = {}

    def download(bucket: str, key: str) -> bytes:
        payload = storage.get((bucket, key))
        if payload is None:
            raise S3Error(
                code="NoSuchKey",
                message="missing",
                resource=key,
                request_id="r",
                host_id="h",
                response=MagicMock(status=404),
            )
        return payload

    def upload(*, bucket_name: str, object_name: str, data: bytes) -> None:
        storage[(bucket_name, object_name)] = data

    client = MagicMock(spec=MinioClient)
    client.download_object.side_effect = download
    client.upload_object.side_effect = upload

    bucket = "bucket"
    key = "ns/llama-3-8b/manifest.yaml"

    async def write_one(document: dict) -> None:
        async with manifest_write_lock(bucket, key):
            existing = await read_manifest_from_s3(client, bucket, key)
            merged = upsert_manifest_documents(existing=existing, new_documents=[document])
            # Yield mid-cycle so an unlocked second writer would have
            # ample opportunity to overtake; the lock must prevent that.
            await asyncio.sleep(0)
            await write_manifest_to_s3(client, bucket, key, merged)

    await asyncio.gather(
        write_one(_aim_model_document()),
        write_one(_aim_profile_document()),
    )

    final_documents = parse_manifest(storage[(bucket, key)])
    kinds = sorted(doc["kind"] for doc in final_documents)
    assert kinds == ["AIMModel", "AIMProfile"], f"both writers' documents must survive; got {kinds}"
