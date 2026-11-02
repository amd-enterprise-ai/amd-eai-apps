// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package aigateway

import (
	"sort"

	"github.com/silogen/ai-gateway-discovery/internal/common"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

const (
	// APIKeyLabel is the contract label marking a Secret as an API key. AIWB stamps it
	// (via ESO) on each per-key Secret; the controller filters Secret events and reads bindings by
	// the bound label below. Must match AIWB's API_KEY_LABEL.
	APIKeyLabel = "eai.amd.com/api-key"

	// BoundLabelPrefix + workload-id is the membership label AIWB stamps on a key's Secret to bind
	// it to a model. A model's SecurityPolicy lists every Secret carrying its bound label, so
	// authorization = membership. Must match AIWB's BOUND_LABEL_PREFIX.
	BoundLabelPrefix = "apikey.eai.amd.com/bound-"

	// AIMServiceLabel marks an HTTPRoute as an aim-engine AIM inference service route. Only the
	// workloads *serving* routes (workloads.<domain>) carry it — workspace routes (workspaces.<domain>,
	// e.g. VS Code / ComfyUI) do not, even though both carry a workload-id label. The workloads
	// ext_authz selector requires this so it guards only inference serving routes and never attaches
	// API-key auth to browser/OAuth workspace routes. Propagated to the route unconditionally by
	// aim-engine (aim.eai.amd.com/*), so it is present whenever the serving route exists.
	AIMServiceLabel = "aim.eai.amd.com/service"

	// KeySecretPrefix + key-id is the ESO-materialized per-key Secret AIWB produces (one
	// Secret per key). Must match AIWB's SECRET_NAME_PREFIX.
	KeySecretPrefix = "apikey-"

	// ClientIDHeader is where apiKeyAuth forwards the matched key's client id (the Secret data-key,
	// token-<ns>-<key>) to the backend. Kept equal to the metrics api_key_id label so per-key
	// attribution survives the cutover.
	ClientIDHeader = "x-api-key-id"

	// BackendHeader carries the resolved backend (workload id). On the header-less/body path the
	// gateway can't resolve the backend from EDS endpoint metadata, so the body-aware ext_authz
	// forwards it here for aim_service_id metric attribution. Equals the routing header clients
	// send on the header path.
	BackendHeader = "x-ai-eg-backend"

	// CatchAllRuleName is the name Envoy AI Gateway gives the catch-all rule it appends to every
	// generated HTTPRoute (path:/, no header match) so its ext_proc can read the body of
	// header-less requests. That rule is covered by the per-model apiKeyAuth (whole-route), which
	// wrongly authorizes header-less requests against an arbitrary model. This is an Envoy AI
	// Gateway internal name (hardcoded upstream), so a reconcile-time guard should confirm it
	// still exists before relying on it.
	CatchAllRuleName = "route-not-found"

	// CatchAllPolicySuffix distinguishes the catch-all ext_authz SecurityPolicy from the per-model
	// apiKeyAuth one on the same HTTPRoute (both are IS-owned, same namespace).
	CatchAllPolicySuffix = "-catchall"

	// WorkloadsExtAuthPolicyName is the fixed name of the namespace-wide ext_authz SecurityPolicy
	// that guards the aim-engine workloads serving routes. Unlike the per-model policies it is not
	// IS-owned: one policy covers every workloads route in the namespace (matched by the AIM-service
	// label), so it is named and stamped per namespace, like the ext_authz ReferenceGrant.
	WorkloadsExtAuthPolicyName = "workloads-extauth"
)

// BoundLabel is the membership label marking a key Secret as bound to the given model.
func BoundLabel(workloadID string) string { return BoundLabelPrefix + workloadID }

// BuildSecurityPolicy constructs an Envoy Gateway SecurityPolicy that enforces API-key auth on the
// model's generated HTTPRoute (same name as the AIGatewayRoute, parented to the ai-gateway
// Gateway), listing every per-key Secret bound to the model as a credentialRef.
//
// Authorization = membership: the policy lists exactly the keys authorized for this backend, so a
// valid-but-unlisted key is rejected. Binding/unbinding a key changes this list, which mutates the
// policy — acceptable for one Secret per key (brief gateway reload on bind/unbind).
// secretNames is sorted so an unrelated reconcile that re-lists the same set does not churn the
// policy. Callers must pass a non-empty list; an empty model gets no policy (gateway backstop).
// Owned by the InferenceService so Kubernetes GC removes it with the IS.
func BuildSecurityPolicy(entry BackendEntry, secretNames []string) *unstructured.Unstructured {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(SecurityPolicyGVK)
	obj.SetName(entry.ResourceName)
	obj.SetNamespace(entry.ISNamespace)
	obj.SetOwnerReferences(isOwnerRef(entry))

	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{
			"group": "gateway.networking.k8s.io",
			"kind":  "HTTPRoute",
			"name":  entry.ResourceName,
		},
	}, "spec", "targetRefs")

	sorted := append([]string(nil), secretNames...)
	sort.Strings(sorted)
	refs := make([]interface{}, 0, len(sorted))
	for _, name := range sorted {
		refs = append(refs, map[string]interface{}{
			"group": "",
			"kind":  "Secret",
			"name":  name,
		})
	}

	_ = unstructured.SetNestedMap(obj.Object, map[string]interface{}{
		"credentialRefs": refs,
		"extractFrom": []interface{}{
			map[string]interface{}{
				"headers": []interface{}{"Authorization"},
			},
		},
		"forwardClientIDHeader": ClientIDHeader,
	}, "spec", "apiKeyAuth")

	return obj
}

