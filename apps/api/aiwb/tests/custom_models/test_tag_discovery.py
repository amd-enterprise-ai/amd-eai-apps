# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Unit coverage for parsing catalog tags out of untrusted model-source content."""

import pytest

from app.custom_models.constants import MAX_DISCOVERED_TAG_LENGTH, MAX_DISCOVERED_TAGS
from app.custom_models.tag_discovery import (
    DiscoveredMetadata,
    card_metadata_from_frontmatter,
    normalize_tags,
    parse_card_frontmatter,
    resolvable_repo_id,
    resolve_discovered_tags,
)

CARD_WITH_FRONTMATTER = """---
base_model: mistralai/Mistral-7B-v0.1
pipeline_tag: text-generation
tags:
  - conversational
  - fine-tuned
---

# My Model

Some prose about the model.
"""


def test_parse_card_frontmatter_extracts_leading_yaml_block() -> None:
    """The fenced YAML block at the top of a card is the model's metadata."""
    frontmatter = parse_card_frontmatter(CARD_WITH_FRONTMATTER)

    assert frontmatter["base_model"] == "mistralai/Mistral-7B-v0.1"
    assert frontmatter["tags"] == ["conversational", "fine-tuned"]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "absent card"),
        ("", "empty card"),
        ("# Just a heading\n\nNo frontmatter here.", "no fence"),
        ("---\ntags:\n  - unterminated\n", "no closing fence"),
        ("Intro prose\n---\ntags:\n  - late\n---\n", "fence is not at the top"),
        ("---\ntags: [unclosed\n---\n", "malformed YAML"),
        ("---\njust a string\n---\n", "frontmatter is not a mapping"),
    ],
)
def test_parse_card_frontmatter_returns_empty_for_unusable_cards(raw: str | None, reason: str) -> None:
    """A card that carries no usable frontmatter yields no metadata rather than raising."""
    assert parse_card_frontmatter(raw) == {}, reason


def test_parse_card_frontmatter_ignores_yaml_samples_further_down() -> None:
    """A fenced YAML example in the prose must not be mistaken for card metadata."""
    card = "# Usage\n\nConfigure it like this:\n\n---\ntags:\n  - not-metadata\n---\n"

    assert parse_card_frontmatter(card) == {}


def test_parse_card_frontmatter_does_not_construct_python_objects() -> None:
    """Card content is parsed safely, so YAML tags cannot instantiate objects."""
    card = "---\ntags: !!python/object/apply:os.system ['echo pwned']\n---\n"

    assert parse_card_frontmatter(card) == {}


def test_parse_card_frontmatter_tolerates_a_leading_byte_order_mark() -> None:
    """A card saved with a BOM still exposes its frontmatter."""
    frontmatter = parse_card_frontmatter("\ufeff---\ntags:\n  - vision\n---\n")

    assert frontmatter["tags"] == ["vision"]


def test_parse_card_frontmatter_accepts_a_long_frontmatter_block_within_bound() -> None:
    """Long gated-prompt blocks should still parse when the closing fence is within the scan cap."""
    long_lines = "\n".join(["extra_gated_prompt: |-", *("  line" for _ in range(215))])
    card = f"---\ntags:\n  - llama\n{long_lines}\n---\n\n# Model Card\n"

    frontmatter = parse_card_frontmatter(card)

    assert frontmatter["tags"] == ["llama"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("single", ["single"]),
        (["a", "b", "a"], ["a", "b"]),
        (["  padded  "], ["padded"]),
        (["keep", 7, None, {"nested": "dict"}, ["nested-list"]], ["keep"]),
        (["", "   "], []),
        (None, []),
        (42, []),
        ({"tags": "mapping"}, []),
    ],
)
def test_normalize_tags_coerces_defensively(value: object, expected: list[str]) -> None:
    """Only strings survive coercion, so structured card data cannot leak into the catalog."""
    assert normalize_tags(value) == expected


def test_normalize_tags_caps_list_length_preserving_leading_order() -> None:
    """An oversized tag list is truncated, keeping the tags the author listed first."""
    result = normalize_tags([f"tag-{index}" for index in range(MAX_DISCOVERED_TAGS + 25)])

    assert len(result) == MAX_DISCOVERED_TAGS
    assert result[0] == "tag-0"


