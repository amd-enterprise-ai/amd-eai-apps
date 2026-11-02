# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from loguru import logger
from prometheus_api_client import PrometheusConnect
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.collections import PaginatedResult, paginate_list
from api_common.exceptions import ConflictException, ExternalServiceError, NotFoundException

from ..config import AI_GW_REQUEST_DURATION_METRIC, AI_GW_TOKEN_USAGE_METRIC
from ..dispatch.kube_client import KubernetesClient
from ..metrics.constants import PROMETHEUS_NAN_STRING
from ..metrics.utils import (
    a_custom_query,
    a_custom_query_range,
    get_aggregation_lookback_for_metrics,
    get_step_for_range_query,
)
from ..openbao.client import OpenBaoClient
from . import external_secret_store as es_store
from .repository import (
    count_api_keys,
    create_api_key,
    delete_api_key,
    get_api_key_by_id,
    get_api_keys_for_namespace,
)
from .schemas import (
    ApiKeyCreate,
    ApiKeyDetails,
    ApiKeyMetricsDataPoint,
    ApiKeyMetricsResponse,
    ApiKeyMetricsStats,
    ApiKeyRequestsTimeseries,
    ApiKeyResponse,
    ApiKeyTokensTimeseries,
    ApiKeyUpdate,
    ApiKeyWithFullKey,
)


def truncate_api_key(full_key: str) -> str:
    """
    Truncate an API key for safe display, preserving the prefix.

    Args:
        full_key: The full API key with prefix (e.g., "amd_aim_api_key_hvs.abc123def456")

    Returns:
        Truncated key for display (e.g., "amd_aim_api_key_••••••••6456")
    """
    prefix = "amd_aim_api_key_"

    # All API keys carry this prefix.
    if not full_key.startswith(prefix):
        raise ValueError(f"API key must start with '{prefix}'")

    # Show prefix + masked middle + last 4 chars of the token part
    token_part = full_key[len(prefix) :]
    if len(token_part) <= 4:
        return full_key
    last_four = token_part[-4:]
    return f"{prefix}••••••••{last_four}"


def generate_api_key() -> str:
    """Generate a new opaque API-key token.

    AIWB now mints the token itself (previously cluster-auth did). The format is kept identical to
    what cluster-auth emitted — ``amd_aim_api_key_hvs.<random>`` — so the value is indistinguishable
    to clients. It is the credential the gateway's native apiKeyAuth matches against the per-backend
    Secret (an opaque byte-for-byte comparison), so a high-entropy random body is sufficient.
    """
    return f"amd_aim_api_key_hvs.{secrets.token_urlsafe(32)}"


# Vault-style duration units accepted in the `ttl` field.
_TTL_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_TTL_COMPONENT_RE = re.compile(r"(\d+)([smhdw])")


def _expires_at_from_ttl(ttl: str | None) -> datetime | None:
    """Convert a Vault-style TTL ('30d', '24h', '1h30m', '86400', '0'/''/None = never) to an expiry.

    Accepts bare seconds and one-or-more ``<int><unit>`` components (compound durations like
    '1h30m' are summed). OpenBao's ``delete_version_after`` enforces the real drop; this is the
    value AIWB persists and the UI displays, so an under-count here would misreport expiry.
    """
    if not ttl or ttl in ("0", "0s"):
        return None
    stripped = ttl.strip()
    if stripped.isdigit():
        seconds = int(stripped)  # bare seconds, e.g. "86400"
    else:
        components = _TTL_COMPONENT_RE.findall(stripped)
        # Require the components to cover the whole string; a partial parse (e.g. "1h30x") would
        # silently drop time, so treat anything that doesn't fully match as non-expiring.
        if not components or "".join(f"{n}{u}" for n, u in components) != stripped:
            logger.warning(f"Unparseable ttl '{ttl}', treating key as non-expiring")
            return None
        seconds = sum(int(n) * _TTL_UNITS[u] for n, u in components)
    return datetime.now(UTC) + timedelta(seconds=seconds)


