# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import uuid
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, NotFoundException
from app.overlays.repository import (
    delete_overlay,
    delete_overlays_absent_from_chart,
    get_overlay,
    insert_overlay,
    list_overlays,
)
from app.overlays.schemas import OverlayUpdate
from app.overlays.service import update_overlay
from tests import factory


@pytest.mark.asyncio
async def test_create_overlay(db_session: AsyncSession) -> None:
    """Test creating an overlay with real database operations."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    overlay_data = {"param1": "value1", "param2": "value2"}
    canonical_name = "test/overlay"
    creator = "test@example.com"

    # Create overlay
    overlay = await insert_overlay(db_session, chart.id, overlay_data, canonical_name, creator=creator)

    assert overlay.canonical_name == "test/overlay"
    assert overlay.chart_id == chart.id
    assert overlay.overlay == {"param1": "value1", "param2": "value2"}
    assert overlay.created_by == creator
    assert overlay.updated_by == creator


@pytest.mark.asyncio
async def test_select_overlay(db_session: AsyncSession) -> None:
    """Test selecting an overlay by ID."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    overlay_data = {"config": "test_config"}

    # Create overlay
    overlay = await insert_overlay(
        db_session, chart.id, overlay_data, "test/select-overlay", creator="test@example.com"
    )

    found_overlay = await get_overlay(db_session, overlay.id)

    assert found_overlay is not None
    assert found_overlay.id == overlay.id
    assert found_overlay.canonical_name == "test/select-overlay"
    assert found_overlay.overlay == {"config": "test_config"}

    non_existent_overlay = await get_overlay(db_session, uuid4())
    assert non_existent_overlay is None


@pytest.mark.asyncio
async def test_get_overlays_by_chart(db_session: AsyncSession) -> None:
    """Test getting overlays by chart ID."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    # Create multiple overlays for the same chart
    overlay1_data = {"env": "production"}
    overlay2_data = {"env": "staging"}

    await insert_overlay(db_session, chart.id, overlay1_data, "test/prod-overlay", creator="test@example.com")
    await insert_overlay(db_session, chart.id, overlay2_data, "test/staging-overlay", creator="test@example.com")

    # Note: list_overlays may return all overlays, so we'll filter by chart_id in assertions
    chart_overlays = await list_overlays(db_session)
    chart_specific_overlays = [o for o in chart_overlays if o.chart_id == chart.id]

    assert len(chart_specific_overlays) == 2
    canonical_names = {o.canonical_name for o in chart_specific_overlays}
    assert "test/prod-overlay" in canonical_names
    assert "test/staging-overlay" in canonical_names


@pytest.mark.asyncio
async def test_delete_overlay(db_session: AsyncSession) -> None:
    """Test deleting an overlay."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    overlay_data = {"temporary": "data"}

    # Create overlay
    overlay = await insert_overlay(db_session, chart.id, overlay_data, "test/temp-overlay", creator="test@example.com")
    overlay_id = overlay.id

    found_overlay = await get_overlay(db_session, overlay_id)
    assert found_overlay is not None

    await delete_overlay(db_session, overlay.id)

    deleted_overlay = await get_overlay(db_session, overlay_id)
    assert deleted_overlay is None


