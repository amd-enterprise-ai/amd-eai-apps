# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Static coverage for AIM undeploy assertions."""

from pathlib import Path

SPECS_DIR = Path(__file__).resolve().parent
AIMS_RESOURCE = SPECS_DIR / "resources" / "aiwb_aims.resource"
AIMS_API_RESOURCE = SPECS_DIR / "resources" / "api" / "aims.resource"


def _block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.rstrip() == name)
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_undeploy_assertion_addresses_the_deleted_workload_by_id() -> None:
    resource = AIMS_RESOURCE.read_text()
    keyword = _block(resource, "AIM should not have active workload deployment")
    check = _block(resource, "No active AIMService for AIM")

    assert "${resource_name}=${TEST_AIM_ID}" in keyword
    assert "Get AIM Service By ID    ${resource_name}" in check
    assert "${response.status_code}    404" in check
    assert "List AIM Services" not in keyword


def test_historical_lookup_polls_fresh_maximum_size_pages() -> None:
    resource = AIMS_RESOURCE.read_text()
    assertion = _block(resource, "Historical list should include the undeployed AIM")
    check = _block(resource, "Historical list contains the undeployed AIM")
    request_keyword = _block(resource, "Historical inference deployments are listed")

    assert "Wait Until Keyword Succeeds" in assertion
    assert "Historical list contains the undeployed AIM" in assertion
    assert "Historical inference deployments are listed" in check
    assert "status_filter=Deleted" in request_keyword
    assert "page_size=100" in request_keyword

    api_resource = AIMS_API_RESOURCE.read_text()
    request = _block(api_resource, "List AIM Services")
    assert "${page_size}=${None}" in request
    assert "pageSize=${page_size}" in request
