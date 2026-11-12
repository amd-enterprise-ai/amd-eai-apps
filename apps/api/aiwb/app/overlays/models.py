# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api_common.models import BaseEntity

from ..charts.models import Chart

# Matches the VARCHAR(512) column migration 014 creates.
SOURCE_PATH_MAX_LENGTH = 512


class Overlay(BaseEntity):
    __tablename__ = "overlays"

    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    canonical_name: Mapped[str] = mapped_column(String, nullable=True)
    # A chart may ship several recipes for one model, one per GPU family, so a registered overlay
    # is identified by the file it came from. Overlays authored through the API have no file and
    # stay unique per model.
    source_path: Mapped[str | None] = mapped_column(String(SOURCE_PATH_MAX_LENGTH), nullable=True)
    overlay: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    chart_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("charts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chart: Mapped[Chart] = relationship(Chart, lazy="joined")

    __table_args__ = (
        Index(
            "overlays_chart_id_canonical_name_unsourced_key",
            chart_id,
            canonical_name,
            unique=True,
            postgresql_where=source_path.is_(None),
        ),
        Index(
            "overlays_chart_id_source_path_key",
            chart_id,
            source_path,
            unique=True,
            postgresql_where=source_path.is_not(None),
        ),
    )
