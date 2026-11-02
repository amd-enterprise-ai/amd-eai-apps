# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Executable behavioral regression tests for ChatAssertions.

These exercise the actual instruction-following contract the AIM catalog/chat
smoke probes rely on: they must fail whenever that behavior regresses, not
merely when some literal text in the .resource file changes.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from ChatAssertions import (
    _REASONING_FAMILIES,
    assert_reasoning_suppressed,
    chat_answer_content,
    chat_support_from_tags,
    reasoning_controls,
    reasoning_request_fields,
)

_LIBRARIES_DIR = Path(__file__).parent / "libraries"


def test_reasoning_suppressed_passes_when_reasoning_key_absent():
    assert_reasoning_suppressed({"content": "Hello!"})


def test_reasoning_suppressed_passes_when_reasoning_is_none():
    assert_reasoning_suppressed({"content": "Hello!", "reasoning": None})


def test_reasoning_suppressed_passes_when_reasoning_is_blank():
    assert_reasoning_suppressed({"content": "Hello!", "reasoning": "   "})


def test_reasoning_suppressed_fails_when_reasoning_field_leaks():
    # A reasoning-off control was sent, but nothing proved the model/template
    # actually honored it: message.reasoning still carries output.
    with pytest.raises(AssertionError, match="reasoning-off control was not honored"):
        assert_reasoning_suppressed({"content": "Hello!", "reasoning": "Let me think about how to greet this user..."})


def test_reasoning_suppressed_allows_reasoning_field_when_family_cannot_suppress():
    # GPT-OSS always emits its analysis channel; the probe asked it for minimal
    # effort, not for silence, so a populated reasoning field is not a defect.
    # Demanding an empty one asserts a contract the model never agreed to.
    assert_reasoning_suppressed(
        {"content": "Hello.", "reasoning": "User says 'Say hello and stop'. Probably just output 'Hello.'"},
        supports_suppression=False,
    )


def test_reasoning_suppressed_still_rejects_inline_leak_when_family_cannot_suppress():
    # Relaxing the reasoning field does not relax the final answer: reasoning
    # wrapped in tags inside content is never a valid answer, for any family.
    with pytest.raises(AssertionError, match="inline reasoning marker"):
        assert_reasoning_suppressed({"content": "<think>hmm</think>Hello!"}, supports_suppression=False)


def test_reasoning_suppressed_fails_when_reasoning_leaks_inline_in_content():
    # A template can honor enable_thinking=false by never populating the
    # separate `reasoning` field at all, yet still leave the reasoning pass
    # wrapped in tags inside `content`. A reasoning-field-only check would
    # miss this; content must be inspected too.
    with pytest.raises(AssertionError, match="inline reasoning marker"):
        assert_reasoning_suppressed({"content": "<think>let me consider this</think>Hello!"})


def test_reasoning_suppressed_fails_when_content_has_thinking_tag_variant():
    with pytest.raises(AssertionError, match="inline reasoning marker"):
        assert_reasoning_suppressed({"content": "<Thinking>hmm</Thinking> Hello!"})


@pytest.mark.parametrize(
    "content",
    [
        "let me consider this</think>Hello!",
        "let me consider this</thinking>Hello!",
        "let me consider this</reasoning>Hello!",
        "let me consider this[/think]Hello!",
    ],
)
def test_reasoning_suppressed_fails_on_a_closing_delimiter_with_no_opening_one(content):
    # The realistic R1-style leak carries no opening tag at all. Those templates put
    # `<think>` in the prompt as a generation prefix, so the model's own output is
    # `...reasoning...</think>answer`; with no reasoning parser configured that whole
    # string lands in content and the opening tag is never in it. Scanning only for
    # opening delimiters passes such a response silently, and then Chat Answer Content
    # hands the reasoning trace back as the final answer.
    #
    # This is the sole guard for the families it matters most for: deepseek-r1 and
    # gpt-oss are mapped supports_suppression=False, which switches the reasoning-field
    # half of this assertion off entirely.
    with pytest.raises(AssertionError, match="inline reasoning marker"):
        assert_reasoning_suppressed({"content": content})


