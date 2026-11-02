// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Package aigateway builds unstructured manifests for Envoy AI Gateway CRDs.
// Envoy AI Gateway does not publish an official Go client library (as of v0.6.0),
// so all resources are managed via unstructured.Unstructured. When an official
// module ships, the conversion is limited to this package.
package aigateway

import (
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
)

var (
	AIGatewayRouteGVK = schema.GroupVersionKind{
		Group:   "aigateway.envoyproxy.io",
		Version: "v1beta1",
		Kind:    "AIGatewayRoute",
	}

	// SecurityPolicyGVK is the Envoy Gateway SecurityPolicy used to enforce API-key
	// auth on a model's generated HTTPRoute. SecurityPolicy targetRefs accept only
	// Gateway/HTTPRoute/GRPCRoute — not AIGatewayRoute — so the policy targets the
	// HTTPRoute the AI Gateway generates (same name as the AIGatewayRoute), which is
	// itself parented to the ai-gateway Gateway.
	SecurityPolicyGVK = schema.GroupVersionKind{
		Group:   "gateway.envoyproxy.io",
		Version: "v1alpha1",
		Kind:    "SecurityPolicy",
	}

	// InferencePoolGVK is the gateway-api-inference-extension InferencePool resource.
	InferencePoolGVK = schema.GroupVersionKind{
		Group:   "inference.networking.k8s.io",
		Version: "v1",
		Kind:    "InferencePool",
	}

	// InferenceServiceGVK is the KServe InferenceService resource we watch.
	// We use unstructured access to avoid a kserve module dependency.
	InferenceServiceGVK = schema.GroupVersionKind{
		Group:   "serving.kserve.io",
		Version: "v1beta1",
		Kind:    "InferenceService",
	}

	// ReferenceGrantGVK is the Gateway API ReferenceGrant, used to allow the per-model catch-all
	// SecurityPolicy (in a workload namespace) to reference this controller's ext_authz Service
	// in another namespace.
	ReferenceGrantGVK = schema.GroupVersionKind{
		Group:   "gateway.networking.k8s.io",
		Version: "v1beta1",
		Kind:    "ReferenceGrant",
	}
)

// BackendEntry is the minimal information needed to represent one model backend.
type BackendEntry struct {
	// ResourceName is the name used for the InferencePool object.
	ResourceName string
	// ISName is the InferenceService name, used as the pod selector label value.
	ISName string
	// ISNamespace is the namespace of the InferenceService (and the InferencePool).
	ISNamespace string
	// ISUID is the UID of the InferenceService, used to set ownerReferences.
	ISUID types.UID
	// ModelName is read from the IS annotation and used to guard reconciliation
	// (ISes without a model name are skipped). Also used as the x-ai-eg-model
	// fallback routing key for standard OpenAI-compatible clients.
	ModelName string
	// WorkloadID is the AIM service UUID from the airm.silogen.ai/workload-id label.
	// It is the same UUID exposed in AIWB API URLs (/v1/projects/{p}/inference/{id}),
	// so it is globally unique, stable, and user-visible. Used as the x-ai-eg-backend
	// routing key for precise per-AIM routing that survives model name collisions.
	WorkloadID string
}
