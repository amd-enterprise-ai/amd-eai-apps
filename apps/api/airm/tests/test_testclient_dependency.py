# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guards the HTTP backend that `starlette.testclient` binds at import time.

From starlette 1.2 the test client prefers `httpx2` and emits a
`StarletteDeprecationWarning` when it falls back to `httpx`. That warning
subclasses `UserWarning`, not `DeprecationWarning`, so `pytest.ini`'s
`ignore::DeprecationWarning` does not cover it and the `error` filter promotes it
to a collection failure that takes down the whole suite. These tests fail if the
`httpx2` dependency is dropped again.
"""

import subprocess
import sys
from importlib import metadata

import httpx2

_MINIMUM_HTTPX2 = (2, 12, 0)

# Set the filter from inside the child rather than via `-W`: `-W` resolves module
# names before starlette is importable, so `-W error::starlette...` is silently
# discarded ("Invalid -W option ignored") and the check would always pass.
_ASSERT_NO_DEPRECATION = """
import warnings

from starlette.exceptions import StarletteDeprecationWarning

warnings.simplefilter("error", StarletteDeprecationWarning)

# imported after simplefilter() so the filter is active
import starlette.testclient
"""


def test_httpx2_meets_the_declared_minimum_version() -> None:
    """`starlette.testclient` needs httpx2 to avoid its deprecation warning."""
    raw_version = getattr(httpx2, "__version__", None) or metadata.version("httpx2")
    installed = tuple(int(part) for part in raw_version.split(".")[:3])

    assert installed >= _MINIMUM_HTTPX2, (
        f"httpx2 {raw_version} is below the declared floor {'.'.join(str(part) for part in _MINIMUM_HTTPX2)}."
    )


def test_importing_starlette_testclient_emits_no_deprecation_warning() -> None:
    """Importing the test client must stay warning-free under an error filter.

    Runs in a subprocess because the warning fires once, at first import of
    `starlette.testclient` — and `tests/conftest.py` has already imported it by
    the time this test body runs, so an in-process check would always pass.
    """
    result = subprocess.run(
        [sys.executable, "-c", _ASSERT_NO_DEPRECATION],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        "Importing starlette.testclient raised a StarletteDeprecationWarning. "
        "This usually means the httpx2 dependency was removed.\n"
        f"{result.stderr}"
    )
