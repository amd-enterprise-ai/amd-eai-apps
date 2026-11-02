# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import pytest

from api_common.slugs import is_slug_stable, slugify


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Test Dataset", "test-dataset"),
        ("Test! @#$%^&*() Dataset", "test-dataset"),
        ("---Test Dataset---", "test-dataset"),
        ("Téśt Dàtáśét", "téśt-dàtáśét"),
        ("name_with_underscores", "name_with_underscores"),
        ("test-dataset", "test-dataset"),
    ],
)
def test_slugify_folds_a_name_into_a_path_safe_form(name: str, expected: str) -> None:
    assert slugify(name) == expected


@pytest.mark.parametrize("name", ["data-bar", "data--bar", "data---bar", "data.bar", "Data Bar", "-data-bar-"])
def test_names_that_differ_can_still_slug_alike(name: str) -> None:
    """Slugging is lossy in several directions at once, which is why uniqueness of names buys nothing.

    Separator runs collapse, every non-alphanumeric character becomes a hyphen, case folds, and
    edges are trimmed — so a caller who cannot have one name can reach its storage under another.
    """
    assert slugify(name) == "data-bar"


@pytest.mark.parametrize("name", ["---", "-", "!!!", ""])
def test_a_name_made_only_of_separators_slugs_away_to_nothing(name: str) -> None:
    """The empty slug is a real output, and slug-stability alone does not exclude it.

    Every character folds to a hyphen and the run is then stripped, so nothing survives. The
    empty string is its own slug, so `is_slug_stable` accepts it and callers keying storage on
    the result would address the bucket root. Callers stay clear of it by bounding the name's
    length — `ProjectBase.name` carries `min_length`, which is what actually rules this out.
    """
    assert slugify(name) == ""
    assert is_slug_stable("")


@pytest.mark.parametrize("name", ["data-bar", "data", "data-bar-1", "téśt-dàtáśét", "name_with_underscores"])
def test_a_slug_stable_name_is_its_own_slug(name: str) -> None:
    assert is_slug_stable(name)
    assert slugify(name) == name


def test_an_underscore_is_kept_apart_from_a_hyphen() -> None:
    """Underscores must not join the class of characters that fold, or the collision reopens.

    `data_bar` and `data-bar` are distinct names that must keep distinct storage prefixes. A
    hyphen run collapses, so `data--bar` is refused at creation; an underscore does not, so
    `data_bar` is accepted and has to remain addressable on its own. Widening the folded class
    to include `_` would silently merge two live tenants' prefixes.
    """
    assert slugify("data_bar") != slugify("data-bar")
    assert slugify("data--bar") == slugify("data-bar")


@pytest.mark.parametrize("name", ["data--bar", "data.bar", "Data-Bar", "-data-bar", "data-bar-", "data bar"])
def test_a_name_that_slugging_would_change_is_not_slug_stable(name: str) -> None:
    assert not is_slug_stable(name)


def test_slug_stable_names_cannot_collide_with_one_another() -> None:
    """The property the creation rules rely on: over slug-stable names, slugify is injective.

    Each such name is a fixed point of slugify, so its slug is itself, and two distinct names
    therefore have two distinct slugs. Anything that weakens the accepted domain back below
    slug-stability breaks this, which is what makes it worth pinning.
    """
    names = ["data-bar", "data", "databar", "data-bar-1", "téśt", "name_with_underscores"]

    assert len({slugify(name) for name in names}) == len(names)
