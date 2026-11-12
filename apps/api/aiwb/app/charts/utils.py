# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import asyncio
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import yaml
from loguru import logger

from api_common.exceptions import ValidationException

from .models import Chart


@contextmanager
def chart_directory(chart: Chart) -> Generator[Path]:
    """
    Context manager that re-creates all the files of the chart in a temporary directory
    to be used with Helm template rendering and cleans it up afterward.

    Args:
        chart: Chart model with files relationship containing ChartFile objects

    Yields:
        Path to temporary directory containing the chart files

    Example:
        >>> with chart_directory(chart) as chart_path:
        ...     deployer.deploy_chart(chart_path=str(chart_path), ...)
    """
    temp_dir = tempfile.TemporaryDirectory()
    try:
        root = Path(temp_dir.name).resolve()
        for file in chart.files:
            # Stored paths are client-supplied and may predate ingest validation, so
            # containment is enforced again here, right before touching the filesystem.
            target = (root / file.path).resolve()
            if target == root or not target.is_relative_to(root):
                raise ValidationException(
                    message="Chart contains a file path outside the chart directory",
                    detail=f"Rejected chart file path: {file.path!r}",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content)

        yield Path(temp_dir.name)
    finally:
        temp_dir.cleanup()


async def render_helm_template(chart: Chart, name: str, namespace: str, overlays_values: list[dict] = []) -> str:
    """
    Render the Helm template for the given chart with the overlays values.

    Args:
        chart: The chart to render.
        name: The name of the workload.
        namespace: Kubernetes namespace to render resources into.
        overlays_values: The values coming from the overlays to render the chart with.

    Returns:
        Rendered manifest as string

    Raises:
        ValidationException: If Helm template rendering fails
    """
    with chart_directory(chart) as chart_dir:
        cmd = ["helm", "template", str(chart_dir), "--namespace", namespace, "--name-template", name]

        for i, values in enumerate(overlays_values):
            overlay_file = chart_dir / f"overlay_{i}.yaml"

            with open(overlay_file, "w") as f:
                yaml.dump(values, f)
                logger.debug(f"Overlay {i} has values: \n{values}\n\n")

            cmd.extend(["--values", str(overlay_file)])
        cmd.extend(["--set", "fullnameOverride=" + name])
        logger.debug(f"Rendering Helm template: {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout, stderr = await process.communicate()

        if process.returncode is not None and process.returncode != 0:
            raise ValidationException(message="Failed to render Helm template", detail=stderr.decode())

        return stdout.decode()
