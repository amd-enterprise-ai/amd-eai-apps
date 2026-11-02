// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package aigateway

import (
	"testing"

	"github.com/silogen/ai-gateway-discovery/internal/config"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

// ruleHeaders returns the header-match name→value pairs of one rule.
func ruleHeaders(t *testing.T, rule interface{}) map[string]string {
	t.Helper()
	m, _ := rule.(map[string]interface{})
	matches, _, _ := unstructured.NestedSlice(m, "matches")
	if len(matches) != 1 {
		t.Fatalf("rule has %d matches, want 1", len(matches))
	}
	headers, _, _ := unstructured.NestedSlice(matches[0].(map[string]interface{}), "headers")
	out := map[string]string{}
	for _, h := range headers {
		hm := h.(map[string]interface{})
		out[hm["name"].(string)] = hm["value"].(string)
	}
	return out
}

// ruleHeaderType returns the match type ("Exact"/"RegularExpression") for a named header in a rule.
func ruleHeaderType(t *testing.T, rule interface{}, name string) string {
	t.Helper()
	m, _ := rule.(map[string]interface{})
	matches, _, _ := unstructured.NestedSlice(m, "matches")
	headers, _, _ := unstructured.NestedSlice(matches[0].(map[string]interface{}), "headers")
	for _, h := range headers {
		hm := h.(map[string]interface{})
		if hm["name"].(string) == name {
			return hm["type"].(string)
		}
	}
	return ""
}

// TestBuildAIGatewayRoute_BackendRulesGraded guards the routing fixes at once. With a workload id
// the route must emit three rules, most-specific first:
//
//  0. Host + x-ai-eg-backend + x-ai-eg-model(RegularExpression ".*") — the backend rule matches ANY
//     model header value (wildcard), keeping three header matches so it out-ranks every other
//     route's two-match model-only rule. This makes x-ai-eg-backend authoritative even when the
//     model header names a different model, closing the cross-model bypass and keeping
//     same-name collisions deterministic.
//  1. Host + x-ai-eg-backend (no model) — binds model-less backend requests to this backend's
//     apiKeyAuth instead of a foreign model rule.
//  2. Host + x-ai-eg-model (Exact, no backend) — the OpenAI-client fallback.
func TestBuildAIGatewayRoute_BackendRulesGraded(t *testing.T) {
	cfg := &config.ControllerConfig{
		GatewayName:           "ai-gateway",
		GatewayNamespace:      "envoy-gateway-system",
		AIRouteHostname:       "gateway.example.com",
		RequestTimeout:        "30m",
		BackendRequestTimeout: "30m",
	}
	entry := BackendEntry{ResourceName: "aim-abc", ISName: "is-abc", ISNamespace: "proj", ModelName: "llama-3", WorkloadID: "uuid-123"}

	obj := BuildAIGatewayRoute(entry, cfg)
	rules, _, _ := unstructured.NestedSlice(obj.Object, "spec", "rules")
	if len(rules) != 3 {
		t.Fatalf("expected 3 rules (backend+model, backend, model fallback), got %d", len(rules))
	}

	// Rule 0: backend + wildcard model. Host and backend are Exact; the model header must be a
	// RegularExpression wildcard (".*"), NOT this backend's model name — that is what lets a
	// backend-targeted request with a mismatched model header still bind here (backend wins).
	both := ruleHeaders(t, rules[0])
	if both["Host"] != cfg.AIRouteHostname || both["x-ai-eg-backend"] != entry.WorkloadID {
		t.Errorf("rule 0 must match Host + backend; headers = %v", both)
	}
	if _, present := both["x-ai-eg-model"]; !present {
		t.Errorf("rule 0 must also match x-ai-eg-model (present, any value); headers = %v", both)
	}
	if got := ruleHeaderType(t, rules[0], "x-ai-eg-model"); got != "RegularExpression" {
		t.Errorf("rule 0 x-ai-eg-model match type = %q, want RegularExpression (wildcard)", got)
	}
	if both["x-ai-eg-model"] != ".*" {
		t.Errorf("rule 0 x-ai-eg-model value = %q, want \".*\" (any model); pinning it re-opens the cross-model mismatch bypass", both["x-ai-eg-model"])
	}
	if got := ruleHeaderType(t, rules[0], "x-ai-eg-backend"); got != "Exact" {
		t.Errorf("rule 0 x-ai-eg-backend match type = %q, want Exact", got)
	}

	// Rule 1: backend only — Host + x-ai-eg-backend, and NOT x-ai-eg-model.
	backend := ruleHeaders(t, rules[1])
	if backend["x-ai-eg-backend"] != entry.WorkloadID || backend["Host"] != cfg.AIRouteHostname {
		t.Errorf("rule 1 must match Host + backend; headers = %v", backend)
	}
	if _, present := backend["x-ai-eg-model"]; present {
		t.Errorf("rule 1 must NOT require x-ai-eg-model (auth-bypass fix); headers = %v", backend)
	}

	// Rule 2: model-only fallback keys on x-ai-eg-model (Exact) and drops the backend header.
	fallback := ruleHeaders(t, rules[2])
	if fallback["x-ai-eg-model"] != entry.ModelName {
		t.Errorf("rule 2 x-ai-eg-model = %q, want %q", fallback["x-ai-eg-model"], entry.ModelName)
	}
	if got := ruleHeaderType(t, rules[2], "x-ai-eg-model"); got != "Exact" {
		t.Errorf("rule 2 x-ai-eg-model match type = %q, want Exact", got)
	}
	if _, present := fallback["x-ai-eg-backend"]; present {
		t.Errorf("rule 2 must be the model-only fallback; headers = %v", fallback)
	}
}

// TestBuildAIGatewayRoute_RulesCarryConfiguredTimeout guards against regressing
// to the Envoy AI Gateway 60s nil-timeouts default, which surfaced as HTTP 504
// "upstream request timeout" on long LLM completions. Every generated rule must
// carry the configured request/backendRequest timeouts. Non-default values are
// used here to prove the values propagate from config rather than being
// hardcoded.
func TestBuildAIGatewayRoute_RulesCarryConfiguredTimeout(t *testing.T) {
	const wantRequest, wantBackendRequest = "45m", "20m"
	cfg := &config.ControllerConfig{
		GatewayName:           "ai-gateway",
		GatewayNamespace:      "envoy-gateway-system",
		AIRouteHostname:       "gateway.example.com",
		RequestTimeout:        wantRequest,
		BackendRequestTimeout: wantBackendRequest,
	}

	cases := map[string]BackendEntry{
		"with-workload-id (uuid + fallback rules)": {
			ResourceName: "aim-abc",
			ISName:       "is-abc",
			ISNamespace:  "proj",
			ModelName:    "llama-3",
			WorkloadID:   "uuid-123",
		},
		"without-workload-id (fallback rule only)": {
			ResourceName: "aim-def",
			ISName:       "is-def",
			ISNamespace:  "proj",
			ModelName:    "llama-3",
		},
	}

	for name, entry := range cases {
		t.Run(name, func(t *testing.T) {
			obj := BuildAIGatewayRoute(entry, cfg)
			rules, found, err := unstructured.NestedSlice(obj.Object, "spec", "rules")
			if err != nil || !found {
				t.Fatalf("spec.rules missing: found=%v err=%v", found, err)
			}
			if len(rules) == 0 {
				t.Fatal("expected at least one rule")
			}
			for i, r := range rules {
				rule, ok := r.(map[string]interface{})
				if !ok {
					t.Fatalf("rule %d is not a map", i)
				}
				timeouts, ok := rule["timeouts"].(map[string]interface{})
				if !ok {
					t.Fatalf("rule %d missing timeouts", i)
				}
				if got := timeouts["request"]; got != wantRequest {
					t.Errorf("rule %d timeouts.request = %v, want %s", i, got, wantRequest)
				}
				if got := timeouts["backendRequest"]; got != wantBackendRequest {
					t.Errorf("rule %d timeouts.backendRequest = %v, want %s", i, got, wantBackendRequest)
				}
			}
		})
	}
}
