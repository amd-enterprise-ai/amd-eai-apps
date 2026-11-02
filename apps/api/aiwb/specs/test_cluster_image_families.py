# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for ClusterImageFamilies: the E2E oracle mapping accelerators to base-image families."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from ClusterImageFamilies import (
    discovered_base_image_family_classes,
    discovered_families_should_cover_cluster_hardware,
    required_base_image_family_classes,
)


def _gpu(model, vendor="amd"):
    return {"acceleratorType": "gpu", "acceleratorModel": model, "acceleratorVendor": vendor, "deviceId": model}


def _cpu(model):
    return {"acceleratorType": "cpu", "acceleratorModel": model, "acceleratorVendor": "amd", "deviceId": model}


def _apu(model="APU_STRIX_HALO"):
    return {"acceleratorType": "apu", "acceleratorModel": model, "acceleratorVendor": "amd", "deviceId": model}


def _family(family_id, repository=None):
    return {"familyId": family_id, "repository": repository, "tags": ["0.12"]}


# -- required_base_image_family_classes (mirrors the backend mapping) --


def test_radeon_gpu_requires_radeon_family():
    assert required_base_image_family_classes([_gpu("R9700")]) == ["radeon"]


def test_radeon_pro_w_series_requires_radeon_family():
    assert required_base_image_family_classes([_gpu("W7900")]) == ["radeon"]


def test_instinct_gpu_requires_default_family():
    assert required_base_image_family_classes([_gpu("MI300X")]) == ["default"]


def test_nvidia_rtx_requires_default_family_not_radeon():
    assert required_base_image_family_classes([_gpu("RTX4090", vendor="nvidia")]) == ["default"]


def test_epyc_cpu_requires_epyc_family():
    assert required_base_image_family_classes([_cpu("EPYC_ZEN5")]) == ["epyc"]


def test_hybrid_radeon_and_epyc_requires_both():
    assert required_base_image_family_classes([_gpu("R9700"), _cpu("EPYC_ZEN5")]) == ["epyc", "radeon"]


def test_mixed_radeon_and_instinct_gpus_require_both_gpu_families():
    assert required_base_image_family_classes([_gpu("R9700"), _gpu("MI300X")]) == ["default", "radeon"]


def test_nvidia_rtx_without_nvidia_vendor_is_not_radeon():
    # Pins the RTX half of the Radeon predicate independently of the vendor check.
    assert required_base_image_family_classes([_gpu("RTX4090", vendor="amd")]) == ["default"]


def test_r_series_model_from_nvidia_vendor_is_not_radeon():
    # Pins the vendor half of the Radeon predicate independently of the RTX check.
    assert required_base_image_family_classes([_gpu("R9700", vendor="nvidia")]) == ["default"]


# These two pin *mirror fidelity* of the mapping — that it reproduces the backend's
# default fallback — not end-to-end coverage. The E2E keyword separately refuses an empty
# accelerator catalog as a discovery defect, since this mapping alone would green on it.


def test_empty_accelerators_default_to_default_family():
    assert required_base_image_family_classes([]) == ["default"]


def test_plain_cpu_only_defaults_to_default_family():
    assert required_base_image_family_classes([_cpu("CPU")]) == ["default"]


def test_apu_only_defaults_to_default_family():
    assert required_base_image_family_classes([_apu()]) == ["default"]


def test_apu_alongside_radeon_requires_only_radeon():
    assert required_base_image_family_classes([_apu(), _gpu("R9700")]) == ["radeon"]


# The oracle mirrors the backend, which maps every non-Radeon GPU (including an empty or
# unrecognized model, or a vendor-only NVIDIA entry) to the default family. The test must
# not be stricter than the API it validates.


def test_gpu_without_model_maps_to_default():
    assert required_base_image_family_classes(
        [{"acceleratorType": "gpu", "acceleratorModel": "", "acceleratorVendor": "amd", "deviceId": "73bf"}]
    ) == ["default"]


def test_gpu_with_unrecognized_model_maps_to_default():
    assert required_base_image_family_classes([_gpu("FOOBAR9000")]) == ["default"]


def test_nvidia_vendor_gpu_maps_to_default():
    assert required_base_image_family_classes([_gpu("", vendor="nvidia")]) == ["default"]


def test_unknown_accelerator_type_is_ignored_and_defaults():
    assert required_base_image_family_classes(
        [{"acceleratorType": "unknown", "acceleratorModel": "", "acceleratorVendor": "", "deviceId": "73bf"}]
    ) == ["default"]


def test_non_object_accelerator_entry_fails_cleanly():
    with pytest.raises(AssertionError, match="Accelerator entry must be an object"):
        required_base_image_family_classes(["R9700"])


# -- discovered_base_image_family_classes (canonical family ids only) --


def test_discovered_classes_ignore_automatic():
    families = [_family("automatic"), _family("aim-radeon-base"), _family("aim-epyc-base")]
    assert discovered_base_image_family_classes(families) == ["epyc", "radeon"]


def test_discovered_default_family_classified():
    assert discovered_base_image_family_classes([_family("aim-base")]) == ["default"]


def test_non_canonical_family_id_is_ignored():
    # An unrelated family must not be counted, and a lookalike must not be misclassified.
    assert discovered_base_image_family_classes([_family("aim-unsupported")]) == []
    assert discovered_base_image_family_classes([_family("custom-radeon-experimental")]) == []


# -- discovered_families_should_cover_cluster_hardware --


def test_coverage_passes_when_required_family_present():
    accelerators = [_gpu("R9700"), _cpu("EPYC_ZEN5")]
    families = [_family("automatic"), _family("aim-radeon-base"), _family("aim-epyc-base")]

    discovered_families_should_cover_cluster_hardware(accelerators, families)

    # Assert why it passes, so the test still has teeth if the check is weakened.
    assert required_base_image_family_classes(accelerators) == ["epyc", "radeon"]
    assert discovered_base_image_family_classes(families) == ["epyc", "radeon"]


def test_coverage_allows_extra_supported_families():
    # Cluster requires only radeon, catalog also exposes a default family — allowed.
    accelerators = [_gpu("R9700")]
    families = [_family("automatic"), _family("aim-radeon-base"), _family("aim-base")]

    discovered_families_should_cover_cluster_hardware(accelerators, families)

    assert required_base_image_family_classes(accelerators) == ["radeon"]
    assert discovered_base_image_family_classes(families) == ["default", "radeon"]


def test_coverage_fails_when_required_family_missing():
    with pytest.raises(AssertionError, match="missing required class"):
        discovered_families_should_cover_cluster_hardware(
            [_gpu("R9700")],
            [_family("automatic"), _family("aim-base")],
        )


def test_coverage_fails_when_default_required_but_only_non_canonical_family_present():
    with pytest.raises(AssertionError, match="missing required class"):
        discovered_families_should_cover_cluster_hardware(
            [_gpu("MI300X")],
            [_family("automatic"), _family("aim-unsupported")],
        )
