# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import datetime

DEFAULT_CATCH_ALL_QUOTA_NAME = "kaiwo"

# How long the cluster is given to apply a quota before a snapshot that omits it, or still
# reports its previous allocation, is treated as a real failure rather than a lagging report.
PENDING_QUOTA_PROVISIONING_GRACE = datetime.timedelta(minutes=5)

QUOTA_FAILURE_REASON_UNSPECIFIED = "The cluster reported a quota failure without a reason."
