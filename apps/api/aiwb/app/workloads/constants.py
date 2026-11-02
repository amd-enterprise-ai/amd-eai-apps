# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Constants for Kubernetes resources used in workload components."""

from dataclasses import dataclass

from ..config import AIWB_METADATA_PREFIX, EAI_APPS_METADATA_PREFIX
from .enums import WorkloadStatus

# Workload label keys for tracking and discovery
WORKLOAD_ID_LABEL = f"{EAI_APPS_METADATA_PREFIX}/workload-id"
MODEL_ID_LABEL = f"{AIWB_METADATA_PREFIX}/model-id"
MODEL_NAME_LABEL = f"{AIWB_METADATA_PREFIX}/model-name"
CANONICAL_NAME_LABEL = f"{AIWB_METADATA_PREFIX}/canonical-name"
DATASET_ID_LABEL = f"{AIWB_METADATA_PREFIX}/dataset-id"
CHART_ID_LABEL = f"{AIWB_METADATA_PREFIX}/chart-id"
DISPLAY_NAME_ANNOTATION = f"{AIWB_METADATA_PREFIX}/display-name"
DESCRIPTION_ANNOTATION = f"{AIWB_METADATA_PREFIX}/description"
TRAINING_OUTPUT_ANNOTATION = f"{AIWB_METADATA_PREFIX}/training-output"
WORKLOAD_TYPE_LABEL = f"{EAI_APPS_METADATA_PREFIX}/workload-type"
MODEL_SOURCE_TYPE_LABEL = f"{AIWB_METADATA_PREFIX}/model-source-type"


# Workload resource kinds
DEPLOYMENT_RESOURCE = "Deployment"
DEPLOYMENT_RESOURCE_PLURAL = "deployments"
JOB_RESOURCE = "Job"
JOB_RESOURCE_PLURAL = "jobs"


@dataclass(frozen=True)
class KubernetesResource:
    """Helper class for Kubernetes resources."""

    api_version: str
    kind: str
    plural: str


# Kubernetes resources to delete when removing workloads
WORKLOAD_RESOURCES = [
    KubernetesResource("apps/v1", DEPLOYMENT_RESOURCE, DEPLOYMENT_RESOURCE_PLURAL),
    KubernetesResource("batch/v1", JOB_RESOURCE, JOB_RESOURCE_PLURAL),
    KubernetesResource("", "Pod", "pods"),  # Explicitly delete Pods to handle Kueue's owner reference removal
    KubernetesResource("v1", "Service", "services"),
    KubernetesResource("v1", "ConfigMap", "configmaps"),
    KubernetesResource("apps/v1", "StatefulSet", "statefulsets"),
    KubernetesResource("apps/v1", "DaemonSet", "daemonsets"),
    KubernetesResource("batch/v1", "CronJob", "cronjobs"),
    KubernetesResource("networking.k8s.io/v1", "Ingress", "ingresses"),
    KubernetesResource("gateway.networking.k8s.io/v1", "HTTPRoute", "httproutes"),
    KubernetesResource("rbac.authorization.k8s.io/v1", "Role", "roles"),
    KubernetesResource("rbac.authorization.k8s.io/v1", "RoleBinding", "rolebindings"),
    KubernetesResource("v1", "ServiceAccount", "serviceaccounts"),
]

# Status filters for workloads (excludes DELETED)
ACTIVE_WORKLOAD_STATUSES = [
    WorkloadStatus.PENDING,
    WorkloadStatus.STARTING,
    WorkloadStatus.RUNNING,
    WorkloadStatus.COMPLETE,
    WorkloadStatus.FAILED,
    WorkloadStatus.UNKNOWN,
]

# K8s Deployment condition types and reasons
DEPLOYMENT_COND_REPLICA_FAILURE = "ReplicaFailure"
DEPLOYMENT_COND_AVAILABLE = "Available"
DEPLOYMENT_COND_PROGRESSING = "Progressing"
DEPLOYMENT_REASON_DEADLINE_EXCEEDED = "ProgressDeadlineExceeded"

# K8s Job condition types
JOB_COND_FAILED = "Failed"
JOB_COND_COMPLETE = "Complete"
JOB_COND_SUSPENDED = "Suspended"
JOB_COND_FAILURE_TARGET = "FailureTarget"
