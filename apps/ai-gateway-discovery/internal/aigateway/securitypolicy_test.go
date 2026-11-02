// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package aigateway

import (
	"testing"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/types"
)

func testEntry() BackendEntry {
	return BackendEntry{
		ResourceName: "workbench-wb-aim-1234",
		ISName:       "wb-aim-1234",
		ISNamespace:  "workbench",
		ISUID:        types.UID("uid-abc"),
		ModelName:    "llama",
		WorkloadID:   "60697976-0000-1111-2222-333344445555",
	}
}

func TestBuildSecurityPolicy_ShapeAndRefs(t *testing.T) {
	entry := testEntry()
	// Two keys bound to this model, passed out of order to assert deterministic sorting.
	sp := BuildSecurityPolicy(entry, []string{"apikey-key-b", "apikey-key-a"})

	if gvk := sp.GroupVersionKind(); gvk != SecurityPolicyGVK {
		t.Fatalf("GVK = %v, want %v", gvk, SecurityPolicyGVK)
	}
	if sp.GetName() != entry.ResourceName {
		t.Errorf("name = %q, want %q", sp.GetName(), entry.ResourceName)
	}
	if sp.GetNamespace() != entry.ISNamespace {
		t.Errorf("namespace = %q, want %q", sp.GetNamespace(), entry.ISNamespace)
	}

	// Owned by the InferenceService so GC removes it with the IS.
	owners := sp.GetOwnerReferences()
	if len(owners) != 1 || owners[0].UID != entry.ISUID || owners[0].Kind != InferenceServiceGVK.Kind {
		t.Errorf("ownerReferences = %+v, want single IS owner with UID %q", owners, entry.ISUID)
	}

	// targetRef → the generated HTTPRoute (same name as the AIGatewayRoute).
	targetRefs, _, _ := unstructured.NestedSlice(sp.Object, "spec", "targetRefs")
	if len(targetRefs) != 1 {
		t.Fatalf("targetRefs len = %d, want 1", len(targetRefs))
	}
	tr := targetRefs[0].(map[string]interface{})
	if tr["kind"] != "HTTPRoute" || tr["group"] != "gateway.networking.k8s.io" || tr["name"] != entry.ResourceName {
		t.Errorf("targetRef = %+v, want HTTPRoute/%s", tr, entry.ResourceName)
	}

	// credentialRefs → every per-key Secret bound to the model, sorted for determinism.
	credRefs, _, _ := unstructured.NestedSlice(sp.Object, "spec", "apiKeyAuth", "credentialRefs")
	if len(credRefs) != 2 {
		t.Fatalf("credentialRefs len = %d, want 2", len(credRefs))
	}
	gotNames := make([]string, 0, len(credRefs))
	for _, ref := range credRefs {
		cr := ref.(map[string]interface{})
		if cr["kind"] != "Secret" {
			t.Errorf("credentialRef kind = %v, want Secret", cr["kind"])
		}
		gotNames = append(gotNames, cr["name"].(string))
	}
	if gotNames[0] != "apikey-key-a" || gotNames[1] != "apikey-key-b" {
		t.Errorf("credentialRefs = %v, want sorted [apikey-key-a apikey-key-b]", gotNames)
	}

	// Client id forwarded to the backend for metric attribution.
	fwd, _, _ := unstructured.NestedString(sp.Object, "spec", "apiKeyAuth", "forwardClientIDHeader")
	if fwd != ClientIDHeader {
		t.Errorf("forwardClientIDHeader = %q, want %q", fwd, ClientIDHeader)
	}

	extractFrom, _, _ := unstructured.NestedSlice(sp.Object, "spec", "apiKeyAuth", "extractFrom")
	if len(extractFrom) != 1 {
		t.Fatalf("extractFrom len = %d, want 1", len(extractFrom))
	}
	headers, _, _ := unstructured.NestedStringSlice(extractFrom[0].(map[string]interface{}), "headers")
	if len(headers) != 1 || headers[0] != "Authorization" {
		t.Errorf("extractFrom headers = %v, want [Authorization]", headers)
	}
}

