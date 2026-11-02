// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Package managerutil holds controller-runtime manager wiring shared by the controller and authz
// binaries, so the two entrypoints build their manager cache the same way.
package managerutil

import (
	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/labels"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/cache"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// secretGVK is the core/v1 Secret, accessed unstructured to match how both the reconciler and the
// ext_authz handler read key Secrets (no typed corev1 dependency on the read path).
var secretGVK = schema.GroupVersionKind{Version: "v1", Kind: "Secret"}

func newUnstructured(gvk schema.GroupVersionKind) *unstructured.Unstructured {
	u := &unstructured.Unstructured{}
	u.SetGroupVersionKind(gvk)
	return u
}

// ScopedCacheOptions restricts the manager cache's Secret informer to only the Secrets carrying the
// api-key contract label. Without this the informer watches EVERY Secret in the cluster (the label
// filter on List is applied after the informer, not on the ListWatch), which is the OOM risk in a
// small pod. The ext_authz handler is fail-closed, so an OOMKill denies all workloads/header-less
// inference — the cache must not grow with unrelated Secret volume.
//
// IMPORTANT: this only takes effect for read paths that actually consult the cache. The handler and
// reconciler read Secrets/InferenceServices as unstructured, and controller-runtime's cache-backed
// client does a LIVE apiserver lookup for unstructured objects unless the manager sets
// Client.Cache.Unstructured = true. The authz binary sets that and prewarms informers (see
// CachedReadObjects) so its fail-closed data path serves from cache instead of a live LIST per check.
//
// The scope also narrows the controller's Secret event stream, independent of the read path: the
// reconciler's Secret watch only fires for Secrets carrying the api-key label, so a bound Secret
// missing that label produces no reconcile event. Benign because AIWB stamps the api-key label on
// every per-key Secret, but it is the reason the scope must match AIWB's labelling contract.
//
// Only Secrets are scoped. The InferenceService informer is deliberately left cluster-wide: a
// cluster has thousands of Secrets but only tens of InferenceServices, so scoping IS saves almost no
// memory, and it would break the finalizer-cleanup path in the controller — hasManagedLabel lets IS
// Delete events through regardless of label so a de-labelled IS still gets its finalizer removed, but
// a label-scoped informer would drop the object from the cache entirely, making the reconcile's Get
// return NotFound and leaving the IS stuck Terminating.
func ScopedCacheOptions() cache.Options {
	return cache.Options{
		ByObject: map[client.Object]cache.ByObject{
			newUnstructured(secretGVK): {
				Label: labels.SelectorFromSet(labels.Set{aigateway.APIKeyLabel: "true"}),
			},
		},
	}
}

// CachedReadObjects are the object types the ext_authz handler reads through the cache. The authz
// binary registers no controller of its own, so nothing would create these informers until the first
// request; it prewarms them (with BlockUntilSynced) so the readiness gate can block on a warm cache
// rather than returning immediately with zero informers.
func CachedReadObjects() []client.Object {
	return []client.Object{
		newUnstructured(secretGVK),
		newUnstructured(aigateway.InferenceServiceGVK),
	}
}
