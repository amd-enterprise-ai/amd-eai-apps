#!/usr/bin/env python3

# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Fixture-backed kubectl executable used only by the black-box Robot suite.

Fixture keys are matched against the full normalized argv (all arguments after the
program name, space-joined), so a fixture only answers the exact command it declares.
A generic key like ``get --raw`` therefore cannot satisfy an arbitrary
``kubectl get --raw <other-path>`` invocation — an unmodelled command fails loudly.
"""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    fixture_path = os.environ.get("CLUSTER_CHECK_FIXTURE")
    if not fixture_path:
        print("CLUSTER_CHECK_FIXTURE is not set", file=sys.stderr)
        return 99
    transcript = json.loads(Path(fixture_path).read_text())
    command = " ".join(sys.argv[1:])
    entry = transcript.get(command)
    if entry is None:
        print(f"unmodelled kubectl command: {command}", file=sys.stderr)
        return 99
    rc, stdout, stderr = entry
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    return int(rc)


if __name__ == "__main__":
    sys.exit(main())
