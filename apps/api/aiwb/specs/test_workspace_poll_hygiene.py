# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Guard against E2E paths that produce incomplete or oversized Robot results.

Long polls and high-frequency HTTP helpers can expand into millions of output.xml
nodes. A finite per-test timeout lets Robot fail stuck tests and close its output,
while live-flattened infrastructure keywords retain their own status and messages
without recording the repetitive child call tree.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

SPECS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SPECS_DIR.parents[3]
WORKSPACES_ROBOT = SPECS_DIR / "workspaces.robot"
SUITE_INIT = SPECS_DIR / "__init__.robot"
AIM_CATALOG = SPECS_DIR / "aim_catalog.robot"
AIM_CATALOG_GENERATOR = SPECS_DIR / "libraries" / "AimCatalogGenerator.py"
LIFECYCLE = REPO_ROOT / "testing" / "resources" / "common" / "resource_lifecycle.resource"
API_COMMON = REPO_ROOT / "testing" / "resources" / "api" / "common.resource"
API_ENDPOINTS = REPO_ROOT / "testing" / "resources" / "api" / "endpoints.resource"
AIMS_RESOURCE = SPECS_DIR / "resources" / "aiwb_aims.resource"
sys.path.insert(0, str(SPECS_DIR / "libraries"))

from AIMPodInspector import terminal_aim_pod_states  # noqa: E402


