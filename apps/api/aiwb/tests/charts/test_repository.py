# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api_common.exceptions import ConflictException, NotFoundException
from app.charts.repository import (
    create_chart,
    create_file_records,
    delete_chart,
    delete_chart_files,
    list_charts,
    select_chart,
    update_chart,
)
from app.charts.schemas import ChartUpdate
from app.workloads.enums import WorkloadType
from tests import factory
from tests.factory import make_chart_create_schema, make_mock_chart_files, make_mock_signature_file


@pytest.mark.asyncio
async def test_create_chart(db_session: AsyncSession) -> None:
    """Test creating a chart with real database operations."""
    chart_schema = make_chart_create_schema(
        name="Test Chart",
        signature_content="model_name: test-model\nreplicas: 1",
        files=[
            {"path": "deployment.yaml", "content": "apiVersion: apps/v1\nkind: Deployment"},
            {"path": "service.yaml", "content": "apiVersion: v1\nkind: Service"},
        ],
    )
    creator = "test@example.com"

    chart = await create_chart(db_session, chart_schema, creator)

    assert chart.name == "Test Chart"
    assert chart.type == WorkloadType.INFERENCE
    assert chart.signature == {"model_name": "test-model", "replicas": 1}
    assert chart.created_by == creator
    assert chart.updated_by == creator
    assert len(chart.files) == 2

    file_paths = {f.path for f in chart.files}
    assert "deployment.yaml" in file_paths
    assert "service.yaml" in file_paths


@pytest.mark.asyncio
async def test_list_charts(db_session: AsyncSession) -> None:
    """Test listing all charts."""

    chart1 = await factory.create_chart(db_session, name="Chart 1", chart_type=WorkloadType.INFERENCE)
    chart2 = await factory.create_chart(db_session, name="Chart 2", chart_type=WorkloadType.FINE_TUNING)

    charts = await list_charts(db_session)

    assert isinstance(charts, list)
    assert len(charts) >= 2

    chart_ids = {c.id for c in charts}
    assert chart1.id in chart_ids
    assert chart2.id in chart_ids

    chart_names = {c.name for c in charts}
    assert "Chart 1" in chart_names
    assert "Chart 2" in chart_names


@pytest.mark.asyncio
async def test_list_charts_filter_by_type(db_session: AsyncSession) -> None:
    """Test filtering charts by workload type returns only matching charts."""

    chart1 = await factory.create_chart(db_session, name="Filter Chart 1", chart_type=WorkloadType.INFERENCE)
    await factory.create_chart(db_session, name="Filter Chart 2", chart_type=WorkloadType.FINE_TUNING)

    filtered = await list_charts(db_session, WorkloadType.INFERENCE)

    assert isinstance(filtered, list)
    assert len(filtered) >= 1

    ids = {c.id for c in filtered}
    names = {c.name for c in filtered}
    assert chart1.id in ids
    assert "Filter Chart 1" in names
    assert "Filter Chart 2" not in names
    assert all(c.type == WorkloadType.INFERENCE for c in filtered)


@pytest.mark.asyncio
async def test_list_charts_filter_by_type_no_matches(db_session: AsyncSession) -> None:
    """Filtering should return empty list when no charts match the type."""

    # Only create FINE_TUNING charts
    await factory.create_chart(db_session, name="Only FT 1", chart_type=WorkloadType.FINE_TUNING)
    await factory.create_chart(db_session, name="Only FT 2", chart_type=WorkloadType.FINE_TUNING)

    filtered = await list_charts(db_session, WorkloadType.INFERENCE)

    assert isinstance(filtered, list)
    assert filtered == []


@pytest.mark.asyncio
async def test_select_chart(db_session: AsyncSession) -> None:
    """Test selecting a chart by ID."""
    chart = await factory.create_chart(db_session, name="Test Chart")

    found_chart = await select_chart(db_session, chart.id)

    assert found_chart is not None
    assert found_chart.id == chart.id
    assert found_chart.name == "Test Chart"

    non_existent_chart = await select_chart(db_session, uuid4())
    assert non_existent_chart is None


@pytest.mark.asyncio
async def test_select_chart_by_name(db_session: AsyncSession) -> None:
    """Test selecting a chart by name."""
    chart = await factory.create_chart(db_session, name="Test Chart By Name")

    found_chart = await select_chart(db_session, chart_name="Test Chart By Name")

    assert found_chart is not None
    assert found_chart.id == chart.id
    assert found_chart.name == "Test Chart By Name"


@pytest.mark.asyncio
async def test_select_chart_no_parameters(db_session: AsyncSession) -> None:
    """Test select_chart returns None when no parameters provided."""
    result = await select_chart(db_session)
    assert result is None


