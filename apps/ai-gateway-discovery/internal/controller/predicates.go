// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package controller

import (
	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/event"
	"sigs.k8s.io/controller-runtime/pkg/predicate"
)

// hasManagedLabel filters events to only InferenceService objects that carry
// the configured managed label. Objects without the label are ignored by the
// InferenceServiceReconciler so unrelated InferenceServices are never touched.
//
// Delete events always pass through regardless of label presence: an IS that
// had its managed label removed while the finalizer is still set must still be
// reconciled so the finalizer cleanup runs and the IS is not stuck terminating.
func hasManagedLabel(labelName, labelValue string) predicate.Predicate {
	hasLabel := func(labels map[string]string) bool {
		return labels[labelName] == labelValue
	}

	return predicate.Funcs{
		CreateFunc: func(e event.CreateEvent) bool {
			return hasLabel(e.Object.GetLabels())
		},
		UpdateFunc: func(e event.UpdateEvent) bool {
			return hasLabel(e.ObjectNew.GetLabels()) || hasLabel(e.ObjectOld.GetLabels())
		},
		DeleteFunc: func(e event.DeleteEvent) bool {
			return true
		},
		GenericFunc: func(e event.GenericEvent) bool {
			return hasLabel(e.Object.GetLabels())
		},
	}
}

// isApiKeySecret filters Secret events to the per-key API-key Secrets (those carrying the
// API-key contract label) that the SecurityPolicy gate depends on, so unrelated Secret churn
// in project namespaces never wakes the reconciler.
func isApiKeySecret() predicate.Predicate {
	return predicate.NewPredicateFuncs(func(o client.Object) bool {
		return o.GetLabels()[aigateway.APIKeyLabel] == "true"
	})
}

// isWorkloadsExtAuthPolicyDelete passes only Delete events for the namespace-wide workloads
// ext_authz SecurityPolicy. That policy is namespace-named (not IS-owned), so Owns() will not
// recreate it; this lets the reconciler re-stamp it when it is deleted out-of-band. Scoped to
// Delete + the fixed name so it never fires on the controller's own SSA writes (Updates) or on the
// per-model SecurityPolicies (already covered by Owns) — avoiding a self-triggered reconcile storm.
func isWorkloadsExtAuthPolicyDelete() predicate.Predicate {
	return predicate.Funcs{
		CreateFunc:  func(event.CreateEvent) bool { return false },
		UpdateFunc:  func(event.UpdateEvent) bool { return false },
		GenericFunc: func(event.GenericEvent) bool { return false },
		DeleteFunc: func(e event.DeleteEvent) bool {
			return e.Object.GetName() == aigateway.WorkloadsExtAuthPolicyName
		},
	}
}
