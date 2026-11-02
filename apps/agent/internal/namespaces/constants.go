// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package namespaces

import "k8s.io/apimachinery/pkg/runtime/schema"

var namespaceGVR = schema.GroupVersionResource{Version: coreV1APIVersion, Resource: "namespaces"}

const (
	coreV1APIVersion = "v1"

	namespaceFinalizer = "airm.silogen.ai/namespace-finalizer"

	KueueManagedLabel = "kueue-managed"

	KaiwoGpuPreemptionEnabledKey     = "kaiwo.silogen.ai/gpu-preemption.enabled"
	KaiwoGpuPreemptionThresholdKey   = "kaiwo.silogen.ai/gpu-preemption.threshold"
	KaiwoGpuPreemptionGracePeriodKey = "kaiwo.silogen.ai/gpu-preemption.grace-period"
	KaiwoGpuPreemptionPolicyKey      = "kaiwo.silogen.ai/gpu-preemption.policy"
)
