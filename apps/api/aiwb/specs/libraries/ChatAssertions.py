# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Behavioral assertions for AIM catalog/chat smoke probes.

Kept in Python (not Robot ``Evaluate`` one-liners in a .resource file) so the
instruction-following contract these probes rely on is covered by executable
pytest regression tests instead of a static source-text check that a refactor
could silently break while still leaving the actual behavior broken.

The contract:
  - a probe must hold back the reasoning pass with the control the model's own
    family honors, not with one borrowed from another family;
  - a probe that asks a family to suppress reasoning outright must then prove
    the request was honored, rather than hope it was. A family that offers no
    off-switch, only an effort level, cannot owe that proof;
  - reasoning must never leak inline into ``message.content`` - wrapped in a
    delimiter like ``<think>...</think>``, or in Harmony's analysis channel -
    for any family. A separate reasoning field is the only acceptable place
    for it;
  - a reasoning-only or null ``message.content`` must never be accepted as a
    passing instruction-following answer;
  - the ``com.amd.aim.model.tags`` label being entirely absent from an image
    (a migration gap) must be distinguishable from the label being present but
    simply omitting "chat", so a harness that silently probes
    ``/v1/completions`` in the first case doesn't mask an untested chat
    endpoint behind an ordinary, deliberate "not a chat model" classification.
