# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Tests for AimCatalogGenerator covering API mode, name filtering, and utility methods."""

import sys
from pathlib import Path

import pytest

# Aliased, not `from ... import TestSuite`: pytest would try to collect a
# top-level name starting with "Test" as a test class.
from robot.running import TestSuite as RobotTestSuite

# Add libraries to path so AimCatalogGenerator is importable
sys.path.insert(0, str(Path(__file__).parent / "libraries"))

from AimCatalogGenerator import AimCatalogGenerator

# -- Fixtures --


@pytest.fixture()
def api_generator():
    """Generator in API mode (no name filter, no models loaded)."""
    return AimCatalogGenerator("api", "full")


# -- Name filter loading --


def test_load_model_names(tmp_path):
    """Model names are loaded correctly from a text file."""
    name_file = tmp_path / "models.txt"
    name_file.write_text("# comment\n\nalpha/Model-A\nbeta/Model-B\n   \n")

    names = AimCatalogGenerator._load_model_names(str(name_file))

    assert names == ["alpha/Model-A", "beta/Model-B"]


def test_load_model_names_file_not_found():
    """FileNotFoundError is raised for missing file."""
    with pytest.raises(FileNotFoundError, match="not found"):
        AimCatalogGenerator._load_model_names("/nonexistent/path.txt")


def test_init_with_name_filter(tmp_path):
    """Init with a file path sets name_filter."""
    name_file = tmp_path / "models.txt"
    name_file.write_text("model-x\nmodel-y\n")

    generator = AimCatalogGenerator(str(name_file), "full")

    assert generator.name_filter == ["model-x", "model-y"]
    assert generator.models == []


# -- API mode initialization --


@pytest.mark.parametrize("arg", ["api", "API", "Api"])
def test_api_mode_no_filter(arg):
    """'api' (case-insensitive) sets no name filter."""
    generator = AimCatalogGenerator(arg, "full")

    assert generator.name_filter is None
    assert generator.models == []


@pytest.mark.parametrize("mode", ["full", "smoke", "quick"])
def test_test_modes(mode):
    """All test modes are accepted and stored."""
    generator = AimCatalogGenerator("api", mode)
    assert generator.test_mode == mode


# -- Variable extraction --


class _MockVariable:
    def __init__(self, name, value):
        self.name = name
        self.value = [value]


class _MockSuite:
    class resource:
        variables = [
            _MockVariable("${INCLUDE_TAGS}", "gpus:1"),
            _MockVariable("${EXCLUDE_TAGS}", "requires-hf-token"),
            _MockVariable("${TEST_MODE}", "smoke"),
        ]


def test_get_variable_extracts_existing(api_generator):
    """_get_variable returns values from suite resource variables."""
    assert api_generator._get_variable(_MockSuite, "INCLUDE_TAGS") == "gpus:1"
    assert api_generator._get_variable(_MockSuite, "EXCLUDE_TAGS") == "requires-hf-token"
    assert api_generator._get_variable(_MockSuite, "TEST_MODE") == "smoke"


def test_get_variable_returns_none_for_missing(api_generator):
    """_get_variable returns None for non-existent variables."""
    assert api_generator._get_variable(_MockSuite, "NONEXISTENT") is None


# -- AIM-to-model mapping --


FULL_AIM_RESPONSE = {
    "metadata": {"name": "aim-meta-llama-llama-3-1-8b-instruct", "namespace": "default"},
    "spec": {"image": "amdenterpriseai/aim-meta-llama-llama-3-1-8b-instruct:0.8.4"},
    "status": {
        "status": "Ready",
        "imageMetadata": {
            "model": {
                "canonicalName": "meta-llama/Llama-3.1-8B-Instruct",
                "hfTokenRequired": True,
                "recommendedDeployments": [{"gpuCount": 1, "gpuModel": "MI300X", "metric": "latency"}],
                "tags": ["chat", "text-generation"],
            },
        },
    },
}