def _require_openbao_client(openbao_client: OpenBaoClient | None, action: str) -> OpenBaoClient:
    """
    Refuse every API-key mutation while the store is disabled (``openBao.enabled: false``).

    Reads stay available so keys created before the store was disabled remain visible, but
    nothing may create, rebind, or delete a key: a delete without the store would drop the DB
    row and leave the raw token alive in OpenBao with nothing left that can revoke it.
    """
    if openbao_client is None:
        raise ExternalServiceError(f"OpenBao store is not configured; cannot {action} API key")
    return openbao_client


async def ensure_store_matches_existing_keys(session: AsyncSession, openbao_client: OpenBaoClient | None) -> None:
    """
    Refuse to run without the OpenBao store while API keys exist.

    OpenBao is an install-time choice and is not removed afterwards. Keys in the database with
    the store disabled therefore mean the configuration was changed underneath live credentials
    that nothing can revoke any more. Startup fails until an operator re-enables the store and
    deletes the keys, or restores the configuration.
    """
    if openbao_client is not None:
        return
    existing = await count_api_keys(session)
    if existing:
        noun = "API key" if existing == 1 else "API keys"
        raise RuntimeError(
            f"OpenBao store is disabled but the database holds {existing} {noun}. Re-enable OpenBao "
            "(openBao.enabled and openbaoToken.enabled) and delete the keys before disabling it."
        )


async def create_api_key_in_store(
    session: AsyncSession,
    kube_client: KubernetesClient,
    namespace: str,
    api_key_in: ApiKeyCreate,
    user: str,
    openbao_client: OpenBaoClient | None = None,
) -> ApiKeyWithFullKey:
    """
    Create an API key in the OpenBao/ESO store (the sole key path).

    AIWB generates the token, writes it to OpenBao KV, and records the key's bindings as entries in
    each bound backend's ExternalSecret (ESO materializes the labelled Secrets the gateway reads).
    No cluster-auth calls. The store is the source of truth; on any store failure the DB row is
    rolled back so a key is never half-created.

    Returns:
        The created API key with the full key (shown only once)
    """
    logger.info(f"Creating API key '{api_key_in.display_name}' for namespace {namespace}")

    openbao_client = _require_openbao_client(openbao_client, "create")

    full_key = generate_api_key()
    truncated_key = truncate_api_key(full_key)
    expires_at = _expires_at_from_ttl(api_key_in.ttl)

    # Distinct display names can sanitize to the same client_id (the Secret data-key /
    # x-api-key-id / metric label): e.g. "my key" and "my-key" both collapse to token-<ns>-my-key.
    # The DB uniqueness guards the raw display_name, so the derived id needs its own guard here —
    # otherwise the two keys would share one OpenBao path and silently overwrite each other.
    client_id = es_store.compute_client_id(namespace, api_key_in.display_name)
    existing_keys = await get_api_keys_for_namespace(session, namespace)
    if any(es_store.compute_client_id(namespace, k.display_name) == client_id for k in existing_keys):
        raise ConflictException(
            f"An API key whose name normalizes to the same identifier already exists in namespace "
            f"'{namespace}'. Choose a more distinct display name."
        )

    api_key_db = await create_api_key(
        session=session,
        display_name=api_key_in.display_name,
        truncated_key=truncated_key,
        namespace=namespace,
        creator=user,
        expires_at=expires_at,
    )

    key_id = str(api_key_db.id)
    try:
        await openbao_client.put_token(key_id, full_key, namespace, client_id, ttl=api_key_in.ttl)
        await es_store.create_key_secret(
            kube_client,
            namespace,
            key_id,
            client_id,
            api_key_in.display_name,
            {str(a) for a in (api_key_in.aim_ids or [])},
        )
    except Exception:
        # Store is the source of truth — never leave a DB row without its token/bindings.
        logger.error(f"Store write failed for API key '{api_key_in.display_name}', rolling back")
        await delete_api_key(session, api_key_db)
        try:
            await es_store.delete_key_secret(kube_client, namespace, key_id)
            await openbao_client.delete_token(key_id)
        except Exception as cleanup_error:
            # Log the identifiers so an orphaned OpenBao token / ExternalSecret entry stays
            # discoverable and reapable — the DB row is already gone at this point.
            logger.error(
                f"Partial-store cleanup after failed create also failed "
                f"(key_id={key_id}, client_id={client_id}, namespace={namespace}): {cleanup_error}"
            )
        raise

    return ApiKeyWithFullKey(
        id=api_key_db.id,
        display_name=api_key_db.display_name,
        truncated_key=api_key_db.truncated_key,
        namespace=api_key_db.namespace,
        expires_at=expires_at,
        ttl=api_key_in.ttl if expires_at else None,
        created_at=api_key_db.created_at,
        updated_at=api_key_db.updated_at,
        created_by=api_key_db.created_by,
        updated_by=api_key_db.updated_by,
        full_key=full_key,
    )


