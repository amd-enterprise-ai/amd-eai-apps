// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package controller

import (
	"context"
	"testing"

	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"sigs.k8s.io/controller-runtime/pkg/event"
)

// The self-heal watch must fire only on out-of-band deletion of the namespace-wide workloads
// policy — never on the controller's own SSA writes (Updates) or on the per-model SecurityPolicies
// (already covered by Owns), which would otherwise cause a self-triggered reconcile storm.
func TestIsWorkloadsExtAuthPolicyDelete(t *testing.T) {
	p := isWorkloadsExtAuthPolicyDelete()
	wl := un(aigateway.SecurityPolicyGVK, gateNS, aigateway.WorkloadsExtAuthPolicyName)
	perModel := un(aigateway.SecurityPolicyGVK, gateNS, resourceName(gateNS, gateIS))

	if !p.Delete(event.DeleteEvent{Object: wl}) {
		t.Error("delete of the workloads-extauth policy must pass")
	}
	if p.Delete(event.DeleteEvent{Object: perModel}) {
		t.Error("delete of a per-model SecurityPolicy must not pass (Owns covers it)")
	}
	if p.Create(event.CreateEvent{Object: wl}) {
		t.Error("create must not pass")
	}
	if p.Update(event.UpdateEvent{ObjectOld: wl, ObjectNew: wl}) {
		t.Error("update must not pass (would fire on our own SSA writes)")
	}
	if p.Generic(event.GenericEvent{Object: wl}) {
		t.Error("generic must not pass")
	}
}

// On deletion, the mapping enqueues the managed InferenceServices in the policy's namespace, so
// reconcileWorkloadsExtAuth re-stamps the policy (+ shared ReferenceGrant).
func TestMapWorkloadsPolicyToInferenceServices(t *testing.T) {
	r := gateReconciler(gateISObj())
	policy := un(aigateway.SecurityPolicyGVK, gateNS, aigateway.WorkloadsExtAuthPolicyName)

	reqs := r.mapWorkloadsPolicyToInferenceServices(context.Background(), policy)
	if len(reqs) != 1 || reqs[0].Namespace != gateNS || reqs[0].Name != gateIS {
		t.Fatalf("reqs = %+v, want one request for %s/%s", reqs, gateNS, gateIS)
	}
}