@pytest.mark.asyncio
async def test_create_overlay_duplicate_canonical_name_chart(db_session: AsyncSession) -> None:
    """Test that overlays with duplicate canonical names in the same chart raise an error."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    overlay_data = {"param": "value"}
    canonical_name = "duplicate/overlay"
    creator = "test@example.com"

    # Create first overlay
    await insert_overlay(db_session, chart.id, overlay_data, canonical_name, creator=creator)

    # Try to create second overlay with same canonical name and chart
    # This should raise a ConflictException due to unique constraint
    with pytest.raises(ConflictException):
        await insert_overlay(db_session, chart.id, overlay_data, canonical_name, creator=creator)


@pytest.mark.asyncio
async def test_overlay_isolation_between_charts(db_session: AsyncSession) -> None:
    """Test that overlays are properly isolated between different charts."""
    # Create charts
    chart1 = await factory.create_chart(db_session, name="Chart 1")
    chart2 = await factory.create_chart(db_session, name="Chart 2")

    # Create overlays for both charts with same canonical name (should be allowed)
    overlay_data = {"shared": "config"}
    canonical_name = "shared/overlay"

    overlay1 = await insert_overlay(db_session, chart1.id, overlay_data, canonical_name, creator="test@example.com")
    overlay2 = await insert_overlay(db_session, chart2.id, overlay_data, canonical_name, creator="test@example.com")

    assert overlay1.chart_id == chart1.id
    assert overlay2.chart_id == chart2.id
    assert overlay1.canonical_name == canonical_name
    assert overlay2.canonical_name == canonical_name
    assert overlay1.id != overlay2.id


@pytest.mark.asyncio
async def test_insert_overlay_invalid_chart_id(db_session: AsyncSession) -> None:
    """Test that creating an overlay with invalid chart_id raises foreign key constraint error."""
    invalid_chart_id = uuid4()
    overlay_data = {"param": "value"}

    # This should raise a NotFoundException due to foreign key constraint
    with pytest.raises(NotFoundException):
        await insert_overlay(
            db_session, invalid_chart_id, overlay_data, "test/invalid-chart", creator="test@example.com"
        )


@pytest.mark.asyncio
async def test_list_overlays_by_canonical_name(db_session: AsyncSession) -> None:
    """Test filtering overlays by specific canonical name."""
    chart1 = await factory.create_chart(db_session, name="Chart 1")
    chart2 = await factory.create_chart(db_session, name="Chart 2")

    target_canonical_name = "production/config"

    # Create overlays with same canonical name in different charts
    await factory.create_overlay(
        db_session, chart_id=chart1.id, canonical_name=target_canonical_name, overlay_data={"env": "prod"}
    )
    await factory.create_overlay(
        db_session, chart_id=chart2.id, canonical_name=target_canonical_name, overlay_data={"env": "prod-2"}
    )

    # Create overlay with different canonical name
    await factory.create_overlay(
        db_session, chart_id=chart1.id, canonical_name="staging/config", overlay_data={"env": "staging"}
    )

    # Filter by canonical name
    overlays = await list_overlays(db_session, canonical_name=target_canonical_name)

    assert len(overlays) == 2
    for overlay in overlays:
        assert overlay.canonical_name == target_canonical_name


@pytest.mark.asyncio
async def test_list_overlays_by_canonical_name_include_generic(db_session: AsyncSession) -> None:
    """Test filtering overlays by canonical name including generic overlays."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    target_canonical_name = "production/config"

    # Create specific overlay
    await factory.create_overlay(
        db_session,
        chart_id=chart.id,
        canonical_name=target_canonical_name,
        overlay_data={"env": "prod", "specific": True},
    )

    # Create generic overlay (no canonical name)
    await factory.create_overlay(
        db_session, chart_id=chart.id, canonical_name=None, overlay_data={"env": "generic", "default": True}
    )

    # Create overlay with different canonical name
    await factory.create_overlay(
        db_session, chart_id=chart.id, canonical_name="staging/config", overlay_data={"env": "staging"}
    )

    # Filter by canonical name including generic
    overlays = await list_overlays(db_session, canonical_name=target_canonical_name, include_generic=True)

    assert len(overlays) == 2
    canonical_names = {o.canonical_name for o in overlays}
    assert target_canonical_name in canonical_names
    assert None in canonical_names  # Generic overlay


@pytest.mark.asyncio
async def test_list_overlays_only_generic(db_session: AsyncSession) -> None:
    """Test filtering to get only generic overlays."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    # Create specific overlay
    await factory.create_overlay(
        db_session, chart_id=chart.id, canonical_name="production/config", overlay_data={"env": "prod"}
    )

    # Create generic overlay (no canonical name)
    await factory.create_overlay(
        db_session, chart_id=chart.id, canonical_name=None, overlay_data={"env": "generic", "default": True}
    )

    # Filter for generic overlays by using canonical_name=None with include_generic=True
    # Note: This tests the behavior when canonical_name is None
    all_overlays = await list_overlays(db_session)
    generic_overlays = [o for o in all_overlays if o.canonical_name is None]

    assert len(generic_overlays) == 1
    assert generic_overlays[0].canonical_name is None
    assert generic_overlays[0].overlay["default"] is True


@pytest.mark.asyncio
async def test_list_overlays_no_match(db_session: AsyncSession) -> None:
    """Test filtering overlays with no matches returns empty list."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    # Create overlay with known canonical name
    await factory.create_overlay(
        db_session, chart_id=chart.id, canonical_name="production/config", overlay_data={"env": "prod"}
    )

    # Search for non-existent canonical name
    overlays = await list_overlays(db_session, canonical_name="non-existent/config")

    assert len(overlays) == 0


