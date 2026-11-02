// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package common

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/event"
)

const testFinalizer = "example.com/test-finalizer"

func TestManagedNamespaceEventFilter(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)
	_ = appsv1.AddToScheme(scheme)

	t.Run("allows resource in namespace with project-id label", func(t *testing.T) {
		ns := &corev1.Namespace{
			ObjectMeta: metav1.ObjectMeta{
				Name: "managed-namespace",
				Labels: map[string]string{
					ProjectIDLabel: "project-123",
				},
			},
		}

		deployment := &appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-deployment",
				Namespace: "managed-namespace",
			},
		}

		client := fake.NewClientBuilder().WithScheme(scheme).WithObjects(ns).Build()

		filter := ManagedNamespaceEventFilter(client)
		result := filter.Create(event.CreateEvent{Object: deployment})

		assert.True(t, result, "should allow resource in managed namespace")
	})

	t.Run("blocks resource in namespace without project-id label", func(t *testing.T) {
		ns := &corev1.Namespace{
			ObjectMeta: metav1.ObjectMeta{
				Name: "unmanaged-namespace",
				Labels: map[string]string{
					"other-label": "other-value",
				},
			},
		}

		deployment := &appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-deployment",
				Namespace: "unmanaged-namespace",
			},
		}

		client := fake.NewClientBuilder().WithScheme(scheme).WithObjects(ns).Build()

		filter := ManagedNamespaceEventFilter(client)
		result := filter.Create(event.CreateEvent{Object: deployment})

		assert.False(t, result, "should block resource in unmanaged namespace")
	})

	t.Run("blocks resource when namespace does not exist", func(t *testing.T) {
		deployment := &appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-deployment",
				Namespace: "non-existent-namespace",
			},
		}

		client := fake.NewClientBuilder().WithScheme(scheme).Build()

		filter := ManagedNamespaceEventFilter(client)
		result := filter.Create(event.CreateEvent{Object: deployment})

		assert.False(t, result, "should block resource when namespace does not exist")
	})
}

// getFresh reads the object back from the client so it carries the
// resourceVersion a real controller always has after Get — the precondition for
// the optimistic-lock patch the finalizer helpers issue.
func getFresh(t *testing.T, c client.Client, obj client.Object) {
	t.Helper()
	require.NoError(t, c.Get(context.Background(), client.ObjectKeyFromObject(obj), obj))
}

func TestAddFinalizerIfNeeded(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)

	t.Run("adds finalizer when not present", func(t *testing.T) {
		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-pod",
				Namespace: "test-namespace",
			},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()
		getFresh(t, c, pod)

		err := AddFinalizerIfNeeded(context.Background(), c, pod, testFinalizer)

		assert.NoError(t, err)
		assert.True(t, controllerutil.ContainsFinalizer(pod, testFinalizer))
	})

	t.Run("does not duplicate finalizer", func(t *testing.T) {
		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:       "test-pod",
				Namespace:  "test-namespace",
				Finalizers: []string{testFinalizer},
			},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()
		getFresh(t, c, pod)

		err := AddFinalizerIfNeeded(context.Background(), c, pod, testFinalizer)

		assert.NoError(t, err)
		assert.True(t, controllerutil.ContainsFinalizer(pod, testFinalizer))
		assert.Len(t, pod.GetFinalizers(), 1)
	})

	t.Run("requires resourceVersion when adding", func(t *testing.T) {
		stored := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{Name: "test-pod", Namespace: "test-namespace"},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(stored).Build()

		// A controller-constructed object with no resourceVersion (never Get-ed).
		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{Name: "test-pod", Namespace: "test-namespace"},
		}
		err := AddFinalizerIfNeeded(context.Background(), c, pod, testFinalizer)

		require.Error(t, err)
		assert.ErrorContains(t, err, "does not have any resource version")
	})

	t.Run("stale add conflicts instead of racing a concurrent change", func(t *testing.T) {
		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test-pod",
				Namespace: "test-namespace",
			},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()

		// stale holds the object as first read; the live copy then advances.
		stale := &corev1.Pod{}
		require.NoError(t, c.Get(context.Background(), client.ObjectKeyFromObject(pod), stale))

		live := stale.DeepCopy()
		live.Labels = map[string]string{"changed": "true"}
		require.NoError(t, c.Update(context.Background(), live))

		err := AddFinalizerIfNeeded(context.Background(), c, stale, testFinalizer)

		require.Error(t, err)
		assert.True(t, apierrors.IsConflict(err), "expected a conflict, got: %v", err)

		// The conflicted patch must not have touched storage: no finalizer added,
		// and the concurrent change preserved.
		after := &corev1.Pod{}
		require.NoError(t, c.Get(context.Background(), client.ObjectKeyFromObject(pod), after))
		assert.False(t, controllerutil.ContainsFinalizer(after, testFinalizer),
			"conflicted add must not persist the finalizer")
		assert.Equal(t, "true", after.Labels["changed"],
			"conflicted add must not clobber the concurrent change")
	})
}