// TestBuildCatchAllExtAuthSecurityPolicy_Shape verifies the catch-all override policy: distinct
// name, targets the HTTPRoute's route-not-found rule via sectionName (so it overrides only the
// catch-all, leaving native apiKeyAuth on the header rules), and wires extAuth to the discovery
// Service. This is what routes header-less/body-only requests to ext_authz.
func TestBuildCatchAllExtAuthSecurityPolicy_Shape(t *testing.T) {
	entry := testEntry()
	sp := BuildCatchAllExtAuthSecurityPolicy(entry, "ai-gateway-discovery", "ai-gateway-discovery", 8083, 1234567)

	if got, want := sp.GetName(), entry.ResourceName+CatchAllPolicySuffix; got != want {
		t.Errorf("name = %q, want %q", got, want)
	}
	if sp.GetNamespace() != entry.ISNamespace {
		t.Errorf("namespace = %q, want %q", sp.GetNamespace(), entry.ISNamespace)
	}
	if owners := sp.GetOwnerReferences(); len(owners) != 1 || owners[0].UID != entry.ISUID {
		t.Errorf("ownerReferences = %+v, want single IS owner", owners)
	}

	// Targets the catch-all rule by sectionName (overrides only that rule, not the header rules).
	targetRefs, _, _ := unstructured.NestedSlice(sp.Object, "spec", "targetRefs")
	if len(targetRefs) != 1 {
		t.Fatalf("targetRefs len = %d, want 1", len(targetRefs))
	}
	tr := targetRefs[0].(map[string]interface{})
	if tr["kind"] != "HTTPRoute" || tr["name"] != entry.ResourceName || tr["sectionName"] != CatchAllRuleName {
		t.Errorf("targetRef = %+v, want HTTPRoute/%s sectionName=%s", tr, entry.ResourceName, CatchAllRuleName)
	}

	// extAuth points at the discovery Service and forwards body + authorization.
	be, _, _ := unstructured.NestedSlice(sp.Object, "spec", "extAuth", "http", "backendRefs")
	if len(be) != 1 {
		t.Fatalf("extAuth backendRefs len = %d, want 1", len(be))
	}
	b := be[0].(map[string]interface{})
	if b["name"] != "ai-gateway-discovery" || b["port"] != int64(8083) {
		t.Errorf("extAuth backendRef = %+v, want ai-gateway-discovery:8083", b)
	}
	if _, found, _ := unstructured.NestedMap(sp.Object, "spec", "extAuth", "bodyToExtAuth"); !found {
		t.Error("extAuth must set bodyToExtAuth so the handler can read the body model")
	}
	// The ceiling must come from config, not a literal: Envoy 413s a body over it and skips auth
	// entirely, so a stale 64KiB here rejects ordinary large-context requests regardless of what
	// the gateway-scoped policy allows. Deliberately not the default — a value equal to
	// DefaultBodyAuthMaxRequestBytes would also pass if the argument were ignored outright.
	if mrb, _, _ := unstructured.NestedInt64(sp.Object, "spec", "extAuth", "bodyToExtAuth", "maxRequestBytes"); mrb != 1234567 {
		t.Errorf("bodyToExtAuth.maxRequestBytes = %d, want 1234567 (the value passed in)", mrb)
	}
	// Must NOT carry apiKeyAuth — the whole point is to replace it on the catch-all.
	if _, found, _ := unstructured.NestedMap(sp.Object, "spec", "apiKeyAuth"); found {
		t.Error("catch-all policy must not carry apiKeyAuth")
	}
	// content-type must be forwarded. The handler takes the multipart boundary from it and
	// refuses to infer one from the body, because an inferred boundary can be made to disagree
	// with every compliant parser downstream (RFC 2046 preamble discarding), which would let a
	// request be authorized for one model and served as another. Without this header multipart
	// requests are denied rather than mis-authorized, but they are denied.
	h2e, _, _ := unstructured.NestedStringSlice(sp.Object, "spec", "extAuth", "headersToExtAuth")
	if len(h2e) != 2 || h2e[0] != "authorization" || h2e[1] != "content-type" {
		t.Errorf("headersToExtAuth = %v, want [authorization content-type]", h2e)
	}
}

// TestBuildExtAuthReferenceGrant_Shape verifies the cross-namespace grant: it lives in the authz
// (controller) namespace, is named after and grants from the workload namespace's SecurityPolicies
// to the ext_authz Service — enabling the catch-all SP's cross-namespace backendRef per workload ns.
func TestBuildExtAuthReferenceGrant_Shape(t *testing.T) {
	rg := BuildExtAuthReferenceGrant("workbench", "ai-gateway-discovery", "ai-gateway-discovery")
	if rg.GroupVersionKind() != ReferenceGrantGVK {
		t.Fatalf("GVK = %v, want %v", rg.GroupVersionKind(), ReferenceGrantGVK)
	}
	if rg.GetName() != "workbench" || rg.GetNamespace() != "ai-gateway-discovery" {
		t.Errorf("name/ns = %q/%q, want workbench/ai-gateway-discovery", rg.GetName(), rg.GetNamespace())
	}
	from, _, _ := unstructured.NestedSlice(rg.Object, "spec", "from")
	if len(from) != 1 {
		t.Fatalf("from len = %d, want 1", len(from))
	}
	f := from[0].(map[string]interface{})
	if f["kind"] != "SecurityPolicy" || f["namespace"] != "workbench" || f["group"] != "gateway.envoyproxy.io" {
		t.Errorf("from = %+v, want SecurityPolicy in workbench", f)
	}
	to, _, _ := unstructured.NestedSlice(rg.Object, "spec", "to")
	tm := to[0].(map[string]interface{})
	if tm["kind"] != "Service" || tm["name"] != "ai-gateway-discovery" {
		t.Errorf("to = %+v, want Service ai-gateway-discovery", tm)
	}
}