def test_map_aim_to_model_full_response(api_generator):
    """Full API response maps all fields correctly."""
    model = api_generator._map_aim_to_model(FULL_AIM_RESPONSE)

    assert model["model_name"] == "meta-llama/Llama-3.1-8B-Instruct"
    assert model["image_name"] == "aim-meta-llama-llama-3-1-8b-instruct"
    assert model["docker_image"] == "amdenterpriseai/aim-meta-llama-llama-3-1-8b-instruct:0.8.4"
    assert model["gpu_count"] == 1
    assert model["requires_hf_token"] is True
    assert model["version"] == "0.8.4"


def test_map_aim_to_model_fallback_fields(api_generator):
    """Minimal API response extracts fields from nested structure."""
    aim_response = {
        "metadata": {"name": "aim-custom-model"},
        "spec": {"image": "registry.example.com/org/aim-custom-model:1.0.0"},
        "status": {
            "status": "Ready",
            "imageMetadata": {
                "model": {
                    "recommendedDeployments": [{"gpuCount": 4}],
                },
            },
        },
    }

    model = api_generator._map_aim_to_model(aim_response)

    assert model["model_name"] == "aim-custom-model"
    assert model["image_name"] == "aim-custom-model"
    assert model["docker_image"] == "registry.example.com/org/aim-custom-model:1.0.0"
    assert model["gpu_count"] == 4
    assert model["requires_hf_token"] is False
    assert model["version"] == "1.0.0"


# -- GPU count extraction --


@pytest.mark.parametrize(
    ("deployments", "expected"),
    [
        ([{"gpuCount": 8, "gpuModel": "MI300X"}], 8),
        ([{"numGpus": 8}], 8),
        ([{"gpu_count": 2}], 2),
        ([{"gpus": 16}], 16),
        # Multiple deployments returns minimum
        ([{"gpuCount": 2}, {"gpuCount": 4}], 2),
    ],
    ids=["gpuCount", "numGpus", "gpu_count", "gpus", "min-of-multiple"],
)
def test_extract_gpu_count(deployments, expected):
    """GPU count is extracted from various field names, min across deployments."""
    assert AimCatalogGenerator._extract_gpu_count(deployments) == expected


@pytest.mark.parametrize(
    "deployments",
    [
        [],
        None,
        [{"name": "default", "memory": "16Gi"}],
        ["not-a-dict", 42],
        [{"numGpus": "invalid"}],
        [{"numGpus": 0}],
    ],
    ids=["empty-list", "none", "no-gpu-fields", "non-dict", "invalid-value", "zero"],
)
def test_extract_gpu_count_defaults_to_1(deployments):
    """GPU count defaults to 1 when data is missing, invalid, or zero."""
    assert AimCatalogGenerator._extract_gpu_count(deployments) == 1


# -- GPU count mapping in _map_aim_to_model --


def test_map_aim_to_model_uses_recommended_deployments(api_generator):
    """_map_aim_to_model derives gpu_count from recommendedDeployments."""
    aim_response = {
        "metadata": {"name": "aim-test-model"},
        "spec": {"image": "amdenterpriseai/aim-test-model:0.9.0"},
        "status": {
            "status": "Ready",
            "imageMetadata": {
                "model": {
                    "recommendedDeployments": [{"gpuCount": 8}],
                },
            },
        },
    }

    model = api_generator._map_aim_to_model(aim_response)

    assert model["gpu_count"] == 8


def test_map_aim_to_model_defaults_gpu_count_to_1(api_generator):
    """_map_aim_to_model defaults gpu_count to 1 when recommendedDeployments is absent."""
    aim_response = {
        "metadata": {"name": "aim-no-recommendations"},
        "spec": {"image": "amdenterpriseai/aim-no-recommendations:0.9.0"},
        "status": {
            "status": "Ready",
            "imageMetadata": {"model": {}},
        },
    }

    model = api_generator._map_aim_to_model(aim_response)

    assert model["gpu_count"] == 1


# -- Image name extraction --


