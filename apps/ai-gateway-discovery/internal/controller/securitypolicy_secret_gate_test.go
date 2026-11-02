// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package controller

import (
	"context"
	"testing"

	"github.com/go-logr/logr"
	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"github.com/silogen/ai-gateway-discovery/internal/config"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/event"
)

const (
	gateNS       = "proj"
	gateWL       = "wl-uuid"
	gateIS       = "model-a"
	gateManagedK = "app.kubernetes.io/managed-by"
	gateManagedV = "ai-gateway-discovery"
)

// gateTestScheme registers the unstructured GVKs (and their List kinds) the reconciler
// touches so the fake client can Get/List/Delete/Apply them.
func gateTestScheme() *runtime.Scheme {
	s := runtime.NewScheme()
	for _, gvk := range []schema.GroupVersionKind{
		aigateway.InferenceServiceGVK,
		aigateway.SecurityPolicyGVK,
		aigateway.ReferenceGrantGVK,
		secretGVK,
	} {
		s.AddKnownTypeWithName(gvk, &unstructured.Unstructured{})
		listGVK := gvk
		listGVK.Kind += "List"
		s.AddKnownTypeWithName(listGVK, &unstructured.UnstructuredList{})
	}
	return s
}

func un(gvk schema.GroupVersionKind, ns, name string) *unstructured.Unstructured {
	o := &unstructured.Unstructured{}
	o.SetGroupVersionKind(gvk)
	o.SetNamespace(ns)
	o.SetName(name)
	return o
}

func gateReconciler(objs ...client.Object) *InferenceServiceReconciler {
	c := fake.NewClientBuilder().WithScheme(gateTestScheme()).WithObjects(objs...).Build()
	return &InferenceServiceReconciler{
		Client: c,
		Log:    logr.Discard(),
		Config: &config.ControllerConfig{
			APIKeyAuthAnnotation: "aim.eai.amd.com/api-key-auth",
			ManagedLabelName:     gateManagedK,
			ManagedLabelValue:    gateManagedV,
		},
	}
}

func gateEntry() aigateway.BackendEntry {
	return aigateway.BackendEntry{
		ResourceName: resourceName(gateNS, gateIS),
		ISName:       gateIS,
		ISNamespace:  gateNS,
		WorkloadID:   gateWL,
	}
}

// gateISObj is the InferenceService passed into reconcileSecurityPolicy; its annotations
// (the opt-out) are read there, and its managed label lets the Secret→IS mapping find it.
func gateISObj() *unstructured.Unstructured {
	o := un(aigateway.InferenceServiceGVK, gateNS, gateIS)
	o.SetLabels(map[string]string{gateManagedK: gateManagedV})
	return o
}

// boundKeySecret is a per-key Secret bound to the gate model via its bound-<workload-id> label.
func boundKeySecret() *unstructured.Unstructured {
	o := un(secretGVK, gateNS, aigateway.KeySecretPrefix+"key-1")
	o.SetLabels(map[string]string{
		aigateway.APIKeyLabel:        "true",
		aigateway.BoundLabel(gateWL): "true",
	})
	return o
}

func spPresent(t *testing.T, c client.Client) bool {
	t.Helper()
	sp := &unstructured.Unstructured{}
	sp.SetGroupVersionKind(aigateway.SecurityPolicyGVK)
	err := c.Get(context.Background(), client.ObjectKey{Namespace: gateNS, Name: resourceName(gateNS, gateIS)}, sp)
	if apierrors.IsNotFound(err) {
		return false
	}
	if err != nil {
		t.Fatalf("unexpected error getting SecurityPolicy: %v", err)
	}
	return true
}

// No key is bound to the model → enforcement must NOT create a policy (an empty credentialRefs
// list would 500 the route). It falls through to the gateway backstop instead.
func TestReconcileSecurityPolicy_DefersWhenNoKeyBound(t *testing.T) {
	r := gateReconciler(gateISObj())
	if _, err := r.reconcileSecurityPolicy(context.Background(), logr.Discard(), gateISObj(), gateEntry()); err != nil {
		t.Fatalf("reconcileSecurityPolicy: %v", err)
	}
	if spPresent(t, r.Client) {
		t.Fatal("SecurityPolicy was created for a model with no bound key")
	}
}

// A key Secret bound to the model exists → enforcement produces the policy.
func TestReconcileSecurityPolicy_CreatesWhenKeyBound(t *testing.T) {
	r := gateReconciler(gateISObj(), boundKeySecret())
	if _, err := r.reconcileSecurityPolicy(context.Background(), logr.Discard(), gateISObj(), gateEntry()); err != nil {
		t.Fatalf("reconcileSecurityPolicy: %v", err)
	}
	if !spPresent(t, r.Client) {
		t.Fatal("SecurityPolicy was not created despite a bound key Secret existing")
	}
}

// A previously-created policy must be removed once the last key is unbound (no key Secret carries
// the model's bound label), reverting the model to the gateway backstop.
func TestReconcileSecurityPolicy_RemovesStaleWhenNoKeyBound(t *testing.T) {
	stale := un(aigateway.SecurityPolicyGVK, gateNS, resourceName(gateNS, gateIS))
	r := gateReconciler(gateISObj(), stale)
	if !spPresent(t, r.Client) {
		t.Fatal("precondition: stale SecurityPolicy should exist")
	}
	if _, err := r.reconcileSecurityPolicy(context.Background(), logr.Discard(), gateISObj(), gateEntry()); err != nil {
		t.Fatalf("reconcileSecurityPolicy: %v", err)
	}
	if spPresent(t, r.Client) {
		t.Fatal("stale SecurityPolicy was not removed when no key is bound")
	}
}

// The opt-out annotation removes the policy regardless of bound keys.
func TestReconcileSecurityPolicy_OptOutRemovesPolicy(t *testing.T) {
	is := gateISObj()
	is.SetAnnotations(map[string]string{"aim.eai.amd.com/api-key-auth": "false"})
	stale := un(aigateway.SecurityPolicyGVK, gateNS, resourceName(gateNS, gateIS))
	r := gateReconciler(is, boundKeySecret(), stale)
	if _, err := r.reconcileSecurityPolicy(context.Background(), logr.Discard(), is, gateEntry()); err != nil {
		t.Fatalf("reconcileSecurityPolicy: %v", err)
	}
	if spPresent(t, r.Client) {
		t.Fatal("opt-out model kept its SecurityPolicy")
	}
}

// A key-Secret event re-reconciles every managed InferenceService in the namespace (each recomputes
// its credentialRefs from the current label state).
func TestMapSecretToInferenceServices(t *testing.T) {
	r := gateReconciler(gateISObj())

	reqs := r.mapSecretToInferenceServices(context.Background(), boundKeySecret())
	if len(reqs) != 1 {
		t.Fatalf("expected 1 reconcile request, got %d: %v", len(reqs), reqs)
	}
	if reqs[0].Namespace != gateNS || reqs[0].Name != gateIS {
		t.Fatalf("unexpected request %v", reqs[0])
	}
}

// The Secret watch predicate only admits Secrets carrying the api-key contract label.
func TestIsApiKeySecretPredicate(t *testing.T) {
	pred := isApiKeySecret()
	if !pred.Create(event.CreateEvent{Object: boundKeySecret()}) {
		t.Error("api-key Secret should pass the predicate")
	}
	if pred.Create(event.CreateEvent{Object: un(secretGVK, gateNS, "unrelated-secret")}) {
		t.Error("Secret without the api-key label should be filtered out")
	}
}
