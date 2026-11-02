# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Configuration for reclaiming data left behind by deleted projects."""

import os

# Off unless an operator turns it on. Reclamation is irreversible, and the rule behind it compares
# timestamps taken from two different clocks, so the first environment it acts on should be a
# deliberate choice rather than whichever one deployed first. Off, nothing is scheduled at all.
CLEANUP_ENABLED = os.getenv("DELETED_PROJECT_CLEANUP_ENABLED", "false").lower() == "true"

# An hour. The work is a listing of every prefix in the bucket, and what it looks for — a project
# having been deleted — does not become more urgent for being noticed sooner.
CLEANUP_INTERVAL_SECONDS = int(os.getenv("DELETED_PROJECT_CLEANUP_INTERVAL_SECONDS", "3600"))

# How far data must predate a namespace before it is credited to a previous holder of that name.
#
# The two timestamps being compared come from different clocks — database rows are stamped by the
# app pod, namespaces by the kube API server — so a bare comparison would misjudge data written
# either side of a namespace's own creation. An hour is far wider than any plausible drift between
# NTP-synced hosts and far narrower than the gap between a project being deleted and its name being
# taken again. Since acting on this verdict is destructive, it is applied in the direction that
# keeps data: too large only hides an orphan, too small would eventually condemn a live one.
#
# Configurable because the right value is a property of an installation's clocks and how quickly
# names get reused there, and neither is knowable from here.
CLEANUP_SKEW_MARGIN_SECONDS = int(os.getenv("DELETED_PROJECT_CLEANUP_SKEW_MARGIN_SECONDS", "3600"))

# Identifies this job's Postgres advisory lock. Arbitrary, but must stay stable: replicas
# coordinate by agreeing on the number.
CLEANUP_LOCK_KEY = 6023_0001