@pytest.mark.parametrize(
    ("docker_image", "metadata_name", "expected"),
    [
        ("amdenterpriseai/aim-foo:0.8.4", "fallback", "aim-foo"),
        ("registry.io/org/aim-bar:latest", "fallback", "aim-bar"),
        ("amdenterpriseai/aim-baz", "fallback", "aim-baz"),
        ("org/aim-digest@sha256:abc123", "fallback", "aim-digest"),
        ("", "my-fallback", "my-fallback"),
        ("", "", "unknown"),
    ],
    ids=["standard", "full-registry", "no-tag", "digest", "empty-uses-fallback", "both-empty"],
)
def test_extract_image_name(docker_image, metadata_name, expected):
    """Image name is extracted from docker refs with proper fallbacks."""
    assert AimCatalogGenerator._extract_image_name(docker_image, metadata_name) == expected


# -- Version extraction --


@pytest.mark.parametrize(
    ("docker_image", "expected"),
    [
        ("amdenterpriseai/aim-foo:0.8.5", "0.8.5"),
        ("registry.io/org/aim-bar:latest", "latest"),
        ("org/aim-foo:1.0.0-preview", "1.0.0-preview"),
        ("amdenterpriseai/aim-baz", None),
        ("", None),
        ("org/aim-foo@sha256:abcdef1234567890", None),
        ("registry.example.com:5000/org/aim-foo", None),
        ("registry:5000/aim-foo:0.8.5", "0.8.5"),
    ],
    ids=[
        "semver",
        "latest-tag",
        "prerelease",
        "no-tag",
        "empty",
        "sha256-digest",
        "registry-port-no-tag",
        "registry-port-with-tag",
    ],
)
def test_extract_version(docker_image, expected):
    """Version tag is extracted from docker image references."""
    assert AimCatalogGenerator._extract_version(docker_image) == expected


# -- Version key parsing --


@pytest.mark.parametrize(
    ("version_a", "version_b", "a_is_greater"),
    [
        ("0.9.0", "0.8.5", True),
        ("0.8.5", "0.8.5-preview", True),
        ("1.0.0", "0.99.99", True),
        ("0.8.5", "0.8.5", False),
    ],
    ids=["minor-higher", "release-beats-preview", "major-higher", "equal"],
)
def test_parse_version_key_ordering(version_a, version_b, a_is_greater):
    """Version keys compare correctly using packaging.version semantics."""
    key_a = AimCatalogGenerator._parse_version_key(version_a)
    key_b = AimCatalogGenerator._parse_version_key(version_b)

    if a_is_greater:
        assert key_a > key_b
    else:
        assert key_a == key_b


def test_parse_version_key_none_and_invalid():
    """None and invalid versions parse to Version('0') for safe comparison."""
    none_key = AimCatalogGenerator._parse_version_key(None)
    invalid_key = AimCatalogGenerator._parse_version_key("not-a-version")
    valid_key = AimCatalogGenerator._parse_version_key("0.8.5")

    assert none_key < valid_key
    assert invalid_key < valid_key


# -- Version filtering --


def _make_models(*versions):
    """Create model dicts with the given versions for filtering tests."""
    return [{"image_name": f"aim-model-{i}", "version": v, "model_name": f"model-{i}"} for i, v in enumerate(versions)]


@pytest.mark.parametrize(
    ("version_filter", "versions", "expected_versions"),
    [
        ("0.8.5", ["0.8.4", "0.8.5", "0.9.0"], ["0.8.5"]),
        (">=0.9.0", ["0.8.4", "0.8.5", "0.9.0", "1.0.0"], ["0.9.0", "1.0.0"]),
        (">0.8.5", ["0.8.4", "0.8.5", "0.9.0"], ["0.9.0"]),
        ("<=0.8.5", ["0.8.4", "0.8.5", "0.9.0"], ["0.8.4", "0.8.5"]),
        ("<0.9.0", ["0.8.4", "0.8.5", "0.9.0"], ["0.8.4", "0.8.5"]),
    ],
    ids=["exact", "gte", "gt", "lte", "lt"],
)
def test_apply_version_filter(api_generator, version_filter, versions, expected_versions):
    """Version filter operators select the correct subset of models."""
    models = _make_models(*versions)
    filtered = api_generator._apply_version_filter(models, version_filter)
    assert [m["version"] for m in filtered] == expected_versions


