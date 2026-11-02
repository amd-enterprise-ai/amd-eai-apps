# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Pure parsing helpers for discovering catalog tags from model source content.

Object-storage sources carry no catalog metadata of their own: unlike a Hub repo
there is no API to ask "what is this model tagged as". Discovery therefore reads
the model card the uploader left in the model tree. Card content is untrusted, so
malformed metadata yields fewer tags, never an exception. Tag discovery is
display metadata and must never block preview.
"""

from dataclasses import dataclass, field
from typing import Any

import yaml

from .constants import (
    _REPO_PART_PATTERN,
    MAX_DISCOVERED_TAG_LENGTH,
    MAX_DISCOVERED_TAGS,
)

_FRONTMATTER_FENCE = "---"

# Frontmatter is a leading YAML document; a card that opens with hundreds of
# lines before its closing fence is not one, and scanning further wastes work on
# content that is not frontmatter anyway.
_MAX_FRONTMATTER_LINES = 500


@dataclass
class DiscoveredMetadata:
    """Catalog metadata discovered from a model card and optional Hub lookup.

    All fields are optional because discovery is best-effort.
    """

    tags: list[str] = field(default_factory=list)
    base_model: str | None = None
    pipeline_tag: str | None = None


def normalize_tags(values: Any) -> list[str]:
    """Coerce an arbitrary parsed value into a bounded, deduplicated tag list.

    Accepts a single string or a list of them; anything else (dicts, nested
    lists, numbers) is dropped rather than stringified, so a card that puts
    structured data under ``tags:`` cannot inject ``{'foo': 'bar'}`` into the
    catalog. Order is preserved so the most significant tags — which authors put
    first — survive the cap.
    """
    if isinstance(values, str):
        candidates: list[Any] = [values]
    elif isinstance(values, list):
        candidates = list(values)
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        tag = candidate.strip()
        if not tag or len(tag) > MAX_DISCOVERED_TAG_LENGTH:
            continue
        if tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
        if len(normalized) == MAX_DISCOVERED_TAGS:
            break
    return normalized


def parse_card_frontmatter(raw: str | None) -> dict[str, Any]:
    """Extract the YAML frontmatter block from a model card, or {} when absent.

    Frontmatter is the leading ``---``-fenced document at the top of a README.
    Parsed with ``safe_load`` so tags in the card cannot instantiate Python
    objects, and bounded to the leading block so a card embedding YAML samples
    further down does not get mistaken for metadata.
    """
    if not raw:
        return {}

    lines = raw.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}

    body: list[str] = []
    for line in lines[1 : _MAX_FRONTMATTER_LINES + 1]:
        if line.strip() == _FRONTMATTER_FENCE:
            break
        body.append(line)
    else:
        # No closing fence within the bound: not a frontmatter block.
        return {}

    try:
        parsed = yaml.safe_load("\n".join(body))
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_scalar(value: Any) -> str | None:
    """Return the first string in a scalar-or-list frontmatter value.

    ``base_model`` is documented as a string but is commonly authored as a list
    (merges cite several parents), so both shapes are accepted.
    """
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                return entry.strip()
    return None


def resolvable_repo_id(candidate: Any) -> str | None:
    """Return ``candidate`` when it is a bare ``owner/model`` repo id, else None.

    Provenance comes from a file in a user-controlled bucket and is used to build
    an outbound Hub request, so it is accepted in repo-id form only. Rejecting
    anything with a scheme, host, port, userinfo, query, extra path segments, or
    traversal components keeps the value from steering that request anywhere
    other than the model it names on the fixed Hub host — the URL is then
    assembled from a constant base, never from caller-supplied text.
    """
    if not isinstance(candidate, str):
        return None
    repo_id = candidate.strip()
    if not repo_id or any(char.isspace() for char in repo_id):
        return None
    parts = repo_id.split("/")
    if len(parts) != 2:
        return None
    if not all(_REPO_PART_PATTERN.match(part) for part in parts):
        return None
    return repo_id


def card_metadata_from_frontmatter(frontmatter: dict[str, Any]) -> DiscoveredMetadata:
    """Project parsed frontmatter onto fields used by source preview."""
    tags = normalize_tags(frontmatter.get("tags"))

    pipeline_tag = _first_scalar(frontmatter.get("pipeline_tag"))
    if pipeline_tag:
        tags = normalize_tags([*tags, pipeline_tag])

    return DiscoveredMetadata(
        tags=tags,
        base_model=_card_base_model(frontmatter),
        pipeline_tag=pipeline_tag,
    )


def _card_base_model(frontmatter: dict[str, Any]) -> str | None:
    """Return the card's provenance when it is a usable repo id."""
    return resolvable_repo_id(_first_scalar(frontmatter.get("base_model")))


def resolve_discovered_tags(
    *,
    card: DiscoveredMetadata,
    hub_data: dict[str, Any] | None,
) -> DiscoveredMetadata:
    """Merge Hub and model-card tags."""
    hub_tags = normalize_tags(hub_data.get("tags")) if hub_data else []
    hub_pipeline_tag = _first_scalar(hub_data.get("pipeline_tag")) if hub_data else None
    tags = normalize_tags([*hub_tags, *card.tags])

    return DiscoveredMetadata(
        tags=tags,
        base_model=card.base_model,
        pipeline_tag=hub_pipeline_tag or card.pipeline_tag,
    )
