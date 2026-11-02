# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for how the CLI renders what the core layer reports."""

from pathlib import Path

from click.testing import CliRunner

from tests.conftest import COPYRIGHT_HEADER
from workloads_manager.cli import cli


def test_init_reports_a_markup_hostile_pin_verbatim(workloads: dict[str, str]) -> None:
    """`wm init` quotes the pin file it rejected, so that value must survive rendering intact."""
    pin = "not-a-hash[/][red]SPOOFED"
    (Path(workloads["package_dir"]) / "PATCHED_VERSION").write_text(f"{COPYRIGHT_HEADER}\n{pin}\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["init"])

    # Console wrapping can split the message across lines; only whitespace is affected.
    rendered = " ".join(result.output.split())

    assert result.exit_code == 1
    # Without escaping, rich consumes the tags and the diagnostic reports a value the
    # file does not contain - or raises MarkupError and loses the line altogether.
    assert pin in rendered
    # ...while the failure line's own markup must still be markup. Escaping the whole
    # f-string rather than just the message would satisfy the assertion above and
    # silently print the styling tags as literal text.
    assert "[bold red]" not in rendered
