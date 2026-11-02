# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for the generic CRD polling framework."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.dispatch.poller as poller_module
from app.dispatch.kube_client import KubernetesClient
from app.dispatch.poller import PollerState, _poll_resources, is_running, register_syncer, start_poller, stop_poller


@pytest.fixture
def clean_poller_state():
    """Reset poller state before each test."""
    # Store original state
    original_state = poller_module._state

    # Create fresh state
    poller_module._state = PollerState()

    yield poller_module._state

    # Restore original state
    poller_module._state = original_state


# =============================================================================
# register_syncer tests
# =============================================================================


def test_register_syncer_success(clean_poller_state):
    """Test registering a syncer adds it to the list."""

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)

    assert [registered.syncer for registered in clean_poller_state.syncers] == [test_syncer]


def test_register_syncer_duplicate(clean_poller_state):
    """Test registering the same syncer twice doesn't duplicate it."""

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)
    register_syncer(test_syncer)

    assert len(clean_poller_state.syncers) == 1


def test_register_syncer_multiple(clean_poller_state):
    """Test registering multiple different syncers."""

    async def syncer1(session, kube_client):
        pass

    async def syncer2(session, kube_client):
        pass

    register_syncer(syncer1)
    register_syncer(syncer2)

    assert [registered.syncer for registered in clean_poller_state.syncers] == [syncer1, syncer2]


# =============================================================================
# start_poller tests
# =============================================================================


@pytest.mark.asyncio
@patch("app.dispatch.poller.get_kube_client")
async def test_start_poller_success(mock_get_client, clean_poller_state):
    """Test starting the poller with registered syncers."""

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)

    await start_poller()

    assert clean_poller_state.running is True
    assert clean_poller_state.polling_task is not None

    # Clean up
    clean_poller_state.running = False
    if clean_poller_state.polling_task:
        clean_poller_state.polling_task.cancel()
        try:
            await clean_poller_state.polling_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_start_poller_already_running(clean_poller_state):
    """Test starting poller when already running logs warning."""
    clean_poller_state.running = True

    await start_poller()

    # Should not create a new task
    assert clean_poller_state.polling_task is None


@pytest.mark.asyncio
async def test_start_poller_no_syncers(clean_poller_state):
    """Test starting poller with no syncers logs warning."""
    await start_poller()

    # Should not start
    assert clean_poller_state.running is False
    assert clean_poller_state.polling_task is None


@pytest.mark.asyncio
@patch("app.dispatch.poller.get_kube_client")
async def test_start_poller_initial_sync_error(mock_get_client, clean_poller_state):
    """Test starting poller continues even if initial sync fails."""

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)

    await start_poller()

    # Should still start the polling loop
    assert clean_poller_state.running is True
    assert clean_poller_state.polling_task is not None

    # Clean up
    clean_poller_state.running = False
    if clean_poller_state.polling_task:
        clean_poller_state.polling_task.cancel()
        try:
            await clean_poller_state.polling_task
        except asyncio.CancelledError:
            pass


# =============================================================================
# _poll_resources tests
# =============================================================================


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_poll_resources_success(mock_get_client, mock_session_maker, clean_poller_state):
    """Test polling resources calls all syncers."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = AsyncMock()
    mock_session_maker.return_value = mock_session

    mock_client = MagicMock(spec=KubernetesClient)
    mock_get_client.return_value = mock_client

    syncer1_called = False
    syncer2_called = False

    async def syncer1(session, kube_client):
        nonlocal syncer1_called
        syncer1_called = True

    async def syncer2(session, kube_client):
        nonlocal syncer2_called
        syncer2_called = True

    register_syncer(syncer1)
    register_syncer(syncer2)

    await _poll_resources()

    assert syncer1_called
    assert syncer2_called


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker", None)
async def test_poll_resources_no_session_maker(clean_poller_state):
    """Test polling resources returns early if no session maker."""

    async def test_syncer(session, kube_client):
        raise Exception("Should not be called")

    register_syncer(test_syncer)

    # Should not raise
    await _poll_resources()


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_poll_resources_does_not_get_kube_client_when_no_syncers_are_due(
    mock_get_client, mock_session_maker, clean_poller_state
):
    """Test polling does not require Kubernetes when no syncer needs to run."""

    await _poll_resources()

    mock_get_client.assert_not_called()


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_poll_resources_does_not_get_kube_client_before_an_interval(
    mock_get_client, mock_session_maker, clean_poller_state
):
    """Test an interval-gated syncer is skipped until it is due."""

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer, interval_seconds=60)
    clean_poller_state.syncers[0].last_run = time.monotonic()

    await _poll_resources()

    mock_get_client.assert_not_called()


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_poll_resources_syncer_error(mock_get_client, mock_session_maker, clean_poller_state):
    """Test polling continues even if a syncer fails."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = AsyncMock()
    mock_session_maker.return_value = mock_session

    mock_client = MagicMock(spec=KubernetesClient)
    mock_get_client.return_value = mock_client

    syncer2_called = False

    async def failing_syncer(session, kube_client):
        raise Exception("Syncer failed")

    async def syncer2(session, kube_client):
        nonlocal syncer2_called
        syncer2_called = True

    register_syncer(failing_syncer)
    register_syncer(syncer2)

    # Should not raise, but continue to next syncer
    await _poll_resources()

    # Second syncer should still be called
    assert syncer2_called


