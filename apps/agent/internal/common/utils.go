// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package common

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/predicate"
)

// ManagedNamespaceEventFilter returns a predicate that filters events based on namespace labels.
func ManagedNamespaceEventFilter(c client.Client) predicate.Predicate {
	return predicate.NewPredicateFuncs(func(obj client.Object) bool {
		ns := &corev1.Namespace{}
		if err := c.Get(context.Background(), client.ObjectKey{Name: obj.GetNamespace()}, ns); err != nil {
			return false
		}

		nsLabels := ns.GetLabels()
		if nsLabels == nil {
			return false
		}
		_, hasLabel := nsLabels[ProjectIDLabel]
		return hasLabel
	})
}

// RemoveFinalizer removes the provided finalizer from an object read from the API.
// The object must carry a resourceVersion so stale-cache writes fail with a conflict.
func RemoveFinalizer(
	ctx context.Context,
	c client.Client,
	obj client.Object,
	finalizer string,
) error {
	if !controllerutil.ContainsFinalizer(obj, finalizer) {
		return nil
	}

	baseObj := obj.DeepCopyObject()
	base, ok := baseObj.(client.Object)
	if !ok {
		return fmt.Errorf("failed to deep copy object: expected client.Object, got %T", baseObj)
	}

	controllerutil.RemoveFinalizer(obj, finalizer)
	// Optimistic lock: a merge patch replaces the whole finalizers array, so a patch
	// built from a stale informer-cache copy would re-add finalizers another controller
	// already removed. On a deleting object the apiserver rejects that as "no new
	// finalizers can be added if the object is being deleted", looping the reconciler.
	// Carrying resourceVersion turns a stale write into a retriable conflict instead.
	return c.Patch(ctx, obj, client.MergeFromWithOptions(base, client.MergeFromWithOptimisticLock{}))
}

// AddFinalizerIfNeeded adds a finalizer to an object read from the API when needed.
// The object must carry a resourceVersion so stale-cache writes fail with a conflict.
func AddFinalizerIfNeeded(
	ctx context.Context,
	c client.Client,
	obj client.Object,
	finalizer string,
) error {
	if !controllerutil.ContainsFinalizer(obj, finalizer) {
		// deep copy the object to avoid modifying the original object
		// use a patch (instead of Update) so we only modify the finalizers field
		baseObj := obj.DeepCopyObject()
		base, ok := baseObj.(client.Object)
		if !ok {
			return fmt.Errorf("failed to deep copy object: expected client.Object, got %T", baseObj)
		}
		controllerutil.AddFinalizer(obj, finalizer)
		// Optimistic lock so a stale-cache add cannot race a concurrent deletion: if the
		// object started deleting after this cached read, the resourceVersion mismatch
		// yields a retriable conflict rather than a rejected finalizer add (see
		// RemoveFinalizer for the same hazard).
		return c.Patch(ctx, obj, client.MergeFromWithOptions(base, client.MergeFromWithOptimisticLock{}))
	}
	return nil
}
