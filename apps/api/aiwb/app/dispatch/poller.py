# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Generic CRD polling framework - syncs K8s CRD state to DB.

This module provides a generic polling framework that can be configured
to poll different types of Kubernetes Custom Resources and sync their
state with the database.

The framework is configured by registering resource syncer callables that
handle the specific sync logic for each resource type.

## Syncer Design Requirements

Syncers run concurrently, each with its own isolated database session.
When writing syncers, follow these guidelines:

1. **Independence**: Syncers should operate on independent data sets.
   Do not rely on another syncer's changes within the same polling cycle.

2. **Session Isolation**: Each syncer receives its own AsyncSession.
   This session is NOT shared with other syncers running concurrently.

3. **Transaction Handling**: Each syncer's session operates in its own
   transaction. Commit or rollback decisions are independent per syncer.

4. **Resource Constraints**: Keep syncers lightweight to avoid connection
   pool exhaustion. Limit concurrent database operations within each syncer.

5. **Error Handling**: Syncers should handle their own exceptions.
   One syncer's failure does not affect other syncers in the same cycle.

6. **Idempotency**: Syncers may be called multiple times. Ensure they
   handle repeated calls safely without duplicating work or data.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api_common import database

from ..dispatch.config import POLLING_INTERVAL_SECONDS
from .kube_client import KubernetesClient, get_kube_client

# Type alias for resource sync functions
ResourceSyncer = Callable[[AsyncSession, KubernetesClient], Awaitable[None]]


@dataclass
class RegisteredSyncer:
    """A syncer and how often it wants to run."""

    syncer: ResourceSyncer
    interval_seconds: int | None = None
    last_run: float | None = None

    def is_due(self, now: float) -> bool:
        if self.interval_seconds is None:
            return True
        return self.last_run is None or now - self.last_run >= self.interval_seconds


@dataclass
class PollerState:
    """Encapsulates poller state."""

    running: bool = False
    polling_task: asyncio.Task | None = None
    syncers: list[RegisteredSyncer] = field(default_factory=list)


# Module-level state instance
_state = PollerState()


def register_syncer(syncer: ResourceSyncer, interval_seconds: int | None = None) -> None:
    """Register a resource syncer function.

    Syncers are executed concurrently during each polling cycle, each with
    its own isolated database session. See module docstring for syncer
    design requirements.

    Args:
        syncer: Async callable that takes (session, kube_client) and syncs resources.
                Must be safe for concurrent execution with other registered syncers.
        interval_seconds: Minimum seconds between runs of this syncer. Omit for the poller's own
                cadence, which is what a syncer tracking live cluster state wants. Set it for work
                too heavy to belong at that cadence, so such a syncer can share the one polling
                loop rather than bringing a second scheduler with it.
    """
    if any(registered.syncer is syncer for registered in _state.syncers):
        return
    _state.syncers.append(RegisteredSyncer(syncer=syncer, interval_seconds=interval_seconds))
    logger.debug(f"Registered syncer: {syncer.__name__}")


async def start_poller() -> None:
    """Start the unified resource poller."""
    if _state.running:
        logger.warning("Resource poller already running")
        return

    if not _state.syncers:
        logger.warning("No resource syncers registered - poller will not run")
        return

    _state.running = True

    # Start polling task (initial sync will happen in background)
    _state.polling_task = asyncio.create_task(_polling_loop())
    logger.info(f"Started resource poller ({POLLING_INTERVAL_SECONDS}-second interval, {len(_state.syncers)} syncers)")


async def _polling_loop() -> None:
    """Poll resource state periodically."""
    # Perform initial sync immediately on first run
    try:
        await _poll_resources()
    except Exception as e:
        logger.error(f"Error during initial sync: {e}")

    while _state.running:
        try:
            await asyncio.sleep(POLLING_INTERVAL_SECONDS)

            if not _state.running:
                break

            await _poll_resources()

        except Exception as e:
            logger.exception(f"Error in polling loop: {e}")


async def _poll_resources() -> None:
    """Poll all registered resources and sync their status from K8s."""
    if not database.session_maker:
        return

    now = time.monotonic()
    due = [registered for registered in _state.syncers if registered.is_due(now)]
    if not due:
        return

    kube_client = get_kube_client()

    # Stamped before running rather than after, so a syncer that takes longer than its own interval
    # paces from when it started and does not begin again the moment it finishes.
    for registered in due:
        registered.last_run = now

    # Run all syncers concurrently, each with its own database session
    # This prevents session sharing issues when syncers run in parallel
    async def run_syncer_with_session(syncer: ResourceSyncer) -> None:
        async with database.session_maker() as session:
            try:
                await syncer(session, kube_client)
            except Exception as e:
                logger.error(f"Error in syncer {syncer.__name__}: {e}")

    await asyncio.gather(*[run_syncer_with_session(registered.syncer) for registered in due])


async def stop_poller() -> None:
    """Stop the unified resource poller."""
    if not _state.running:
        return

    logger.info("Stopping resource poller")
    _state.running = False

    # Stop polling task
    if _state.polling_task:
        _state.polling_task.cancel()
        try:
            await _state.polling_task
        except asyncio.CancelledError:
            pass
        _state.polling_task = None

    logger.info("Stopped resource poller")


def is_running() -> bool:
    """Check if resource poller is running."""
    return _state.running
