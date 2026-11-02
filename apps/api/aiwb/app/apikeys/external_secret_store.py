# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Per-key ExternalSecret store for API keys.

Each API key is one **ExternalSecret** ``apikey-<key_id>`` whose single ``data`` entry is a
``remoteRef`` to the key's OpenBao KV path, so External Secrets Operator (ESO) materializes one
labelled Kubernetes Secret per key. **AIWB never writes that Secret** — ESO owns it; AIWB only owns
the ExternalSecret.

Binding a key to a deployed model is expressed as a ``bound-<workload-id>`` **label** stamped (via
``target.template``) onto the materialized Secret. ai-gateway-discovery lists the key Secrets bound
to a model and lists them all in that model's SecurityPolicy ``credentialRefs`` (authorization =
membership). So:

- Create  = one ExternalSecret per key (created on key create, independent of bindings).
- Bind    = add ``bound-<workload-id>: "true"`` to the key's ExternalSecret template labels.
- Unbind  = remove that label.
- Delete  = delete the ExternalSecret (on key delete).
- Expiry  = native: OpenBao ``delete_version_after`` drops the version; the next ESO sync prunes it.

``target.deletionPolicy: Merge`` is load-bearing for expiry: when OpenBao soft-deletes a KV version
the read returns "gone" — the default ``Retain`` treats that as an error and keeps the stale key,
whereas ``Merge`` prunes it. ``Merge`` + ``creationPolicy: Owner`` is an allowed combination.
"""

import re

from kubernetes_asyncio.client import ApiException
from loguru import logger

from ..dispatch.kube_client import KubernetesClient
from ..openbao.config import OPENBAO_API_KEY_PATH_PREFIX, OPENBAO_SECRET_STORE_REF

# ExternalSecret CRD (matches the deployed cluster-forge openbao-secret-store).
ES_GROUP = "external-secrets.io"
ES_VERSION = "v1beta1"
ES_PLURAL = "externalsecrets"

# The API-key contract label; the gateway/SecurityPolicy selects Secrets by it.
API_KEY_LABEL = "eai.amd.com/api-key"
MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
MANAGED_BY_VALUE = "aiwb"

# Per-model binding is a label ``<BOUND_LABEL_PREFIX><workload-id>: "true"`` on the key's Secret.
# ai-gateway-discovery selects a model's key Secrets with a label selector on this key, and reads
# a key's bindings back off these labels. Must match the controller's boundLabelPrefix.
BOUND_LABEL_PREFIX = "apikey.eai.amd.com/bound-"

# The key's human-friendly name, propagated to the ExternalSecret + materialized Secret as an
# annotation (not a label — display names allow spaces/case/unicode that labels forbid). Display
# only; the Secret name is apikey-<key_id> and the data-key is the sanitized client_id.
DISPLAY_NAME_ANNOTATION = "apikey.eai.amd.com/display-name"

# One ExternalSecret / Secret per key: apikey-<key_id>. Must match the controller's prefix.
SECRET_NAME_PREFIX = "apikey-"

# ESO poll interval — also the upper bound on how fast an expired key drops from the Secret.
REFRESH_INTERVAL = "1m"


def key_secret_name(key_id: str) -> str:
    """Name of the per-key ExternalSecret / materialized Secret."""
    return f"{SECRET_NAME_PREFIX}{key_id}"


def bound_label(workload_id: str) -> str:
    """Membership label marking a key's Secret as bound to a model (value ``"true"``)."""
    return f"{BOUND_LABEL_PREFIX}{workload_id}"


def compute_client_id(namespace: str, display_name: str) -> str:
    """Return the ``x-api-key-id`` (``token-<ns>-<key>``) used as the Secret data-key.

    Format is fixed by the metrics + rate-limiting contract; keep it stable. Non ``[a-z0-9-]`` is
    replaced with ``-`` and lowercased, mirroring how OpenBao/cluster-auth derive the token name.
    """
    ns = re.sub(r"[^a-z0-9-]", "-", namespace.lower())
    key = re.sub(r"[^a-z0-9-]", "-", display_name.lower())
    return f"token-{ns}-{key}"


def _remote_ref(key_id: str) -> dict:
    """ESO data entry pointing at the key's OpenBao KV path (property ``token``)."""
    return {"key": f"{OPENBAO_API_KEY_PATH_PREFIX}/{key_id}", "property": "token"}


def _template_labels(bound_workload_ids: set[str]) -> dict:
    """Labels ESO stamps on the materialized Secret: the contract label plus one per binding."""
    labels = {API_KEY_LABEL: "true", MANAGED_BY_LABEL: MANAGED_BY_VALUE}
    for workload_id in sorted(bound_workload_ids):
        labels[bound_label(workload_id)] = "true"
    return labels