"""

import copy

# A reasoning trace that leaks into `content` instead of the separate reasoning
# field is wrapped in one of these delimiters. When a reasoning-off control is
# only partially honored, a template can skip the reasoning field entirely and
# leave the trace inline in `content` instead - a plain "is the reasoning field
# blank" check does not catch that leak. Matched case-insensitively.
#
#   <think>/<thinking>/<reasoning>  DeepSeek-R1, Qwen3 and GLM-style templates.
#   [think]                         Mistral/Magistral-style bracket delimiters.
#   <|channel|>analysis             Harmony (gpt-oss). Harmony does not use
#                                   <think> at all, and gpt-oss is exempt from
#                                   the reasoning-field check below because it
#                                   has no off-switch - so without this marker
#                                   there is no realistic gpt-oss response this
#                                   assertion could fail on, and it would be an
#                                   inert call for a default smoke model.
#
# Both spellings of each delimiter, because a leak need not carry the opening one.
# R1-style templates put the opening <think> in the prompt as a generation prefix,
# so the model's own output is `...reasoning...</think>answer` - with no reasoning
# parser configured, that whole string lands in `content` and the only delimiter
# present is the closing tag. The families that leak this way, deepseek-r1 and
# gpt-oss, are exactly the ones mapped supports_suppression=False, so this scan is
# the sole guard for them.
_INLINE_REASONING_MARKERS = (
    "<think>",
    "</think>",
    "<thinking>",
    "</thinking>",
    "<reasoning>",
    "</reasoning>",
    "[think]",
    "[/think]",
    "<|channel|>analysis",
)

# The separate reasoning field goes by two spellings in OpenAI-compatible chat
# responses: vLLM's --reasoning-parser populates `reasoning_content` (the
# spelling DeepSeek's own API uses), while the OpenRouter/OpenAI-Responses style
# is `reasoning`. Which one a given AIM image returns depends on its serving
# stack, so a probe that reads only one spelling silently passes whenever the
# other is the field carrying the trace - the assertion would never fire on the
# good path, and could not tell a honored control from an ignored one.
_REASONING_FIELDS = ("reasoning", "reasoning_content")

# Mirrors CHAT_TAG_VALUE in app/aims/constants.py. The probe must classify on the
# same literal the platform does; if that value ever changes, this is the one place
# the harness has to follow it.
_CHAT_TAG = "chat"

# Reasoning families that do not honor ``enable_thinking``, each mapped to the
# request fields that hold reasoning back as far as that family allows and to
# whether that control is a true off-switch (so an empty ``message.reasoning``
# may be demanded as proof it took effect). Ordered: the first substring found in
# the served model id wins, so a longer, more specific family must precede any
# prefix of itself.
#
#   gpt-oss        Harmony format, trained with CoT-RL. Always emits an analysis
#                  channel; there is no off-switch, only a reasoning effort of
#                  low/medium/high. reasoning_effort is a top-level OpenAI request
#                  field, not a chat-template kwarg. Nothing to prove.
#   deepseek-r1    Its chat template opens a reasoning block unconditionally and
#                  declares no kwarg to stop it, so there is no control to send.
#                  Matches the -0528 revision too. Nothing to prove.
#   deepseek-v3.1  Hybrid thinking model whose template gates the reasoning pass on
#                  a kwarg named "thinking", not "enable_thinking". thinking=false
#                  is a real off-switch - the template then closes the reasoning
#                  block in the prompt itself - so this family stays on the strict
#                  path and must return an empty reasoning field. Both the
#                  HuggingFace spelling (v3.1) and the image spelling (v3-1) appear
#                  as served ids, and each also matches the -terminus revision.
#   minimax-m3     Its template reads a variable named "thinking_mode" taking
#                  enabled/disabled/adaptive, and defaults to "adaptive" - the model
#                  decides for itself - whenever the variable is unset. enable_thinking
#                  is never read, and vLLM silently drops undeclared chat-template
#                  kwargs, so the default control is a no-op here. thinking_mode
#                  "disabled" is a real off-switch: the template both instructs the
#                  system message not to think and emits the think-end token as a
#                  generation prefix, closing the reasoning block in the prompt the
#                  way deepseek-v3.1 does. Keyed to m3 rather than bare "minimax"
#                  because only M3's template has been read; a sibling gets its own
#                  entry once it is actually probed.
# One family, two spellings: the HuggingFace name carries a dot, the image tag a
# dash. Both rows share this literal so a future change to the control cannot be
# applied to one spelling and silently miss the other.
_DEEPSEEK_V31_CONTROLS = {"chat_template_kwargs": {"thinking": False}}

_REASONING_FAMILIES: tuple[tuple[str, dict, bool], ...] = (
    ("gpt-oss", {"reasoning_effort": "low"}, False),
    ("deepseek-r1", {}, False),
    ("deepseek-v3.1", _DEEPSEEK_V31_CONTROLS, True),
    ("deepseek-v3-1", _DEEPSEEK_V31_CONTROLS, True),
    ("minimax-m3", {"chat_template_kwargs": {"thinking_mode": "disabled"}}, True),
)

# Every other family: ask the chat template to skip the reasoning pass outright,
# and hold it to that.
_DEFAULT_CONTROLS: tuple[dict, bool] = ({"chat_template_kwargs": {"enable_thinking": False}}, True)


def _require_optional_str(value: object, field_name: str) -> str | None:
    """Return ``value`` if it is a string or ``None``, else raise deterministically.

    Guards every ``.strip()``/``.lower()`` call below: a non-string value
    (e.g. a stray number or dict from a malformed response) must fail with an
    actionable ``AssertionError``, not an opaque ``AttributeError`` from
    calling a string method on the wrong type.
    """
    if value is not None and not isinstance(value, str):
        raise AssertionError(f"{field_name} must be a string or null, got {type(value).__name__}: {value!r}")
    return value


def _require_dict(value: object, field_name: str) -> dict:
    """Return ``value`` if it is a dict, else raise deterministically.

    Guards every ``.get()`` below for the same reason the string check above
    exists: a malformed response that puts ``null`` or a list where an object
    belongs must name the offending field, not surface an ``AttributeError``
    from calling a dict method on it.
    """
    if not isinstance(value, dict):
        raise AssertionError(f"{field_name} must be a dict, got {type(value).__name__}: {value!r}")
    return value


def _model_tags(model_metadata: dict) -> list[str]:
    """Return ``model_metadata.tags`` verbatim, or raise deterministically.

    Verbatim, because the platform reads it verbatim: ``is_chattable`` in
    ``app/aims/gateway.py`` is ``CHAT_TAG_VALUE in ...model.tags`` against
    ``CHAT_TAG_VALUE = "chat"``, and nothing on the ingest path normalizes the
    list (``AIMModelMetadata.tags`` is a plain ``list[str]``). A probe that
    lowercased or stripped here would classify an AIM the platform does not,
    and the AIM would be chat-probed green while users cannot discover it as
    chattable at all. See ``chat_support_from_tags`` for how the near miss is
    reported instead of absorbed.

    ``AIMModelMetadata.tags: list[str] = Field(default_factory=list)`` always
    serializes, so a conforming response carries a genuine list and never omits
    the key. The absent-key branch is therefore tolerance for a caller passing
    a hand-built or trimmed dict, not a shape the API produces - which is why
    it is the *only* case allowed to default to ``[]``. A present-but-wrong
    value is a malformed response: quietly reading it as "no tags" would route
    the AIM to ``/v1/completions`` and report the chat endpoint as deliberately
    unsupported. That misclassification is exactly what this module exists to
    prevent, and it is invisible in the result - ``tags_missing`` describes the
    *label*, so a bad ``tags`` value still reports ``False`` there and no
    warning is ever logged.

    Each element is type-checked rather than coerced with ``str()``, which
    would turn ``None`` into ``"none"`` and ``["chat"]`` into ``"['chat']"``:
    valid-looking tags manufactured from malformed input.
    """
    if "tags" not in model_metadata:
        return []
    raw_tags = model_metadata["tags"]
    if not isinstance(raw_tags, list):
        raise AssertionError(f"model_metadata.tags must be a list, got {type(raw_tags).__name__}: {raw_tags!r}")
    for tag in raw_tags:
        if not isinstance(tag, str):
            raise AssertionError(
                f"model_metadata.tags entries must be strings, got {type(tag).__name__}: {tag!r} in {raw_tags!r}"
            )
    return raw_tags


def _leaked_reasoning(message: dict) -> tuple[str, str] | None:
    """Return ``(field_name, text)`` for the populated reasoning field, else ``None``.

    Every spelling in ``_REASONING_FIELDS`` is type-checked even once a leak has
    been found, so a malformed sibling field still fails loudly rather than
    being skipped by an early return.
    """
    leaked = None
    for field_name in _REASONING_FIELDS:
        value = _require_optional_str(message.get(field_name), f"message.{field_name}")
        if leaked is None and value and value.strip():
            leaked = (field_name, value.strip())
    return leaked


def assert_reasoning_suppressed(message: dict, supports_suppression: bool = True) -> None:
    """Raise when a supported reasoning-off control failed to suppress reasoning.

    ``supports_suppression`` must only be true when the model family exposes a
    reasoning off-switch. GPT-OSS, for example, always reasons and supports
    effort levels rather than an off-switch, so its separate reasoning field is
    valid. Inline reasoning markers are never valid final-answer content and are
    checked for every family.

    Uses explicit ``raise AssertionError`` rather than the ``assert``
    statement: ``assert`` is compiled out entirely when Python runs with
    ``-O``, which would silently let a reasoning leak pass.
    """
    _require_dict(message, "message")
    leaked = _leaked_reasoning(message)
    if supports_suppression and leaked is not None:
        leaked_field, leaked_text = leaked
        raise AssertionError(
            f"The requested reasoning-off control was not honored: message.{leaked_field} was not empty: "
            f"{leaked_text!r}. Check this model's family mapping in _REASONING_FAMILIES in "
            f"ChatAssertions.py against its deployed chat template. Either the control being sent is one "
            f"the template does not declare - vLLM silently drops undeclared chat-template kwargs - or it "
            f"is not a true off-switch, in which case that entry's supports_suppression belongs at False. "
            f"Fix the mapping rather than relaxing this check for everyone."
        )

    content = (_require_optional_str(message.get("content"), "message.content") or "").lower()
    leaked_marker = next((marker for marker in _INLINE_REASONING_MARKERS if marker in content), None)
    if leaked_marker is not None:
        raise AssertionError(
            f"message.content contains an inline reasoning marker ({leaked_marker!r}): reasoning leaked into final-answer "
            f"content instead of message.reasoning"
        )


def reasoning_controls(model_id: str) -> tuple[dict, bool]:
    """Return the request fields that hold back reasoning, and whether it can be suppressed.

    Returns ``(request_fields, supports_suppression)``. Merge ``request_fields``
    into the chat completion body, and pass ``supports_suppression`` to
    ``assert_reasoning_suppressed``.

    ``enable_thinking`` is a Qwen-style chat-template variable. A template that
    does not declare it has the kwarg silently filtered out, so sending it to
    every family and then asserting suppression asserts a contract the model
    never agreed to - which is why a GPT-OSS probe kept returning reasoning.
    Families listed in ``_REASONING_FAMILIES`` are asked to hold reasoning back
    with whatever control they do expose (possibly none at all). Only those whose
    control is not a true off-switch are excused from returning an empty
    ``message.reasoning``; a family with a real off-switch under a different
    kwarg name still owes that proof.

    The default stays strict for unlisted families: most of the catalog does not
    reason at all, so the check costs them nothing, and a reasoning family that
    is missing from the table fails loudly with a message naming the fix rather
    than passing silently.

    Matching is a substring of the served model id (``/v1/models`` ``data[].id``)
    because that id varies by deployment: a HuggingFace repo id, a local model
    path, and a ``--served-model-name`` override all name the same family.
    """
    if not isinstance(model_id, str):
        raise AssertionError(f"model_id must be a string, got {type(model_id).__name__}: {model_id!r}")
    normalized_model_id = model_id.strip().lower()
    for family, request_fields, supports_suppression in _REASONING_FAMILIES:
        if family in normalized_model_id:
            return copy.deepcopy(request_fields), supports_suppression
    default_fields, default_supports_suppression = _DEFAULT_CONTROLS
    return copy.deepcopy(default_fields), default_supports_suppression


def reasoning_request_fields(model_id: str) -> dict:
    """Return only the request fields from :func:`reasoning_controls`.

    For probes that send the reasoning control but never inspect the response
    body - endpoint reachability and authorization checks - so they do not bind
    a ``supports_suppression`` flag they have no way to honor.
    """
    request_fields, _ = reasoning_controls(model_id)
    return request_fields


def chat_answer_content(message: dict) -> str:
    """Return the final answer text a probe must judge instruction-following on.

    Reads ``message.content`` directly, with no fallback to
    ``message.reasoning``: reasoning-only or null content must never satisfy
    instruction-following.

    Uses explicit ``raise AssertionError`` rather than the ``assert``
    statement (immune to ``python -O``), and validates the type before
    calling ``.strip()`` so a non-string ``content`` fails deterministically
    instead of raising an unrelated ``AttributeError``.
    """
    _require_dict(message, "message")
    content = _require_optional_str(message.get("content"), "message.content")
    if content is None:
        raise AssertionError("Chat response content must not be null")
    content = content.strip()
    if not content:
        raise AssertionError("Chat response content must not be empty")
    return content


def chat_support_from_tags(model_metadata: dict, original_labels: dict) -> tuple[bool, bool, bool]:
    """Decide whether an AIM should be probed via ``/v1/chat/completions``.

    Returns ``(supports_chat, tags_missing, tags_near_miss)``.

    ``supports_chat`` is the platform's own predicate, character for character:
    ``"chat" in tags``, matching ``is_chattable`` in ``app/aims/gateway.py``.
    The probe deliberately does not normalize. A test that classifies more
    generously than production reports a chat endpoint green for an AIM the
    platform never lists as chattable, which is a user-visible defect the run
    would then hide - and the harness exists to surface that class of gap, not
    to paper over it.

    ``tags_near_miss`` is how the tolerance is kept without moving the
    predicate: ``True`` when some tag becomes "chat" once stripped and
    lowercased but is not "chat" as written. That is the migration gap made
    loud - the image meant to say chat and the platform will not read it that
    way. Without it, aligning on the exact predicate would trade one silence
    for another: ``tags_missing`` describes the *label*, so a ``"Chat"`` tag
    reports ``False`` there, the AIM is classified non-chat, and nothing says
    why. Callers must surface it as they surface ``tags_missing``.

    If the conclusion is that production should tolerate casing and whitespace,
    that is a change to ``gateway.py`` and its own tests, not something this
    library may decide unilaterally by disagreeing quietly.

    ``model_metadata`` is the structured ``status.imageMetadata.model`` dict:
    its ``tags`` field is defaulted to ``[]`` by the API schema
    (``AIMModelMetadata.tags: list[str] = Field(default_factory=list)``), so it
    is never null/absent on the wire and cannot be used to detect a metadata
    migration gap - an image that never had a ``com.amd.aim.model.tags`` label
    and an image with that label deliberately set to empty both serialize
    identically as ``tags: []``.

    ``original_labels`` is the raw ``status.imageMetadata.originalLabels``
    dict aim-engine records before extracting structured fields; it still
    reflects whether the label was ever set. ``tags_missing`` is ``True`` only
    when ``"com.amd.aim.model.tags"`` is absent from ``original_labels`` — not
    merely when the structured ``tags`` list is empty or lacks "chat".
    Callers should surface ``tags_missing`` loudly: silently treating it the
    same as an explicit non-chat classification routes the probe to
    ``/v1/completions`` without any signal that the chat endpoint went
    untested because of a metadata gap rather than a deliberate model
    classification.

    Both arguments are guarded the same way the string fields above are: a
    malformed response that puts a non-dict here must fail with an actionable
    ``AssertionError``, not a ``TypeError`` from the membership test. The same
    applies to ``tags`` itself - see ``_model_tags``.
    """
    _require_dict(original_labels, "original_labels")
    _require_dict(model_metadata, "model_metadata")

    tags = _model_tags(model_metadata)
    tags_missing = "com.amd.aim.model.tags" not in original_labels
    supports_chat = _CHAT_TAG in tags
    tags_near_miss = not supports_chat and any(tag.strip().lower() == _CHAT_TAG for tag in tags)
    return supports_chat, tags_missing, tags_near_miss
