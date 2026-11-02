# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the presigning MinIO client, which targets the externally reachable endpoint."""

import importlib
from unittest.mock import patch

import pytest

import app.minio.config as minio_config
from app.minio import init_minio_client
from app.minio.client import MinioClient, is_in_cluster_host


def test_external_client_targets_the_external_endpoint():
    """The presigning client must connect to the endpoint it is given, not the in-cluster one."""
    with (
        patch("app.minio.MINIO_URL", "http://filer-s3.example.svc.cluster.local:80"),
        patch("app.minio.MINIO_ACCESS_KEY", "access_key"),
        patch("app.minio.MINIO_SECRET_KEY", "secret_key"),
        patch("app.minio.client.Minio") as mock_minio,
    ):
        assert init_minio_client("https://s3.example.com") is not None

    args, kwargs = mock_minio.call_args
    assert args[0] == "s3.example.com"
    assert kwargs.get("secure") is True


def test_client_defaults_to_the_internal_endpoint():
    """Called with no endpoint, the client stays on the in-cluster service."""
    with (
        patch("app.minio.MINIO_URL", "http://filer-s3.example.svc.cluster.local:80"),
        patch("app.minio.MINIO_ACCESS_KEY", "access_key"),
        patch("app.minio.MINIO_SECRET_KEY", "secret_key"),
        patch("app.minio.client.Minio") as mock_minio,
    ):
        assert init_minio_client() is not None

    args, kwargs = mock_minio.call_args
    assert args[0] == "filer-s3.example.svc.cluster.local:80"
    assert kwargs.get("secure") is False


def test_external_client_is_unavailable_without_credentials():
    """Missing credentials degrade to no client rather than raising at startup."""
    with (
        patch("app.minio.MINIO_ACCESS_KEY", ""),
        patch("app.minio.MINIO_SECRET_KEY", ""),
    ):
        assert init_minio_client("https://s3.example.com") is None


def test_external_url_defaults_to_internal_url(monkeypatch):
    """Deployments that never set MINIO_EXTERNAL_URL keep signing for the internal endpoint."""
    monkeypatch.delenv("MINIO_EXTERNAL_URL", raising=False)
    monkeypatch.setenv("MINIO_URL", "http://filer-s3.example.svc.cluster.local:80")
    try:
        reloaded = importlib.reload(minio_config)
        assert reloaded.MINIO_EXTERNAL_URL == "http://filer-s3.example.svc.cluster.local:80"
    finally:
        monkeypatch.undo()
        importlib.reload(minio_config)


def test_external_url_overrides_internal_url(monkeypatch):
    """When set, MINIO_EXTERNAL_URL is used for signing and leaves MINIO_URL untouched."""
    monkeypatch.setenv("MINIO_URL", "http://filer-s3.example.svc.cluster.local:80")
    monkeypatch.setenv("MINIO_EXTERNAL_URL", "https://s3.example.com")
    try:
        reloaded = importlib.reload(minio_config)
        assert reloaded.MINIO_EXTERNAL_URL == "https://s3.example.com"
        assert reloaded.MINIO_URL == "http://filer-s3.example.svc.cluster.local:80"
    finally:
        monkeypatch.undo()
        importlib.reload(minio_config)


@pytest.mark.parametrize(
    ("url", "in_cluster"),
    [
        ("http://minio.minio-tenant-default.svc.cluster.local:80", True),
        ("http://filer-s3.default.svc", True),
        ("http://minio", True),
        ("https://seaweed.example.com", False),
        ("https://s3.example.com:9000", False),
        ("s3.example.com", False),
        ("https://S3.EXAMPLE.COM", False),
    ],
)
def test_host_classification(url, in_cluster):
    """A port, a missing scheme, or an uppercase host must not change the verdict."""
    assert is_in_cluster_host(url) is in_cluster


@pytest.mark.parametrize("url", ["http://10.0.0.5:9000", "http://localhost:9000"])
def test_private_and_loopback_hosts_classify_as_external(url):
    """Not on the public Internet is a different question from not reachable by the caller, and
    only the second one matters here. On-prem and air-gapped installs hand out exactly these
    addresses, so classifying them as unusable would break the installs the check protects."""
    assert is_in_cluster_host(url) is False


def _presigning_client(host: str) -> MinioClient:
    with patch("app.minio.client.Minio"):
        return MinioClient(host=host, access_key="access_key", secret_key="secret_key")


def test_configured_public_endpoint_is_externally_addressable():
    assert _presigning_client("https://s3.example.com").is_externally_addressable() is True


def test_configured_in_cluster_endpoint_is_not_externally_addressable():
    client = _presigning_client("http://filer-s3.example.svc.cluster.local:80")
    assert client.is_externally_addressable() is False
