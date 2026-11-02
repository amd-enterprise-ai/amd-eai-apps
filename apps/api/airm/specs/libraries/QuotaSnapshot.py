# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Robot Framework support for reproducing quota snapshot races."""

import asyncio
import json
from datetime import UTC, datetime

import aio_pika


class QuotaSnapshot:
    """Publishes simulated cluster status messages through RabbitMQ."""

    ROBOT_LIBRARY_SCOPE = "TEST"

    def make_simulated_cluster_ready(
        self,
        cluster_id: str,
        cluster_secret: str,
        cluster_name: str,
        rabbitmq_host: str,
        rabbitmq_port: int,
    ) -> str:
        """Publish heartbeat and node capacity, followed by a processing marker."""
        now = datetime.now(UTC).isoformat()
        messages: list[dict[str, object]] = [
            {
                "message_type": "heartbeat",
                "last_heartbeat_at": now,
                "cluster_name": cluster_name,
            },
            {
                "message_type": "cluster_nodes",
                "updated_at": now,
                "cluster_nodes": [
                    {
                        "name": "simulated-node",
                        "cpu_milli_cores": 4000,
                        "memory_bytes": 4294967296,
                        "ephemeral_storage_bytes": 4294967296,
                        "gpu_information": None,
                        "status": "Ready",
                        "is_ready": True,
                    }
                ],
            },
        ]
        return asyncio.run(
            self._publish_with_marker(
                cluster_id,
                cluster_secret,
                cluster_name,
                rabbitmq_host,
                rabbitmq_port,
                messages,
            )
        )

    def publish_quota_snapshot_without_project(
        self,
        cluster_id: str,
        cluster_secret: str,
        cluster_name: str,
        rabbitmq_host: str,
        rabbitmq_port: int,
    ) -> str:
        """Publish an empty allocation snapshot, followed by a processing marker."""
        messages: list[dict[str, object]] = [
            {
                "message_type": "cluster_quotas_status",
                "updated_at": datetime.now(UTC).isoformat(),
                "quota_allocations": [],
            }
        ]
        return asyncio.run(
            self._publish_with_marker(
                cluster_id,
                cluster_secret,
                cluster_name,
                rabbitmq_host,
                rabbitmq_port,
                messages,
            )
        )

    def publish_quota_allocation(
        self,
        cluster_id: str,
        cluster_secret: str,
        cluster_name: str,
        rabbitmq_host: str,
        rabbitmq_port: int,
        project_name: str,
        cpu_milli_cores: int,
        memory_bytes: int,
        ephemeral_storage_bytes: int,
        gpu_count: int,
    ) -> str:
        """Publish a snapshot carrying one named allocation, followed by a processing marker."""
        messages: list[dict[str, object]] = [
            {
                "message_type": "cluster_quotas_status",
                "updated_at": datetime.now(UTC).isoformat(),
                "quota_allocations": [
                    {
                        "quota_name": project_name,
                        "namespaces": [project_name],
                        "cpu_milli_cores": int(cpu_milli_cores),
                        "memory_bytes": int(memory_bytes),
                        "ephemeral_storage_bytes": int(ephemeral_storage_bytes),
                        "gpu_count": int(gpu_count),
                    }
                ],
            }
        ]
        return asyncio.run(
            self._publish_with_marker(
                cluster_id,
                cluster_secret,
                cluster_name,
                rabbitmq_host,
                rabbitmq_port,
                messages,
            )
        )

    def publish_quota_failure_without_reason(
        self,
        cluster_id: str,
        cluster_secret: str,
        cluster_name: str,
        rabbitmq_host: str,
        rabbitmq_port: int,
    ) -> str:
        """Publish a quota failure carrying no reason, followed by a processing marker."""
        messages: list[dict[str, object]] = [
            {
                "message_type": "cluster_quotas_failure",
                "updated_at": datetime.now(UTC).isoformat(),
                "reason": None,
            }
        ]
        return asyncio.run(
            self._publish_with_marker(
                cluster_id,
                cluster_secret,
                cluster_name,
                rabbitmq_host,
                rabbitmq_port,
                messages,
            )
        )

    def publish_project_ready(
        self,
        cluster_id: str,
        cluster_secret: str,
        cluster_name: str,
        rabbitmq_host: str,
        rabbitmq_port: int,
        project_id: str,
        project_name: str,
        cpu_milli_cores: int,
        memory_bytes: int,
        ephemeral_storage_bytes: int,
        gpu_count: int,
    ) -> str:
        """Publish matching quota and namespace state, followed by a processing marker."""
        messages: list[dict[str, object]] = [
            {
                "message_type": "cluster_quotas_status",
                "updated_at": datetime.now(UTC).isoformat(),
                "quota_allocations": [
                    {
                        "quota_name": project_name,
                        "namespaces": [project_name],
                        "cpu_milli_cores": int(cpu_milli_cores),
                        "memory_bytes": int(memory_bytes),
                        "ephemeral_storage_bytes": int(ephemeral_storage_bytes),
                        "gpu_count": int(gpu_count),
                    }
                ],
            },
            {
                "message_type": "project_namespace_status",
                "project_id": project_id,
                "status": "Active",
                "status_reason": None,
            },
        ]
        return asyncio.run(
            self._publish_with_marker(
                cluster_id,
                cluster_secret,
                cluster_name,
                rabbitmq_host,
                rabbitmq_port,
                messages,
            )
        )

    def publish_project_deleted(
        self,
        cluster_id: str,
        cluster_secret: str,
        cluster_name: str,
        rabbitmq_host: str,
        rabbitmq_port: int,
        project_id: str,
    ) -> str:
        """Publish deleted quota and namespace state, followed by a processing marker."""
        messages: list[dict[str, object]] = [
            {
                "message_type": "cluster_quotas_status",
                "updated_at": datetime.now(UTC).isoformat(),
                "quota_allocations": [],
            },
            {
                "message_type": "project_namespace_status",
                "project_id": project_id,
                "status": "Deleted",
                "status_reason": None,
            },
        ]
        return asyncio.run(
            self._publish_with_marker(
                cluster_id,
                cluster_secret,
                cluster_name,
                rabbitmq_host,
                rabbitmq_port,
                messages,
            )
        )

    async def _publish_with_marker(
        self,
        cluster_id: str,
        cluster_secret: str,
        cluster_name: str,
        rabbitmq_host: str,
        rabbitmq_port: int,
        messages: list[dict[str, object]],
    ) -> str:
        marker = datetime.now(UTC).isoformat()
        messages.append(
            {
                "message_type": "heartbeat",
                "last_heartbeat_at": marker,
                "cluster_name": cluster_name,
            }
        )

        connection = await aio_pika.connect_robust(
            host=rabbitmq_host,
            port=int(rabbitmq_port),
            virtualhost="vh_airm_common",
            login=cluster_id,
            password=cluster_secret,
        )
        try:
            channel = await connection.channel()
            for body in messages:
                message = aio_pika.Message(
                    json.dumps(body).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    user_id=cluster_id,
                )
                await channel.default_exchange.publish(message, routing_key="airm_common")
        finally:
            await connection.close()
        return marker

    @staticmethod
    def current_utc_timestamp() -> str:
        """Return the runner's current UTC time, as stamped onto published messages."""
        return datetime.now(UTC).isoformat()

    @staticmethod
    def timestamp_should_be_at_or_after(actual: str, expected: str) -> None:
        """Assert that an API timestamp is at or after the expected marker."""
        actual_timestamp = datetime.fromisoformat(actual.replace("Z", "+00:00"))
        expected_timestamp = datetime.fromisoformat(expected.replace("Z", "+00:00"))
        if actual_timestamp < expected_timestamp:
            raise AssertionError(f"Timestamp {actual} is before marker {expected}")
