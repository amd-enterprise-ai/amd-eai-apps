# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Core Kubernetes API client - shared across all domains."""

import sys
import threading
from typing import Any

from kubernetes import client as sync_client
from kubernetes import config as sync_config
from kubernetes import dynamic
from kubernetes_asyncio import client
from kubernetes_asyncio.client import ApiException
from loguru import logger

from ..aims.constants import (
    AIM_API_GROUP,
    AIM_CLUSTER_MODEL_PLURAL,
    AIM_CLUSTER_PROFILE_PLURAL,
    AIM_PROFILE_PLURAL,
    AIM_PROFILE_SET_PLURAL,
    AIM_SERVICE_PLURAL,
    HTTP_ROUTE_API_GROUP,
    HTTP_ROUTE_PLURAL,
)
from .config import USE_LOCAL_KUBE_CONTEXT

# Required CRDs for the service to function.
REQUIRED_CRDS = [
    f"{AIM_SERVICE_PLURAL}.{AIM_API_GROUP}",
    f"{AIM_CLUSTER_MODEL_PLURAL}.{AIM_API_GROUP}",
    f"{AIM_CLUSTER_PROFILE_PLURAL}.{AIM_API_GROUP}",
    f"{AIM_PROFILE_PLURAL}.{AIM_API_GROUP}",
    f"{AIM_PROFILE_SET_PLURAL}.{AIM_API_GROUP}",
    f"aimprofilecaches.{AIM_API_GROUP}",
    f"{HTTP_ROUTE_PLURAL}.{HTTP_ROUTE_API_GROUP}",
]


