# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Kubectl-based inference-pod inspection helpers for AIWB E2E tests.

The runtime-profile E2E scenarios must prove that profile values —
container image, accelerator product and count, precision, engine args, and
env vars — actually reach the *live inference pod*, not just the AIMService /
AIMProfile custom resources. The existing kubectl keywords stop at the CR
boundary (``AIMService CR should have runtime profile overrides``) and at pod
*count* (``Get AIM running pod count``); none of them read the running
container's spec.

This library resolves the predictor pod for an AIMService and exposes its
effective runtime configuration so behavioural keywords can assert on it.
Shell invocation and JSON parsing live here, per the project convention that
keyword bodies in ``.resource`` files delegate real logic to Python libraries
(see ``AIMModelHelper.py``).

aim-engine (an external operator) owns the exact pod shape, so the extractors
search across containers and both supported engine contracts. Direct engines
receive engine settings in container ``env``/``args``; AIM-runtime images
receive them in the profile YAML ConfigMap mounted by the running pod. Resource
limits and node placement remain direct pod properties. This keeps assertions
resilient to aim-engine-side layout changes while still proving the values
reached the runtime used by the pod.
"""

import json
import subprocess

import yaml
from robot.api import logger
from robot.api.deco import keyword

_KUBECTL_TIMEOUT = 60

# Sidecars/init containers injected by the serving stack (KServe, service mesh,
# weight loaders) are not the inference container. Skip them when locating the
# container that carries the runtime profile so assertions target the real
# model server.
_NON_INFERENCE_CONTAINERS = frozenset(
    {
        "queue-proxy",
        "storage-initializer",
        "istio-proxy",
        "istio-init",
        "aim-sidecar",
    }
)

# Container waiting reasons a pod never recovers from on its own. Seeing one of
# these means the deploy is broken now, not slow, so a test can stop waiting.
_TERMINAL_WAITING_REASONS = frozenset(
    {
        "ImagePullBackOff",
        "ErrImagePull",
        "InvalidImageName",
        "CrashLoopBackOff",
        "CreateContainerConfigError",
    }
)


@keyword("Terminal AIM Pod States")
def terminal_aim_pod_states(pods_json: str, service_name: str, superseded: set[str] | None = None) -> list[str]:
    """Return terminal waiting states for pods belonging to an AIM service.

    ``superseded`` names ReplicaSets a newer revision has already replaced; their pods
    are skipped. Callers that cannot resolve supersession omit it and every matching pod
    is judged, which is the historical behaviour.
    """
    terminal_states = []
    for pod in json.loads(pods_json).get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "")
        if not pod_name.startswith(f"{service_name}-"):
            continue
        if superseded and _owning_replica_set(pod) in superseded:
            continue
        status = pod.get("status") or {}
        containers = (status.get("containerStatuses") or []) + (status.get("initContainerStatuses") or [])
        for container in containers:
            reason = ((container.get("state") or {}).get("waiting") or {}).get("reason")
            if reason in _TERMINAL_WAITING_REASONS:
                terminal_states.append(f"{pod_name}/{container['name']}={reason}")
    return terminal_states


def _run_kubectl(args: list[str], action: str) -> str:
    try:
        result = subprocess.run(
            ["kubectl", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=_KUBECTL_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError(f"kubectl not found on PATH — cannot {action}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl timed out after {_KUBECTL_TIMEOUT}s while trying to {action}")
    if result.returncode != 0:
        raise RuntimeError(f"kubectl failed while trying to {action}: {result.stderr}")
    return result.stdout


def _try_kubectl_json(args: list[str], action: str) -> dict | None:
    """Return parsed kubectl JSON, or None when kubectl is unavailable or the call fails.

    Callers use this for best-effort inspection that must never turn a missing or
    misconfigured kubectl into a test failure of its own.
    """
    try:
        raw = _run_kubectl(args, action)
    except RuntimeError:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _replica_set_revision(replica_set: dict) -> int:
    raw = replica_set.get("metadata", {}).get("annotations", {}).get("deployment.kubernetes.io/revision")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _superseded_replica_sets(replica_sets: list[dict]) -> set[str]:
    """Names of ReplicaSets a newer revision of the same Deployment has already replaced.

    During a rollout both revisions are desired=1 until the new pod turns Ready, so
    "desired replicas" cannot distinguish them; rank by the revision annotation the
    Deployment controller stamps, falling back to creation order when it is absent.
    """
    newest: dict[str, tuple[tuple, str]] = {}
    owned: list[tuple[str, str]] = []
    for replica_set in replica_sets:
        meta = replica_set.get("metadata", {})
        name = meta.get("name")
        owner = next(
            (o.get("name") for o in meta.get("ownerReferences", []) if o.get("kind") == "Deployment"),
            None,
        )
        if not name or owner is None:
            continue
        owned.append((owner, name))
        rank = (_replica_set_revision(replica_set), meta.get("creationTimestamp", ""), name)
        if owner not in newest or rank > newest[owner][0]:
            newest[owner] = (rank, name)
    current = {name for _, name in newest.values()}
    return {name for _, name in owned if name not in current}


def _owning_replica_set(pod: dict) -> str | None:
    return next(
        (o.get("name") for o in pod.get("metadata", {}).get("ownerReferences", []) if o.get("kind") == "ReplicaSet"),
        None,
    )


@keyword("AIM Pods Should Not Be In A Terminal State")
def aim_pods_should_not_be_in_a_terminal_state(name: str, namespace: str) -> None:
    """Fail when a *live* pod of AIM ``name`` is stuck in a terminal image or crash state.

    Pods belonging to a superseded ReplicaSet are ignored. aim-engine can publish the
    predictor Deployment before the profile ConfigMap it mounts exists, so revision 1
    starts without the profile and crash-loops while revision 2 — the one that will
    actually serve — is still pulling weights. Failing on the abandoned pod reports a
    broken deploy for one that is recovering on its own. A genuinely broken image still
    fails in seconds, because there the crash-looping pod *is* the current revision.

    No-op when the pod listing is unavailable, and silent when no pods exist yet (early
    Pending is normal). When only the ReplicaSet listing is unavailable the check narrows
    rather than stopping: a pod with no ReplicaSet owner cannot be superseded by a newer
    revision, so it is still judged, while owned pods are skipped because there is no way
    to tell a superseded one from a current one. Skips are logged at DEBUG (not INFO —
    this runs on every poll, and an INFO line per poll floods output.xml).
    """
    pods = _try_kubectl_json(["get", "pods", "-n", namespace, "-o", "json"], f"list pods in namespace {namespace}")
    if pods is None:
        logger.debug(f"Terminal-state check skipped for AIM {name}: cannot list pods in namespace {namespace}")
        return
    replica_sets = _try_kubectl_json(
        ["get", "replicasets", "-n", namespace, "-o", "json"],
        f"list replicasets in namespace {namespace}",
    )
    # None means "supersession is unknowable", which is not the same as "nothing is
    # superseded" — the latter would judge every pod and reintroduce the false failure.
    superseded = None if replica_sets is None else _superseded_replica_sets(replica_sets.get("items", []))
    if superseded is None:
        logger.debug(
            f"Terminal-state check narrowed for AIM {name}: cannot list replicasets in namespace "
            f"{namespace}, so only pods with no ReplicaSet owner are checked"
        )

    if superseded is None:
        # Without ReplicaSets, only unowned pods are safe to judge: an owned one could be
        # a superseded revision. Preserve that uncertainty in the JSON handed to the
        # shared state extractor rather than teaching it about kubectl failures.
        pods = {"items": [pod for pod in pods.get("items", []) if _owning_replica_set(pod) is None]}
        superseded = set()
    offenders = terminal_aim_pod_states(json.dumps(pods), name, superseded)

    # Only the short "pod/container=reason" strings reach the failure message — never the
    # full pod JSON — because this runs on every poll and Robot records each failure.
    if offenders:
        raise AssertionError(
            f"AIM {name} pod(s) in a terminal state: {offenders}. "
            "Failing fast (broken image / crash-loop) instead of waiting for Running."
        )


def _predictor_pod(service_name: str, namespace: str) -> dict:
    """Return the JSON of the most recently created Running predictor pod for ``service_name``.

    Mirrors the deployment/pod matching in ``Get AIM running pod count``
    (``aiwb_aims.resource``): the predictor Deployment is named
    ``<service>-<hash>-predictor`` and its pods are prefixed with the
    Deployment name. Selecting on the name prefix keeps this independent of
    whatever labels aim-engine stamps on a given cluster.
    """
    deployments_raw = _run_kubectl(
        ["get", "deployments", "-n", namespace, "-o", "json"],
        f"list deployments in namespace {namespace}",
    )
    deployments = json.loads(deployments_raw).get("items", [])
    predictor_names = [
        d["metadata"]["name"]
        for d in deployments
        if d["metadata"]["name"].startswith(f"{service_name}-") and d["metadata"]["name"].endswith("-predictor")
    ]
    if not predictor_names:
        raise AssertionError(
            f"No predictor Deployment matching {service_name}-*-predictor found in namespace {namespace}"
        )

    # A rollout can leave more than one predictor Deployment (old + new) around,
    # each with Running pods at the same time. Scope the query to Running pods and,
    # among those belonging to any matching predictor Deployment, return the most
    # recently created one so assertions track the latest rollout rather than an
    # arbitrary stale revision. creationTimestamp is RFC3339 and therefore sorts
    # correctly lexicographically.
    pods_raw = _run_kubectl(
        ["get", "pods", "-n", namespace, "--field-selector=status.phase=Running", "-o", "json"],
        f"list Running pods in namespace {namespace}",
    )
    pods = json.loads(pods_raw).get("items", [])
    matching = [
        pod
        for pod in pods
        if any(pod["metadata"]["name"].startswith(f"{deployment_name}-") for deployment_name in predictor_names)
    ]
    if not matching:
        raise AssertionError(f"No Running pod for any predictor Deployment {predictor_names} in namespace {namespace}")
    return max(matching, key=lambda pod: pod["metadata"].get("creationTimestamp", ""))


def _inference_containers(pod: dict) -> list[dict]:
    containers = pod.get("spec", {}).get("containers", [])
    inference = [c for c in containers if c.get("name") not in _NON_INFERENCE_CONTAINERS]
    # Fall back to every container rather than raising: a cluster may name the
    # inference container something this list does not anticipate, and an
    # over-eager skip would hide a real value that did reach the pod.
    return inference or containers


def _gpu_limit(container: dict) -> int:
    limits = container.get("resources", {}).get("limits", {})
    for resource_name, value in limits.items():
        if "gpu" in resource_name.lower():
            return int(value)
    return 0


def _env_map(container: dict) -> dict[str, str]:
    env_map: dict[str, str] = {}
    for entry in container.get("env", []):
        name = entry.get("name")
        if name is not None and "value" in entry:
            env_map[name] = entry["value"]
    return env_map


def _arg_tokens(container: dict) -> list[str]:
    return [str(token) for token in (container.get("command", []) + container.get("args", []))]


def _volume_by_name(pod: dict, name: str) -> dict | None:
    return next((volume for volume in pod.get("spec", {}).get("volumes", []) if volume.get("name") == name), None)


def _mounted_profile_config_map(pod: dict, container: dict) -> tuple[str, str] | None:
    """Return the ConfigMap and key selected by AIM_PROFILE_ID."""
    profile_id = _env_map(container).get("AIM_PROFILE_ID")
    if not profile_id:
        return None

    profile_filename = f"{profile_id.rsplit('/', 1)[-1]}.yaml"
    for mount in container.get("volumeMounts", []):
        if "/profiles/" not in mount.get("mountPath", ""):
            continue
        volume = _volume_by_name(pod, mount.get("name", ""))
        config_map_name = (volume or {}).get("configMap", {}).get("name")
        if config_map_name:
            return config_map_name, profile_filename
    return None


def _profile_runtime_config(pod: dict, container: dict, namespace: str) -> dict:
    mounted_profile = _mounted_profile_config_map(pod, container)
    if mounted_profile is None:
        return {"env": {}, "args": {}}

    config_map_name, profile_filename = mounted_profile
    config_map_raw = _run_kubectl(
        ["get", "configmap", config_map_name, "-n", namespace, "-o", "json"],
        f"read runtime profile ConfigMap {config_map_name} in namespace {namespace}",
    )
    config_map = json.loads(config_map_raw)
    data = config_map.get("data", {})
    profile_yaml = data.get(profile_filename)
    if profile_yaml is None:
        raise AssertionError(
            f"Runtime profile '{profile_filename}' selected by pod {pod['metadata']['name']} "
            f"is absent from ConfigMap {config_map_name}; keys: {sorted(data)}"
        )

    try:
        profile = yaml.safe_load(profile_yaml) or {}
    except yaml.YAMLError as error:
        raise AssertionError(
            f"Runtime profile '{profile_filename}' in ConfigMap {config_map_name} is not valid YAML: {error}"
        ) from error
    if not isinstance(profile, dict):
        raise AssertionError(
            f"Runtime profile '{profile_filename}' in ConfigMap {config_map_name} must contain a YAML mapping"
        )
    engine_env = profile.get("env_vars") or {}
    engine_args = profile.get("engine_args") or {}
    if not isinstance(engine_env, dict) or not isinstance(engine_args, dict):
        raise AssertionError(
            f"Runtime profile '{profile_filename}' in ConfigMap {config_map_name} "
            "must contain map-shaped env_vars and engine_args"
        )
    return {"env": engine_env, "args": engine_args}


def _engine_runtime_config(pod: dict, container: dict, namespace: str) -> dict:
    """Return effective engine settings for direct and AIM-runtime images."""
    container_env = _env_map(container)
    container_args = _arg_tokens(container)
    profile = _profile_runtime_config(pod, container, namespace)
    return {
        "env": {**container_env, **profile["env"]},
        "args": profile["args"],
        "argTokens": container_args,
    }


@keyword("Get Inference Pod Runtime Config")
def get_inference_pod_runtime_config(service_name: str, namespace: str) -> dict:
    """Return the effective runtime config of the inference container.

    Shape::

        {
            "podName": str,
            "containerName": str,
            "image": str,
            "acceleratorCount": int,        # from resources.limits *gpu*
            "nodeSelector": dict,
            "env": {name: value, ...},          # effective engine + container env
            "engineArgs": {name: value, ...},   # mounted AIM profile engine_args
            "argTokens": [token, ...],          # direct-engine command + args
        }

    Picks the inference container with a GPU limit when one is present,
    otherwise the first non-sidecar container.
    """
    pod = _predictor_pod(service_name, namespace)
    containers = _inference_containers(pod)
    primary = next((c for c in containers if _gpu_limit(c) > 0), containers[0])
    engine_runtime = _engine_runtime_config(pod, primary, namespace)
    return {
        "podName": pod["metadata"]["name"],
        "containerName": primary.get("name", ""),
        "image": primary.get("image", ""),
        "acceleratorCount": _gpu_limit(primary),
        "nodeSelector": pod.get("spec", {}).get("nodeSelector", {}),
        "env": engine_runtime["env"],
        "engineArgs": engine_runtime["args"],
        "argTokens": engine_runtime["argTokens"],
    }


@keyword("Inference Pod Should Use Image")
def inference_pod_should_use_image(service_name: str, namespace: str, expected_image: str) -> None:
    """Assert at least one inference container runs ``expected_image``.

    Substring match: aim-engine may resolve a family/tag to a fully qualified
    reference (registry host, digest), so the chosen image is expected to
    *contain* the value the user supplied rather than equal it byte-for-byte.
    """
    pod = _predictor_pod(service_name, namespace)
    images = [c.get("image", "") for c in _inference_containers(pod)]
    if not any(expected_image in image for image in images):
        raise AssertionError(
            f"No inference container uses image containing '{expected_image}'. "
            f"Container images on pod {pod['metadata']['name']}: {images}"
        )


@keyword("Inference Pod Should Use Image Pull Secrets")
def inference_pod_should_use_image_pull_secrets(service_name: str, namespace: str, *expected_secrets: str) -> None:
    """Assert the inference pod pulls its images with every one of ``expected_secrets``.

    Containment rather than equality: the cluster may add its own registry
    credentials to the pod alongside the ones the user selected.
    """
    if not expected_secrets:
        raise ValueError("At least one expected image pull secret is required")
    pod = _predictor_pod(service_name, namespace)
    # The pod spec allows a null list and entries without a name; neither names a secret.
    actual = {s["name"] for s in pod["spec"].get("imagePullSecrets") or [] if s.get("name")}
    missing = sorted(set(expected_secrets) - actual)
    if missing:
        raise AssertionError(
            f"Inference pod {pod['metadata']['name']} is missing image pull secrets {missing}; it uses {sorted(actual)}"
        )


@keyword("Inference Pod Should Request Accelerator Count")
def inference_pod_should_request_accelerator_count(service_name: str, namespace: str, expected_count: int) -> None:
    """Assert the inference container requests ``expected_count`` accelerators."""
    expected = int(expected_count)
    pod = _predictor_pod(service_name, namespace)
    counts = [_gpu_limit(c) for c in _inference_containers(pod)]
    if expected not in counts:
        raise AssertionError(
            f"No inference container requests {expected} accelerators "
            f"(found GPU limits {counts} on pod {pod['metadata']['name']})"
        )


@keyword("Inference Pod Should Request No Accelerators")
def inference_pod_should_request_no_accelerators(service_name: str, namespace: str) -> None:
    """Assert *no* inference container requests a GPU (CPU/EPYC serving).

    Requires every candidate inference container to have a zero GPU limit, so a
    GPU-pinned model server alongside a no-GPU sidecar cannot pass — unlike checking
    that a zero merely appears among the per-container counts.
    """
    pod = _predictor_pod(service_name, namespace)
    spec = pod.get("spec", {})
    containers = [*spec.get("containers", []), *spec.get("initContainers", [])]
    if not containers:
        raise AssertionError(f"Inference pod {pod['metadata']['name']} has no regular or init containers")
    counts = [_gpu_limit(c) for c in containers]
    if any(count > 0 for count in counts):
        raise AssertionError(
            f"Inference pod {pod['metadata']['name']} has a GPU-requesting container "
            f"(GPU limits {counts}); expected all zero for CPU/EPYC serving"
        )


def _is_positive_label_value(value: object) -> bool:
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}


def _label_or_selector_matches_product(key: object, value: object, expected_product: str) -> bool:
    """Match positive labels/selectors without treating generic CPU keys as placement proof."""
    key_text = str(key)
    value_text = str(value)
    positive = _is_positive_label_value(value)
    # aim-accelerator.CPU is written on every node, including GPU nodes. Its key
    # is therefore never evidence of CPU placement; a literal selector value
    # such as accelerator=CPU remains meaningful.
    key_match = expected_product.upper() != "CPU" and expected_product in key_text and positive
    value_match = expected_product in value_text and positive
    return key_match or value_match


def _node_has_gpu_accelerator(labels: dict) -> bool:
    return any("aim-accelerator.GPU" in str(key) and _is_positive_label_value(value) for key, value in labels.items())


@keyword("Inference Pod Should Be Scheduled On Accelerator")
def inference_pod_should_be_scheduled_on_accelerator(service_name: str, namespace: str, expected_product: str) -> None:
    """Assert the pod is positively constrained to ``expected_product`` accelerators."""
    pod = _predictor_pod(service_name, namespace)
    spec = pod.get("spec", {})

    node_selector = spec.get("nodeSelector", {})
    product_matches = any(
        _label_or_selector_matches_product(key, value, expected_product) for key, value in node_selector.items()
    )

    affinity = spec.get("affinity", {}).get("nodeAffinity", {})
    required = affinity.get("requiredDuringSchedulingIgnoredDuringExecution", {})
    for term in required.get("nodeSelectorTerms", []):
        for expr in term.get("matchExpressions", []):
            operator = expr.get("operator")
            if operator == "Exists":
                key = str(expr.get("key", ""))
                product_matches |= expected_product.upper() != "CPU" and expected_product in key
            elif operator == "In":
                product_matches |= any(expected_product in str(v) for v in expr.get("values", []))

    node_name = spec.get("nodeName")
    if node_name:
        node_raw = _run_kubectl(["get", "node", node_name, "-o", "json"], f"read node {node_name}")
        node_labels = json.loads(node_raw).get("metadata", {}).get("labels", {})
        expects_cpu = expected_product.upper() == "CPU" or expected_product.upper().startswith("EPYC_")
        if expects_cpu and _node_has_gpu_accelerator(node_labels):
            raise AssertionError(
                f"Inference pod {pod['metadata']['name']} is scheduled on GPU node {node_name}; "
                f"expected CPU/EPYC-only placement"
            )
        product_matches |= any(
            _label_or_selector_matches_product(key, value, expected_product) for key, value in node_labels.items()
        )

    if product_matches:
        return

    raise AssertionError(
        f"Inference pod {pod['metadata']['name']} is not constrained to accelerator product "
        f"'{expected_product}' via nodeSelector, node affinity, or scheduled-node labels"
    )


@keyword("Inference Pod Should Use Engine Env")
def inference_pod_should_use_engine_env(service_name: str, namespace: str, name: str, expected_value: str) -> None:
    """Assert the effective inference runtime env includes the expected value."""
    config = get_inference_pod_runtime_config(service_name, namespace)
    actual = config["env"].get(name)
    if actual is None:
        raise AssertionError(
            f"Env var '{name}' not present in effective runtime config for inference container "
            f"{config['containerName']} (pod {config['podName']}); env keys: {sorted(config['env'])}"
        )
    if str(actual) != expected_value:
        raise AssertionError(
            f"Env var '{name}' is '{actual}', expected '{expected_value}' in effective runtime config "
            f"for inference container {config['containerName']} (pod {config['podName']})"
        )


@keyword("Inference Pod Should Carry Engine Arg")
def inference_pod_should_carry_engine_arg(service_name: str, namespace: str, expected_value: str) -> None:
    """Assert ``expected_value`` appears in the effective engine arguments.

    AIM-runtime images load ``engineArgs`` from the mounted runtime profile;
    direct engines receive them in the container command/args. Check both
    supported contracts so the assertion follows the selected runtime.
    """
    config = get_inference_pod_runtime_config(service_name, namespace)
    profile_args = json.dumps(config["engineArgs"], sort_keys=True)
    tokens = config["argTokens"]
    if expected_value not in profile_args and not any(expected_value in token for token in tokens):
        raise AssertionError(
            f"Engine arg containing '{expected_value}' not found in effective runtime config for "
            f"inference container {config['containerName']} (pod {config['podName']}); "
            f"profile args: {config['engineArgs']}; command/args: {tokens}"
        )