@pytest.mark.asyncio
async def test_delete_chart(db_session: AsyncSession) -> None:
    """Test deleting a chart."""
    chart = await factory.create_chart(db_session, name="Chart to Delete")
    chart_id = chart.id

    found_chart = await select_chart(db_session, chart_id)
    assert found_chart is not None

    result = await delete_chart(db_session, chart_id)
    assert result is True

    deleted_chart = await select_chart(db_session, chart_id)
    assert deleted_chart is None


@pytest.mark.asyncio
async def test_delete_chart_not_found(db_session: AsyncSession) -> None:
    """Test deleting a non-existent chart returns False."""
    non_existent_id = uuid4()
    result = await delete_chart(db_session, non_existent_id)
    assert result is False


@pytest.mark.asyncio
async def test_create_chart_duplicate_name_same_organization(db_session: AsyncSession) -> None:
    """Test that creating duplicate chart names raises error (charts are global)."""
    chart_schema = make_chart_create_schema(name="Duplicate Chart")
    creator = "test@example.com"

    await create_chart(db_session, chart_schema, creator)

    duplicate_schema = make_chart_create_schema(name="Duplicate Chart")
    with pytest.raises(ConflictException):
        await create_chart(db_session, duplicate_schema, creator)


@pytest.mark.asyncio
async def test_create_chart_different_names_globally(db_session: AsyncSession) -> None:
    """Test that different chart names can be created (charts are global)."""
    chart_name = "Shared Chart Name"

    chart1 = await factory.create_chart(db_session, name=f"{chart_name}-1")

    # Should succeed since charts are global
    chart2 = await factory.create_chart(db_session, name=f"{chart_name}-2")

    assert chart1.name == f"{chart_name}-1"
    assert chart2.name == f"{chart_name}-2"
    assert chart1.id != chart2.id


@pytest.mark.asyncio
async def test_list_charts_global_access(db_session: AsyncSession) -> None:
    """Test that charts are globally accessible."""
    # Charts are global
    chart1 = await factory.create_chart(db_session, name="Global Chart 1")
    chart2 = await factory.create_chart(db_session, name="Global Chart 2")

    all_charts = await list_charts(db_session)

    chart_ids = {c.id for c in all_charts}
    assert chart1.id in chart_ids
    assert chart2.id in chart_ids

    chart_names = {c.name for c in all_charts}
    assert "Global Chart 1" in chart_names
    assert "Global Chart 2" in chart_names


@pytest.mark.asyncio
async def test_select_chart_not_found_id(db_session: AsyncSession) -> None:
    retrieved_chart = await select_chart(session=db_session, chart_id=uuid4())
    assert retrieved_chart is None


@pytest.mark.asyncio
async def test_select_chart_not_found_name(db_session: AsyncSession) -> None:
    retrieved_chart = await select_chart(session=db_session, chart_name=f"nonexistent-{uuid4()}")
    assert retrieved_chart is None


@pytest.mark.asyncio
async def test_select_chart_no_identifier(db_session: AsyncSession) -> None:
    result = await select_chart(session=db_session)
    assert result is None


@pytest.mark.asyncio
async def test_create_chart_with_files(db_session: AsyncSession) -> None:
    chart_name = f"create-test-{uuid4()}"
    chart_schema = make_chart_create_schema(
        name=chart_name,
        files=[
            {"path": "values.yaml", "content": "key: value"},
            {"path": "Chart.yaml", "content": "apiVersion: v2"},
        ],
    )
    creator = "create_user"

    created_chart = await create_chart(session=db_session, chart_schema=chart_schema, creator=creator)

    assert created_chart.id is not None
    assert created_chart.name == chart_name
    assert created_chart.type == WorkloadType.INFERENCE
    assert created_chart.created_by == creator
    assert created_chart.updated_by == creator
    assert len(created_chart.files) == 2
    assert {f.path for f in created_chart.files} == {"values.yaml", "Chart.yaml"}

    # Verify it's in the DB
    retrieved_chart = await select_chart(db_session, chart_id=created_chart.id)
    assert retrieved_chart is not None
    assert retrieved_chart.id == created_chart.id
    assert len(retrieved_chart.files) == 2


@pytest.mark.asyncio
async def test_create_chart_duplicate_name_via_factory(db_session: AsyncSession) -> None:
    # Create chart using factory
    chart = await factory.create_chart(db_session, name="duplicate-chart")

    duplicate_chart_schema = make_chart_create_schema(
        name=chart.name,
        files=[{"path": "dup.yaml", "content": "dup_content"}],
    )
    with pytest.raises(ConflictException):  # Repository should raise ConflictException
        await create_chart(session=db_session, chart_schema=duplicate_chart_schema, creator="dup_user")