def _new_external_secret(
    namespace: str, key_id: str, client_id: str, display_name: str, bound_workload_ids: set[str]
) -> dict:
    name = key_secret_name(key_id)
    annotations = {DISPLAY_NAME_ANNOTATION: display_name}
    return {
        "apiVersion": f"{ES_GROUP}/{ES_VERSION}",
        "kind": "ExternalSecret",
        "metadata": {
            "name": name,
            "namespace": namespace,
            # The contract label also goes on the ExternalSecret itself so the airm secret-discovery
            # webhooks (which fire on all secrets/externalsecrets in a project namespace) skip it.
            "labels": {API_KEY_LABEL: "true", MANAGED_BY_LABEL: MANAGED_BY_VALUE},
            # Human-friendly name for discoverability (the object name is a UUID).
            "annotations": annotations,
        },
        "spec": {
            "refreshInterval": REFRESH_INTERVAL,
            "secretStoreRef": {"name": OPENBAO_SECRET_STORE_REF, "kind": "ClusterSecretStore"},
            "target": {
                "name": name,
                "creationPolicy": "Owner",
                # Merge prunes an expired/deleted key from the Secret instead of erroring and
                # retaining it (the default Retain does) — required for native OpenBao expiry.
                "deletionPolicy": "Merge",
                # ESO stamps these onto the materialized Secret: the contract label so the gateway
                # can find it, one bound-<workload-id> per model, and the display-name annotation.
                "template": {"metadata": {"labels": _template_labels(bound_workload_ids), "annotations": annotations}},
            },
            "data": [{"secretKey": client_id, "remoteRef": _remote_ref(key_id)}],
        },
    }


async def _get(kube_client: KubernetesClient, namespace: str, name: str) -> dict | None:
    try:
        return await kube_client.custom_objects.get_namespaced_custom_object(
            group=ES_GROUP, version=ES_VERSION, namespace=namespace, plural=ES_PLURAL, name=name
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def _patch_template_labels(kube_client: KubernetesClient, namespace: str, name: str, labels: dict) -> None:
    # Replace spec.target.template.metadata.labels via a JSON Patch. The ExternalSecret is always
    # created with that path present, so "replace" is safe (a merge-patch body is rejected by the
    # json-patch content type the client sends by default).
    await kube_client.custom_objects.patch_namespaced_custom_object(
        group=ES_GROUP,
        version=ES_VERSION,
        namespace=namespace,
        plural=ES_PLURAL,
        name=name,
        body=[{"op": "replace", "path": "/spec/target/template/metadata/labels", "value": labels}],
    )


async def _delete(kube_client: KubernetesClient, namespace: str, name: str) -> None:
    try:
        await kube_client.custom_objects.delete_namespaced_custom_object(
            group=ES_GROUP, version=ES_VERSION, namespace=namespace, plural=ES_PLURAL, name=name
        )
    except ApiException as e:
        if e.status != 404:
            raise


def _bound_workload_ids(es: dict) -> set[str]:
    """The workload-ids a key's ExternalSecret is bound to (from its template labels)."""
    labels = es.get("spec", {}).get("target", {}).get("template", {}).get("metadata", {}).get("labels", {}) or {}
    return {k[len(BOUND_LABEL_PREFIX) :] for k in labels if k.startswith(BOUND_LABEL_PREFIX)}


async def create_key_secret(
    kube_client: KubernetesClient,
    namespace: str,
    key_id: str,
    client_id: str,
    display_name: str,
    bound_workload_ids: set[str] | None = None,
) -> None:
    """Create the per-key ExternalSecret (idempotent), optionally pre-bound to some models.

    ``display_name`` is stamped as the ``apikey.eai.amd.com/display-name`` annotation on the
    ExternalSecret and (via the template) the materialized Secret, for human discoverability.
    """
    name = key_secret_name(key_id)
    bound = set(bound_workload_ids or set())
    try:
        await kube_client.custom_objects.create_namespaced_custom_object(
            group=ES_GROUP,
            version=ES_VERSION,
            namespace=namespace,
            plural=ES_PLURAL,
            body=_new_external_secret(namespace, key_id, client_id, display_name, bound),
        )
        logger.info(f"Created ExternalSecret '{name}' in '{namespace}' (bound to {len(bound)} model(s))")
    except ApiException as e:
        if e.status != 409:
            raise
        # Already exists: converge its bindings on the requested set (idempotent create).
        await set_key_bindings(kube_client, namespace, key_id, bound)


async def set_key_bindings(
    kube_client: KubernetesClient,
    namespace: str,
    key_id: str,
    target_workload_ids: set[str],
) -> None:
    """Converge a key's model bindings on ``target_workload_ids`` by rewriting its template labels.

    The SecurityPolicy per model lists every key Secret carrying its bound-<workload-id> label, so
    a binding change is a label edit on the key's Secret — no token handling, no cluster-auth calls.
    """
    name = key_secret_name(key_id)
    existing = await _get(kube_client, namespace, name)
    if existing is None:
        raise NotFoundKeySecret(f"ExternalSecret '{name}' not found in '{namespace}'")
    target = set(target_workload_ids)
    if _bound_workload_ids(existing) == target:
        return  # already converged
    await _patch_template_labels(kube_client, namespace, name, _template_labels(target))
    logger.info(f"Set bindings for ExternalSecret '{name}' in '{namespace}' to {len(target)} model(s)")


async def list_workload_ids_for_key(
    kube_client: KubernetesClient,
    namespace: str,
    key_id: str,
) -> list[str]:
    """Return the workload-ids of every model this key is bound to (its Secret membership)."""
    existing = await _get(kube_client, namespace, key_secret_name(key_id))
    if existing is None:
        return []
    return sorted(_bound_workload_ids(existing))


async def delete_key_secret(kube_client: KubernetesClient, namespace: str, key_id: str) -> None:
    """Delete a key's ExternalSecret (on key delete). Idempotent (404 tolerated)."""
    name = key_secret_name(key_id)
    await _delete(kube_client, namespace, name)
    logger.info(f"Deleted ExternalSecret '{name}' in '{namespace}'")


class NotFoundKeySecret(Exception):
    """Raised when a key's ExternalSecret is expected but absent (e.g. rebind before create)."""
