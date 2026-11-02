# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.orphans.reap import SKEW_MARGIN, _index_by_prefix, _should_be_reclaimed
from app.projects.constants import NAMESPACE_ID_LABEL
from app.projects.crds import Namespace

NAMESPACE_CREATED = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def namespace(name: str = "acme", created_at: datetime | None = NAMESPACE_CREATED, labelled: bool = True) -> Namespace:
    return Namespace(
        name=name,
        labels={NAMESPACE_ID_LABEL: "3f2b1c4d-0000-4000-8000-000000000001"} if labelled else {},
        created_at=created_at,
    )


@pytest.mark.parametrize(
    ("written_at", "holder", "expected"),
    [
        pytest.param(
            NAMESPACE_CREATED,
            None,
            True,
            id="no namespace holds the name",
        ),
        pytest.param(
            NAMESPACE_CREATED + timedelta(days=1),
            namespace(),
            False,
            id="written after the namespace was created",
        ),
        pytest.param(
            NAMESPACE_CREATED - SKEW_MARGIN - timedelta(minutes=1),
            namespace(),
            True,
            id="predates the namespace by more than the margin",
        ),
        pytest.param(
            NAMESPACE_CREATED - SKEW_MARGIN + timedelta(minutes=1),
            namespace(),
            False,
            id="predates the namespace by less than the margin",
        ),
        pytest.param(
            NAMESPACE_CREATED - timedelta(days=30),
            namespace(created_at=None),
            False,
            id="namespace reports no creation time",
        ),
        pytest.param(
            NAMESPACE_CREATED - timedelta(days=30),
            namespace(labelled=False),
            True,
            id="unlabelled namespace still holds the name",
        ),
    ],
)
def test_should_be_reclaimed(written_at: datetime, holder: Namespace | None, expected: bool) -> None:
    assert _should_be_reclaimed(written_at, holder) is expected


def test_exactly_at_the_margin_is_kept() -> None:
    """The margin is inclusive on the keeping side — a tie is not evidence of a previous holder."""
    assert _should_be_reclaimed(NAMESPACE_CREATED - SKEW_MARGIN, namespace()) is False


@pytest.mark.parametrize(
    ("written_at", "holder"),
    [
        pytest.param(
            (NAMESPACE_CREATED - timedelta(days=30)).replace(tzinfo=None),
            namespace(),
            id="naive data against an aware namespace",
        ),
        pytest.param(
            NAMESPACE_CREATED - timedelta(days=30),
            namespace(created_at=NAMESPACE_CREATED.replace(tzinfo=None)),
            id="aware data against a naive namespace",
        ),
    ],
)
def test_mixing_naive_and_aware_does_not_abort(written_at: datetime, holder: Namespace) -> None:
    """One naive value from any producer would otherwise raise on the first comparison.

    Both sides naive would not exercise this — that case compares cleanly on its own.
    """
    assert _should_be_reclaimed(written_at, holder) is True


def test_offsets_are_converted_rather_than_compared_as_wall_time() -> None:
    """Comparing wall-clock readings across offsets would misjudge data close to the boundary.

    Both values name the same instant, ten minutes inside the margin, so the only way to reclaim it
    would be to compare the numbers on the clock faces instead of the instants.
    """
    ten_minutes_inside = NAMESPACE_CREATED - SKEW_MARGIN + timedelta(minutes=10)
    same_instant_in_tokyo = ten_minutes_inside.astimezone(timezone(timedelta(hours=9)))

    assert same_instant_in_tokyo.hour != ten_minutes_inside.hour
    assert _should_be_reclaimed(same_instant_in_tokyo, namespace()) is False


def test_indexing_groups_colliding_names_rather_than_dropping_them() -> None:
    """A mapping that kept one namespace per prefix would hide the collision entirely."""
    index = _index_by_prefix([namespace("data--science"), namespace("data-science"), namespace("acme")])

    assert len(index["data-science"]) == 2
    assert len(index["acme"]) == 1