// BuildCatchAllExtAuthSecurityPolicy constructs a rule-scoped SecurityPolicy that overrides the
// per-model apiKeyAuth on the HTTPRoute's catch-all rule (CatchAllRuleName) with body-aware
// ext_authz. Header rules keep native apiKeyAuth; header-less (body-only) requests, which fall to
// the catch-all, are instead authorized by the ext_authz handler against the model named in the
// body — which is the only thing in the chain that can, since the model isn't known at route/auth
// time. Being sectionName-scoped, it is more specific than the whole-route apiKeyAuth and wins for
// just that rule. Owned by the InferenceService so GC removes it with the IS.
func BuildCatchAllExtAuthSecurityPolicy(entry BackendEntry, authzService, authzNamespace string, authzPort, maxRequestBytes int) *unstructured.Unstructured {
	// A zero here would publish maxRequestBytes: 0 and reject the whole header-less path. Config
	// validation rejects that before the controller starts, so this only covers callers that build
	// a config value directly rather than loading one.
	if maxRequestBytes <= 0 {
		maxRequestBytes = common.DefaultBodyAuthMaxRequestBytes
	}

	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(SecurityPolicyGVK)
	obj.SetName(entry.ResourceName + CatchAllPolicySuffix)
	obj.SetNamespace(entry.ISNamespace)
	obj.SetOwnerReferences(isOwnerRef(entry))

	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{
			"group":       "gateway.networking.k8s.io",
			"kind":        "HTTPRoute",
			"name":        entry.ResourceName,
			"sectionName": CatchAllRuleName,
		},
	}, "spec", "targetRefs")

	_ = unstructured.SetNestedMap(obj.Object, map[string]interface{}{
		"failOpen": false,
		"bodyToExtAuth": map[string]interface{}{
			// Hard request-size ceiling on the header-less path; see
			// common.DefaultBodyAuthMaxRequestBytes for why and how it is sized.
			"maxRequestBytes": int64(maxRequestBytes),
		},
		// content-type is load-bearing, not diagnostic: the handler reads the multipart boundary
		// from it and refuses to guess one from the body, because a guessed boundary can be made
		// to disagree with every compliant parser downstream (RFC 2046 §5.1.1 preamble
		// discarding). Drop this and audio requests stop being authorizable rather than being
		// authorized wrongly, but drop it silently and that is a confusing outage.
		"headersToExtAuth": []interface{}{"authorization", "content-type"},
		"http": map[string]interface{}{
			"backendRefs": []interface{}{
				map[string]interface{}{
					"group":     "",
					"kind":      "Service",
					"name":      authzService,
					"namespace": authzNamespace,
					"port":      int64(authzPort),
				},
			},
			"headersToBackend": []interface{}{ClientIDHeader, BackendHeader},
		},
	}, "spec", "extAuth")

	return obj
}

