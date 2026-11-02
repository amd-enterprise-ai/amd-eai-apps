# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Static coverage for the project GPU allocation E2E contract."""

from pathlib import Path

SPECS_DIR = Path(__file__).resolve().parent
PROJECTS_SUITE = SPECS_DIR / "projects.robot"
PROJECTS_RESOURCE = SPECS_DIR / "resources" / "aiwb_projects.resource"
CLUSTER_API_RESOURCE = SPECS_DIR / "resources" / "api" / "cluster.resource"


def _block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.rstrip() == name), None)
    assert start is not None, f"{name!r} not found"
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_project_without_gpu_quota_asserts_cluster_capacity_fallback() -> None:
    suite = PROJECTS_SUITE.read_text()
    scenario = _block(suite, "Project without an assigned GPU quota sees cluster capacity available")

    assert "Given a fresh project with user access exists" in scenario
    assert 'When AIWB project workload metric request is sent for "gpu_device_utilization"' in scenario
    assert "And GPU device metric should report cluster capacity as its available ceiling" in scenario

    resource = PROJECTS_RESOURCE.read_text()
    keyword = _block(resource, "GPU device metric should report cluster capacity as its available ceiling")

    assert "Get AIWB Cluster Resources    expected_status=200" in keyword
    assert "${response.json()}[data][availableResources]    gpuCount" in keyword
    assert "Get cluster GPU capacity" not in keyword
    assert 'GPU device metric should report an allocation ceiling of "${expected_gpu_count}"' in keyword
    assert "Should Be Empty" not in keyword

    api_resource = CLUSTER_API_RESOURCE.read_text()
    endpoint = _block(api_resource, "Cluster resources endpoint")
    request = _block(api_resource, "Get AIWB Cluster Resources")

    assert "Service API Endpoint    aiwb    endpoint=resources" in endpoint
    assert "Safe Get Request    ${endpoint}" in request


def test_gpu_allocation_ceiling_assertion_rejects_missing_or_null_values() -> None:
    resource = PROJECTS_RESOURCE.read_text()
    keyword = _block(resource, 'GPU device metric should report an allocation ceiling of "${expected_gpu_count}"')

    assert "Should Not Be Empty    ${allocation_series}" in keyword
    assert "Should Not Be Empty    ${values}" in keyword
    assert "FOR    ${datapoint}    IN    @{values}" in keyword
    assert "Should Be Equal As Numbers    ${value}    ${expected_gpu_count}" in keyword
