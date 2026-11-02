# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Provisioning of the storage-credentials Secret the S3 test Jobs mount.

The credentials never become Robot variables. Robot logs every variable assignment at INFO,
so reading them in a .resource file put the access key and secret key into routine test output;
reading, decoding, and applying them here keeps them inside one keyword call whose arguments
name only the namespace and the key names, and which returns nothing.
"""

import base64
import json
import socket
import subprocess
from urllib.parse import urlsplit, urlunsplit

from robot.api.deco import keyword
from robot.libraries.BuiltIn import BuiltIn

_KUBECTL_TIMEOUT = 60
_PROJECT_CREDENTIALS_SECRET = "minio-credentials"
_ACCESS_KEY_FIELD = "minio-access-key"
_SECRET_KEY_FIELD = "minio-secret-key"


@keyword("Normalize Object Storage Bucket URL")
def normalize_object_storage_bucket_url(bucket_url: str) -> str:
    """A full HTTP(S) bucket URL for every consumer, including the S3 Jobs.

    Robot callers may supply the same bare ``host:port/bucket`` form accepted by the direct-client
    endpoint override. Normalize it once here because the Jobs receive this value verbatim and
    ``urlparse`` otherwise reads the host as a scheme, leaving them with no endpoint. The path must
    name exactly one bucket segment: the Jobs derive the bucket with ``path.lstrip('/')``, so a
    trailing slash or a multi-segment path would yield an invalid bucket name. Returns a canonical
    URL with no trailing slash.
    """
    if "://" in bucket_url:
        normalized = bucket_url
    elif bucket_url.startswith("//"):
        normalized = f"http:{bucket_url}"
    else:
        normalized = f"http://{bucket_url}"

    parts = urlsplit(normalized)
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError(f"Object-storage URL {bucket_url!r} does not name a valid port") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"Object-storage URL {bucket_url!r} must name an HTTP(S) host")
    if parts.username is not None or parts.password is not None:
        raise ValueError(
            # Deliberately omit the raw URL: it carries the userinfo we are rejecting, and this
            # message reaches Robot/CI logs.
            "Object-storage URL must not contain embedded credentials (userinfo); use the project Secret instead"
        )
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) != 1:
        raise ValueError(f"Object-storage URL {bucket_url!r} must include exactly one /<bucket> path segment")
    if parts.query or parts.fragment:
        raise ValueError(f"Object-storage URL {bucket_url!r} must not contain a query or fragment")
    return urlunsplit((parts.scheme, parts.netloc, f"/{segments[0]}", "", ""))


def _object_storage_reachable(bucket_url: str, timeout: float = 2.0) -> bool:
    """True when a TCP connection to ``bucket_url`` can be opened.

    The URL is passed in rather than read from the environment because it decides whether a test
    skips, and that decision has to be made about the store the S3 Jobs actually use. The Jobs read
    it from the storage spec, which a run can override without touching the environment.

    False means the address did not answer -- refused, timed out, or its name did not resolve.
    Name resolution counts: an in-cluster service no release deploys has no DNS record, which is
    how genuinely-absent object storage presents itself.

    A malformed URL raises rather than answering False: this answer decides whether a test is
    skipped, and a configuration error reported as "no object storage here" would be skipped over
    instead of surfaced. A schemeless ``host:port/bucket`` is tolerated, because ``urlsplit`` would
    otherwise read its host as a scheme and leave no host at all.
    """
    parts = urlsplit(bucket_url if "//" in bucket_url else f"//{bucket_url}")
    try:
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        raise ValueError(f"Object-storage URL {bucket_url!r} does not name a valid port") from exc
    if not host:
        raise ValueError(f"Object-storage URL {bucket_url!r} names no host")
    try:
        with socket.create_connection((host, port or (443 if parts.scheme == "https" else 80)), timeout=timeout):
            return True
    except OSError:
        return False


def _read_project_credentials(namespace: str, bucket_url: str) -> tuple[str, str]:
    """The project's object-storage access key and secret key.

    A test is skipped only where there is genuinely no object storage to verify against. An absent
    secret on an install whose store answers is a provisioning failure, not an absent feature, so
    it fails: the platform means to hand every project these credentials, and skipping there
    reports a real bug as an environmental limitation and hides it.

    A denied lookup or an API-server error is likewise raised rather than skipped — the failure
    mode a piped `kubectl ... | base64 -d` produced, where the pipeline's own status hid kubectl's.
    """
    result = subprocess.run(
        ["kubectl", "get", "secret", _PROJECT_CREDENTIALS_SECRET, "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=_KUBECTL_TIMEOUT,
    )
    if result.returncode != 0:
        # Kubernetes keeps the reason marker and resource name stable even when kubectl's prose
        # varies ("secret" vs "secrets", or extra context). Both are required: a namespace-level
        # NotFound must fail rather than masquerade as an absent credentials Secret.
        secret_not_found = "(NotFound)" in result.stderr and f'"{_PROJECT_CREDENTIALS_SECRET}"' in result.stderr
        if secret_not_found:
            if _object_storage_reachable(bucket_url):
                raise AssertionError(
                    f"Object storage at {bucket_url} is reachable, but project namespace "
                    f"{namespace} was never given the {_PROJECT_CREDENTIALS_SECRET} secret the "
                    "platform provisions for it. The store exists, so this is a credential "
                    "provisioning failure rather than an install without object storage."
                )
            BuiltIn().skip(
                f"No object storage to verify against: nothing is listening at {bucket_url}, "
                f"and project namespace {namespace} holds no {_PROJECT_CREDENTIALS_SECRET} secret."
            )
        raise RuntimeError(
            f"Could not read secret {_PROJECT_CREDENTIALS_SECRET} in namespace {namespace} "
            f"(rc={result.returncode}): {result.stderr.strip()}"
        )

    data = json.loads(result.stdout).get("data") or {}
    access = base64.b64decode(data.get(_ACCESS_KEY_FIELD, "")).decode().strip()
    secret = base64.b64decode(data.get(_SECRET_KEY_FIELD, "")).decode().strip()
    # The secret exists, so this install does hand projects credentials: a missing field is
    # malformed configuration rather than an absent feature, and must fail rather than skip.
    missing = [field for field, value in ((_ACCESS_KEY_FIELD, access), (_SECRET_KEY_FIELD, secret)) if not value]
    if missing:
        raise AssertionError(
            f"Secret {_PROJECT_CREDENTIALS_SECRET} in namespace {namespace} carries no {', '.join(missing)}"
        )
    return access, secret


@keyword("Provision Storage Credentials Secret")
def provision_storage_credentials_secret(
    namespace: str,
    secret_name: str,
    access_key_name: str,
    secret_key_name: str,
    bucket_url: str,
) -> None:
    """Create the Secret the S3 Jobs mount, holding the project's own storage credentials.

    In a real cluster the Agent creates this from the storage's ExternalSecret; the E2E flow
    stands it up directly. The manifest is piped to kubectl rather than written to a temp file,
    so the credentials are never left in plaintext on disk.

    ``bucket_url`` is the storage spec's own bucket URL -- the same value the Jobs' ConfigMap
    carries -- so that whether an absent secret skips or fails is decided about the store those
    Jobs really talk to, not a default the run may have overridden.
    """
    access, secret = _read_project_credentials(namespace, bucket_url)
    manifest = json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": secret_name, "namespace": namespace},
            "type": "Opaque",
            "stringData": {access_key_name: access, secret_key_name: secret},
        }
    )
    result = subprocess.run(
        ["kubectl", "apply", "-n", namespace, "-f", "-"],
        input=manifest,
        capture_output=True,
        text=True,
        check=False,
        timeout=_KUBECTL_TIMEOUT,
    )
    if result.returncode != 0:
        # stderr only: the manifest carries the credentials and must not reach the log.
        raise RuntimeError(f"Failed to create secret {secret_name} in namespace {namespace}: {result.stderr.strip()}")
