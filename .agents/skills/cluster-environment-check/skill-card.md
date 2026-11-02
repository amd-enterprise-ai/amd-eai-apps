<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Skill Card

## Description

Checks a Kubernetes cluster for known, silent AI Workbench platform problems — Cilium MTU left unpinned, unhealthy shared storage, dead storage provisioners, stuck workloads, a broken GPU-metrics pipeline, GPUs with no matching AIM profile, unsynced secrets, missing MinIO, unhealthy AIWB API/UI, GPUs Kueue cannot schedule, missing AIMArtifact create permission, AIM route-hostname gaps that break catalog deploys, an E2E test identity missing the permissions its suites use, AIRM projects stuck deleting or without scheduling quota, an inference gateway erroring instead of refusing invalid keys, and deployed AIRM/AIWB builds older than the specs about to run — plus container-image existence. Reports a plain-language or JSON verdict for install-readiness, in-flight health, and E2E-readiness, and never reports healthy without actively proving it.

## Owner

AMD

## License

MIT
