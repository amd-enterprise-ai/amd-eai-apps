# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import pytest
from pydantic import ValidationError

from app.overlays.models import SOURCE_PATH_MAX_LENGTH, Overlay
from app.overlays.schemas import OverlayResponse, OverlayUpdate


def test_overlay_update_accepts_source_path_at_column_limit() -> None:
    update = OverlayUpdate(source_path="a" * SOURCE_PATH_MAX_LENGTH, updated_by="user@example.com")

    assert update.source_path == "a" * SOURCE_PATH_MAX_LENGTH


def test_overlay_update_rejects_source_path_beyond_column_limit() -> None:
    with pytest.raises(ValidationError, match=f"at most {SOURCE_PATH_MAX_LENGTH} characters"):
        OverlayUpdate(source_path="a" * (SOURCE_PATH_MAX_LENGTH + 1), updated_by="user@example.com")


def test_generic_overlay_response_from_model(sample_generic_overlay: Overlay) -> None:
    """Test OverlayResponse validation from a model without canonical_name."""
    overlay = sample_generic_overlay
    response = OverlayResponse.model_validate(overlay)

    assert response.id == overlay.id
    assert response.chart_id == overlay.chart_id
    assert response.canonical_name is None
    assert response.overlay == overlay.overlay
    assert response.created_by == overlay.created_by
    assert response.created_at == overlay.created_at
    assert response.updated_at == overlay.updated_at


def test_model_overlay_response_from_model(sample_model_overlay: Overlay) -> None:
    """Test OverlayResponse validation from a model with canonical_name."""
    overlay = sample_model_overlay
    response = OverlayResponse.model_validate(overlay)

    assert response.id == overlay.id
    assert response.chart_id == overlay.chart_id
    assert response.canonical_name == overlay.canonical_name
    assert response.overlay == overlay.overlay
    assert response.created_by == overlay.created_by
    assert response.created_at == overlay.created_at
    assert response.updated_at == overlay.updated_at