def test_reasoning_suppressed_fails_when_the_leak_uses_the_reasoning_content_spelling():
    # vLLM's --reasoning-parser populates `reasoning_content`, not `reasoning`.
    # Reading only one spelling would let the assertion pass on the good path -
    # trace cleanly separated out of content - whether or not the control was
    # honored, which is exactly the inert proof this PR exists to remove.
    with pytest.raises(AssertionError, match="message.reasoning_content was not empty"):
        assert_reasoning_suppressed({"content": "Hello!", "reasoning_content": "Let me think about the greeting..."})


def test_reasoning_suppressed_allows_reasoning_content_when_family_cannot_suppress():
    # The relaxation must follow the family, not the spelling of the field.
    assert_reasoning_suppressed(
        {"content": "Hello.", "reasoning_content": "User says 'Say hello and stop'."},
        supports_suppression=False,
    )


def test_reasoning_suppressed_fails_deterministically_when_reasoning_content_is_not_a_string():
    # Both spellings get the same type guard; a malformed one must not slip
    # through just because the other spelling was absent or blank.
    with pytest.raises(AssertionError, match="message.reasoning_content must be a string or null"):
        assert_reasoning_suppressed({"content": "Hello!", "reasoning_content": {"unexpected": "shape"}})


def test_reasoning_suppressed_type_checks_every_spelling_even_after_finding_a_leak():
    # `reasoning` already carries a leak, but `reasoning_content` is malformed.
    # An early return on the first populated field would skip that guard and
    # report a leak while a malformed sibling went unmentioned.
    with pytest.raises(AssertionError, match="message.reasoning_content must be a string or null"):
        assert_reasoning_suppressed({"content": "Hello!", "reasoning": "thinking", "reasoning_content": 42})


def test_reasoning_suppressed_fails_on_harmony_analysis_channel_leaking_into_content():
    # Harmony (gpt-oss) does not use <think> at all, and gpt-oss is exempt from
    # the reasoning-field check because it has no off-switch. Without this
    # marker there is no realistic gpt-oss response the assertion could fail
    # on, so it would be an inert call for a default smoke model.
    _, supports_suppression = reasoning_controls("openai/gpt-oss-20b")
    assert supports_suppression is False

    with pytest.raises(AssertionError, match="inline reasoning marker"):
        assert_reasoning_suppressed(
            {"content": "<|channel|>analysis<|message|>user greeted me<|end|>Hello."},
            supports_suppression=supports_suppression,
        )


def test_reasoning_suppressed_fails_on_bracket_style_reasoning_delimiter():
    with pytest.raises(AssertionError, match="inline reasoning marker"):
        assert_reasoning_suppressed({"content": "[THINK]let me consider[/THINK] Hello!"})


def test_reasoning_suppressed_fails_deterministically_when_reasoning_is_not_a_string():
    # A malformed response could put a non-string value (e.g. a dict/number)
    # in message.reasoning; that must fail with an actionable AssertionError,
    # not an unrelated AttributeError from calling .strip() on the wrong type.
    with pytest.raises(AssertionError, match="message.reasoning must be a string or null"):
        assert_reasoning_suppressed({"content": "Hello!", "reasoning": {"unexpected": "shape"}})


def test_reasoning_suppressed_fails_deterministically_when_content_is_not_a_string():
    with pytest.raises(AssertionError, match="message.content must be a string or null"):
        assert_reasoning_suppressed({"content": 42})


