// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package managerutil

import (
	"testing"

	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"sigs.k8s.io/controller-runtime/pkg/cache"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// TestScopedCacheOptionsScopesSecretsOnly is the regression guard for the OOM fix: the manager cache
// must ListWatch only api-key Secrets, never every Secret in the cluster. It also guards the
// deliberate decision NOT to scope the InferenceService informer — label-scoping IS would break the
// finalizer-cleanup path (see ScopedCacheOptions doc), so only Secret must appear in ByObject.
func TestScopedCacheOptionsScopesSecretsOnly(t *testing.T) {
	opts := ScopedCacheOptions()
	if len(opts.ByObject) != 1 {
		t.Fatalf("expected exactly 1 scoped type (Secret only), got %d", len(opts.ByObject))
	}

	got := map[string]string{}
	for obj, byObj := range opts.ByObject {
		u, ok := obj.(*unstructured.Unstructured)
		if !ok {
			t.Fatalf("cache key is %T, want *unstructured.Unstructured", obj)
		}
		if byObj.Label == nil {
			t.Fatalf("kind %q has no label selector; cache would watch all of them", u.GetKind())
		}
		got[u.GetKind()] = byObj.Label.String()
	}

	wantSecret := aigateway.APIKeyLabel + "=true"
	if got["Secret"] != wantSecret {
		t.Errorf("Secret selector = %q, want %q", got["Secret"], wantSecret)
	}
	// InferenceService must NOT be scoped — scoping it would strand de-labelled ISes in Terminating.
	if _, scoped := got["InferenceService"]; scoped {
		t.Errorf("InferenceService is label-scoped; it must stay cluster-wide to preserve finalizer cleanup")
	}
}

// ensure the exported signature stays usable as a controller-runtime cache option source.
var _ func() cache.Options = ScopedCacheOptions
var _ client.Object = &unstructured.Unstructured{}