@pytest.mark.asyncio
async def test_list_overlays_with_chart_id_parameter(db_session: AsyncSession) -> None:
    """Test filtering overlays by chart_id parameter."""
    chart1 = await factory.create_chart(db_session, name="Chart 1")
    chart2 = await factory.create_chart(db_session, name="Chart 2")

    # Create overlays in different charts
    overlay1 = await factory.create_overlay(
        db_session, chart_id=chart1.id, canonical_name="config/overlay1", overlay_data={"chart": "1"}
    )
    overlay2 = await factory.create_overlay(
        db_session, chart_id=chart2.id, canonical_name="config/overlay2", overlay_data={"chart": "2"}
    )

    # Filter by chart_id
    chart1_overlays = await list_overlays(db_session, chart_id=chart1.id)
    chart2_overlays = await list_overlays(db_session, chart_id=chart2.id)

    assert len(chart1_overlays) == 1
    assert len(chart2_overlays) == 1
    assert chart1_overlays[0].id == overlay1.id
    assert chart2_overlays[0].id == overlay2.id


@pytest.mark.asyncio
async def test_delete_non_existent_overlay(db_session: AsyncSession) -> None:
    """Test deleting a non-existent overlay returns False."""
    non_existent_id = uuid4()

    # Attempt to delete non-existent overlay
    result = await delete_overlay(db_session, non_existent_id)

    assert result is False


@pytest.mark.asyncio
async def test_update_overlay(db_session: AsyncSession) -> None:
    # Create test chart using factory
    chart = await factory.create_chart(db_session, name="Test Chart")

    # Create initial overlay
    overlay_data = {"key": "duplicate_test"}
    original_overlay = await insert_overlay(
        db_session,
        chart_id=chart.id,
        overlay_data=overlay_data,
        canonical_name="initial-canonical",
        creator="test_creator",
    )
    original_created_at = original_overlay.created_at
    original_creator = original_overlay.created_by

    # Prepare update data
    updated_overlay_data = OverlayUpdate(
        canonical_name="updated-canonical", overlay={"new_param": "new_value"}, updated_by="test_updater"
    )

    updated_overlay = await update_overlay(db_session, original_overlay.id, updated_overlay_data)

    # Refresh after commit to prevent expired attribute error
    await db_session.refresh(updated_overlay)

    assert updated_overlay.canonical_name == "updated-canonical"
    assert updated_overlay.overlay == {"new_param": "new_value"}
    assert updated_overlay.updated_by == "test_updater"
    assert updated_overlay.updated_by != original_creator
    assert updated_overlay.updated_at > original_created_at
    assert updated_overlay.updated_at > updated_overlay.created_at

    # Verify in DB
    overlay_from_db = await get_overlay(db_session, original_overlay.id)
    assert overlay_from_db.canonical_name == "updated-canonical"
    assert overlay_from_db.overlay == {"new_param": "new_value"}
    assert overlay_from_db.updated_by == "test_updater"
    assert overlay_from_db.updated_at > original_created_at


