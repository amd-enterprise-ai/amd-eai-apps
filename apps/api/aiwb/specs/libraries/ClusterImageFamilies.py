# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Assert discovered base-image families cover the cluster's accelerator hardware.

The oracle mirrors the backend's own accelerator->family mapping
(``app/cluster/service.py::_resolve_cluster_base_image_ref``) rather than imposing a
stricter rule: an E2E check that fails when the system legitimately selects a family
would be brittle by construction. The two sides it compares come from different sources
-- the required side from the accelerator rule, the discovered side from the base models
actually validated on the cluster -- so the comparison stays meaningful.

Discovered families are matched by their canonical family id (the shipped default image
basenames). A cluster configured with non-default base image refs would need this map
extended; that is out of scope for the default installs this test targets.

Limitation: the assertion is only meaningful while the discovered side comes from
hardware-validated models. If the backend's model listing fails, ``get_aim_image_families``
falls back to running the same accelerator mapping this oracle mirrors, so both sides
coincide and the check cannot detect a mismatch on that degraded path.
"""

try:
    from robot.api import logger
except ImportError:
    # Fallback so the pure-logic unit tests run without Robot Framework installed
    # (mirrors AimCatalogGenerator.py).
    class _FallbackLogger:
        def info(self, msg):
            print(f"INFO: {msg}")

    logger = _FallbackLogger()

_RADEON = "radeon"
_EPYC = "epyc"
_DEFAULT = "default"

# Canonical family ids -> class, from the default AIM base image refs
# (aim-base / aim-radeon-base / aim-epyc-base). Anything else is not a base family the
# test recognizes and is ignored (an unrelated ``custom-*`` entry neither satisfies nor
# blocks a required class).
_CANONICAL_FAMILY_IDS = {
    "aim-radeon-base": _RADEON,
    "aim-epyc-base": _EPYC,
    "aim-base": _DEFAULT,
}


def _is_radeon_gpu(model: str, vendor: str) -> bool:
    """AMD Radeon AI PRO R-series and Radeon PRO W-series GPUs."""
    normalized = model.upper()
    return normalized.startswith(("R", "W")) and not normalized.startswith("RTX") and vendor.strip().lower() != "nvidia"


def required_base_image_family_classes(accelerators: list[dict]) -> list[str]:
    """Return the base-image family classes the cluster's accelerators require.

    Mirrors ``_resolve_cluster_base_image_ref``: any Radeon GPU -> radeon, any other GPU
    -> default, any EPYC CPU -> epyc; non-GPU/CPU types and plain CPUs contribute nothing
    and fall back to default when nothing else is required.
    """
    has_radeon_gpu = False
    has_other_gpu = False
    has_epyc_cpu = False

    for entry in accelerators:
        if not isinstance(entry, dict):
            raise AssertionError(f"Accelerator entry must be an object, got {type(entry).__name__}")
        accelerator_type = str(entry.get("acceleratorType", "")).strip().lower()
        model = str(entry.get("acceleratorModel") or "").strip()
        vendor = str(entry.get("acceleratorVendor") or "").strip()

        if accelerator_type == "gpu":
            if _is_radeon_gpu(model, vendor):
                has_radeon_gpu = True
            else:
                has_other_gpu = True
        elif accelerator_type == "cpu" and model.startswith("EPYC_"):
            has_epyc_cpu = True

    classes = set()
    if has_other_gpu:
        classes.add(_DEFAULT)
    if has_radeon_gpu:
        classes.add(_RADEON)
    if has_epyc_cpu:
        classes.add(_EPYC)
    if not classes:
        classes.add(_DEFAULT)
    return sorted(classes)


def discovered_base_image_family_classes(families: list[dict]) -> list[str]:
    """Return the canonical base-family classes among discovered families."""
    classes = {_CANONICAL_FAMILY_IDS.get(str(f.get("familyId", "")).lower()) for f in families}
    return sorted(c for c in classes if c is not None)


def discovered_families_should_cover_cluster_hardware(accelerators: list[dict], families: list[dict]) -> None:
    """Assert every hardware-required base-image family class is in the discovered catalog.

    Extra supported families are allowed; a missing required family fails.
    """
    required = required_base_image_family_classes(accelerators)
    discovered = discovered_base_image_family_classes(families)
    logger.info(f"Required base-image family classes: {required}; discovered: {discovered}")

    missing = sorted(set(required) - set(discovered))
    if missing:
        raise AssertionError(
            f"Discovered base-image families {discovered} do not cover the cluster's hardware; "
            f"missing required class(es): {missing} (accelerators required {required})"
        )
