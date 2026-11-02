# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guards the skip-vs-fail branching in the storage-credentials keyword.

Only a genuinely absent object store may skip these scenarios. Everything else -- a denied
lookup, an API-server error, a secret missing a field, a malformed URL -- has to fail loudly,
because a skip that swallows one of those reports a real bug as an environmental limitation and
hides it. That distinction is easy to widen by accident on a later edit, so it is pinned here.

Also pinned: the credentials never leave this module. Robot logs every variable assignment at
INFO, so a keyword that returned them would put the access key and secret key into routine test
output.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

_LIB = pathlib.Path(__file__).resolve().parent / "libraries" / "StorageCredentials.py"
_spec = importlib.util.spec_from_file_location("StorageCredentials", _LIB)
assert _spec is not None and _spec.loader is not None
storage_credentials = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("StorageCredentials", storage_credentials)
_spec.loader.exec_module(storage_credentials)

NAMESPACE = "e2e-project"
BUCKET_URL = "http://store.example:80/default-bucket"
ACCESS_KEY = "api-default-user"
SECRET_KEY = "s3cr3t-value"
PASSWORD_USERINFO_URL = "http://" + ":".join(("user", "password")) + "@store:80/bucket"


class _Skipped(Exception):
    """Stands in for the Robot skip, so a skip is distinguishable from a failure."""


def _fake_builtin(recorder: list[str]) -> type:
    class _FakeBuiltIn:
        def skip(self, message: str) -> None:
            recorder.append(message)
            raise _Skipped(message)

    return _FakeBuiltIn


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _secret_payload(access: str | None = ACCESS_KEY, secret: str | None = SECRET_KEY) -> str:
    data = {}
    if access is not None:
        data["minio-access-key"] = base64.b64encode(access.encode()).decode()
    if secret is not None:
        data["minio-secret-key"] = base64.b64encode(secret.encode()).decode()
    return json.dumps({"data": data})


