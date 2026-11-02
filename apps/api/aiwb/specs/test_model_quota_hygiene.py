# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Static guards for catalog-sized GPU quota in model-driven scenarios."""

import re
from pathlib import Path

SPECS_DIR = Path(__file__).resolve().parent
MODEL_DRIVEN_SOURCES = (
    SPECS_DIR / "adapter_serving.robot",
    SPECS_DIR / "ai_gateway.robot",
    SPECS_DIR / "aims.robot",
    SPECS_DIR / "api_keys.robot",
    SPECS_DIR / "chat.robot",
    SPECS_DIR / "finetuning.robot",
    SPECS_DIR / "resources" / "aiwb_ai_gateway.resource",
    SPECS_DIR / "resources" / "aiwb_adapter_serving.resource",
    SPECS_DIR / "resources" / "aiwb_aims.resource",
    SPECS_DIR / "resources" / "aiwb_models.resource",
    SPECS_DIR / "resources" / "aims" / "api_keys.resource",
)
API_KEYS = SPECS_DIR / "api_keys.robot"
FINETUNING = SPECS_DIR / "finetuning.robot"
AIMS = SPECS_DIR / "aims.robot"
AIMS_RESOURCE = SPECS_DIR / "resources" / "aiwb_aims.resource"
ADAPTER_SERVING = SPECS_DIR / "adapter_serving.robot"
AI_GATEWAY = SPECS_DIR / "ai_gateway.robot"
AI_GATEWAY_RESOURCE = SPECS_DIR / "resources" / "aiwb_ai_gateway.resource"
API_KEY_AIMS_RESOURCE = SPECS_DIR / "resources" / "aims" / "api_keys.resource"
MODELS_RESOURCE = SPECS_DIR / "resources" / "aiwb_models.resource"

# A literal count, whether bare (gpu_count=2) or wrapped as a Robot number (gpu_count=${2}).
HARD_CODED_GPU_QUOTA = re.compile(r"gpu_count=\$?\{?\s*\d")


def _declares_variable(text: str, name: str) -> bool:
    """Whether the variables table declares ``name`` with a ${None} default.

    Matches on tokens rather than the table's column alignment, which robotidy and
    manual reformatting are both free to change without altering the declaration.
    """
    return re.search(rf"^{re.escape(name)}[ \t]+\$\{{None\}}[ \t]*$", text, re.MULTILINE) is not None


def _calls(text: str, keyword: str, *arguments: str) -> bool:
    """Whether ``keyword`` is called with ``arguments`` in order, ignoring column widths."""
    pattern = re.escape(keyword) + "".join(rf"[ \t]+{re.escape(argument)}" for argument in arguments)
    return re.search(pattern, text) is not None


def _robot_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.rstrip() == name), None)
    assert start is not None, f"Robot block {name!r} not found"
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def test_model_driven_sources_do_not_hard_code_gpu_quota():
    for source in MODEL_DRIVEN_SOURCES:
        assert not HARD_CODED_GPU_QUOTA.search(source.read_text()), (
            f"{source.name} must size quota to the selected model"
        )


def test_api_key_aim_scenarios_use_selected_model_gpu_quota():
    text = API_KEYS.read_text()

    for scenario in (
        "Access AIMS model without api key",
        "Assign multiple keys to single AIMS model",
    ):
        block = _robot_block(text, scenario)
        assert "the project has GPU quota available" in block
        assert "gpu_count=2" not in block


def test_gpu_quota_keyword_scales_all_selected_aim_resources():
    text = AIMS_RESOURCE.read_text()
    block = _robot_block(text, "The project has GPU quota available")
    helper = _robot_block(text, "Set project quota for model GPU count")

    assert "An AIM exists in system" in block
    assert _calls(block, "Set project quota for model GPU count", "${TEST_AIM_GPU_COUNT}")
    assert "Get Model Resource Quota" in helper
    assert "gpu_count=${gpu_count}" in helper
    assert "cpu_milli_cores=${cpu_milli_cores}" in helper
    assert "memory_bytes=${memory_bytes}" in helper
    assert "gpu_count=2" not in block


def test_planned_output_scenarios_use_selected_recipe_quota():
    text = FINETUNING.read_text()
    expectations = {
        "Running fine-tuning job reports its planned output": "the project has fine-tuning quota available",
        "Adapter fine-tuning job reports its planned output": "the project has adapter fine-tuning quota available",
    }

    for scenario, quota_step in expectations.items():
        block = _robot_block(text, scenario)
        assert quota_step in block
        assert "gpu_count=2" not in block


def test_finetuning_quota_keywords_scale_selected_recipe_resources():
    text = MODELS_RESOURCE.read_text()

    for keyword in (
        "The project has fine-tuning quota available",
        "The project has adapter fine-tuning quota available",
    ):
        block = _robot_block(text, keyword)
        assert "Get Model Resource Quota" in block
        assert "${TEST_FINETUNING_GPU_COUNT}" in block
        assert "gpu_count=${gpu_count}" in block
        assert "cpu_milli_cores=${cpu_milli_cores}" in block
        assert "memory_bytes=${memory_bytes}" in block