def test_reasoning_suppressed_survives_python_dash_o():
    # `assert` statements are compiled out entirely under `python -O`, which
    # would silently let a reasoning leak pass. The check must be written as
    # an explicit `raise AssertionError`, which -O cannot strip; run it in a
    # real -O subprocess to prove that, not just read the source.
    script = (
        f"import sys; sys.path.insert(0, {str(_LIBRARIES_DIR)!r}); "
        "from ChatAssertions import assert_reasoning_suppressed; "
        "assert_reasoning_suppressed({'content': 'Hello!', 'reasoning': 'leaked reasoning'})"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "assert_reasoning_suppressed must still raise under python -O"
    assert "reasoning-off control was not honored" in result.stderr


def test_reasoning_controls_use_top_level_low_effort_for_gpt_oss():
    request_fields, supports_suppression = reasoning_controls("openai/gpt-oss-20b")

    assert request_fields == {"reasoning_effort": "low"}
    assert "chat_template_kwargs" not in request_fields
    assert supports_suppression is False


def test_reasoning_controls_recognize_gpt_oss_in_served_model_path():
    request_fields, supports_suppression = reasoning_controls("/models/openai/gpt-oss-120b")

    assert request_fields == {"reasoning_effort": "low"}
    assert supports_suppression is False


def test_reasoning_controls_disable_thinking_for_other_families():
    request_fields, supports_suppression = reasoning_controls("meta-llama/Llama-3.2-1B-Instruct")

    assert request_fields == {"chat_template_kwargs": {"enable_thinking": False}}
    assert supports_suppression is True


@pytest.mark.parametrize(
    "model_id",
    [
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-R1-0528",
        "/models/ghcr.io/silogen/aim-deepseek-ai-deepseek-r1",
    ],
)
def test_reasoning_controls_send_no_control_for_deepseek_r1(model_id):
    # R1's chat template opens a reasoning block unconditionally and declares no
    # kwarg to stop it. Sending enable_thinking would be the same borrowed-knob
    # mistake that broke the gpt-oss probe, so the probe sends nothing and does
    # not demand an empty reasoning field.
    request_fields, supports_suppression = reasoning_controls(model_id)

    assert request_fields == {}
    assert supports_suppression is False


@pytest.mark.parametrize(
    "model_id",
    [
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3.1-Terminus",
        "ghcr.io/silogen/aim-deepseek-ai-deepseek-v3-1",
        "ghcr.io/silogen/aim-deepseek-ai-deepseek-v3-1-terminus",
    ],
)
def test_reasoning_controls_use_thinking_kwarg_for_deepseek_v31(model_id):
    # V3.1 gates its reasoning pass on a kwarg named "thinking", not
    # "enable_thinking". Both the HuggingFace spelling (v3.1) and the image
    # spelling (v3-1) reach the same family entry. Unlike gpt-oss and R1,
    # thinking=false is a real off-switch (the template closes the reasoning
    # block in the prompt), so this family still owes proof it was honored.
    request_fields, supports_suppression = reasoning_controls(model_id)

    assert request_fields == {"chat_template_kwargs": {"thinking": False}}
    assert supports_suppression is True


def test_reasoning_controls_do_not_match_non_reasoning_deepseek_v3():
    # Plain V3 is not a reasoning model and must not be captured by the V3.1 entry.
    request_fields, supports_suppression = reasoning_controls("deepseek-ai/DeepSeek-V3")

    assert request_fields == {"chat_template_kwargs": {"enable_thinking": False}}
    assert supports_suppression is True


@pytest.mark.parametrize(
    "model_id",
    [
        "MiniMaxAI/MiniMax-M3",
        "docker.io/silogenai/aim-instinct-minimaxai-minimax-m3",
    ],
)
def test_reasoning_controls_use_thinking_mode_kwarg_for_minimax_m3(model_id):
    # M3's template reads "thinking_mode", never "enable_thinking", and defaults to
    # letting the model choose when the variable is unset - so the default control is
    # a no-op and reasoning comes back populated. "disabled" is a true off-switch
    # (the template closes the reasoning block in the prompt), so the family stays on
    # the strict path and still owes proof it was honored.
    request_fields, supports_suppression = reasoning_controls(model_id)

    assert request_fields == {"chat_template_kwargs": {"thinking_mode": "disabled"}}
    assert supports_suppression is True


def test_reasoning_controls_do_not_claim_a_control_for_unprobed_minimax_siblings():
    # The key is scoped to m3 because only M3's template has been read. A sibling must
    # fall through to the default rather than silently inherit a control nobody probed.
    request_fields, _ = reasoning_controls("MiniMaxAI/MiniMax-M2")

    assert request_fields == {"chat_template_kwargs": {"enable_thinking": False}}


def test_reasoning_controls_keep_strict_default_for_qwen3():
    # Qwen3 is the family that actually declares enable_thinking, so it must stay
    # on the strict path and still owe proof that suppression was honored.
    request_fields, supports_suppression = reasoning_controls("Qwen/Qwen3-32B")

    assert request_fields == {"chat_template_kwargs": {"enable_thinking": False}}
    assert supports_suppression is True


def test_reasoning_family_table_lists_specific_entries_before_their_prefixes():
    # The table documents that the first substring found in the served model id
    # wins. If an earlier entry is a substring of a later one, the later entry
    # can never be reached. No current pair violates this, so assert it
    # structurally over the real table rather than on a hand-built example -
    # otherwise a future entry could break the invariant undetected.
    families = [family for family, _, _ in _REASONING_FAMILIES]
    for index, earlier in enumerate(families):
        for later in families[index + 1 :]:
            assert earlier not in later, (
                f"{earlier!r} is listed before {later!r} and is a substring of it, so {later!r} can never "
                f"match - the more specific family must come first"
            )


def test_reasoning_controls_fail_deterministically_when_model_id_is_not_a_string():
    # Same fail-loud discipline the response fields get: a non-string model id
    # must not raise a bare AttributeError from .strip().
    with pytest.raises(AssertionError, match="model_id must be a string"):
        reasoning_controls(None)


def test_unsuppressed_reasoning_failure_names_the_family_table():
    # The failure must point at the real fix (add the family to the table) rather
    # than tempting the next reader to relax the check for every model.
    with pytest.raises(AssertionError, match="_REASONING_FAMILIES"):
        assert_reasoning_suppressed({"content": "Hello!", "reasoning": "thinking hard"})


def test_leak_diagnostic_does_not_name_a_control_the_family_never_sent():
    # The assertion sees only the response, so it cannot know which control was
    # requested. V3.1 sends thinking=false and is already in the table, so a
    # message blaming enable_thinking=false and telling the reader to add the
    # family would send them hunting a bug that is not there. Composed over both
    # functions, because the mismatch only exists once a family maps to a control
    # other than the default.
    request_fields, supports_suppression = reasoning_controls("deepseek-ai/DeepSeek-V3.1")
    assert request_fields == {"chat_template_kwargs": {"thinking": False}}

    with pytest.raises(AssertionError) as excinfo:
        assert_reasoning_suppressed(
            {"content": "Hello.", "reasoning": "Let me work through the greeting..."},
            supports_suppression=supports_suppression,
        )

    diagnostic = str(excinfo.value)
    assert "enable_thinking" not in diagnostic, "must not blame a kwarg this family never sent"
    assert "add the family" not in diagnostic, "V3.1 is already mapped; do not send the reader to add it"
    assert "_REASONING_FAMILIES" in diagnostic, "must still point at the mapping to verify"


def test_deepseek_v31_leaked_reasoning_fails_while_gpt_oss_and_r1_stay_exempt():
    # End-to-end over the pair of functions the probe actually composes: whether a
    # leak fails must follow from the family, not from a flag a caller hand-picked.
    # V3.1 requested a documented off-switch, so a populated reasoning field means
    # the control did not take effect - that is a real defect and must fail.
    _, v31_supports_suppression = reasoning_controls("deepseek-ai/DeepSeek-V3.1")
    with pytest.raises(AssertionError, match="message.reasoning was not empty"):
        assert_reasoning_suppressed(
            {"content": "Hello.", "reasoning": "Let me work through the greeting..."},
            supports_suppression=v31_supports_suppression,
        )

    # gpt-oss and R1 have no off-switch to honor, so the same populated field is
    # not a defect and must still pass.
    for model_id in ("openai/gpt-oss-20b", "deepseek-ai/DeepSeek-R1"):
        _, supports_suppression = reasoning_controls(model_id)
        assert_reasoning_suppressed(
            {"content": "Hello.", "reasoning": "Let me work through the greeting..."},
            supports_suppression=supports_suppression,
        )


def test_reasoning_request_fields_returns_only_the_request_fields():
    assert reasoning_request_fields("openai/gpt-oss-20b") == {"reasoning_effort": "low"}
    assert reasoning_request_fields("meta-llama/Llama-3.2-1B-Instruct") == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_reasoning_request_fields_return_fresh_nested_dicts():
    first = reasoning_request_fields("deepseek-ai/DeepSeek-V3.1")
    first["chat_template_kwargs"]["thinking"] = True

    assert reasoning_request_fields("deepseek-ai/DeepSeek-V3.1") == {"chat_template_kwargs": {"thinking": False}}


def test_reasoning_controls_return_fresh_nested_dicts():
    first, _ = reasoning_controls("meta-llama/Llama-3.2-1B-Instruct")
    first["chat_template_kwargs"]["enable_thinking"] = True

    second, _ = reasoning_controls("meta-llama/Llama-3.2-1B-Instruct")
    assert second == {"chat_template_kwargs": {"enable_thinking": False}}


def test_chat_answer_content_returns_stripped_content():
    assert chat_answer_content({"content": "  Hello there!  "}) == "Hello there!"


def test_chat_answer_content_fails_when_content_is_null():
    # Reasoning-only responses (message.content=null) must never satisfy
    # instruction-following, even if message.reasoning contains "hello".
    with pytest.raises(AssertionError, match="must not be null"):
        chat_answer_content({"content": None, "reasoning": "hello, here is my internal reasoning"})


def test_chat_answer_content_fails_when_content_key_absent():
    with pytest.raises(AssertionError, match="must not be null"):
        chat_answer_content({"reasoning": "hello, here is my internal reasoning"})


def test_chat_answer_content_fails_when_content_is_empty_string():
    with pytest.raises(AssertionError, match="must not be empty"):
        chat_answer_content({"content": ""})


def test_chat_answer_content_fails_when_content_is_only_whitespace():
    with pytest.raises(AssertionError, match="must not be empty"):
        chat_answer_content({"content": "   "})


def test_chat_answer_content_fails_deterministically_when_content_is_not_a_string():
    # A malformed response could put a non-string value (e.g. a list/number)
    # in message.content; that must fail with an actionable AssertionError,
    # not an unrelated AttributeError from calling .strip() on the wrong type.
    with pytest.raises(AssertionError, match="message.content must be a string or null"):
        chat_answer_content({"content": ["unexpected", "shape"]})


def test_chat_answer_content_survives_python_dash_o():
    # Same -O hazard as assert_reasoning_suppressed: the null-content check
    # must be an explicit raise, not a bare `assert`, or it silently
    # disappears under optimized Python.
    script = (
        f"import sys; sys.path.insert(0, {str(_LIBRARIES_DIR)!r}); "
        "from ChatAssertions import chat_answer_content; "
        "chat_answer_content({'content': None})"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "chat_answer_content must still raise under python -O"
    assert "must not be null" in result.stderr


def test_chat_support_true_when_chat_tag_present():
    supports_chat, tags_missing, near_miss = chat_support_from_tags(
        {"tags": ["instruct", "chat"]}, {"com.amd.aim.model.tags": "instruct,chat"}
    )
    assert supports_chat is True
    assert tags_missing is False
    assert near_miss is False


@pytest.mark.parametrize("tag", [" chat ", "Chat", "CHAT", "chat\t"])
def test_chat_support_follows_the_platform_and_reports_a_near_miss(tag):
    # The platform's predicate is exact: is_chattable in app/aims/gateway.py is
    # `CHAT_TAG_VALUE in ...model.tags` with CHAT_TAG_VALUE == "chat", and nothing
    # normalizes the list on the way in. A probe that lowercased or stripped would
    # chat-probe an AIM the platform does not list as chattable, report it green,
    # and hide a user-visible defect - so supports_chat must be False here.
    #
    # But silently classifying it non-chat would trade one silence for another:
    # tags_missing describes the *label*, which is present, so nothing would say
    # why the chat endpoint went untested. near_miss is that signal.
    supports_chat, tags_missing, near_miss = chat_support_from_tags({"tags": [tag]}, {"com.amd.aim.model.tags": tag})
    assert supports_chat is False, "the probe must not classify more generously than the platform"
    assert tags_missing is False
    assert near_miss is True, "a tag that only matches after normalizing must be reported, not absorbed"


def test_chat_support_reports_no_near_miss_for_an_ordinary_non_chat_tag():
    # near_miss must mean "this meant chat and the platform will not read it that
    # way", not "this is not chat" - otherwise it is noise on every base model.
    _, _, near_miss = chat_support_from_tags({"tags": ["completion"]}, {"com.amd.aim.model.tags": "completion"})
    assert near_miss is False


def test_chat_support_reports_no_near_miss_when_an_exact_chat_tag_is_also_present():
    # An exactly-spelled tag already satisfies the platform, so a sloppy duplicate
    # alongside it changes nothing the caller needs to act on.
    supports_chat, _, near_miss = chat_support_from_tags(
        {"tags": ["chat", "Chat"]}, {"com.amd.aim.model.tags": "chat,Chat"}
    )
    assert supports_chat is True
    assert near_miss is False


def test_chat_support_false_when_tags_present_without_chat():
    supports_chat, tags_missing, _ = chat_support_from_tags(
        {"tags": ["completion", "base"]}, {"com.amd.aim.model.tags": "completion,base"}
    )
    assert supports_chat is False
    assert tags_missing is False


def test_chat_support_false_and_not_missing_when_label_present_but_empty():
    # The label was recorded with an empty value: a deliberate classification,
    # distinct from the label never having been attached to the image.
    supports_chat, tags_missing, _ = chat_support_from_tags({"tags": []}, {"com.amd.aim.model.tags": ""})
    assert supports_chat is False
    assert tags_missing is False


def test_chat_support_false_and_missing_when_label_absent_from_original_labels():
    # This is the metadata-migration gap the harness must not mask: aim-engine
    # never recorded the com.amd.aim.model.tags label on this image, so we
    # cannot claim to know this model isn't a chat model. The structured
    # model_metadata dict alone can't reveal this (its "tags" field is
    # defaulted to [] by the API schema either way); original_labels can.
    supports_chat, tags_missing, _ = chat_support_from_tags({"tags": []}, {"some.other.label": "x"})
    assert supports_chat is False
    assert tags_missing is True


def test_chat_support_missing_when_original_labels_is_empty():
    supports_chat, tags_missing, _ = chat_support_from_tags({}, {})
    assert supports_chat is False
    assert tags_missing is True


def test_chat_support_fails_deterministically_when_original_labels_is_not_a_dict():
    # Same guard the string fields get: a malformed response must raise an
    # actionable AssertionError, not a TypeError from the membership test.
    with pytest.raises(AssertionError, match="original_labels must be a dict"):
        chat_support_from_tags({"tags": []}, "com.amd.aim.model.tags=chat")


def test_chat_support_fails_deterministically_when_model_metadata_is_not_a_dict():
    with pytest.raises(AssertionError, match="model_metadata must be a dict"):
        chat_support_from_tags(["chat"], {"com.amd.aim.model.tags": "chat"})


def test_chat_support_fails_deterministically_when_tags_is_a_string():
    # A bare string would iterate as characters, so "chat" in tags is False and
    # the AIM is quietly misclassified as a non-chat model - the probe then
    # skips the chat endpoint with no signal that anything was wrong.
    with pytest.raises(AssertionError, match="model_metadata.tags must be a list"):
        chat_support_from_tags({"tags": "chat"}, {"com.amd.aim.model.tags": "chat"})


@pytest.mark.parametrize("malformed", [None, "", {}, 0, set()])
def test_chat_support_fails_deterministically_when_tags_is_falsey_but_not_a_list(malformed):
    # These are the malformed values a truthiness default would swallow. They
    # must fail exactly like the truthy non-list values above: the label IS
    # present, so tags_missing would be False and the caller would log no
    # warning - the AIM is silently reported as a non-chat model.
    with pytest.raises(AssertionError, match="model_metadata.tags must be a list"):
        chat_support_from_tags({"tags": malformed}, {"com.amd.aim.model.tags": "chat"})


def test_chat_support_defaults_only_when_tags_key_is_absent():
    # The one case a default is legitimate: an older payload with no tags key
    # at all. It must still be distinguishable from a malformed value.
    supports_chat, tags_missing, _ = chat_support_from_tags({}, {"com.amd.aim.model.tags": ""})

    assert supports_chat is False
    assert tags_missing is False


@pytest.mark.parametrize("malformed", [None, True, 1, ["chat"], {"chat": 1}])
def test_chat_support_fails_deterministically_when_a_tag_element_is_not_a_string(malformed):
    # str() would manufacture valid-looking tags from malformed input: None
    # becomes "none" and ["chat"] becomes "['chat']". The schema declares
    # list[str], so anything else is a malformed response, not a tag.
    with pytest.raises(AssertionError, match="model_metadata.tags entries must be strings"):
        chat_support_from_tags({"tags": [malformed]}, {})


def test_chat_support_rejects_a_non_string_tag_even_when_chat_is_present():
    # The malformed element must fail even though a valid "chat" tag would
    # otherwise satisfy the lookup - a partially malformed list is still a
    # malformed response, and silently honoring it hides the defect.
    with pytest.raises(AssertionError, match="model_metadata.tags entries must be strings"):
        chat_support_from_tags({"tags": ["chat", None]}, {"com.amd.aim.model.tags": "chat"})


@pytest.mark.parametrize("malformed", [None, "a string", ["a", "list"], 0])
def test_chat_answer_content_fails_deterministically_when_message_is_not_a_dict(malformed):
    # message is externally derived like every other argument in this module, so a
    # malformed envelope such as {"message": null} must name the offending field rather
    # than surface an AttributeError from calling .get() on the wrong type.
    with pytest.raises(AssertionError, match="message must be a dict"):
        chat_answer_content(malformed)


@pytest.mark.parametrize("malformed", [None, "a string", ["a", "list"], 0])
def test_assert_reasoning_suppressed_fails_deterministically_when_message_is_not_a_dict(malformed):
    with pytest.raises(AssertionError, match="message must be a dict"):
        assert_reasoning_suppressed(malformed)


def test_message_dict_guard_survives_optimized_bytecode():
    # Same -O hazard as the checks above: an explicit raise, not a bare `assert`,
    # or the guard disappears under optimized Python exactly when a malformed
    # response would otherwise surface as an AttributeError.
    script = (
        f"import sys; sys.path.insert(0, {str(_LIBRARIES_DIR)!r}); "
        "from ChatAssertions import chat_answer_content; "
        "chat_answer_content(None)"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "the message guard must still raise under python -O"
    assert "message must be a dict" in result.stderr