def test_normalize_tags_drops_overlong_entries() -> None:
    """A single absurdly long tag is dropped rather than truncated into a meaningless string."""
    too_long = "x" * (MAX_DISCOVERED_TAG_LENGTH + 1)

    assert normalize_tags([too_long, "fine"]) == ["fine"]


@pytest.mark.parametrize(
    "candidate",
    [
        "https://huggingface.co/owner/model",
        "http://evil.example/owner/model",
        "//evil.example/owner/model",
        "owner/model/extra",
        "owner",
        "../../etc/passwd",
        "owner/../secrets",
        "user:token@owner/model",
        "owner/model?revision=main",
        "owner /model",
        "owner\t/model",
        "",
        "   ",
        None,
        42,
        ["owner/model"],
    ],
)
def test_resolvable_repo_id_rejects_anything_but_a_bare_repo_id(candidate: object) -> None:
    """Provenance builds an outbound request, so only bare 'owner/model' is accepted."""
    assert resolvable_repo_id(candidate) is None


@pytest.mark.parametrize(
    "candidate",
    ["owner/model", "  owner/model  ", "owner/model\n", "Org.Name/model-v1.5_beta"],
)
def test_resolvable_repo_id_accepts_well_formed_repo_ids(candidate: str) -> None:
    """A bare repo id is usable provenance; surrounding whitespace from file content is trimmed."""
    assert resolvable_repo_id(candidate) == candidate.strip()


def test_card_metadata_folds_pipeline_tag_into_tags() -> None:
    """Pipeline metadata is included in the editable tag suggestions."""
    card = card_metadata_from_frontmatter(parse_card_frontmatter(CARD_WITH_FRONTMATTER))

    assert card.tags == ["conversational", "fine-tuned", "text-generation"]
    assert card.base_model == "mistralai/Mistral-7B-v0.1"
    assert card.pipeline_tag == "text-generation"


def test_card_metadata_accepts_base_model_authored_as_a_list() -> None:
    """Merges cite several parents, so base_model is commonly a list."""
    card = card_metadata_from_frontmatter(
        parse_card_frontmatter("---\nbase_model:\n  - owner/first\n  - owner/second\n---\n")
    )

    assert card.base_model == "owner/first"


def test_card_metadata_rejects_a_base_model_that_is_not_a_repo_id() -> None:
    """A card citing a URL yields no provenance, so no request is built from it."""
    card = card_metadata_from_frontmatter(
        parse_card_frontmatter("---\nbase_model: https://huggingface.co/owner/model\n---\n")
    )

    assert card.base_model is None


def test_hub_and_card_tags_are_merged_when_provenance_resolves() -> None:
    """Catalog tags lead the merged result when provenance resolves."""
    result = resolve_discovered_tags(
        card=DiscoveredMetadata(tags=["card-tag"], base_model="owner/base"),
        hub_data={"tags": ["text-generation", "mistral"], "pipeline_tag": "text-generation"},
    )

    assert result.tags == ["text-generation", "mistral", "card-tag"]
    assert result.pipeline_tag == "text-generation"


def test_card_tags_are_used_when_provenance_did_not_resolve() -> None:
    """An unresolved base model falls back to author metadata."""
    result = resolve_discovered_tags(
        card=DiscoveredMetadata(tags=["card-tag"], base_model="owner/base"),
        hub_data=None,
    )

    assert result.tags == ["card-tag"]


def test_card_tags_are_used_when_hub_reports_no_tags() -> None:
    """An empty catalog response leaves the card tags unchanged."""
    result = resolve_discovered_tags(
        card=DiscoveredMetadata(tags=["card-tag"]),
        hub_data={"tags": []},
    )

    assert result.tags == ["card-tag"]


def test_no_discoverable_tags_returns_an_empty_list() -> None:
    """Missing model-card and Hub tags produce an empty editable list."""
    result = resolve_discovered_tags(card=DiscoveredMetadata(), hub_data=None)

    assert result.tags == []