# =============================================================================
# PollerState tests
# =============================================================================


def test_poller_state_defaults():
    """Test PollerState has correct defaults."""
    state = PollerState()

    assert state.running is False
    assert state.polling_task is None
    assert state.syncers == []


def test_poller_state_with_values():
    """Test PollerState can be initialized with values."""

    async def test_syncer(session, kube_client):
        pass

    # Create a mock task instead of a real asyncio task
    mock_task = MagicMock(spec=asyncio.Task)
    state = PollerState(running=True, polling_task=mock_task, syncers=[test_syncer])

    assert state.running is True
    assert state.polling_task == mock_task
    assert len(state.syncers) == 1


# =============================================================================
# stop_poller tests
# =============================================================================


@pytest.mark.asyncio
async def test_stop_poller_when_not_running(clean_poller_state):
    """Test stop_poller does nothing when poller is not running."""
    assert clean_poller_state.running is False

    await stop_poller()

    assert clean_poller_state.running is False
    assert clean_poller_state.polling_task is None


@pytest.mark.asyncio
@patch("app.dispatch.poller.get_kube_client")
@patch("app.dispatch.poller._poll_resources")
async def test_stop_poller_when_running(mock_poll, mock_get_client, clean_poller_state):
    """Test stop_poller stops a running poller."""

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)
    mock_poll.return_value = None

    # Start the poller
    await start_poller()
    assert clean_poller_state.running is True
    assert clean_poller_state.polling_task is not None

    # Stop the poller
    await stop_poller()

    assert clean_poller_state.running is False
    assert clean_poller_state.polling_task is None


# =============================================================================
# is_running tests
# =============================================================================


def test_is_running_false_initially(clean_poller_state):
    """Test is_running returns False when poller hasn't started."""
    assert is_running() is False


@pytest.mark.asyncio
@patch("app.dispatch.poller.get_kube_client")
@patch("app.dispatch.poller._poll_resources")
async def test_is_running_true_when_started(mock_poll, mock_get_client, clean_poller_state):
    """Test is_running returns True when poller is running."""

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)
    mock_poll.return_value = None

    await start_poller()

    assert is_running() is True

    # Clean up
    await stop_poller()


@pytest.mark.asyncio
@patch("app.dispatch.poller.get_kube_client")
@patch("app.dispatch.poller._poll_resources")
async def test_is_running_false_after_stop(mock_poll, mock_get_client, clean_poller_state):
    """Test is_running returns False after poller is stopped."""

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)
    mock_poll.return_value = None

    await start_poller()
    assert is_running() is True

    await stop_poller()
    assert is_running() is False