@pytest.fixture
def skips(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    recorded: list[str] = []
    monkeypatch.setattr(storage_credentials, "BuiltIn", _fake_builtin(recorded))
    return recorded


def _stub_kubectl(
    monkeypatch: pytest.MonkeyPatch,
    result: subprocess.CompletedProcess,
    calls: list | None = None,
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if calls is not None:
            calls.append((argv, kwargs))
        return result

    monkeypatch.setattr(storage_credentials.subprocess, "run", fake_run)


def _stub_reachability(monkeypatch: pytest.MonkeyPatch, reachable: bool, seen: list[str] | None = None) -> None:
    def fake_probe(bucket_url: str, timeout: float = 2.0) -> bool:
        if seen is not None:
            seen.append(bucket_url)
        return reachable

    monkeypatch.setattr(storage_credentials, "_object_storage_reachable", fake_probe)


def test_absent_secret_fails_when_the_store_is_reachable(monkeypatch: pytest.MonkeyPatch, skips: list[str]) -> None:
    """The store answers, so missing credentials are a provisioning failure, not an absent feature."""
    _stub_kubectl(
        monkeypatch, _completed(1, stderr='Error from server (NotFound): secrets "minio-credentials" not found')
    )
    _stub_reachability(monkeypatch, reachable=True)

    with pytest.raises(AssertionError, match="provisioning failure"):
        storage_credentials._read_project_credentials(NAMESPACE, BUCKET_URL)
    assert skips == [], "a reachable store must not skip"


def test_absent_secret_skips_only_when_the_store_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, skips: list[str]
) -> None:
    """Nothing is listening and no credentials exist: genuinely no object storage to verify."""
    _stub_kubectl(
        monkeypatch, _completed(1, stderr='Error from server (NotFound): secrets "minio-credentials" not found')
    )
    _stub_reachability(monkeypatch, reachable=False)

    with pytest.raises(_Skipped):
        storage_credentials._read_project_credentials(NAMESPACE, BUCKET_URL)
    assert len(skips) == 1


@pytest.mark.parametrize(
    "stderr",
    [
        'Error from server (NotFound): secrets "minio-credentials" not found',
        'Error from server (NotFound): secret "minio-credentials" not found',
        'Error from server (NotFound): secrets "minio-credentials" not found in namespace "e2e-project"',
    ],
    ids=["plural", "singular", "extra-context"],
)
def test_the_skip_survives_kubectl_wording_changes(
    monkeypatch: pytest.MonkeyPatch, skips: list[str], stderr: str
) -> None:
    """The skip keys on the stable reason marker plus the secret name, not on one English sentence."""
    _stub_kubectl(monkeypatch, _completed(1, stderr=stderr))
    _stub_reachability(monkeypatch, reachable=False)

    with pytest.raises(_Skipped):
        storage_credentials._read_project_credentials(NAMESPACE, BUCKET_URL)
    assert len(skips) == 1


def test_an_absent_namespace_fails_rather_than_skipping(monkeypatch: pytest.MonkeyPatch, skips: list[str]) -> None:
    """A NotFound naming the namespace is a broken test fixture, not an install without storage."""
    _stub_kubectl(monkeypatch, _completed(1, stderr='Error from server (NotFound): namespaces "e2e-project" not found'))
    _stub_reachability(monkeypatch, reachable=False)

    with pytest.raises(RuntimeError, match="Could not read secret"):
        storage_credentials._read_project_credentials(NAMESPACE, BUCKET_URL)
    assert skips == [], "only an absent credentials secret may skip"


def test_denied_lookup_raises_rather_than_skipping(monkeypatch: pytest.MonkeyPatch, skips: list[str]) -> None:
    """A 403 is a broken environment; skipping it would hide a broken permission path."""
    _stub_kubectl(
        monkeypatch,
        _completed(1, stderr='Error from server (Forbidden): secrets "minio-credentials" is forbidden'),
    )
    _stub_reachability(monkeypatch, reachable=False)

    with pytest.raises(RuntimeError, match="Could not read secret"):
        storage_credentials._read_project_credentials(NAMESPACE, BUCKET_URL)
    assert skips == [], "a denied lookup must never skip, reachable or not"


@pytest.mark.parametrize(
    ("access", "secret", "expected"),
    [(None, SECRET_KEY, "minio-access-key"), (ACCESS_KEY, None, "minio-secret-key")],
)
def test_secret_missing_a_field_fails(
    monkeypatch: pytest.MonkeyPatch,
    skips: list[str],
    access: str | None,
    secret: str | None,
    expected: str,
) -> None:
    """The secret exists, so a missing field is malformed config rather than an absent feature."""
    _stub_kubectl(monkeypatch, _completed(0, stdout=_secret_payload(access, secret)))

    with pytest.raises(AssertionError, match=expected):
        storage_credentials._read_project_credentials(NAMESPACE, BUCKET_URL)
    assert skips == []


def test_the_probe_asks_about_the_url_it_was_given(monkeypatch: pytest.MonkeyPatch, skips: list[str]) -> None:
    """The skip decision must be made about the store the S3 Jobs use, not a module default."""
    seen: list[str] = []
    _stub_kubectl(
        monkeypatch, _completed(1, stderr='Error from server (NotFound): secrets "minio-credentials" not found')
    )
    _stub_reachability(monkeypatch, reachable=False, seen=seen)

    with pytest.raises(_Skipped):
        storage_credentials._read_project_credentials(NAMESPACE, "http://override.example:9443/override-bucket")
    assert seen == ["http://override.example:9443/override-bucket"]


def test_provisioning_pipes_the_manifest_and_returns_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentials reach kubectl on stdin and never become a Robot variable or a temp file."""
    calls: list = []
    _stub_kubectl(monkeypatch, _completed(0, stdout=_secret_payload()), calls=calls)

    returned = storage_credentials.provision_storage_credentials_secret(
        NAMESPACE, "storage-secret", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY", BUCKET_URL
    )

    assert returned is None, "returning the credentials would let Robot log them"
    apply_argv, apply_kwargs = calls[-1]
    assert apply_argv[:2] == ["kubectl", "apply"]
    assert apply_argv[-1] == "-", "the manifest must be piped, not written to disk"
    manifest = json.loads(apply_kwargs["input"])
    assert manifest["stringData"] == {"ACCESS_KEY_ID": ACCESS_KEY, "SECRET_ACCESS_KEY": SECRET_KEY}


def test_a_failed_apply_reports_stderr_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The manifest carries the credentials, so it must not reach the error text."""
    _stub_kubectl(monkeypatch, _completed(0, stdout=_secret_payload()))

    def failing_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if argv[:2] == ["kubectl", "apply"]:
            return _completed(1, stderr="forbidden")
        return _completed(0, stdout=_secret_payload())

    monkeypatch.setattr(storage_credentials.subprocess, "run", failing_run)

    with pytest.raises(RuntimeError) as excinfo:
        storage_credentials.provision_storage_credentials_secret(
            NAMESPACE, "storage-secret", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY", BUCKET_URL
        )
    assert SECRET_KEY not in str(excinfo.value)


@pytest.mark.parametrize("url", ["http://host:notaport/b", "http:///b"])
def test_a_malformed_url_raises_instead_of_reporting_unreachable(url: str) -> None:
    """Answering False would skip the test, turning a configuration error into a silent pass-over."""
    with pytest.raises(ValueError):
        storage_credentials._object_storage_reachable(url, timeout=0.01)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://store:80/default-bucket", "http://store:80/default-bucket"),
        ("https://store:443/default-bucket", "https://store:443/default-bucket"),
        ("store:80/default-bucket", "http://store:80/default-bucket"),
        ("//store:80/default-bucket", "http://store:80/default-bucket"),
        ("http://store:80/default-bucket/", "http://store:80/default-bucket"),
    ],
    ids=["http", "https", "schemeless", "protocol-relative", "trailing-slash"],
)
def test_bucket_url_is_normalized_for_the_s3_jobs(raw: str, expected: str) -> None:
    """Every accepted input becomes the full, trailing-slash-free URL handed to the Job ConfigMap."""
    assert storage_credentials.normalize_object_storage_bucket_url(raw) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://store:80",
        "http://store:80/",
        "http://store:80/a/b",
        "ftp://store:21/bucket",
        "http://host:notaport/bucket",
        "http:///bucket",
        "http://user@store:80/bucket",
        PASSWORD_USERINFO_URL,
        "http://store:80/bucket?versioning=on",
        "http://store:80/bucket#frag",
    ],
    ids=[
        "no-path",
        "empty-path",
        "multi-segment",
        "wrong-scheme",
        "bad-port",
        "no-host",
        "username",
        "username-password",
        "query",
        "fragment",
    ],
)
def test_bucket_url_requires_an_http_host_and_single_bucket_segment(url: str) -> None:
    """The Job parser needs an HTTP endpoint and exactly one bucket path segment."""
    with pytest.raises(ValueError):
        storage_credentials.normalize_object_storage_bucket_url(url)


def test_a_schemeless_url_is_tolerated_by_the_probe() -> None:
    """The reachability probe accepts the same bare address form the normalizer accepts."""
    assert storage_credentials._object_storage_reachable("127.0.0.1:9/default-bucket", timeout=0.05) is False


def test_module_exposes_no_credential_state() -> None:
    """Nothing caches the credentials at module scope where a later reader could pick them up."""
    leaked = [
        name for name, value in vars(storage_credentials).items() if isinstance(value, str) and SECRET_KEY in value
    ]
    assert leaked == []