// BuildWorkloadsExtAuthSecurityPolicy constructs a namespace-wide SecurityPolicy that routes every
// aim-engine workloads *serving* route to the body-aware ext_authz handler. It selects routes by the
// AIM-service label (Exists) alone. That label marks aim-engine inference serving routes and is set
// unconditionally by aim-engine in code, so the guard is robust to runtime config. It deliberately
// does NOT select on the workload-id label, even though workloads routes carry it, for two reasons:
//   - workspace routes (workspaces.<domain>, e.g. VS Code / ComfyUI) also carry workload-id but not
//     the AIM-service label, so selecting on AIM-service excludes them (attaching API-key ext_authz to
//     a browser/OAuth workspace route breaks it with "missing api key"); and
//   - the workload-id label reaches routes only via aim-engine's AIMClusterRuntimeConfig.labelPropagation
//     (a mutable, cross-component config); if it were narrowed/disabled the label would vanish, the
//     selector would match nothing, and — since the shared https gateway has no default-deny backstop —
//     the workloads route would silently fail OPEN. AIM-service, being code-set, has no such dependency.
//
// The handler still gets the workload id from the request path, not the label. Still a single
// namespace-wide policy, so it attaches to every serving route including ones the reconciler has not
// individually processed, which closes the create-order gap.
//
// Unlike native apiKeyAuth, the ext_authz filter config is static (it only names the handler
// Service), so binding/unbinding a key never mutates the shared https listener — no drain, no
// dropped app connections. The handler authorizes on the request path (which names the workload) and
// denies by default, so an unmatched or key-less request on a workloads route is refused with no
// per-route policy. failOpen is false: an unreachable handler denies, matching the cluster-auth
// behavior this replaces. No bodyToExtAuth — the path carries the workload id, so the body is not
// needed. Namespace-scoped and named by WorkloadsExtAuthPolicyName (not IS-owned), stamped
// idempotently alongside the ext_authz ReferenceGrant.
func BuildWorkloadsExtAuthSecurityPolicy(namespace, authzService, authzNamespace string, authzPort int) *unstructured.Unstructured {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(SecurityPolicyGVK)
	obj.SetName(WorkloadsExtAuthPolicyName)
	obj.SetNamespace(namespace)

	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{
			"group": "gateway.networking.k8s.io",
			"kind":  "HTTPRoute",
			"matchExpressions": []interface{}{
				// AIM-service marks aim-engine inference serving routes (code-set, unconditional).
				// Workspace routes lack it, so they are excluded. Not selecting on workload-id avoids a
				// silent fail-open if labelPropagation drops that label from the route.
				map[string]interface{}{
					"key":      AIMServiceLabel,
					"operator": "Exists",
				},
			},
		},
	}, "spec", "targetSelectors")

	_ = unstructured.SetNestedMap(obj.Object, map[string]interface{}{
		"failOpen":         false,
		"headersToExtAuth": []interface{}{"authorization"},
		"http": map[string]interface{}{
			"backendRefs": []interface{}{
				map[string]interface{}{
					"group":     "",
					"kind":      "Service",
					"name":      authzService,
					"namespace": authzNamespace,
					"port":      int64(authzPort),
				},
			},
			"headersToBackend": []interface{}{ClientIDHeader, BackendHeader},
		},
	}, "spec", "extAuth")

	return obj
}

// BuildExtAuthReferenceGrant grants SecurityPolicies in a workload namespace permission to
// reference the ext_authz Service in the controller's namespace — required because the catch-all
// SecurityPolicy lives in the workload namespace but points its extAuth backendRef at the Service
// cross-namespace. One grant per workload namespace (named after it), stamped idempotently during
// reconcile so it scales to dynamically-created namespaces. It lives in the Service's namespace and
// cannot carry a cross-namespace owner ref, so it is not GC'd with the IS; an unused grant is inert.
func BuildExtAuthReferenceGrant(workloadNamespace, authzService, authzNamespace string) *unstructured.Unstructured {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(ReferenceGrantGVK)
	obj.SetName(workloadNamespace)
	obj.SetNamespace(authzNamespace)

	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{
			"group":     "gateway.envoyproxy.io",
			"kind":      "SecurityPolicy",
			"namespace": workloadNamespace,
		},
	}, "spec", "from")
	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{
			"group": "",
			"kind":  "Service",
			"name":  authzService,
		},
	}, "spec", "to")

	return obj
}