// TestBuildWorkloadsExtAuthSecurityPolicy_Shape verifies the namespace-wide workloads guard: a fixed
// name (not IS-owned), selects inference serving routes by the AIM-service label (Exists) rather than
// targetRefs, and wires static ext_authz to the handler (failClosed, no body).
func TestBuildWorkloadsExtAuthSecurityPolicy_Shape(t *testing.T) {
	sp := BuildWorkloadsExtAuthSecurityPolicy("workbench", "ai-gateway-discovery", "ai-gateway-discovery", 8084)

	if sp.GetName() != WorkloadsExtAuthPolicyName {
		t.Errorf("name = %q, want %q", sp.GetName(), WorkloadsExtAuthPolicyName)
	}
	if sp.GetNamespace() != "workbench" {
		t.Errorf("namespace = %q, want workbench", sp.GetNamespace())
	}
	// Namespace-wide, not per-IS: no owner reference.
	if owners := sp.GetOwnerReferences(); len(owners) != 0 {
		t.Errorf("ownerReferences = %+v, want none", owners)
	}
	// Selects by label existence, not targetRefs by name.
	if _, found, _ := unstructured.NestedSlice(sp.Object, "spec", "targetRefs"); found {
		t.Error("workloads ext_authz must target by selector, not targetRefs")
	}
	sel, _, _ := unstructured.NestedSlice(sp.Object, "spec", "targetSelectors")
	if len(sel) != 1 {
		t.Fatalf("targetSelectors len = %d, want 1", len(sel))
	}
	s := sel[0].(map[string]interface{})
	if s["kind"] != "HTTPRoute" {
		t.Errorf("selector kind = %v, want HTTPRoute", s["kind"])
	}
	// One Exists expression: AIM-service only. Selecting on this code-set label (not the
	// labelPropagation-dependent workload-id) attaches to inference serving routes, excludes workspace
	// routes (which carry workload-id but not AIM-service), and can't silently fail-open if the
	// workload-id label is dropped from routes.
	exprs, _, _ := unstructured.NestedSlice(s, "matchExpressions")
	if len(exprs) != 1 {
		t.Fatalf("matchExpressions len = %d, want 1 (AIM-service)", len(exprs))
	}
	e := exprs[0].(map[string]interface{})
	if e["key"] != AIMServiceLabel || e["operator"] != "Exists" {
		t.Errorf("matchExpression = %+v, want %s Exists", e, AIMServiceLabel)
	}
	// Static ext_authz → handler, failClosed, no body (path carries the workload id).
	if failOpen, _, _ := unstructured.NestedBool(sp.Object, "spec", "extAuth", "failOpen"); failOpen {
		t.Error("extAuth.failOpen must be false")
	}
	// The absence of bodyToExtAuth is what lets multipart audio uploads
	// (/v1/audio/transcriptions) authorize on this route: the handler authorizes
	// on the request path and never reads the body, so a
	// multipart/form-data body is not decoded as JSON and large uploads are not
	// buffered to a maxRequestBytes ceiling (unlike the header-less unified path).
	if _, found, _ := unstructured.NestedMap(sp.Object, "spec", "extAuth", "bodyToExtAuth"); found {
		t.Error("workloads ext_authz must not forward the body (path-based; keeps multipart audio auth working)")
	}
	be, _, _ := unstructured.NestedSlice(sp.Object, "spec", "extAuth", "http", "backendRefs")
	if len(be) != 1 {
		t.Fatalf("backendRefs len = %d, want 1", len(be))
	}
	b := be[0].(map[string]interface{})
	if b["name"] != "ai-gateway-discovery" || b["namespace"] != "ai-gateway-discovery" || b["port"] != int64(8084) {
		t.Errorf("backendRef = %+v, want ai-gateway-discovery/ai-gateway-discovery:8084 (the workloads port)", b)
	}
	// Forwards the Authorization header to the handler; forwards client-id/backend upstream.
	h2e, _, _ := unstructured.NestedStringSlice(sp.Object, "spec", "extAuth", "headersToExtAuth")
	if len(h2e) != 1 || h2e[0] != "authorization" {
		t.Errorf("headersToExtAuth = %v, want [authorization]", h2e)
	}
	h2b, _, _ := unstructured.NestedStringSlice(sp.Object, "spec", "extAuth", "http", "headersToBackend")
	if len(h2b) != 2 || h2b[0] != ClientIDHeader || h2b[1] != BackendHeader {
		t.Errorf("headersToBackend = %v, want [%s %s]", h2b, ClientIDHeader, BackendHeader)
	}
}
