// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package controller

import (
	"context"
	"testing"

	"github.com/go-logr/logr"
	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"github.com/silogen/ai-gateway-discovery/internal/common"
	"github.com/silogen/ai-gateway-discovery/internal/config"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

// deletingManagedIS is a managed InferenceService that is mid-deletion (has a deletionTimestamp and
// the finalizer). Used to exercise the last-one-out workloads ext_authz cleanup.
func deletingManagedIS(name string) *unstructured.Unstructured {
	o := un(aigateway.InferenceServiceGVK, gateNS, name)
	o.SetLabels(map[string]string{gateManagedK: gateManagedV})
	o.SetFinalizers([]string{common.Finalizer}) // fake client requires a finalizer to keep a deletionTimestamp
	ts := metav1.Now()
	o.SetDeletionTimestamp(&ts)
	return o
}

// Deleting the last managed InferenceService in a namespace removes the namespace-wide workloads
// ext_authz SecurityPolicy — otherwise it lingers with nothing to guard and can never be corrected
// (it is only re-stamped on an IS reconcile).
func TestCleanupWorkloadsExtAuth_LastISRemovesPolicy(t *testing.T) {
	sp := un(aigateway.SecurityPolicyGVK, gateNS, aigateway.WorkloadsExtAuthPolicyName)
	deleting := deletingManagedIS(gateIS)
	r := gateReconciler(sp, deleting)

	if err := r.cleanupWorkloadsExtAuthIfLast(context.Background(), logr.Discard(), deleting); err != nil {
		t.Fatalf("cleanupWorkloadsExtAuthIfLast: %v", err)
	}
	if objPresent(t, r.Client, aigateway.SecurityPolicyGVK, gateNS, aigateway.WorkloadsExtAuthPolicyName) {
		t.Fatal("workloads-extauth SP should be removed when the last managed IS is deleted")
	}
}

// While another managed InferenceService is still serving (not being deleted), the workloads ext_authz
// SecurityPolicy must remain.
func TestCleanupWorkloadsExtAuth_OtherISKeepsPolicy(t *testing.T) {
	sp := un(aigateway.SecurityPolicyGVK, gateNS, aigateway.WorkloadsExtAuthPolicyName)
	deleting := deletingManagedIS(gateIS)
	live := gateISObj() // managed, not being deleted
	live.SetName("model-b")
	r := gateReconciler(sp, deleting, live)

	if err := r.cleanupWorkloadsExtAuthIfLast(context.Background(), logr.Discard(), deleting); err != nil {
		t.Fatalf("cleanupWorkloadsExtAuthIfLast: %v", err)
	}
	if !objPresent(t, r.Client, aigateway.SecurityPolicyGVK, gateNS, aigateway.WorkloadsExtAuthPolicyName) {
		t.Fatal("workloads-extauth SP must remain while another managed IS still serves")
	}
}

// authzNS (the ext_authz Service namespace) is declared in catchall_extauth_test.go.

// reconcileWorkloadsExtAuth stamps one namespace-wide ext_authz SecurityPolicy plus the shared
// cross-namespace ReferenceGrant, idempotently — the always-on guard for the workloads route.
func TestReconcileWorkloadsExtAuth_StampsPolicyAndGrant(t *testing.T) {
	r := &InferenceServiceReconciler{
		Client: fake.NewClientBuilder().WithScheme(gateTestScheme()).Build(),
		Log:    logr.Discard(),
		Config: &config.ControllerConfig{
			WorkloadIDLabel:       "airm.silogen.ai/workload-id",
			AuthzServiceName:      authzNS,
			AuthzServiceNamespace: authzNS,
			AuthzPort:             8083,
			WorkloadsAuthzPort:    8084,
		},
	}
	ctx := context.Background()
	if err := r.reconcileWorkloadsExtAuth(ctx, logr.Discard(), gateNS); err != nil {
		t.Fatalf("reconcileWorkloadsExtAuth: %v", err)
	}

	// The namespace-wide workloads ext_authz SecurityPolicy exists and carries extAuth.
	sp := &unstructured.Unstructured{}
	sp.SetGroupVersionKind(aigateway.SecurityPolicyGVK)
	if err := r.Get(ctx, client.ObjectKey{Namespace: gateNS, Name: aigateway.WorkloadsExtAuthPolicyName}, sp); err != nil {
		t.Fatalf("workloads-extauth SecurityPolicy not created: %v", err)
	}
	if _, found, _ := unstructured.NestedMap(sp.Object, "spec", "extAuth"); !found {
		t.Error("workloads SecurityPolicy must carry extAuth")
	}
	if owners := sp.GetOwnerReferences(); len(owners) != 0 {
		t.Errorf("workloads SecurityPolicy must be namespace-wide (no owner ref), got %+v", owners)
	}

	// The cross-namespace ReferenceGrant exists in the authz namespace, named after the workload ns.
	rg := &unstructured.Unstructured{}
	rg.SetGroupVersionKind(aigateway.ReferenceGrantGVK)
	if err := r.Get(ctx, client.ObjectKey{Namespace: authzNS, Name: gateNS}, rg); err != nil {
		t.Fatalf("ext_authz ReferenceGrant not created: %v", err)
	}

	// Idempotent: a second reconcile must not error (server-side apply is a no-op).
	if err := r.reconcileWorkloadsExtAuth(ctx, logr.Discard(), gateNS); err != nil {
		t.Fatalf("second reconcileWorkloadsExtAuth: %v", err)
	}
}