def test_full_finetuning_caches_one_selection_for_quota_and_submission():
    text = MODELS_RESOURCE.read_text()
    selector = _robot_block(text, "Get smallest finetunable catalog model")
    submit = _robot_block(text, "A finetune request is sent")

    assert _declares_variable(text, "${TEST_FINETUNING_BASE_MODEL}")
    assert _declares_variable(text, "${TEST_ADAPTER_RECIPE_NAME}")
    assert "${TEST_FINETUNING_BASE_MODEL}" in selector
    assert "Get smallest finetunable catalog model" in submit
    assert _calls(submit, "Finetune model", "${base_model_name}")


def test_gateway_selection_precedes_quota_and_carries_override_profile():
    gateway_suite = AI_GATEWAY.read_text()
    gateway_resource = AI_GATEWAY_RESOURCE.read_text()

    assert "the gateway project has GPU quota available" in gateway_suite
    quota = _robot_block(gateway_resource, "The gateway project has GPU quota available")
    selector = _robot_block(gateway_resource, "The smallest deployable AIM is selected")
    assert quota.index("The smallest deployable AIM is selected") < quota.index("Set project quota")
    assert "The pinned AIM override" in selector
    assert "${TEST_AIM_PROFILE_NAME}" in selector
    assert "${TEST_AIM_GPU_COUNT}" in selector


def test_pinned_aim_override_survives_an_unplaceable_catalog_lookup():
    override = _robot_block(AI_GATEWAY_RESOURCE.read_text(), "The pinned AIM override")

    assert "Get Deployable Aim Profile" in override
    # The override exists for clusters whose catalog cannot place the pinned model,
    # so the lookup it now performs must not be able to fail the gateway suite.
    assert "TRY" in override and "EXCEPT" in override
    assert override.index("Get Deployable Aim Profile") < override.index("EXCEPT")
    assert _calls(override, "VAR", "${profile_name}", "${None}")
    assert _calls(override, "VAR", "${gpu_count}", "${OVERRIDE_FALLBACK_GPU_COUNT}")
    # The handler must log a message built beforehand. Robot's "..." continues the cell
    # list, not the string, so a multi-cell message binds its tail to Log's level argument
    # and the handler raises instead of completing the fallback.
    handler = override[override.index("EXCEPT") :]
    assert re.search(r"^\s+Log[ \t]+\$\{\w+\}[ \t]+WARN[ \t]*$", handler, re.MULTILINE)


def test_selected_aim_profile_is_not_re_resolved_after_a_fallback():
    block = _robot_block(AIMS_RESOURCE.read_text(), "An AIM exists in system")

    # A selector that fell back leaves no profile but does set the GPU count, so gating
    # re-resolution on the profile alone would repeat the lookup the fallback absorbed —
    # here without a TRY/EXCEPT to catch it.
    assert "$profile_name is None and $gpu_count is None" in block
    assert block.index("$gpu_count is None") < block.index("Get Deployable Aim Profile")


def test_dual_aim_quota_sums_both_selected_models_before_second_deploy():
    aim_resource = AIMS_RESOURCE.read_text()
    block = _robot_block(API_KEY_AIMS_RESOURCE.read_text(), "A second AIM model is running")

    assert _declares_variable(aim_resource, "${TEST_AIM_PROFILE_NAME}")
    assert _declares_variable(aim_resource, "${TEST_AIM_GPU_COUNT}")
    assert _calls(block, "Evaluate", "int($saved_gpu_count) + int($aim_b_gpu_count)")
    assert block.index("Set project quota for model GPU count") < block.index("AIM is deployed and running")
    assert _calls(block, "VAR", "${TEST_AIM_PROFILE_NAME}", "${aim_b_profile_name}")


def test_runtime_override_and_adapter_flows_size_the_profile_actually_deployed():
    aims = AIMS.read_text()
    adapter = ADAPTER_SERVING.read_text()
    aim_resource = AIMS_RESOURCE.read_text()

    for scenario in (
        "Deploy AIM with runtime profile overrides persists on AIMService CR",
        "Deploy-time profile overrides reach the catalog AIM inference pod",
    ):
        assert "the project has runtime-override quota available" in _robot_block(aims, scenario)
    assert _calls(
        _robot_block(aim_resource, "The project has runtime-override quota available"),
        "Set project quota for model GPU count",
        "${2}",
    )
    for scenario in (
        "A deployment actually serves a compatible adapter",
        "Deploying with adapters left free to change onto hardware that can carry them is accepted",
    ):
        block = _robot_block(adapter, scenario)
        assert "the project has adapter-serving quota available" in block
        assert block.index("adapter-serving quota") < block.index("When ")