async def update_api_key_bindings_in_store(
    session: AsyncSession,
    kube_client: KubernetesClient,
    namespace: str,
    api_key_id: UUID,
    api_key_update: ApiKeyUpdate,
    openbao_client: OpenBaoClient | None = None,
) -> ApiKeyDetails:
    """
    Update an API key's model bindings via the store.

    ``aim_ids`` is the complete desired set; the key's bindings (the ``bound-<workload-id>`` labels
    on its ExternalSecret) are converged on it. A per-model SecurityPolicy lists every key Secret
    carrying its label, so a binding change is a label edit — no token handling, no cluster-auth.
    The store client is still required: a rebind widens what an existing key can reach, and
    that must stay impossible while the store is disabled.

    Raises:
        NotFoundException: If the API key is not found
    """
    _require_openbao_client(openbao_client, "update")

    api_key = await get_api_key_by_id(session, api_key_id, namespace)
    if not api_key:
        raise NotFoundException(f"API key with ID {api_key_id} not found in namespace '{namespace}'")

    logger.info(f"Updating API key {api_key_id} bindings for {len(api_key_update.aim_ids)} model(s)")

    key_id = str(api_key.id)
    await es_store.set_key_bindings(kube_client, namespace, key_id, {str(a) for a in (api_key_update.aim_ids or [])})

    return await get_api_key_details_from_store(
        session=session,
        kube_client=kube_client,
        namespace=namespace,
        api_key_id=api_key_id,
    )