def test_apply_version_filter_skips_unversioned(api_generator):
    """Models without a version tag are excluded by version filters."""
    models = _make_models("0.8.5", None, "0.9.0")
    filtered = api_generator._apply_version_filter(models, ">=0.8.5")
    assert len(filtered) == 2
    assert all(m["version"] is not None for m in filtered)


def test_apply_version_filter_skips_unparseable(api_generator):
    """Models with unparseable version strings are excluded by version filters."""
    models = _make_models("0.8.5", "not-a-version", "0.9.0")
    filtered = api_generator._apply_version_filter(models, ">=0.8.5")
    assert len(filtered) == 2


def test_apply_version_filter_latest_returns_all(api_generator):
    """'latest' filter is a no-op (dedup is handled separately)."""
    models = _make_models("0.8.4", "0.8.5", "0.9.0")
    filtered = api_generator._apply_version_filter(models, "latest")
    assert len(filtered) == 3


def test_apply_version_filter_invalid_target(api_generator):
    """Invalid filter target returns all models with a warning."""
    models = _make_models("0.8.5", "0.9.0")
    filtered = api_generator._apply_version_filter(models, "not-a-version")
    assert len(filtered) == 2


def test_apply_version_filter_none_returns_all(api_generator):
    """None filter is a no-op."""
    models = _make_models("0.8.4", "0.8.5")
    filtered = api_generator._apply_version_filter(models, None)
    assert filtered == models


def test_apply_version_filter_empty_returns_all(api_generator):
    """Empty string filter is a no-op."""
    models = _make_models("0.8.4", "0.8.5")
    filtered = api_generator._apply_version_filter(models, "")
    assert filtered == models


# -- Deduplication --


def test_dedup_keeps_highest_version(api_generator):
    """Dedup by image_name keeps the model with the highest version."""
    models = [
        {"image_name": "aim-foo", "version": "0.8.4", "model_name": "foo-old"},
        {"image_name": "aim-foo", "version": "0.9.0", "model_name": "foo-new"},
        {"image_name": "aim-bar", "version": "1.0.0", "model_name": "bar"},
    ]
    result = api_generator._deduplicate_models(models)

    assert len(result) == 2
    assert result[0]["version"] == "0.9.0"
    assert result[0]["model_name"] == "foo-new"
    assert result[1]["image_name"] == "aim-bar"


def test_dedup_keeps_first_when_no_version(api_generator):
    """Dedup keeps the first model when neither has a version."""
    models = [
        {"image_name": "aim-foo", "version": None, "model_name": "first"},
        {"image_name": "aim-foo", "version": None, "model_name": "second"},
    ]
    result = api_generator._deduplicate_models(models)

    assert len(result) == 1
    assert result[0]["model_name"] == "first"


def test_dedup_no_duplicates_is_noop(api_generator):
    """Dedup with all unique image_names returns all models."""
    models = [
        {"image_name": "aim-a", "version": "1.0.0", "model_name": "a"},
        {"image_name": "aim-b", "version": "2.0.0", "model_name": "b"},
        {"image_name": "aim-c", "version": "3.0.0", "model_name": "c"},
    ]
    result = api_generator._deduplicate_models(models)

    assert len(result) == 3


# -- Snake_case API field fallbacks --


def test_map_aim_to_model_snake_case_fields(api_generator):
    """API response with snake_case fields maps correctly."""
    aim_response = {
        "metadata": {"name": "aim-snake-model"},
        "spec": {"image": "registry.io/aim-snake-model:0.9.0"},
        "status": {
            "status": "Ready",
            "image_metadata": {
                "model": {
                    "canonical_name": "org/SnakeModel",
                    "hf_token_required": True,
                    "recommended_deployments": [{"gpu_count": 2}],
                },
            },
        },
    }

    model = api_generator._map_aim_to_model(aim_response)

    assert model["model_name"] == "org/SnakeModel"
    assert model["gpu_count"] == 2
    assert model["requires_hf_token"] is True