@pytest.mark.asyncio
async def test_update_overlay_not_found(db_session: AsyncSession) -> None:
    non_existing_id = uuid.uuid4()
    update_data = OverlayUpdate(canonical_name="should-not-exist", updated_by="test_user")

    with pytest.raises(NotFoundException) as exc_info:
        await update_overlay(db_session, non_existing_id, update_data)

    assert "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_generic_vs_model_specific_overlay_distinction(db_session: AsyncSession) -> None:
    """Test proper distinction between generic and model-specific overlays."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    # Create generic overlay (no canonical name)
    generic_overlay = await factory.create_overlay(
        db_session, chart_id=chart.id, canonical_name=None, overlay_data={"type": "generic", "applies_to": "all"}
    )

    # Create model-specific overlay
    specific_overlay = await factory.create_overlay(
        db_session,
        chart_id=chart.id,
        canonical_name="model/specific-config",
        overlay_data={"type": "specific", "model": "custom-model"},
    )

    # Get all overlays
    all_overlays = await list_overlays(db_session, chart_id=chart.id)

    # Verify both exist with correct properties
    assert len(all_overlays) == 2

    overlays_by_type = {o.canonical_name: o for o in all_overlays}

    # Verify generic overlay
    assert None in overlays_by_type
    generic = overlays_by_type[None]
    assert generic.id == generic_overlay.id
    assert generic.overlay["type"] == "generic"

    # Verify specific overlay
    assert "model/specific-config" in overlays_by_type
    specific = overlays_by_type["model/specific-config"]
    assert specific.id == specific_overlay.id
    assert specific.overlay["type"] == "specific"


@pytest.mark.asyncio
async def test_delete_overlays_absent_from_chart(db_session: AsyncSession) -> None:
    """A registered overlay the chart no longer ships is removed."""
    chart = await factory.create_chart(db_session, name=f"prune-chart-{uuid4()}")
    kept = await factory.create_overlay(db_session, chart_id=chart.id, canonical_name="model/kept", created_by="system")
    stale = await factory.create_overlay(
        db_session, chart_id=chart.id, canonical_name="model/stale", created_by="system"
    )

    deleted = await delete_overlays_absent_from_chart(db_session, chart.id, keep_ids=[kept.id], creator="system")

    assert deleted == [stale.id]
    remaining = await list_overlays(db_session, chart_id=chart.id)
    assert [o.id for o in remaining] == [kept.id]


@pytest.mark.asyncio
async def test_delete_overlays_absent_from_chart_spares_other_creators(db_session: AsyncSession) -> None:
    """Overlays added through the API survive pruning of registered ones."""
    chart = await factory.create_chart(db_session, name=f"prune-chart-{uuid4()}")
    user_overlay = await factory.create_overlay(
        db_session, chart_id=chart.id, canonical_name="model/user-added", created_by="user@example.com"
    )

    deleted = await delete_overlays_absent_from_chart(db_session, chart.id, keep_ids=[], creator="system")

    assert deleted == []
    remaining = await list_overlays(db_session, chart_id=chart.id)
    assert [o.id for o in remaining] == [user_overlay.id]


@pytest.mark.asyncio
async def test_delete_overlays_absent_from_chart_spares_generic_overlays(db_session: AsyncSession) -> None:
    """An overlay without a canonical name cannot be traced to a file, so it is never pruned."""
    chart = await factory.create_chart(db_session, name=f"prune-chart-{uuid4()}")
    generic = await factory.create_overlay(db_session, chart_id=chart.id, canonical_name=None, created_by="system")

    deleted = await delete_overlays_absent_from_chart(db_session, chart.id, keep_ids=[], creator="system")

    assert deleted == []
    remaining = await list_overlays(db_session, chart_id=chart.id)
    assert [o.id for o in remaining] == [generic.id]


@pytest.mark.asyncio
async def test_delete_overlays_absent_from_chart_spares_other_charts(db_session: AsyncSession) -> None:
    """Pruning one chart leaves another chart's registered overlays alone."""
    chart = await factory.create_chart(db_session, name=f"prune-chart-{uuid4()}")
    other_chart = await factory.create_chart(db_session, name=f"other-chart-{uuid4()}")
    other_overlay = await factory.create_overlay(
        db_session, chart_id=other_chart.id, canonical_name="model/elsewhere", created_by="system"
    )

    deleted = await delete_overlays_absent_from_chart(db_session, chart.id, keep_ids=[], creator="system")

    assert deleted == []
    remaining = await list_overlays(db_session, chart_id=other_chart.id)
    assert [o.id for o in remaining] == [other_overlay.id]
