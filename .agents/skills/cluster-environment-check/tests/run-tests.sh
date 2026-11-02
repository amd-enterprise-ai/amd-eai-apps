#!/usr/bin/env bash
set -euo pipefail

# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
# Run both layers without a cluster or registry: Python regression tests stub run(), while the
# Robot suite drives the shipped CLI through a fixture-backed kubectl executable.
test_dir=$(cd "$(dirname "$0")" && pwd)
skill_dir=$(cd "${test_dir}/.." && pwd)
python3 "${test_dir}/test_environment_check.py" "$@"
(
  cd "${skill_dir}/specs" || exit
  uv run --locked robot --argumentfile arguments.txt environment_check.robot
)
