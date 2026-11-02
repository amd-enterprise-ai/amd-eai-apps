# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import re
from datetime import UTC, datetime
from itertools import product
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api_common.slugs import is_slug_stable
from app.projects.enums import GpuPreemptionPolicy, ProjectStatus
from app.projects.schemas import (
    PROJECT_NAME_PATTERN,
    SLUG_STABLE_PROJECT_NAME_PATTERN,
    GpuPreemptionConfig,
    ProjectCreate,
    ProjectResponse,
)
from app.projects.utils import flatten_gpu_preemption
from app.quotas.schemas import QuotaUpdate


def test_gpu_preemption_config_defaults():
    config = GpuPreemptionConfig()
    assert config.enabled is False
    assert config.threshold is None
    assert config.grace_period is None
    assert config.policy is None


def test_gpu_preemption_config_full():
    config = GpuPreemptionConfig(enabled=True, threshold=80, grace_period=900, policy=GpuPreemptionPolicy.ON_PRESSURE)
    assert config.enabled is True
    assert config.threshold == 80
    assert config.grace_period == 900
    assert config.policy == GpuPreemptionPolicy.ON_PRESSURE


def test_gpu_preemption_config_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GpuPreemptionConfig(enabled=True, threshhold=80)


def test_gpu_preemption_config_threshold_range():
    with pytest.raises(ValidationError):
        GpuPreemptionConfig(threshold=-1)
    with pytest.raises(ValidationError):
        GpuPreemptionConfig(threshold=101)


def test_gpu_preemption_config_grace_period_minimum():
    with pytest.raises(ValidationError):
        GpuPreemptionConfig(grace_period=0)
    with pytest.raises(ValidationError):
        GpuPreemptionConfig(grace_period=899)
    GpuPreemptionConfig(grace_period=900)


def test_gpu_preemption_config_grace_period_multiple_of_sixty_seconds():
    with pytest.raises(ValidationError):
        GpuPreemptionConfig(grace_period=901)
    GpuPreemptionConfig(grace_period=960)


def test_flatten_gpu_preemption():
    config = GpuPreemptionConfig(enabled=True, threshold=75, grace_period=1800, policy=GpuPreemptionPolicy.ALWAYS)
    assert flatten_gpu_preemption(config) == {
        "gpu_preemption_enabled": True,
        "gpu_preemption_threshold": 75,
        "gpu_preemption_grace_period": 1800,
        "gpu_preemption_policy": GpuPreemptionPolicy.ALWAYS,
    }


def _project_create(name: str) -> ProjectCreate:
    return ProjectCreate(
        name=name,
        description="A test project",
        cluster_id=uuid4(),
        quota=QuotaUpdate(cpu_milli_cores=0, memory_bytes=0, ephemeral_storage_bytes=0, gpu_count=0),
    )


@pytest.mark.parametrize("name", ["data-science", "datascience", "data-science-2", "ds"])
def test_a_project_name_that_is_its_own_storage_path_segment_is_accepted(name: str) -> None:
    assert _project_create(name).name == name


@pytest.mark.parametrize("name", ["data--science", "data---science"])
def test_a_project_name_that_would_be_rewritten_into_another_projects_prefix_is_rejected(name: str) -> None:
    """The name becomes a namespace, and the namespace's slug is the object-storage boundary.

    Slugging folds runs of hyphens, so these names address the prefix `data-science` — a prefix a
    differently-named project can also legitimately hold. Names carrying other separators are
    already refused by the field's character pattern; a repeated hyphen is the one shape that
    clears the pattern and still fails to survive slugging, so it is what this rule adds.
    """
    with pytest.raises(ValidationError):
        _project_create(name)


def test_the_rejection_tells_the_caller_what_shape_of_name_to_use() -> None:
    with pytest.raises(ValidationError, match="Use a single hyphen between words"):
        _project_create("data--science")


def test_the_published_contract_advertises_the_rule_the_server_applies() -> None:
    """A generated client must not be able to build a name the API will refuse.

    The accepted set is the intersection of the field's character pattern and the slug-stability
    validator, but a validator is invisible to JSON Schema, so the schema publishes a tightened
    pattern instead. The two are declared separately and could drift, so this pins them together
    over every name the character pattern admits.
    """
    published = ProjectCreate.model_json_schema()["properties"]["name"]["pattern"]

    assert published == SLUG_STABLE_PROJECT_NAME_PATTERN

    admitted_by_pattern = re.compile(PROJECT_NAME_PATTERN)
    published_rule = re.compile(published)
    for name in ("".join(c) for length in range(2, 7) for c in product("ab0-", repeat=length)):
        if not admitted_by_pattern.match(name):
            continue
        assert (published_rule.match(name) is not None) == is_slug_stable(name), name


def test_a_project_named_before_the_rule_existed_can_still_be_read_back() -> None:
    """The rule gates creation only — it must not make projects that predate it unreadable.

    'data--science' cannot be created now, but rows holding that name were legal when they were
    written and are not renamed by this rule. Every read builds a `ProjectResponse`, so a name
    rule shared with the response schema would raise while merely serialising such a row and
    take the project out of every list and detail endpoint that touches it.
    """
    now = datetime.now(tz=UTC)

    project = ProjectResponse(
        id=uuid4(),
        name="data--science",
        description="Created before the naming rule existed",
        cluster_id=uuid4(),
        status=ProjectStatus.READY,
        created_at=now,
        updated_at=now,
        created_by="someone",
        updated_by="someone",
    )

    assert project.name == "data--science"