def _keyword_block(text: str, name: str) -> str:
    """Return the body of a Robot keyword (from its name line to the next keyword)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == name), None)
    assert start is not None, f"keyword {name!r} not found"
    body = []
    for ln in lines[start + 1 :]:
        # A new top-level keyword starts at column 0 (non-indented, non-blank).
        if ln and not ln[0].isspace():
            break
        body.append(ln)
    return "\n".join(body)


def test_comfyui_workspace_tests_are_tagged_for_exclusion():
    """All ComfyUI workspace tests must carry the `comfyui` tag so CI can exclude them.

    ComfyUI is skipped in CI (--exclude comfyui) until the fixed chart deploys; a
    ComfyUI test lacking the tag would slip back into the run and hang it.

    TODO: drop the exclusion once the fixed ai-workloads chart ships.
    """
    text = WORKSPACES_ROBOT.read_text()
    lines = text.splitlines()
    # Only scan the *** Test Cases *** section, and treat a line as a test-case name
    # only if it is at column 0 and is not a section header or a `...` continuation.
    start = next((i for i, ln in enumerate(lines) if ln.strip().lower().startswith("*** test cases")), None)
    assert start is not None, "workspaces.robot has no *** Test Cases *** section"
    found_comfyui_test = False
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if not ln.strip() or ln[0].isspace() or ln.startswith(("*", "...")):
            continue  # continuation, indented step, blank, or a new section header
        if "ComfyUI" in ln:
            found_comfyui_test = True
            tags_line = next((t for t in lines[i + 1 : i + 12] if t.strip().startswith("[Tags]")), None)
            assert tags_line and "comfyui" in tags_line, f"ComfyUI test {ln.strip()!r} must carry the comfyui tag"
    assert found_comfyui_test, "expected at least one ComfyUI workspace test"


def test_aim_wait_fails_fast_on_terminal_pod_state():
    """The AIM Running-wait must fail fast on terminal pod states, not wait out the bound.

    A broken image (ImagePullBackOff) leaves the AIMService at Pending, so without a
    pod-state check the wait would run the full deploy timeout and — when several
    workloads are broken — blow the robot --timeout and truncate the report.
    """
    text = AIMS_RESOURCE.read_text()
    wait_block = _keyword_block(text, "Wait for AIM workload to reach state")
    assert "AIM pods should not be in a terminal image or crash state" in wait_block, (
        "the AIM Running-wait loop must call the terminal-pod-state fail-fast check"
    )
    check_block = _keyword_block(text, "AIM pods should not be in a terminal image or crash state")
    # The keyword delegates to the Python library, which also resolves ReplicaSet
    # supersession so a superseded revision's pod cannot fail a recovering deploy.
    assert "AIM Pods Should Not Be In A Terminal State    ${name}    ${namespace}" in check_block
    assert "Evaluate" not in check_block
    # The wait must remain bounded (finite timeout), so a stuck deploy fails its own test.
    assert re.search(r"\$\{timeout\}=\d+", wait_block), "AIM wait must keep a finite default timeout"


@pytest.mark.parametrize("service_name", ["aim-service", "aim-service'\"\\name"])
def test_terminal_pod_state_lookup_treats_service_name_as_data(service_name):
    pod_list = {
        "items": [
            {
                "metadata": {"name": f"{service_name}-predictor-abc"},
                "status": {
                    "containerStatuses": [{"name": "inference", "state": {"waiting": {"reason": "ImagePullBackOff"}}}],
                    "initContainerStatuses": [
                        {"name": "storage", "state": {"waiting": {"reason": "ContainerCreating"}}}
                    ],
                },
            },
            {
                "metadata": {"name": "another-service-predictor-def"},
                "status": {
                    "containerStatuses": [{"name": "inference", "state": {"waiting": {"reason": "CrashLoopBackOff"}}}]
                },
            },
        ]
    }

    assert terminal_aim_pod_states(json.dumps(pod_list), service_name) == [
        f"{service_name}-predictor-abc/inference=ImagePullBackOff"
    ]


@pytest.mark.parametrize(
    ("reason", "status_field"),
    [
        ("ImagePullBackOff", "containerStatuses"),
        ("ErrImagePull", "containerStatuses"),
        ("InvalidImageName", "containerStatuses"),
        ("CrashLoopBackOff", "containerStatuses"),
        ("CreateContainerConfigError", "initContainerStatuses"),
    ],
)
def test_terminal_pod_state_lookup_preserves_all_terminal_reasons(reason, status_field):
    pod_list = {
        "items": [
            {
                "metadata": {"name": "aim-service-predictor-abc"},
                "status": {status_field: [{"name": "container", "state": {"waiting": {"reason": reason}}}]},
            }
        ]
    }

    assert terminal_aim_pod_states(json.dumps(pod_list), "aim-service") == [
        f"aim-service-predictor-abc/container={reason}"
    ]


def test_status_poll_does_not_bind_full_response_body():
    """The shared poll helpers must not bind the whole JSON body to a VAR (Robot logs VAR values)."""
    text = LIFECYCLE.read_text()
    for keyword in ("Verify Resource Status", "Resource Status Should Be One Of"):
        block = _keyword_block(text, keyword)
        assert "${response.json()}" not in block, (
            f"{keyword} must not bind the full response body to a variable in the poll helper"
        )
        assert re.search(r"VAR\s+\$\{data\}", block) is None, (
            f"{keyword} must not store the full body in a ${{data}} VAR"
        )
        # It should extract only the scalar status field.
        assert "get($status_field)" in block or "get(${status_field})" in block, (
            f"{keyword} should extract only the status field"
        )


def test_shared_http_infrastructure_is_flattened_in_live_results():
    """High-frequency request plumbing must not expand into millions of XML nodes."""
    for path, keywords in (
        (API_ENDPOINTS, ("Service API Endpoint",)),
        (
            API_COMMON,
            (
                "Create api session",
                "Safe Get Request",
                "Safe Post Request",
                "Safe Put Request",
                "Safe Delete Request",
                "Safe Patch Request",
            ),
        ),
    ):
        text = path.read_text()
        for keyword in keywords:
            block = _keyword_block(text, keyword)
            tags_line = next(
                (line for line in block.splitlines() if line.strip().startswith("[Tags]")),
                "",
            )
            assert "robot:flatten" in tags_line.split(), (
                f"{keyword} must use robot:flatten so its child call tree is not written to output.xml"
            )


def test_safe_http_wrappers_suppress_routine_request_payload_logs():
    """RequestsLibrary INFO bodies must not survive flattening and inflate output.xml."""
    text = API_COMMON.read_text()
    for keyword in (
        "Safe Get Request",
        "Safe Post Request",
        "Safe Put Request",
        "Safe Delete Request",
        "Safe Patch Request",
    ):
        block = _keyword_block(text, keyword)
        cells = [re.split(r"\s{2,}", line.strip()) for line in block.splitlines()]
        assert ["${old_log_level}=", "Set Log Level", "WARN"] in cells, (
            f"{keyword} must suppress RequestsLibrary's routine INFO payload logs"
        )
        assert ["Set Log Level", "${old_log_level}"] in cells, f"{keyword} must restore the caller's Robot log level"
        assert "FINALLY" in block, f"{keyword} must restore the log level even when the request fails"


def test_aiwb_tests_have_the_intended_timeouts():
    """Stuck tests must fail inside Robot, while catalog deploys keep their larger bound."""
    root_timeout = re.search(r"^Test Timeout\s+(\d+)\s+minutes\s*$", SUITE_INIT.read_text(), re.MULTILINE)
    assert root_timeout and root_timeout.group(1) == "60", (
        "the AIWB root suite must define Test Timeout as exactly 60 minutes"
    )

    catalog_timeout = re.search(r"^Test Timeout\s+(\d+)\s+minutes\s*$", AIM_CATALOG.read_text(), re.MULTILINE)
    assert catalog_timeout and catalog_timeout.group(1) == "100", (
        "the AIM catalog suite must retain its explicit 100-minute timeout"
    )

    generator = AIM_CATALOG_GENERATOR.read_text()
    assert 'TEST_TIMEOUT = "100 minutes"' in generator, (
        "the catalog generator must define the same timeout as the source suite"
    )
    assert generator.count("timeout=self.TEST_TIMEOUT") == 5, (
        "every dynamically generated catalog test must receive the 100-minute timeout"
    )
