# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""Black-box Robot keywords for the cluster environment-check CLI."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from robot.api.deco import keyword, library


@library(scope="TEST")
class ClusterEnvironmentCheck:
    """Run the shipped CLI with fixture-backed kubectl responses."""

    def __init__(self) -> None:
        self._root = Path(__file__).resolve().parents[2]
        self._fixtures = Path(__file__).resolve().parents[1] / "fixtures"
        self._temp_dir: Path | None = None
        self._fixture: dict[str, list[Any]] | None = None
        self._result: subprocess.CompletedProcess[str] | None = None
        self._payload: dict[str, Any] | None = None
        self._skew_mode: str | None = None

    @keyword("a healthy cluster")
    def setup_healthy_cluster(self) -> None:
        self._load_fixture("healthy")

    @keyword("a cluster the operator cannot reach")
    def setup_unreachable_cluster(self) -> None:
        self._load_fixture("unreachable")

    @keyword("a Cilium cluster whose MTU is left to auto-detect")
    def setup_unpinned_cilium(self) -> None:
        self._load_fixture("cilium_unpinned")

    @keyword("a cluster where a model download exceeded its deadline")
    def setup_deadline_exceeded(self) -> None:
        self._load_fixture("deadline_exceeded")

    @keyword("a cluster running a GPU workload with no metrics delivered")
    def setup_active_gpu_without_metrics(self) -> None:
        self._load_fixture("gpu_metrics_active_zero")

    @keyword("an idle cluster with no GPU workload")
    def setup_idle_gpu_cluster(self) -> None:
        self._load_fixture("gpu_metrics_idle_zero")

    @keyword("a cluster whose test namespace has no GPU quota")
    def setup_test_namespace_without_gpu_quota(self) -> None:
        self._load_fixture("gpu_queue_zero")

    @keyword("a cluster whose workbench routing coordinates cannot be read")
    def setup_unreadable_route_coordinates(self) -> None:
        self._load_fixture("route_coordinates_unreadable")

    @keyword("a cluster with several known problems")
    def setup_multiple_problems(self) -> None:
        self._load_fixture("multiple_problems")

    @keyword("a cluster where the E2E test identity has no permissions")
    def setup_e2e_rbac_missing(self) -> None:
        self._load_fixture("e2e_rbac_missing")

    @keyword("a cluster where a project is stuck being deleted")
    def setup_airm_project_stuck(self) -> None:
        self._load_fixture("airm_project_stuck")

    @keyword("a cluster whose inference gateway address cannot be read")
    def setup_gateway_address_unreadable(self) -> None:
        self._load_fixture("gateway_address_unreadable")

    @keyword("the operator runs the environment check")
    def run_environment_check(self) -> None:
        if self._fixture is None:
            raise AssertionError("A fixture Given step must run before the environment check")
        self._temp_dir = Path(tempfile.mkdtemp(prefix="cluster-check-e2e-"))
        fake_kubectl = self._temp_dir / "kubectl"
        shutil.copy2(Path(__file__).with_name("fake_kubectl.py"), fake_kubectl)
        fake_kubectl.chmod(fake_kubectl.stat().st_mode | stat.S_IXUSR)
        fixture_file = self._temp_dir / "fixture.json"
        fixture_file.write_text(json.dumps(self._fixture))
        env = {
            **os.environ,
            "PATH": f"{self._temp_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "CLUSTER_CHECK_FIXTURE": str(fixture_file),
        }
        self._result = subprocess.run(
            ["bash", str(self._root / "scripts" / "environment-check.sh"), "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=env,
        )
        try:
            self._payload = json.loads(self._result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"Environment check did not emit JSON. rc={self._result.returncode}; "
                f"stdout={self._result.stdout!r}; stderr={self._result.stderr!r}"
            ) from exc

    # ---- release-spec-skew: build a throwaway core repo, then drive the subcommand ----
    @keyword("a cluster whose deployed products contain the target specifications")
    def setup_skew_compatible(self) -> None:
        self._skew_mode = "compatible"

    @keyword("a cluster whose deployed product predates the target specifications")
    def setup_skew_older(self) -> None:
        self._skew_mode = "older"

    @keyword("a cluster whose deployed revision cannot be established")
    def setup_skew_unresolvable(self) -> None:
        self._skew_mode = "unresolvable"

    @keyword("the operator runs the release-spec-skew check")
    def run_release_spec_skew(self) -> None:
        if self._skew_mode is None:
            raise AssertionError("A release-spec-skew Given step must run first")
        self._temp_dir = Path(tempfile.mkdtemp(prefix="release-spec-skew-e2e-"))
        repo = self._temp_dir / "core"
        repo.mkdir()
        self._git(repo, "init")
        self._git(repo, "config", "user.email", "e2e@example.com")
        self._git(repo, "config", "user.name", "E2E")
        older = self._commit(repo, "deployed product behavior")
        newer = self._commit(repo, "specification behavior")
        # deployed_tag names the immutable release tag the pods advertise; spec_revision is the commit
        # whose specs will run. compatible: deployed == spec. older: deployed predates spec.
        # unresolvable: pods advertise a mutable branch tag that resolves to no commit.
        if self._skew_mode == "compatible":
            self._git(repo, "tag", "2.0.2-rc.3", newer)
            deployed_tag, spec_revision = "2.0.2-rc.3", newer
        elif self._skew_mode == "older":
            self._git(repo, "tag", "2.0.2-rc.2", older)
            deployed_tag, spec_revision = "2.0.2-rc.2", newer
        else:
            deployed_tag, spec_revision = "main", newer

        fixture = self._skew_transcript(deployed_tag)
        fake_kubectl = self._temp_dir / "kubectl"
        shutil.copy2(Path(__file__).with_name("fake_kubectl.py"), fake_kubectl)
        fake_kubectl.chmod(fake_kubectl.stat().st_mode | stat.S_IXUSR)
        fixture_file = self._temp_dir / "fixture.json"
        fixture_file.write_text(json.dumps(fixture))
        env = {
            **os.environ,
            "PATH": f"{self._temp_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "CLUSTER_CHECK_FIXTURE": str(fixture_file),
        }
        self._result = subprocess.run(
            [
                "bash", str(self._root / "scripts" / "environment-check.sh"),
                "release-spec-skew", spec_revision, "--core-repo", str(repo), "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=env,
        )
        try:
            self._payload = json.loads(self._result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"release-spec-skew did not emit JSON. rc={self._result.returncode}; "
                f"stdout={self._result.stdout!r}; stderr={self._result.stderr!r}"
            ) from exc

    def _git(self, repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def _commit(self, repo: Path, message: str) -> str:
        (repo / "state.txt").write_text(message)
        self._git(repo, "add", "state.txt")
        self._git(repo, "commit", "-m", message)
        return self._git(repo, "rev-parse", "HEAD")

    @staticmethod
    def _skew_transcript(deployed_tag: str) -> dict[str, list[Any]]:
        """kubectl transcript for a completed rollout of both products on one running digest each."""
        transcript: dict[str, list[Any]] = {}
        for product, digest in (("aiwb", "a" * 64), ("airm", "b" * 64)):
            deploy = f"{product}-api"
            transcript[f"get deploy {deploy} -n {product} -o json"] = [
                0,
                json.dumps({
                    "metadata": {"generation": 3},
                    "spec": {"replicas": 1, "selector": {"matchLabels": {"app": deploy}}},
                    "status": {"observedGeneration": 3, "updatedReplicas": 1, "readyReplicas": 1,
                               "availableReplicas": 1, "unavailableReplicas": 0},
                }),
                "",
            ]
            transcript[f"get pods -n {product} -l app={deploy} -o json"] = [
                0,
                json.dumps({"items": [{
                    "metadata": {"name": f"{deploy}-1"},
                    "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                               "containerStatuses": [{
                                   "name": product,
                                   "image": f"registry.example.com/{deploy}:{deployed_tag}",
                                   "imageID": f"registry.example.com/{deploy}@sha256:{digest}",
                               }]},
                }]}),
                "",
            ]
        return transcript

    @keyword("the cluster should be reported healthy")
    def assert_cluster_healthy(self) -> None:
        self._assert_overall("ok")

    @keyword("the cluster should not be reported healthy")
    def assert_cluster_not_healthy(self) -> None:
        payload = self._require_payload()
        assert payload["overall"] != "ok", payload

    @keyword("the cluster should be reported unreachable")
    def assert_cluster_unreachable(self) -> None:
        self._assert_overall("unreachable")

    @keyword("the check should report problems")
    def assert_problems(self) -> None:
        self._assert_overall("problems")

    @keyword("the check should be inconclusive")
    def assert_inconclusive(self) -> None:
        self._assert_overall("inconclusive")

    @keyword("the ${name} check should be ${status}")
    def assert_check_status(self, name: str, status: str) -> None:
        payload = self._require_payload()
        match = next((check for check in payload["checks"] if check["name"] == name), None)
        assert match is not None, f"No check named {name!r}: {payload['checks']}"
        assert match["status"] == status, match

    @keyword("the result should name ${text}")
    def assert_result_names(self, text: str) -> None:
        payload = self._require_payload()
        rendered = json.dumps(payload)
        assert text.lower() in rendered.lower(), f"{text!r} not found in {rendered}"

    @keyword("the exit code should be ${expected}")
    def assert_exit_code(self, expected: str) -> None:
        result = self._require_result()
        assert result.returncode == int(expected), (
            f"Expected exit {expected}, got {result.returncode}; stderr={result.stderr!r}"
        )

    @keyword("Clean Up Environment Check")
    def cleanup_environment_check(self) -> None:
        """Remove the per-test fake-kubectl directory, including after a failed assertion."""
        if self._temp_dir is not None:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def _load_fixture(self, name: str) -> None:
        baseline = json.loads((self._fixtures / "healthy.json").read_text())
        if name != "healthy":
            baseline.update(json.loads((self._fixtures / f"{name}.json").read_text()))
        self._fixture = baseline

    def _assert_overall(self, expected: str) -> None:
        payload = self._require_payload()
        assert payload["overall"] == expected, payload

    def _require_payload(self) -> dict[str, Any]:
        if self._payload is None:
            raise AssertionError("The environment check has not run")
        return self._payload

    def _require_result(self) -> subprocess.CompletedProcess[str]:
        if self._result is None:
            raise AssertionError("The environment check has not run")
        return self._result