class KubernetesClient:
    """Core Kubernetes client providing access to standard K8s APIs.

    This client uses kubernetes_asyncio for true async I/O operations.
    All API methods are async and use aiohttp under the hood.

    The ApiClient is created once and reused for connection pooling efficiency.
    """

    def __init__(self):
        """Initialize Kubernetes client and create API clients.

        Note: Kubernetes configuration must be loaded (via load_k8s_config) before
        creating this client, typically during application startup.
        """
        # Create API client and all API instances
        # Configuration must already be loaded by this point
        self._api_client = client.ApiClient()
        self.core_v1 = client.CoreV1Api(self._api_client)
        self.apps_v1 = client.AppsV1Api(self._api_client)
        self.batch_v1 = client.BatchV1Api(self._api_client)
        self.custom_objects = client.CustomObjectsApi(self._api_client)
        self.api_extensions = client.ApiextensionsV1Api(self._api_client)

    async def close(self) -> None:
        """Close the API client and clean up resources."""
        await self._api_client.close()

    async def check_required_crds(self) -> None:
        """Check that all required CRDs are installed in the cluster.

        Exits the process if any required CRDs are missing.
        """
        missing_crds = []
        for crd_name in REQUIRED_CRDS:
            try:
                await self.api_extensions.read_custom_resource_definition(crd_name)
            except ApiException as e:
                if e.status == 404:
                    missing_crds.append(crd_name)
                else:
                    raise

        if missing_crds:
            logger.error(f"Required CRDs not found in cluster: {missing_crds}")
            logger.error("Please install the required CRDs before starting the service")
            sys.exit(1)

        logger.info(f"All required CRDs found: {REQUIRED_CRDS}")

    async def get_namespaced_custom_object(
        self,
        group: str,
        version: str,
        plural: str,
        namespace: str,
        name: str,
    ) -> dict[str, Any] | None:
        """Get a namespaced custom object.

        Returns:
            The custom object dict if found, None if not found (404)
        """
        try:
            result = await self.custom_objects.get_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name,
            )
            return result
        except ApiException as e:
            if e.status == 404:
                return None
            logger.error(f"Failed to get {plural}/{name} in {namespace}: {e}")
            raise

    async def get_events_for_resource(
        self,
        namespace: str,
        resource_name: str,
        resource_kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get events for a specific resource.

        Args:
            namespace: Kubernetes namespace
            resource_name: Name of the resource
            resource_kind: Optional kind filter (e.g., 'Pod', 'Job', 'Deployment')

        Returns:
            List of event dictionaries with type, reason, message, timestamp
        """
        try:
            events = await self.core_v1.list_namespaced_event(namespace=namespace)

            resource_events = []

            for event in events.items:
                # Match by involved object name
                if event.involved_object.name == resource_name:
                    if resource_kind and event.involved_object.kind != resource_kind:
                        continue

                    resource_events.append(
                        {
                            "type": event.type,
                            "reason": event.reason,
                            "message": event.message,
                            "timestamp": event.last_timestamp or event.event_time,
                            "count": event.count,
                            "source": event.source.component if event.source else None,
                        }
                    )

            # Sort by timestamp, most recent first
            resource_events.sort(key=lambda e: e["timestamp"] or "", reverse=True)
            return resource_events

        except ApiException as e:
            logger.error(f"Failed to get events for {resource_name} in {namespace}: {e}")
            return []


# Global client instances
_kube_client: KubernetesClient | None = None
_dynamic_client: dynamic.DynamicClient | None = None
_sync_api_client: sync_client.ApiClient | None = None
_dynamic_client_lock = threading.Lock()


async def init_kube_client() -> KubernetesClient:
    """Initialize the global Kubernetes client and verify required CRDs.

    Creates the client, checks that all required CRDs are installed,
    and caches the client globally.

    Returns:
        KubernetesClient instance

    Raises:
        RuntimeError: If Kubernetes client cannot be initialized
        SystemExit: If required CRDs are not found
    """
    global _kube_client
    _kube_client = KubernetesClient()
    await _kube_client.check_required_crds()
    return _kube_client


def get_kube_client() -> KubernetesClient:
    """Get the global Kubernetes client instance.

    Returns:
        KubernetesClient instance

    Raises:
        RuntimeError: If client has not been initialized via init_kube_client()
    """
    global _kube_client
    if _kube_client is None:
        raise RuntimeError("Kubernetes client not initialized. Call init_kube_client() first.")
    return _kube_client


def get_dynamic_client() -> dynamic.DynamicClient:
    """Get or create the global dynamic Kubernetes client instance.

    This uses the sync kubernetes library's DynamicClient since kubernetes_asyncio
    doesn't have an async dynamic client equivalent. Should be used with asyncio.to_thread.

    The client is cached globally and reused across all calls for efficiency.
    Thread-safe initialization using double-check locking pattern.

    Returns:
        kubernetes.dynamic.DynamicClient instance (cached)

    Raises:
        RuntimeError: If Kubernetes client cannot be initialized
    """
    global _dynamic_client, _sync_api_client

    # Fast path: client already exists
    if _dynamic_client is not None:
        return _dynamic_client

    # Slow path: need to create client (thread-safe)
    with _dynamic_client_lock:
        # Double-check: another thread might have created it while we waited for lock
        if _dynamic_client is None:
            try:
                # Load sync kubernetes config
                if USE_LOCAL_KUBE_CONTEXT:
                    sync_config.load_kube_config()
                else:
                    sync_config.load_incluster_config()

                # Create API client and dynamic client (cached globally)
                _sync_api_client = sync_client.ApiClient()
                _dynamic_client = dynamic.DynamicClient(_sync_api_client)
                logger.debug("Created and cached DynamicClient instance")
            except Exception as e:
                logger.error(f"Failed to initialize dynamic Kubernetes client: {e}")
                raise RuntimeError("Dynamic Kubernetes client not available") from e

    return _dynamic_client


def close_dynamic_client() -> None:
    """Close the dynamic Kubernetes client and its underlying API client.

    This should be called during application shutdown to properly clean up resources.
    """
    global _sync_api_client
    if _sync_api_client is not None:
        try:
            _sync_api_client.close()
            logger.debug("Closed sync API client for DynamicClient")
        except Exception as e:
            logger.error(f"Error closing sync API client: {e}")
