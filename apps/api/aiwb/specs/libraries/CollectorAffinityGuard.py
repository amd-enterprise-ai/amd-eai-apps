# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Keep the CPU/EPYC test selector aligned with the collector's node affinity.

The allowlist itself lives in ModelCatalog (the selector owns the policy); this module only
lints it against the deployed chart, so it imports the constant rather than mirroring it.
"""

from pathlib import Path

from ModelCatalog import COLLECTOR_SUPPORTED_EPYC_MODELS

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_CHART = _REPO_ROOT / "helm" / "aiwb" / "templates" / "vllm-otel-collector.yaml"
_KEY_PREFIX = "feature.node.kubernetes.io/aim-accelerator."


def collector_epyc_models_from_chart(chart_text: str) -> set[str]:
    """Return EPYC models from valid, OR-ed ``Exists`` affinity terms.

    The collector chart expresses each supported hardware class as its own
    ``nodeSelectorTerm`` (terms are OR-ed), containing one matchExpression with
    ``operator: Exists``. This parser validates that load-bearing structure as well
    as the key set, so changing Exists to DoesNotExist or collapsing several SKUs
    into one AND-ed term fails loudly.
    """
    terms: list[list[tuple[str, str]]] = []
    current_term: list[tuple[str, str]] | None = None
    pending_key: str | None = None

    for raw_line in chart_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "- matchExpressions:":
            if current_term is not None:
                terms.append(current_term)
            current_term = []
            pending_key = None
            continue
        if current_term is None:
            continue
        if stripped.startswith("- key: "):
            pending_key = stripped.removeprefix("- key: ").strip()
            continue
        if stripped.startswith("operator:") and pending_key is not None:
            current_term.append((pending_key, stripped.removeprefix("operator:").strip()))
            pending_key = None

    if current_term is not None:
        terms.append(current_term)

    models: set[str] = set()
    for expressions in terms:
        epyc = [
            (key.removeprefix(_KEY_PREFIX), operator)
            for key, operator in expressions
            if key.startswith(f"{_KEY_PREFIX}EPYC_")
        ]
        if not epyc:
            continue
        if len(expressions) != 1 or len(epyc) != 1 or epyc[0][1] != "Exists":
            raise AssertionError(
                "Each collector EPYC model must be one OR-ed nodeSelectorTerm with exactly "
                f"one `operator: Exists` expression; got {expressions!r}"
            )
        models.add(epyc[0][0])
    return models


def check_collector_epyc_allowlist(chart_path: Path = _DEFAULT_CHART) -> None:
    """Assert the selector allowlist exactly matches the collector affinity contract."""
    chart_models = collector_epyc_models_from_chart(chart_path.read_text())
    if chart_models != COLLECTOR_SUPPORTED_EPYC_MODELS:
        raise AssertionError(
            "Collector EPYC affinity and test selector differ: "
            f"chart={sorted(chart_models)}, selector={sorted(COLLECTOR_SUPPORTED_EPYC_MODELS)}"
        )


if __name__ == "__main__":
    check_collector_epyc_allowlist()
    print("Collector EPYC affinity matches the test selector allowlist")
