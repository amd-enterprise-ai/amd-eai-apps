# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Pins the separate endpoint and bucket contract used by AIWB S3 specs."""

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

_LIBRARIES = Path(__file__).resolve().parent / "libraries"
if str(_LIBRARIES) not in sys.path:
    sys.path.insert(0, str(_LIBRARIES))

_HELPER_MODULE = "AIMModelHelper"
_ENV_KEYS = ("AIWB_SPECS_S3_BUCKET_URL", "AIWB_SPECS_MINIO_ENDPOINT", "AIWB_SPECS_MINIO_BUCKET")
# Build this at runtime so GitHub's secret masker does not replace the fake password-bearing URL
# with asterisks before reviewers can see which validation branch the test exercises.
_PASSWORD_USERINFO_URL = "http://" + ":".join(("user", "password")) + "@store:80/bucket"


def _load_helper(monkeypatch: pytest.MonkeyPatch, **env: str) -> ModuleType:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop(_HELPER_MODULE, None)
    try:
        return importlib.import_module(_HELPER_MODULE)
    finally:
        # A failed import can leave a half-initialized module registered; drop it so a later load
        # re-executes module-scope code against fresh environment.
        sys.modules.pop(_HELPER_MODULE, None)


def test_default_uses_a_pathless_endpoint_and_separate_default_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    """AIWB's BUCKET_URL is an endpoint origin; S3 source URIs carry the bucket separately."""
    helper = _load_helper(monkeypatch)

    assert helper._S3_BUCKET_URL == "http://filer-s3.seaweedfs-instance.svc.cluster.local:80"
    assert helper._MINIO_ENDPOINT == "filer-s3.seaweedfs-instance.svc.cluster.local:80"
    assert helper._MINIO_BUCKET == "default-bucket"


def test_bucket_url_may_override_the_bucket_via_a_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit path is honoured, but one is not required by the endpoint contract."""
    helper = _load_helper(monkeypatch, AIWB_SPECS_S3_BUCKET_URL="https://store.example:9443/other-bucket")

    assert helper._S3_BUCKET_URL == "https://store.example:9443/other-bucket"
    assert helper._MINIO_ENDPOINT == "store.example:9443"
    assert helper._MINIO_SECURE is True
    assert helper._MINIO_BUCKET == "other-bucket"


def test_explicit_bucket_setting_takes_precedence_over_url_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dedicated bucket setting remains the authoritative override when both are present."""
    helper = _load_helper(
        monkeypatch,
        AIWB_SPECS_S3_BUCKET_URL="http://store.example:80/path-bucket",
        AIWB_SPECS_MINIO_BUCKET="explicit-bucket",
    )

    assert helper._MINIO_BUCKET == "explicit-bucket"


def test_trailing_slash_and_scheme_are_canonicalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """A trailing slash must not leak into the bucket name or the ConfigMap BUCKET_URL."""
    helper = _load_helper(monkeypatch, AIWB_SPECS_S3_BUCKET_URL="store.example:80/other-bucket/")

    assert helper._S3_BUCKET_URL == "http://store.example:80/other-bucket"
    assert helper._MINIO_BUCKET == "other-bucket"


@pytest.mark.parametrize(
    "url",
    [
        "http://store:80/a/b",
        "ftp://store:21/bucket",
        "http://host:notaport/bucket",
        "http:///bucket",
        "http://user@store:80/bucket",
        _PASSWORD_USERINFO_URL,
        "http://store:80/bucket?versioning=on",
        "http://store:80/bucket#frag",
    ],
    ids=[
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
def test_an_invalid_bucket_url_is_rejected_at_import(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    """A malformed bucket URL fails loudly rather than yielding an invalid endpoint or bucket."""
    with pytest.raises(ValueError):
        _load_helper(monkeypatch, AIWB_SPECS_S3_BUCKET_URL=url)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://user@store:9000",
        _PASSWORD_USERINFO_URL.rsplit("/", maxsplit=1)[0],
        "http://store:9000/a-bucket",
        "ftp://store:21",
        "http://host:notaport",
        "http:///",
        "http://store:9000?bucket=other",
        "http://store:9000#other",
    ],
    ids=[
        "username",
        "username-password",
        "path",
        "wrong-scheme",
        "bad-port",
        "no-host",
        "query",
        "fragment",
    ],
)
def test_an_invalid_endpoint_override_is_rejected(monkeypatch: pytest.MonkeyPatch, endpoint: str) -> None:
    """Endpoint overrides carry no credentials, path, invalid transport, host, or port."""
    with pytest.raises(ValueError):
        _load_helper(monkeypatch, AIWB_SPECS_MINIO_ENDPOINT=endpoint)


@pytest.mark.parametrize(
    ("endpoint", "expected", "secure"),
    [
        ("store:9000", "store:9000", False),
        ("http://store:9000", "store:9000", False),
        ("http://store:9000/", "store:9000", False),
        ("https://store:9443", "store:9443", True),
    ],
    ids=["bare", "http", "http-trailing-slash", "https"],
)
def test_endpoint_override_accepts_only_an_origin(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, expected: str, secure: bool
) -> None:
    """Valid endpoint overrides retain only the HTTP(S) origin and transport."""
    helper = _load_helper(monkeypatch, AIWB_SPECS_MINIO_ENDPOINT=endpoint)
    assert helper._MINIO_ENDPOINT == expected
    assert helper._MINIO_SECURE is secure