def test_map_aim_to_model_minimal_input(api_generator):
    """Minimal/empty input produces safe defaults without raising."""
    model = api_generator._map_aim_to_model({"metadata": {}, "spec": {}, "status": {}})

    assert model["model_name"] == ""
    assert model["image_name"] == "unknown"
    assert model["docker_image"] == ""
    assert model["gpu_count"] == 1
    assert model["requires_hf_token"] is False
    assert model["version"] is None


# -- Name filter error paths --


def test_name_filter_file_not_found():
    """FileNotFoundError is raised for non-existent name filter path."""
    with pytest.raises(FileNotFoundError, match="not found"):
        AimCatalogGenerator("/nonexistent/path/models.txt", "full")


# -- Dynamic test generation --


def test_generated_catalog_tests_keep_the_suite_timeout(api_generator):
    """Every runtime-generated test gets the catalog suite's 100-minute bound."""
    api_generator.models = [
        {
            "model_name": "org/TestModel",
            "image_name": "aim-test-model",
            "docker_image": "registry.example.com/org/aim-test-model:1.0.0",
            "gpu_count": 1,
            "requires_hf_token": False,
            "version": "1.0.0",
        }
    ]
    suite = RobotTestSuite(name="Aim Catalog")

    api_generator._generate_test_cases(suite)

    assert len(suite.tests) == 5
    assert {test.timeout for test in suite.tests} == {"100 minutes"}


# -- start_suite EXCLUDE_TAGS short-circuit --


class _MockSuiteData:
    """Minimal running.TestSuite stand-in for start_suite."""

    def __init__(self, name, variables):
        self.name = name
        self.parent = None
        self.tests = []

        class _Resource:
            pass

        self._resource = _Resource()
        self._resource.variables = [_MockVariable(f"${{{k}}}", v) for k, v in variables.items()]

    @property
    def resource(self):
        return self._resource


def test_start_suite_short_circuits_when_aim_catalog_excluded(api_generator, monkeypatch):
    """EXCLUDE_TAGS:aim-catalog removes every static test without API discovery.

    Opting out must not call the API (which would raise 'no Ready AIMs' on clusters
    without them), and must leave the suite genuinely empty — the placeholder has to
    go too, or an excluded catalog reports a passing test it never ran.
    """

    def _boom(*args, **kwargs):
        raise AssertionError("_load_models_from_api must not be called when aim-catalog is excluded")

    monkeypatch.setattr(api_generator, "_load_models_from_api", _boom)
    monkeypatch.setattr(
        api_generator,
        "_get_variable",
        lambda _suite, name: "aim-catalog" if name == "EXCLUDE_TAGS" else None,
    )
    suite = RobotTestSuite.from_file_system(Path(__file__).parent / "aim_catalog.robot")

    api_generator.start_suite(suite, None)

    assert len(suite.tests) == 0
    assert api_generator.models == []


def test_every_static_test_carries_the_aim_catalog_tag():
    """`--exclude aim-catalog` can only prune the suite if no static test escapes the tag.

    This is a contract, not an implementation detail, and nothing else guards it. RF
    prunes a suite at build time only when *every* test in it is excluded, so a single
    static test missing `aim-catalog` silently turns the exclusion into a no-op — the
    listener fires and runs a full GPU catalog against the cluster instead of skipping
    it. Asserting over all static tests (rather than just the placeholder) is what makes
    this catch a newly added test that forgets the tag.
    """
    suite = RobotTestSuite.from_file_system(Path(__file__).parent / "aim_catalog.robot")

    assert suite.tests, "aim_catalog.robot must ship at least one static test"
    untagged = [test.name for test in suite.tests if "aim-catalog" not in [str(tag) for tag in test.tags]]
    assert not untagged, f"static tests missing the aim-catalog tag: {untagged}"


def test_placeholder_keeps_its_control_tag():
    """`DYNAMIC_TEST_PLACEHOLDER` keeps RF from pruning the suite as empty before the
    listener runs, and is how `_remove_tests_with_tag` finds the test to drop."""
    suite = RobotTestSuite.from_file_system(Path(__file__).parent / "aim_catalog.robot")

    placeholders = [t for t in suite.tests if "DYNAMIC_TEST_PLACEHOLDER" in [str(tag) for tag in t.tags]]
    assert len(placeholders) == 1, f"expected exactly one placeholder test, found {len(placeholders)}"


