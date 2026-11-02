// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package controller

import (
	"context"
	"testing"

	"github.com/go-logr/logr"
	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

const authzNS = "ai-gateway-discovery"

// catchAllReconciler builds a reconciler with the ext_authz Service coordinates set, so
// reconcileCatchAllExtAuth has a target to reference.
func catchAllReconciler(objs ...client.Object) *InferenceServiceReconciler {
	r := gateReconciler(objs...)
	r.Config.AuthzServiceName = "ai-gateway-discovery"
	r.Config.AuthzServiceNamespace = authzNS
	r.Config.AuthzPort = 8083
	return r
}

func catchAllName() string { return resourceName(gateNS, gateIS) + aigateway.CatchAllPolicySuffix }

func objPresent(t *testing.T, c client.Client, gvk schema.GroupVersionKind, ns, name string) bool {
	t.Helper()
	o := &unstructured.Unstructured{}
	o.SetGroupVersionKind(gvk)
	err := c.Get(context.Background(), client.ObjectKey{Namespace: ns, Name: name}, o)
	if apierrors.IsNotFound(err) {
		return false
	}
	if err != nil {
		t.Fatalf("unexpected error getting %s %s/%s: %v", gvk.Kind, ns, name, err)
	}
	return true
}

// The model is enforcing apiKeyAuth → the catch-all ext_authz SecurityPolicy and the shared
// ReferenceGrant are both stamped, closing the body-only cross-model bypass.
func TestReconcileCatchAll_Enforcing_Creates(t *testing.T) {
	r := catchAllReconciler(gateISObj())
	if err := r.reconcileCatchAllExtAuth(context.Background(), logr.Discard(), gateEntry(), true); err != nil {
		t.Fatalf("reconcileCatchAllExtAuth: %v", err)
	}
	if !objPresent(t, r.Client, aigateway.SecurityPolicyGVK, gateNS, catchAllName()) {
		t.Fatal("catch-all SecurityPolicy was not created when enforcing")
	}
	if !objPresent(t, r.Client, aigateway.ReferenceGrantGVK, authzNS, gateNS) {
		t.Fatal("ext_authz ReferenceGrant was not created when enforcing")
	}
}

// The model is NOT enforcing apiKeyAuth (opted out / no bound key) → the catch-all must not be
// stamped, so those models keep gateway-backstop behavior on every path.
func TestReconcileCatchAll_NotEnforcing_CreatesNothing(t *testing.T) {
	r := catchAllReconciler(gateISObj())
	if err := r.reconcileCatchAllExtAuth(context.Background(), logr.Discard(), gateEntry(), false); err != nil {
		t.Fatalf("reconcileCatchAllExtAuth: %v", err)
	}
	if objPresent(t, r.Client, aigateway.SecurityPolicyGVK, gateNS, catchAllName()) {
		t.Fatal("catch-all SecurityPolicy created for a non-enforcing model")
	}
}

// A previously-stamped catch-all policy is removed once the model stops enforcing, reverting the
// body-only path to the gateway backstop rather than leaving a dangling ext_authz override.
func TestReconcileCatchAll_RemovesStaleWhenNotEnforcing(t *testing.T) {
	stale := un(aigateway.SecurityPolicyGVK, gateNS, catchAllName())
	r := catchAllReconciler(gateISObj(), stale)
	if !objPresent(t, r.Client, aigateway.SecurityPolicyGVK, gateNS, catchAllName()) {
		t.Fatal("precondition: stale catch-all SecurityPolicy should exist")
	}
	if err := r.reconcileCatchAllExtAuth(context.Background(), logr.Discard(), gateEntry(), false); err != nil {
		t.Fatalf("reconcileCatchAllExtAuth: %v", err)
	}
	if objPresent(t, r.Client, aigateway.SecurityPolicyGVK, gateNS, catchAllName()) {
		t.Fatal("stale catch-all SecurityPolicy was not removed when the model stopped enforcing")
	}
}
