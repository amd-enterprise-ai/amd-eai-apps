// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package models

import (
	"context"
	"encoding/base64"
	"testing"
	"time"

	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"github.com/silogen/ai-gateway-discovery/internal/common"
	"github.com/silogen/ai-gateway-discovery/internal/config"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

const (
	ns       = "workbench"
	managedK = "app.kubernetes.io/managed-by"
	managedV = "aim-engine"
	keyA     = "amd_aim_api_key_hvs.aaaaaaaa"
	keyB     = "amd_aim_api_key_hvs.bbbbbbbb"
)

var secretGVK = schema.GroupVersionKind{Version: "v1", Kind: "Secret"}

func testScheme() *runtime.Scheme {
	s := runtime.NewScheme()
	for _, gvk := range []schema.GroupVersionKind{aigateway.InferenceServiceGVK, secretGVK} {
		s.AddKnownTypeWithName(gvk, &unstructured.Unstructured{})
		listGVK := gvk
		listGVK.Kind += "List"
		s.AddKnownTypeWithName(listGVK, &unstructured.UnstructuredList{})
	}
	return s
}

func inferenceService(name, workloadID, modelName string) *unstructured.Unstructured {
	return inferenceServiceWithReady(name, workloadID, modelName, "True")
}

func inferenceServiceWithReady(name, workloadID, modelName, ready string) *unstructured.Unstructured {
	o := &unstructured.Unstructured{}
	o.SetGroupVersionKind(aigateway.InferenceServiceGVK)
	o.SetNamespace(ns)
	o.SetName(name)
	o.SetLabels(map[string]string{managedK: managedV, common.DefaultWorkloadIDLabel: workloadID})
	o.SetAnnotations(map[string]string{common.DefaultModelNameAnnotation: modelName})
	_ = unstructured.SetNestedSlice(o.Object, []interface{}{
		map[string]interface{}{"type": "Ready", "status": ready},
	}, "status", "conditions")
	return o
}

func inferenceServiceCreated(name, workloadID, modelName string, createdUnix int64) *unstructured.Unstructured {
	o := inferenceService(name, workloadID, modelName)
	o.SetCreationTimestamp(metav1.NewTime(time.Unix(createdUnix, 0)))
	return o
}

func keySecret(name, clientID, keyValue string, boundWorkloadIDs ...string) *unstructured.Unstructured {
	o := &unstructured.Unstructured{}
	o.SetGroupVersionKind(secretGVK)
	o.SetNamespace(ns)
	o.SetName(name)
	labels := map[string]string{aigateway.APIKeyLabel: "true"}
	for _, wl := range boundWorkloadIDs {
		labels[aigateway.BoundLabel(wl)] = "true"
	}
	o.SetLabels(labels)
	_ = unstructured.SetNestedField(o.Object, base64.StdEncoding.EncodeToString([]byte(keyValue)), "data", clientID)
	return o
}

func handlerCfg() *config.ControllerConfig {
	return &config.ControllerConfig{
		ManagedLabelName:    managedK,
		ManagedLabelValue:   managedV,
		WorkloadIDLabel:     common.DefaultWorkloadIDLabel,
		ModelNameAnnotation: common.DefaultModelNameAnnotation,
		AIRouteHostname:     "ai.example.com",
	}
}

func build(t *testing.T, key string, objs ...client.Object) List {
	t.Helper()
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(objs...).Build()
	list, err := Build(context.Background(), c, handlerCfg(), key)
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	if list.Object != "list" {
		t.Errorf("object = %q, want list", list.Object)
	}
	return list
}

func ids(list List) []string {
	out := make([]string, 0, len(list.Data))
	for _, m := range list.Data {
		out = append(out, m.ID)
	}
	return out
}

// The list is scoped to the key's bindings: only models it is bound to appear, each carrying its
// backend workload id and owned_by the key's display name (derived from the client id).
func TestBuild_FiltersToKeyBindings(t *testing.T) {
	list := build(t, keyA,
		inferenceService("is-a", "wl-a", "model-a"),
		inferenceService("is-b", "wl-b", "model-b"),
		keySecret("apikey-1", "token-workbench-prod-key", keyA, "wl-a"),
	)
	got := ids(list)
	if len(got) != 1 || got[0] != "model-a" {
		t.Fatalf("ids = %v, want [model-a]", got)
	}
	m := list.Data[0]
	if m.Object != "model" || m.OwnedBy != "prod-key" || m.Backend != "wl-a" {
		t.Errorf("shape = %+v, want object=model owned_by=prod-key backend=wl-a", m)
	}
	if m.Status != "Ready" || m.Endpoint != "https://ai.example.com/v1" {
		t.Errorf("shape = %+v, want status=Ready endpoint=https://ai.example.com/v1", m)
	}
}

// A deployed-but-not-ready backend is still listed, with status NotReady.
func TestBuild_NotReadyStatus(t *testing.T) {
	list := build(t, keyA,
		inferenceServiceWithReady("is-a", "wl-a", "model-a", "False"),
		keySecret("apikey-1", "token-workbench-prod-key", keyA, "wl-a"),
	)
	if len(list.Data) != 1 || list.Data[0].Status != "NotReady" {
		t.Fatalf("data = %+v, want one entry with status=NotReady", list.Data)
	}
}

// A backend whose Ready condition is Unknown is reported as Unknown, not misreported as NotReady.
func TestBuild_UnknownStatus(t *testing.T) {
	list := build(t, keyA,
		inferenceServiceWithReady("is-a", "wl-a", "model-a", "Unknown"),
		keySecret("apikey-1", "token-workbench-prod-key", keyA, "wl-a"),
	)
	if len(list.Data) != 1 || list.Data[0].Status != "Unknown" {
		t.Fatalf("data = %+v, want one entry with status=Unknown", list.Data)
	}
}

// When several InferenceServices collide on the same (model, backend), the entry is deterministic —
// the earliest creation time wins regardless of list ordering — so Created does not flap per request.
func TestBuild_DedupeDeterministicCreated(t *testing.T) {
	// is-late sorts before is-early by name (the order the fake client lists in) but was created
	// later; the earlier is-early must win.
	list := build(t, keyA,
		inferenceServiceCreated("is-late", "wl-a", "model-a", 2000),
		inferenceServiceCreated("is-early", "wl-a", "model-a", 1000),
		keySecret("apikey-1", "token-workbench-1", keyA, "wl-a"),
	)
	if len(list.Data) != 1 {
		t.Fatalf("data = %+v, want one deduped entry", list.Data)
	}
	if list.Data[0].Created != 1000 {
		t.Fatalf("created = %d, want 1000 (earliest)", list.Data[0].Created)
	}
}

// A model name served by two bound workloads appears once PER BACKEND, each entry carrying its own
// backend id (so the caller can route precisely to either).
func TestBuild_OneEntryPerBackend(t *testing.T) {
	list := build(t, keyA,
		inferenceService("is-a1", "wl-a1", "shared-model"),
		inferenceService("is-a2", "wl-a2", "shared-model"),
		keySecret("apikey-1", "token-workbench-1", keyA, "wl-a1", "wl-a2"),
	)
	if got := ids(list); len(got) != 2 || got[0] != "shared-model" || got[1] != "shared-model" {
		t.Fatalf("ids = %v, want [shared-model shared-model]", got)
	}
	backends := map[string]bool{}
	for _, m := range list.Data {
		backends[m.Backend] = true
	}
	if !backends["wl-a1"] || !backends["wl-a2"] {
		t.Errorf("backends = %v, want both wl-a1 and wl-a2", backends)
	}
}

// A model the key is bound to but that is not deployed (no InferenceService) is not listed.
func TestBuild_ExcludesUndeployedBinding(t *testing.T) {
	list := build(t, keyA,
		inferenceService("is-a", "wl-a", "model-a"),
		keySecret("apikey-1", "token-workbench-1", keyA, "wl-a", "wl-ghost"),
	)
	if got := ids(list); len(got) != 1 || got[0] != "model-a" {
		t.Fatalf("ids = %v, want [model-a] (undeployed wl-ghost excluded)", got)
	}
}

// A key matching no Secret resolves to an empty (non-nil) list.
func TestBuild_UnknownKeyEmpty(t *testing.T) {
	list := build(t, keyB,
		inferenceService("is-a", "wl-a", "model-a"),
		keySecret("apikey-1", "token-workbench-1", keyA, "wl-a"),
	)
	if list.Data == nil {
		t.Fatal("Data is nil, want empty non-nil slice")
	}
	if len(list.Data) != 0 {
		t.Fatalf("ids = %v, want empty", ids(list))
	}
}