func TestRemoveFinalizer(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)

	t.Run("removes finalizer when present", func(t *testing.T) {
		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:       "test-pod",
				Namespace:  "test-namespace",
				Finalizers: []string{testFinalizer},
			},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()
		getFresh(t, c, pod)

		err := RemoveFinalizer(context.Background(), c, pod, testFinalizer)

		assert.NoError(t, err)
		assert.False(t, controllerutil.ContainsFinalizer(pod, testFinalizer))
	})

	t.Run("no-op when finalizer not present", func(t *testing.T) {
		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:       "test-pod",
				Namespace:  "test-namespace",
				Finalizers: []string{"other-finalizer"},
			},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()
		getFresh(t, c, pod)

		err := RemoveFinalizer(context.Background(), c, pod, testFinalizer)

		assert.NoError(t, err)
		assert.True(t, controllerutil.ContainsFinalizer(pod, "other-finalizer"))
	})

	t.Run("removes only the specified finalizer", func(t *testing.T) {
		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:       "test-pod",
				Namespace:  "test-namespace",
				Finalizers: []string{testFinalizer, "other-finalizer"},
			},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()
		getFresh(t, c, pod)

		err := RemoveFinalizer(context.Background(), c, pod, testFinalizer)

		assert.NoError(t, err)
		assert.False(t, controllerutil.ContainsFinalizer(pod, testFinalizer))
		assert.True(t, controllerutil.ContainsFinalizer(pod, "other-finalizer"))
	})

	t.Run("requires resourceVersion when removing", func(t *testing.T) {
		stored := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:       "test-pod",
				Namespace:  "test-namespace",
				Finalizers: []string{testFinalizer},
			},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(stored).Build()

		// A controller-constructed object with no resourceVersion (never Get-ed).
		pod := stored.DeepCopy()
		pod.ResourceVersion = ""
		err := RemoveFinalizer(context.Background(), c, pod, testFinalizer)

		require.Error(t, err)
		assert.ErrorContains(t, err, "does not have any resource version")
	})

	// Reproduces the airm-agent finalizer race: a controller reads an object from
	// its cache, another actor removes a different finalizer in etcd, and the
	// controller's cached view is now stale. Without optimistic concurrency the
	// whole-array merge patch would re-add the finalizer etcd already dropped —
	// which the apiserver rejects on a deleting object with "no new finalizers can
	// be added". The patch must conflict and requeue instead.
	t.Run("stale removal conflicts instead of clobbering finalizers", func(t *testing.T) {
		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:       "test-pod",
				Namespace:  "test-namespace",
				Finalizers: []string{testFinalizer, "other-finalizer"},
			},
		}
		c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()

		// stale is the controller's cached view: both finalizers still present.
		stale := &corev1.Pod{}
		require.NoError(t, c.Get(context.Background(), client.ObjectKeyFromObject(pod), stale))

		// Another actor drops "other-finalizer" in etcd, advancing resourceVersion.
		live := stale.DeepCopy()
		controllerutil.RemoveFinalizer(live, "other-finalizer")
		require.NoError(t, c.Update(context.Background(), live))

		err := RemoveFinalizer(context.Background(), c, stale, testFinalizer)

		require.Error(t, err)
		assert.True(t, apierrors.IsConflict(err), "expected a conflict, got: %v", err)

		// etcd must not have regained the finalizer the other actor removed.
		after := &corev1.Pod{}
		require.NoError(t, c.Get(context.Background(), client.ObjectKeyFromObject(pod), after))
		assert.False(t, controllerutil.ContainsFinalizer(after, "other-finalizer"),
			"stale patch must not resurrect a removed finalizer")
	})
}