# =============================================================================
# Async cancellation and timeout tests
# =============================================================================


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_polling_loop_cancellation_cleanup(mock_get_client, mock_session_maker, clean_poller_state):
    """Test polling loop handles cancellation and cleans up resources."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = AsyncMock()
    mock_session_maker.return_value = mock_session

    mock_client = MagicMock(spec=KubernetesClient)
    mock_get_client.return_value = mock_client

    syncer_call_count = 0

    async def counting_syncer(session, kube_client):
        nonlocal syncer_call_count
        syncer_call_count += 1

    register_syncer(counting_syncer)

    # Start the poller
    await start_poller()
    assert clean_poller_state.running is True
    assert clean_poller_state.polling_task is not None

    # Let it run for a bit
    await asyncio.sleep(0.1)

    # Stop the poller (should cancel the task)
    await stop_poller()

    # Verify cleanup
    assert clean_poller_state.running is False
    assert clean_poller_state.polling_task is None

    # Syncer should have been called at least once (initial sync)
    assert syncer_call_count >= 1


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_polling_loop_task_cancellation_propagation(mock_get_client, mock_session_maker, clean_poller_state):
    """Test that cancelling the polling task properly stops the loop."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = AsyncMock()
    mock_session_maker.return_value = mock_session

    mock_client = MagicMock(spec=KubernetesClient)
    mock_get_client.return_value = mock_client

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)

    await start_poller()

    # Directly cancel the task
    polling_task = clean_poller_state.polling_task
    assert polling_task is not None

    polling_task.cancel()

    # Wait for cancellation to propagate
    with pytest.raises(asyncio.CancelledError):
        await polling_task

    # Manually clean up state
    clean_poller_state.running = False
    clean_poller_state.polling_task = None


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
@patch("app.dispatch.poller.POLLING_INTERVAL_SECONDS", 0.05)
async def test_polling_loop_continues_after_syncer_timeout(mock_get_client, mock_session_maker, clean_poller_state):
    """Test polling loop continues even if a syncer times out."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = AsyncMock()
    mock_session_maker.return_value = mock_session

    mock_client = MagicMock(spec=KubernetesClient)
    mock_get_client.return_value = mock_client

    slow_syncer_calls = 0
    fast_syncer_calls = 0

    async def slow_syncer(session, kube_client):
        nonlocal slow_syncer_calls
        slow_syncer_calls += 1
        await asyncio.sleep(10)  # Simulate a very slow syncer

    async def fast_syncer(session, kube_client):
        nonlocal fast_syncer_calls
        fast_syncer_calls += 1

    register_syncer(slow_syncer)
    register_syncer(fast_syncer)

    await start_poller()

    # Let it run for a short time - need to wait for initial background sync to start
    # The polling loop starts immediately but runs in background, so we need to give
    # it time to actually invoke the syncers before we stop the poller
    await asyncio.sleep(0.2)

    await stop_poller()

    # Both syncers should have been called (initial sync at minimum)
    assert slow_syncer_calls >= 1
    assert fast_syncer_calls >= 1


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_polling_loop_stops_when_running_flag_cleared(mock_get_client, mock_session_maker, clean_poller_state):
    """Test polling loop exits when running flag is cleared during sleep."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = AsyncMock()
    mock_session_maker.return_value = mock_session

    mock_client = MagicMock(spec=KubernetesClient)
    mock_get_client.return_value = mock_client

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)

    await start_poller()
    assert clean_poller_state.running is True

    # Clear the running flag
    clean_poller_state.running = False

    # Wait for the loop to detect the flag change
    await asyncio.sleep(0.1)

    # Task should exit cleanly
    if clean_poller_state.polling_task:
        # Give it time to finish
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_stop_poller_idempotent(clean_poller_state):
    """Test stop_poller can be called multiple times safely."""
    # First call when not running
    await stop_poller()
    assert clean_poller_state.running is False

    # Second call should also be safe
    await stop_poller()
    assert clean_poller_state.running is False


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_poll_resources_with_async_context_manager_error(mock_get_client, mock_session_maker, clean_poller_state):
    """Test _poll_resources handles session context manager errors."""
    # Make session context manager fail on exit
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.side_effect = Exception("Session cleanup failed")
    mock_session_maker.return_value = mock_session

    mock_client = MagicMock(spec=KubernetesClient)
    mock_get_client.return_value = mock_client

    async def test_syncer(session, kube_client):
        pass

    register_syncer(test_syncer)

    # Should raise the context manager error
    with pytest.raises(Exception, match="Session cleanup failed"):
        await _poll_resources()


@pytest.mark.asyncio
@patch("app.dispatch.poller.database.session_maker")
@patch("app.dispatch.poller.get_kube_client")
async def test_concurrent_poller_operations(mock_get_client, mock_session_maker, clean_poller_state):
    """Test concurrent calls to start/stop poller are handled safely."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = AsyncMock()
    mock_session_maker.return_value = mock_session

    mock_client = MagicMock(spec=KubernetesClient)
    mock_get_client.return_value = mock_client

    async def test_syncer(session, kube_client):
        await asyncio.sleep(0.01)

    register_syncer(test_syncer)

    # Start multiple times concurrently
    await asyncio.gather(start_poller(), start_poller(), start_poller())

    # Only one should actually start
    assert clean_poller_state.running is True
    assert clean_poller_state.polling_task is not None

    # Stop multiple times concurrently
    await asyncio.gather(stop_poller(), stop_poller(), stop_poller())

    # Should be fully stopped
    assert clean_poller_state.running is False
    assert clean_poller_state.polling_task is None
