# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Configuration for MinIO object storage."""

import os

# ============================================================================
# MinIO / Object Storage Configuration
# ============================================================================
MINIO_URL = os.getenv("MINIO_URL", "http://minio.minio-tenant-default.svc.cluster.local:80")

# Signs presigned URLs for clients outside the cluster. SigV4 covers the Host header, so a URL
# signed for the internal service name cannot be rewritten afterwards. The MINIO_URL fallback
# covers non-Helm runs on a single network.
MINIO_EXTERNAL_URL = os.getenv("MINIO_EXTERNAL_URL") or MINIO_URL

MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "default-bucket")

# Emitted CR secretKeyRefs must name the same Secret, and the same keys within it, that the chart
# binds MINIO_ACCESS_KEY/MINIO_SECRET_KEY from. The Secret is platform-provisioned (no chart template
# owns it), so its name and key names can vary per install; all three are threaded in from the chart
# so the pod bindings and the emitted CR refs stay pointed at the same place.
MINIO_CREDENTIALS_SECRET_NAME = os.getenv("MINIO_CREDENTIALS_SECRET_NAME", "minio-credentials")
MINIO_CREDENTIALS_ACCESS_KEY_KEY = os.getenv("MINIO_CREDENTIALS_ACCESS_KEY_KEY", "minio-access-key")
MINIO_CREDENTIALS_SECRET_KEY_KEY = os.getenv("MINIO_CREDENTIALS_SECRET_KEY_KEY", "minio-secret-key")

MINIO_MAX_ATTEMPTS = int(os.getenv("MINIO_MAX_ATTEMPTS", "3"))
MINIO_MIN_WAIT = int(os.getenv("MINIO_MIN_WAIT", "4"))
MINIO_MAX_WAIT = int(os.getenv("MINIO_MAX_WAIT", "60"))