def test_start_suite_non_catalog_suite_is_noop(api_generator, monkeypatch):
    """For a non-catalog suite the listener does nothing (and never calls the API)."""

    def _boom(*args, **kwargs):
        raise AssertionError("_load_models_from_api must not be called for a non-catalog suite")

    monkeypatch.setattr(api_generator, "_load_models_from_api", _boom)

    data = _MockSuiteData("Some Other Suite", {})
    api_generator.start_suite(data, None)

    assert data.tests == []


class _FakeResponse:
    def __init__(self, body):
        self._body = body
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _aim(image_name, gpu_count):
    return {
        "resource_name": image_name,
        "image_reference": f"registry.example.com/{image_name}:1.0.0",
        "status_value": "Ready",
        "status": {
            "imageMetadata": {
                "model": {
                    "canonicalName": f"example/{image_name}",
                    "recommendedDeployments": [{"gpuCount": gpu_count}],
                }
            }
        },
    }


def test_api_discovery_fetches_all_ready_pages(api_generator, monkeypatch):
    """A selected AIM remains discoverable when it appears after the first API page."""
    page_one = [_aim(f"aim-placeholder-{index}", 8) for index in range(100)]
    selected = _aim("aim-selected-placeholder", 1)
    calls = []

    def _get(_url, **kwargs):
        calls.append(kwargs["params"])
        if kwargs["params"]["page"] == 1:
            return _FakeResponse({"data": page_one, "pagination": {"page": 1, "pageSize": 100, "total": 101}})
        return _FakeResponse({"data": [selected], "pagination": {"page": 2, "pageSize": 100, "total": 101}})

    monkeypatch.setattr("requests.get", _get)
    monkeypatch.setattr(api_generator, "_resolve_api_url", lambda: "https://api.example.test")
    monkeypatch.setattr(api_generator, "_get_auth_token", lambda: None)

    models = api_generator._load_models_from_api()

    assert [call["page"] for call in calls] == [1, 2]
    assert all(call["pageSize"] == 100 and call["statusFilter"] == "Ready" for call in calls)
    assert any(model["image_name"] == "aim-selected-placeholder" for model in models)


def test_selected_model_runs_authored_robot_lifecycle(api_generator, monkeypatch):
    """The selector keeps the executable BDD lifecycle and skips generated tests."""
    suite_path = Path(__file__).parent / "aim_catalog.robot"
    suite = RobotTestSuite.from_file_system(suite_path)

    def _boom(*_args, **_kwargs):
        raise AssertionError("selected-AIM scenario must resolve its model through Robot keywords")

    monkeypatch.setattr(api_generator, "_load_models_from_api", _boom)
    monkeypatch.setattr(
        api_generator,
        "resolve_ready_aim",
        lambda _name: {
            "image_name": "aim-selected-placeholder",
            "docker_image": "registry.example.com/aim-selected-placeholder:1.0.0",
            "gpu_count": 1,
            "requires_hf_token": False,
        },
    )
    monkeypatch.setattr(
        api_generator,
        "_get_variable",
        lambda _suite, name: {
            "EXCLUDE_TAGS": None,
            "AIM_CATALOG_MODEL": "aim-selected-placeholder",
        }.get(name),
    )

    api_generator.start_suite(suite, None)

    assert [test.name for test in suite.tests] == ["One selected Ready AIM completes its lifecycle"]
    assert [keyword.name for keyword in suite.tests[0].body] == [
        "Given a selected Ready AIM from the catalog",
        "When the selected AIM is deployed",
        "Then the selected AIM should reach Running state",
        "And the selected AIM should serve inference",
        "And the selected AIM should be removed when undeployed",
    ]


