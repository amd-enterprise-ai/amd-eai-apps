// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package aigateway

import (
	"github.com/silogen/ai-gateway-discovery/internal/config"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
)

// BuildAIGatewayRoute constructs a per-IS AIGatewayRoute with up to three routing rules, ordered
// most-specific first so backend-targeted requests bind deterministically:
//
//  1. Host + x-ai-eg-backend + x-ai-eg-model(any value) — the backend rule when a model header is
//     present. The model header is matched as a wildcard, not this backend's model name, so ANY
//     backend-targeted request keeps three header matches and out-ranks every other route's
//     two-match model-only rule. This makes x-ai-eg-backend authoritative: the request binds to
//     this backend's route (and its apiKeyAuth) whatever x-ai-eg-model says. Pinning the model
//     (Exact) here would instead drop a mismatched request to rule 2, which ties on specificity
//     with the named model's rule 3 — letting that model's SecurityPolicy authorize a different
//     backend the client targets by UUID (a cross-model bypass).
//
//  2. Host + x-ai-eg-backend — the backend rule for requests that target a backend by UUID but omit
//     the optional model header. The UUID uniquely identifies the backend and, being a
//     client-supplied header, is available at Envoy route-selection time, so the request still
//     binds to this backend's route (and its apiKeyAuth) before the AI Gateway ext_proc resolves
//     the model from the body. Without this rule a model-less backend request matches no backend
//     rule, never reaches this backend's apiKeyAuth, and is authorized against the wrong (or no)
//     policy — an auth bypass.
//
//  3. Host + x-ai-eg-model — fallback for standard OpenAI-compatible clients that do not send a
//     backend header. Non-deterministic when the same model name is deployed across projects.
//
// Rules 1 and 2 exist only when the IS carries a workload id. Rule 1 (three header matches) is more
// specific than rule 2 (two), which is more specific than any cross-route model-only rule (two), so
// specificity — not creation order — decides routing, and a present x-ai-eg-backend always wins.
//
// The route is owned by the InferenceService via ownerReferences so Kubernetes GC
// deletes it automatically when the IS is deleted.
func BuildAIGatewayRoute(entry BackendEntry, cfg *config.ControllerConfig) *unstructured.Unstructured {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(AIGatewayRouteGVK)
	obj.SetName(entry.ResourceName)
	obj.SetNamespace(entry.ISNamespace)
	obj.SetOwnerReferences(isOwnerRef(entry))

	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{
			"name":      cfg.GatewayName,
			"namespace": cfg.GatewayNamespace,
		},
	}, "spec", "parentRefs")

	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{"metadataKey": "llm_input_token", "type": "InputToken"},
		map[string]interface{}{"metadataKey": "llm_output_token", "type": "OutputToken"},
		map[string]interface{}{"metadataKey": "llm_total_token", "type": "TotalToken"},
	}, "spec", "llmRequestCosts")

	backendRef := []interface{}{
		map[string]interface{}{
			"group":     InferencePoolGVK.Group,
			"kind":      InferencePoolGVK.Kind,
			"name":      entry.ResourceName,
			"namespace": entry.ISNamespace,
		},
	}

	headerMatch := func(name, value string) interface{} {
		return map[string]interface{}{"type": "Exact", "name": name, "value": value}
	}
	// headerPresent matches a header with any value via a wildcard regex. Used so the backend rule
	// can require x-ai-eg-model to be *present* (any value) without pinning it to this backend's
	// model — see rule 1 below.
	headerPresent := func(name string) interface{} {
		return map[string]interface{}{"type": "RegularExpression", "name": name, "value": ".*"}
	}
	// routeRule builds one rule matching the given headers, pointing at this backend. LLM
	// completions routinely run longer than Envoy AI Gateway's 60s nil-timeouts default, which
	// surfaces as HTTP 504 "upstream request timeout", so every rule carries explicit
	// request/backendRequest timeouts (default 30m, tunable via the Helm chart).
	routeRule := func(headers ...interface{}) map[string]interface{} {
		return map[string]interface{}{
			"matches":     []interface{}{map[string]interface{}{"headers": headers}},
			"backendRefs": backendRef,
			"timeouts": map[string]interface{}{
				"request":        cfg.RequestTimeout,
				"backendRequest": cfg.BackendRequestTimeout,
			},
		}
	}

	host := headerMatch("Host", cfg.AIRouteHostname)
	model := headerMatch("x-ai-eg-model", entry.ModelName)

	rules := []interface{}{}
	if entry.WorkloadID != "" {
		backend := headerMatch("x-ai-eg-backend", entry.WorkloadID)
		// Rule 1: Host + backend + x-ai-eg-model(any) — the backend rule when a model header is
		// present. The model is matched as a wildcard (any value), NOT this backend's model, so any
		// request carrying x-ai-eg-backend keeps three header matches and out-ranks every other
		// route's two-match model-only rule. That makes x-ai-eg-backend authoritative: the request
		// binds to THIS backend's route (and its apiKeyAuth) regardless of what x-ai-eg-model says,
		// so a key valid only for the model named in the header cannot authorize against a different
		// backend it targets by UUID (a cross-model bypass). Pinning the model here (Exact)
		// instead would drop such a request to rule 2, which ties with the named model's rule 3 and
		// lets that model's SecurityPolicy authorize the wrong backend.
		rules = append(rules, routeRule(host, backend, headerPresent("x-ai-eg-model")))
		// Rule 2: Host + backend — binds model-less backend requests to the correct apiKeyAuth
		// — without it they fall through to a foreign model rule and bypass auth.
		rules = append(rules, routeRule(host, backend))
	}
	// Rule 3: Host + model — fallback for clients that do not send x-ai-eg-backend.
	// Non-deterministic when multiple AIMs serve the same model name.
	rules = append(rules, routeRule(host, model))

	_ = unstructured.SetNestedSlice(obj.Object, rules, "spec", "rules")

	return obj
}

func isOwnerRef(entry BackendEntry) []metav1.OwnerReference {
	if entry.ISUID == types.UID("") {
		return nil
	}
	return []metav1.OwnerReference{
		{
			APIVersion:         InferenceServiceGVK.Group + "/" + InferenceServiceGVK.Version,
			Kind:               InferenceServiceGVK.Kind,
			Name:               entry.ISName,
			UID:                entry.ISUID,
			Controller:         ptr.To(true),
			BlockOwnerDeletion: ptr.To(true),
		},
	}
}