@pytest.mark.asyncio
async def test_update_chart(db_session: AsyncSession) -> None:
    # Create initial chart
    chart_name = f"update-test-{uuid4()}"
    chart_schema = make_chart_create_schema(
        name=chart_name,
        signature_content="key: value",
        files=[{"path": "values.yaml", "content": "key: value"}],
        tags=["initial"],
    )
    creator = "create_user"
    updater = "update_user"

    # Create chart first
    created_chart = await create_chart(db_session, chart_schema, creator=creator)
    original_updated_at = created_chart.updated_at
    original_creator = created_chart.created_by
    assert created_chart.tags == ["initial"]

    # Prepare update data
    new_name = f"{chart_name}-updated"
    update_signature_file = make_mock_signature_file("new_key: new_value")
    update_chart_files = make_mock_chart_files(
        [
            {"path": "new_values.yaml", "content": "new: content"},
            {"path": "Chart.yaml", "content": "apiVersion: v2"},
        ]
    )

    update_schema = ChartUpdate(
        name=new_name,
        type=WorkloadType.FINE_TUNING,
        signature=update_signature_file,
        files=update_chart_files,
        tags=["updated"],
    )

    updated_chart = await update_chart(db_session, created_chart.id, update_schema, updater)
    await db_session.flush()

    # Refresh to load updated files relationship
    await db_session.refresh(updated_chart)

    assert updated_chart.name == new_name
    assert updated_chart.type == WorkloadType.FINE_TUNING
    assert updated_chart.signature == {"new_key": "new_value"}
    assert updated_chart.updated_by == updater
    assert updated_chart.updated_by != original_creator
    assert updated_chart.updated_at > original_updated_at
    assert updated_chart.updated_at > updated_chart.created_at
    assert updated_chart.tags == ["updated"]

    files_in_db = updated_chart.files
    assert len(files_in_db) == 2
    paths = {f.path for f in files_in_db}
    assert paths == {"new_values.yaml", "Chart.yaml"}
    assert await select_chart(db_session, updated_chart.id) is not None


@pytest.mark.asyncio
async def test_update_chart_not_found(db_session: AsyncSession) -> None:
    fake_id = uuid4()
    update_schema = ChartUpdate(
        name=str(uuid4()),
        type=WorkloadType.INFERENCE,
        signature=make_mock_signature_file(),
        files=None,
    )

    with pytest.raises(NotFoundException, match="not found"):
        await update_chart(db_session, fake_id, update_schema, creator="test_user")


@pytest.mark.asyncio
async def test_create_file_records(db_session: AsyncSession) -> None:
    # Create chart without files
    chart_name = f"create-files-{uuid4()}"
    chart_schema = make_chart_create_schema(name=chart_name)
    creator = "file_creator"
    created_chart = await create_chart(db_session, chart_schema, creator=creator)

    # Verify initially no files
    chart = await select_chart(db_session, created_chart.id)
    assert len(chart.files) == 0

    # Create new files (repository expects dict objects)
    new_files = [
        {"path": "file1.yaml", "content": "x: y"},
        {"path": "file2.yaml", "content": "z: w"},
    ]

    await create_file_records(db_session, created_chart.id, new_files, creator)

    # Refresh chart to ensure relationship is updated
    await db_session.refresh(chart)

    assert len(chart.files) == 2
    paths = {f.path for f in chart.files}
    assert paths == {"file1.yaml", "file2.yaml"}


@pytest.mark.asyncio
async def test_delete_chart_files_only_files(db_session: AsyncSession) -> None:
    chart_name = f"delete-files-test-{uuid4()}"
    chart_schema = make_chart_create_schema(
        name=chart_name,
        files=[
            {"path": "file1.yaml", "content": "a: b"},
            {"path": "file2.yaml", "content": "c: d"},
        ],
    )
    creator = "file_deleter"

    created_chart = await create_chart(db_session, chart_schema, creator)
    chart = await select_chart(db_session, created_chart.id)
    assert chart is not None
    assert len(chart.files) == 2

    # Delete files
    await delete_chart_files(db_session, chart.id)

    # Refresh chart after deleting files
    await db_session.refresh(chart)

    # Check that files are gone
    assert len(chart.files) == 0

    # Check that chart still exists
    remaining_chart = await select_chart(db_session, chart.id)
    assert remaining_chart is not None
    assert remaining_chart.id == chart.id
    assert remaining_chart.name == chart_name