def test_selected_listener_publishes_exact_resolved_state(api_generator, monkeypatch):
    """The selected lifecycle reuses the listener's exact resolved AIM state."""
    suite = RobotTestSuite.from_file_system(Path(__file__).parent / "aim_catalog.robot")
    selected = {
        "aim": _aim("aim-selected-placeholder", 4),
        "image_name": "aim-selected-placeholder",
        "docker_image": "registry.example.com/aim-selected-placeholder:2.0.0",
        "gpu_count": 4,
        "requires_hf_token": True,
    }
    published = {}

    class _BuiltIn:
        def set_suite_variable(self, name, value):
            published[name] = value

    monkeypatch.setattr(api_generator, "resolve_ready_aim", lambda _name: selected)
    monkeypatch.setattr(
        api_generator,
        "_get_variable",
        lambda _suite, name: {
            "EXCLUDE_TAGS": None,
            "AIM_CATALOG_MODEL": "aim-selected-placeholder",
            "INCLUDE_TAGS": None,
        }.get(name),
    )
    monkeypatch.setattr("robot.libraries.BuiltIn.BuiltIn", _BuiltIn)

    api_generator.start_suite(suite, None)

    assert published == {
        "${SELECTED_AIM_RECORD}": selected["aim"],
        "${SELECTED_AIM_IMAGE}": selected["docker_image"],
        "${SELECTED_AIM_HF}": True,
        "${MAX_GPU_COUNT}": 4,
    }


@pytest.mark.parametrize(
    ("include_tags", "exclude_tags", "expected_count"),
    [
        ("smoke", None, 1),
        ("model:aim-selected-placeholder", None, 1),
        ("gpus:4", None, 1),
        ("version:2.0.0", None, 1),
        ("requires-hf-token", None, 1),
        ("metrics", None, 0),
        ("model:another-aim", None, 0),
        (None, "lifecycle", 0),
        (None, "requires-hf-token", 0),
    ],
)
def test_selected_model_applies_variable_tag_filters(
    api_generator, monkeypatch, include_tags, exclude_tags, expected_count
):
    """Selected-model runs honor static and model-derived tag filters."""
    suite_path = Path(__file__).parent / "aim_catalog.robot"
    suite = RobotTestSuite.from_file_system(suite_path)
    monkeypatch.setattr(
        api_generator,
        "resolve_ready_aim",
        lambda _name: {
            "image_name": "aim-selected-placeholder",
            "docker_image": "registry.example.com/aim-selected-placeholder:2.0.0",
            "gpu_count": 4,
            "requires_hf_token": True,
        },
    )
    monkeypatch.setattr(
        api_generator,
        "_get_variable",
        lambda _suite, name: {
            "EXCLUDE_TAGS": exclude_tags,
            "AIM_CATALOG_MODEL": "aim-selected-placeholder",
            "INCLUDE_TAGS": include_tags,
        }.get(name),
    )

    api_generator.start_suite(suite, None)

    assert len(suite.tests) == expected_count
    if expected_count:
        assert {
            "model:aim-selected-placeholder",
            "gpus:4",
            "version:2.0.0",
            "requires-hf-token",
        }.issubset(set(suite.tests[0].tags))


def test_empty_selector_preserves_generated_full_catalog(api_generator, monkeypatch):
    """Without a selector, the authored opt-in scenario is replaced by catalog tests."""
    suite_path = Path(__file__).parent / "aim_catalog.robot"
    suite = RobotTestSuite.from_file_system(suite_path)
    model = api_generator._map_aim_to_model(_aim("aim-catalog-placeholder", 2))

    monkeypatch.setattr(api_generator, "_load_models_from_api", lambda **_kwargs: [model])
    monkeypatch.setattr(
        api_generator,
        "_get_variable",
        lambda _suite, name: {
            "EXCLUDE_TAGS": None,
            "AIM_CATALOG_MODEL": None,
            "AIM_CATALOG_FILTER": None,
            "TEST_MODE": "quick",
            "INCLUDE_TAGS": None,
        }.get(name),
    )

    api_generator.start_suite(suite, None)

    assert [test.name for test in suite.tests] == [
        "Deploy example/aim-catalog-placeholder",
        "Verify example/aim-catalog-placeholder reaches Running state",
        "Undeploy example/aim-catalog-placeholder",
    ]
    assert all("SELECTED_AIM_LIFECYCLE" not in test.tags for test in suite.tests)