async def list_api_keys_for_namespace(
    session: AsyncSession,
    namespace: str,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedResult[ApiKeyResponse]:
    """
    List all API keys for a namespace as a paginated result.

    Args:
        session: Database session
        namespace: The namespace
        page: 1-indexed page number
        page_size: Maximum number of items per page

    Returns:
        Paginated API keys (without ttl/expires_at - use get_details for those)
    """
    api_keys = await get_api_keys_for_namespace(session, namespace)

    responses = [
        ApiKeyResponse(
            id=key.id,
            display_name=key.display_name,
            truncated_key=key.truncated_key,
            namespace=key.namespace,
            created_at=key.created_at,
            updated_at=key.updated_at,
            created_by=key.created_by,
            updated_by=key.updated_by,
        )
        for key in api_keys
    ]
    # Paginate after building the full list so `total` reflects the full set.
    return paginate_list(responses, page=page, page_size=page_size)


async def get_api_key_details_from_store(
    session: AsyncSession,
    kube_client: KubernetesClient,
    namespace: str,
    api_key_id: UUID,
) -> ApiKeyDetails:
    """
    Get detailed API key information from the store.

    Expiry comes from the DB; the models the key is bound to (``groups``) are the
    ``bound-<workload-id>`` labels on its ExternalSecret. No cluster-auth calls.

    Raises:
        NotFoundException: If the API key is not found
    """
    api_key = await get_api_key_by_id(session, api_key_id, namespace)
    if not api_key:
        raise NotFoundException(f"API key with ID {api_key_id} not found in namespace '{namespace}'")

    workload_ids = await es_store.list_workload_ids_for_key(kube_client, namespace, str(api_key.id))

    return ApiKeyDetails(
        id=api_key.id,
        display_name=api_key.display_name,
        truncated_key=api_key.truncated_key,
        namespace=api_key.namespace,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
        created_by=api_key.created_by,
        updated_by=api_key.updated_by,
        ttl=None,
        # Advisory display value only — OpenBao's delete_version_after enforces the actual drop;
        # nothing gates access on this field.
        expires_at=api_key.expires_at,
        groups=workload_ids,
    )


async def delete_api_key_from_store(
    session: AsyncSession,
    namespace: str,
    api_key_id: UUID,
    kube_client: KubernetesClient,
    openbao_client: OpenBaoClient | None = None,
) -> None:
    """
    Delete an API key from the store: delete its ExternalSecret (and thus the materialized Secret,
    dropping it from every model's SecurityPolicy), delete its OpenBao entry, and remove the DB
    record. No cluster-auth calls.

    Raises:
        NotFoundException: If the API key is not found
        ExternalServiceError: If the OpenBao store is disabled, so the token could not be revoked
    """
    openbao_client = _require_openbao_client(openbao_client, "delete")

    api_key = await get_api_key_by_id(session, api_key_id, namespace)
    if not api_key:
        raise NotFoundException(f"API key with ID {api_key_id} not found in namespace '{namespace}'")

    key_id = str(api_key.id)

    await es_store.delete_key_secret(kube_client, namespace, key_id)
    await openbao_client.delete_token(key_id)

    await delete_api_key(session, api_key)
    logger.info(f"Deleted API key {api_key_id} from the store")


def _pivot_to_wide(results: list[dict], services: list[str]) -> dict[str, dict[str, float]]:
    wide: dict[str, dict[str, float]] = {}
    for series in results:
        service = series["metric"].get("aim_service_id", "")
        if not service:
            continue
        for ts, val in series["values"]:
            iso = datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            wide.setdefault(iso, {s: 0.0 for s in services})
            try:
                wide[iso][service] = wide[iso].get(service, 0.0) + float(val if val != PROMETHEUS_NAN_STRING else 0)
            except (ValueError, TypeError):
                pass
    return wide


def _wide_to_datapoints(wide: dict[str, dict[str, float]], services: list[str]) -> list[ApiKeyMetricsDataPoint]:
    return [{"date": iso, **{s: wide[iso].get(s, 0.0) for s in services}} for iso in sorted(wide)]


async def get_api_key_usage_metrics(
    session: AsyncSession,
    namespace: str,
    api_key_id: UUID,
    start: datetime,
    end: datetime,
    prometheus_client: PrometheusConnect,
) -> ApiKeyMetricsResponse:
    api_key = await get_api_key_by_id(session, api_key_id, namespace)
    if not api_key:
        raise NotFoundException(f"API key with ID {api_key_id} not found in namespace '{namespace}'")

    # The api_key_id label on the gateway metrics is the client id forwarded by the
    # per-model apiKeyAuth SecurityPolicy (forwardClientIDHeader: x-api-key-id), which is
    # the Secret data-key name — i.e. compute_client_id(namespace, display_name) =
    # "token-<namespace>-<display_name>". Build the query id the same way so the filter
    # matches. (The old form omitted the namespace and stopped matching after the move
    # from cluster-auth to native apiKeyAuth.)
    prom_key_id = es_store.compute_client_id(namespace, api_key.display_name)

    step = get_step_for_range_query(start, end)
    lookback = get_aggregation_lookback_for_metrics(step)
    step_str = f"{int(step)}s"
    duration_s = f"{int((end - start).total_seconds())}s"

    # pod!="" deduplicates series scraped twice (PodMonitor vs ServiceMonitor)
    # from the same endpoint — both carry identical counter values.
    # error_type label is absent on successful requests and "_OTHER" on failures
    # (follows OTel GenAI semantic conventions).
    (
        token_results,
        request_results,
        failed_request_results,
        total_token_stat,
        total_request_stat,
        total_failed_stat,
    ) = await asyncio.gather(
        a_custom_query_range(
            prometheus_client,
            query=f'sum by (aim_service_id, gen_ai_token_type) (increase({AI_GW_TOKEN_USAGE_METRIC}{{api_key_id="{prom_key_id}",pod!=""}}[{lookback}]))',
            start_time=start,
            end_time=end,
            step=step_str,
        ),
        a_custom_query_range(
            prometheus_client,
            query=f'sum by (aim_service_id) (increase({AI_GW_REQUEST_DURATION_METRIC}{{api_key_id="{prom_key_id}",pod!="",error_type=""}}[{lookback}]))',
            start_time=start,
            end_time=end,
            step=step_str,
        ),
        a_custom_query_range(
            prometheus_client,
            query=f'sum by (aim_service_id) (increase({AI_GW_REQUEST_DURATION_METRIC}{{api_key_id="{prom_key_id}",pod!="",error_type!=""}}[{lookback}]))',
            start_time=start,
            end_time=end,
            step=step_str,
        ),
        a_custom_query(
            prometheus_client,
            # Offset subtraction instead of increase() so new counters (no prior scrape at 0)
            # still produce a non-zero total. OR fallback fires when offset window has no data.
            query=(
                f'sum({AI_GW_TOKEN_USAGE_METRIC}{{api_key_id="{prom_key_id}",pod!=""}})'
                f' - sum({AI_GW_TOKEN_USAGE_METRIC}{{api_key_id="{prom_key_id}",pod!=""}} offset {duration_s})'
                f' OR sum({AI_GW_TOKEN_USAGE_METRIC}{{api_key_id="{prom_key_id}",pod!=""}})'
            ),
        ),
        a_custom_query(
            prometheus_client,
            query=(
                f'sum({AI_GW_REQUEST_DURATION_METRIC}{{api_key_id="{prom_key_id}",pod!=""}})'
                f' - sum({AI_GW_REQUEST_DURATION_METRIC}{{api_key_id="{prom_key_id}",pod!=""}} offset {duration_s})'
                f' OR sum({AI_GW_REQUEST_DURATION_METRIC}{{api_key_id="{prom_key_id}",pod!=""}})'
            ),
        ),
        a_custom_query(
            prometheus_client,
            query=(
                f'sum({AI_GW_REQUEST_DURATION_METRIC}{{api_key_id="{prom_key_id}",pod!="",error_type!=""}})'
                f' - sum({AI_GW_REQUEST_DURATION_METRIC}{{api_key_id="{prom_key_id}",pod!="",error_type!=""}} offset {duration_s})'
                f' OR sum({AI_GW_REQUEST_DURATION_METRIC}{{api_key_id="{prom_key_id}",pod!="",error_type!=""}})'
            ),
        ),
    )

    services = sorted(
        {
            s["metric"].get("aim_service_id", "")
            for s in token_results + request_results + failed_request_results
            if s["metric"].get("aim_service_id")
        }
    )

    input_results = [s for s in token_results if s["metric"].get("gen_ai_token_type") == "input"]
    output_results = [s for s in token_results if s["metric"].get("gen_ai_token_type") == "output"]

    input_wide = _pivot_to_wide(input_results, services)
    output_wide = _pivot_to_wide(output_results, services)
    successful_request_wide = _pivot_to_wide(request_results, services)
    failed_request_wide = _pivot_to_wide(failed_request_results, services)

    total_token_wide = {
        iso: {s: input_wide.get(iso, {}).get(s, 0.0) + output_wide.get(iso, {}).get(s, 0.0) for s in services}
        for iso in sorted(set(input_wide) | set(output_wide))
    }

    all_timestamps = sorted(set(successful_request_wide) | set(failed_request_wide))
    total_request_wide = {
        iso: {
            s: successful_request_wide.get(iso, {}).get(s, 0.0) + failed_request_wide.get(iso, {}).get(s, 0.0)
            for s in services
        }
        for iso in all_timestamps
    }

    def _extract_stat(result: list[dict]) -> int:
        if result and result[0].get("value"):
            try:
                return max(0, int(float(result[0]["value"][1])))
            except (ValueError, TypeError, IndexError):
                pass
        return 0

    total_tokens = _extract_stat(total_token_stat)
    total_requests = _extract_stat(total_request_stat)
    failed_requests = _extract_stat(total_failed_stat)

    return ApiKeyMetricsResponse(
        stats=ApiKeyMetricsStats(
            total_requests=total_requests,
            successful_requests=max(0, total_requests - failed_requests),
            failed_requests=failed_requests,
            total_tokens=total_tokens,
            linked_deployments=len(services),
        ),
        services=services,
        requests_over_time=ApiKeyRequestsTimeseries(
            total=_wide_to_datapoints(total_request_wide, services),
            successful=_wide_to_datapoints(successful_request_wide, services),
            failed=_wide_to_datapoints(failed_request_wide, services),
        ),
        tokens_over_time=ApiKeyTokensTimeseries(
            total=_wide_to_datapoints(total_token_wide, services),
            input=_wide_to_datapoints(input_wide, services),
            output=_wide_to_datapoints(output_wide, services),
        ),
    )
