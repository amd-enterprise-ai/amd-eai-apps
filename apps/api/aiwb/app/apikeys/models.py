# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api_common.models import BaseEntity


class ApiKey(BaseEntity):
    """
    API key model for AIWB.

    API keys are scoped to namespaces (not projects). The token itself lives in the OpenBao/ESO
    store; this table tracks the key's reference and its expiry.
    """

    __tablename__ = "api_keys"

    display_name: Mapped[str] = mapped_column(String, nullable=False)
    truncated_key: Mapped[str] = mapped_column(String, nullable=False)
    namespace: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Expiry is owned here now (was fetched from cluster-auth). None = never. OpenBao
    # delete_version_after enforces the actual drop; this is the value the UI displays.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Legacy cluster-auth accessor id — internal only, never surfaced in API responses. The
    # OpenBao/ESO store is the sole key path now, so store-created keys leave this NULL. It is
    # retained as the join key the one-time key-import migration needs to locate
    # each pre-store key's material in OpenBao; dropped once that migration has run and cluster-auth
    # is fully retired from the key path.
    cluster_auth_key_id: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (UniqueConstraint("display_name", "namespace", name="uq_api_keys_display_name_namespace"),)