def test_resolve_ready_aim_pages_to_exact_selected_basename(api_generator, monkeypatch):
    """Resolution reaches page two, ignores prefix collisions, and stops at total."""
    page_one = [_aim(f"aim-placeholder-{index}", 1) for index in range(99)]
    page_one.append(_aim("aim-selected-placeholder-large", 8))
    selected = _aim("aim-selected-placeholder", 2)
    calls = []

    def _get(_url, **kwargs):
        calls.append(kwargs["params"])
        if kwargs["params"]["page"] == 1:
            return _FakeResponse({"data": page_one, "pagination": {"page": 1, "pageSize": 100, "total": 101}})
        return _FakeResponse({"data": [selected], "pagination": {"page": 2, "pageSize": 100, "total": 101}})

    monkeypatch.setattr("requests.get", _get)
    monkeypatch.setattr(api_generator, "_resolve_api_url", lambda: "https://api.example.test")
    monkeypatch.setattr(api_generator, "_get_auth_token", lambda: None)

    result = api_generator.resolve_ready_aim("registry.example.com/aim-selected-placeholder:1.0.0")

    assert result["aim"] is selected
    assert result["image_name"] == "aim-selected-placeholder"
    assert result["docker_image"] == "registry.example.com/aim-selected-placeholder:1.0.0"
    assert result["gpu_count"] == 2
    assert [call["page"] for call in calls] == [1, 2]


@pytest.mark.parametrize(
    ("deployments", "expected"),
    [
        ([{"num_gpus": 4}], 4),
        ([{"gpus": 8}], 8),
        (["invalid", {"gpuCount": "bad"}, {"gpu_count": 0}], 1),
    ],
)
def test_resolve_ready_aim_reuses_robust_gpu_mapping(api_generator, monkeypatch, deployments, expected):
    """Selected lifecycle metadata uses the generator's established GPU parser."""
    aim = _aim("aim-selected-placeholder", 1)
    aim["status"]["imageMetadata"]["model"]["recommendedDeployments"] = deployments
    monkeypatch.setattr(api_generator, "_fetch_ready_aim_records", lambda: [aim])

    assert api_generator.resolve_ready_aim("aim-selected-placeholder")["gpu_count"] == expected


def test_resolve_ready_aim_bare_name_takes_highest_version(api_generator, monkeypatch):
    """A bare selector follows the catalog's highest-version rule, as discovery does."""
    first = _aim("aim-selected-placeholder", 1)
    second = _aim("aim-selected-placeholder", 1)
    second["image_reference"] = "registry.example.com/aim-selected-placeholder:2.0.0"
    monkeypatch.setattr(api_generator, "_fetch_ready_aim_records", lambda: [first, second])

    result = api_generator.resolve_ready_aim("aim-selected-placeholder")

    assert result["aim"] is second
    assert result["docker_image"] == "registry.example.com/aim-selected-placeholder:2.0.0"


def test_resolve_ready_aim_pinned_version_selects_that_version(api_generator, monkeypatch):
    """A tag-pinned selector resolves to exactly that version, never a newer one."""
    first = _aim("aim-selected-placeholder", 1)
    second = _aim("aim-selected-placeholder", 1)
    second["image_reference"] = "registry.example.com/aim-selected-placeholder:2.0.0"
    monkeypatch.setattr(api_generator, "_fetch_ready_aim_records", lambda: [first, second])

    result = api_generator.resolve_ready_aim("registry.example.com/aim-selected-placeholder:1.0.0")

    assert result["aim"] is first
    assert result["docker_image"] == "registry.example.com/aim-selected-placeholder:1.0.0"


def test_resolve_ready_aim_pinned_missing_version_is_rejected(api_generator, monkeypatch):
    """A pinned version that is not Ready fails instead of falling back to another."""
    monkeypatch.setattr(api_generator, "_fetch_ready_aim_records", lambda: [_aim("aim-selected-placeholder", 1)])

    with pytest.raises(RuntimeError, match="not Ready or does not exist"):
        api_generator.resolve_ready_aim("registry.example.com/aim-selected-placeholder:9.9.9")
