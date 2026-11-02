// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Package models builds the OpenAI-compatible /v1/models list scoped to a single API key.
//
// Envoy AI Gateway's built-in /v1/models aggregates every managed model with no per-caller
// filtering, so any valid key sees the whole fleet. The ext_authz handler intercepts the
// /v1/models call (it already runs in the request path, ahead of the AI gateway's extProc) and
// returns this scoped list instead — without adding any route or policy to the AI-gateway Gateway,
// which its controller assumes it exclusively owns.
//
// The list is deployed ∩ authorized: the key's bound workloads intersected with the managed
// InferenceServices that actually exist. A model the key is bound to but not deployed has no
// InferenceService (and can't serve inference), so it is omitted; a deployed model that has scaled
// to zero still has its InferenceService and is listed.
package models

import (
	"context"
	"sort"
	"strings"

	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"github.com/silogen/ai-gateway-discovery/internal/apikey"
	"github.com/silogen/ai-gateway-discovery/internal/config"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

var secretListGVK = schema.GroupVersionKind{Version: "v1", Kind: "SecretList"}

// Model is one entry of an OpenAI /v1/models response.
//
// ID is the served model name (what OpenAI clients pass as `model`). The remaining fields are
// non-standard extensions (OpenAI clients ignore unknown fields):
//   - Backend: this model's workload UUID — the value to send as x-ai-eg-backend for precise,
//     backend-authoritative routing.
//   - OwnedBy: the calling key's display name, so the caller sees the list is scoped to their key.
//   - Status: the backend's deployment readiness ("Ready"/"NotReady"/"Unknown") from the
//     InferenceService Ready condition — a listed model may be deployed but not currently ready.
//   - Endpoint: the OpenAI base URL to call this model through (the unified AI gateway).
type Model struct {
	ID       string `json:"id"`
	Object   string `json:"object"`
	Created  int64  `json:"created"`
	OwnedBy  string `json:"owned_by"`
	Backend  string `json:"backend"`
	Status   string `json:"status"`
	Endpoint string `json:"endpoint"`
}

// readyStatus maps the InferenceService Ready condition to a caller-facing status string. A listed
// model always has an InferenceService (it's deployed), but may not be serving yet (e.g. scaled to
// zero or still starting), so this distinguishes Ready from NotReady.
func readyStatus(is *unstructured.Unstructured) string {
	conds, found, _ := unstructured.NestedSlice(is.Object, "status", "conditions")
	if !found {
		return "Unknown"
	}
	for _, c := range conds {
		cm, ok := c.(map[string]interface{})
		if !ok || cm["type"] != "Ready" {
			continue
		}
		switch cm["status"] {
		case "True":
			return "Ready"
		case "False":
			return "NotReady"
		default:
			// A Ready condition is True/False/Unknown; anything not explicitly True or False
			// (including a missing or malformed value) is reported as Unknown rather than being
			// misreported as NotReady.
			return "Unknown"
		}
	}
	return "Unknown"
}

// List is the OpenAI /v1/models response envelope.
type List struct {
	Object string  `json:"object"`
	Data   []Model `json:"data"`
}

// Build returns the model list a key may use: the workloads its Secret is bound to, intersected
// with the deployed managed InferenceServices, as one entry per (model, backend) and sorted for a
// stable response. Each entry carries its backend workload UUID and is owned_by the key's display
// name. An unknown key (bound to nothing deployed) yields an empty, non-nil list.
func Build(ctx context.Context, c client.Client, cfg *config.ControllerConfig, key string) (List, error) {
	bound, owner, err := keyBoundWorkloads(ctx, c, key)
	if err != nil {
		return List{}, err
	}
	data, err := deployedModels(ctx, c, cfg, bound, owner)
	if err != nil {
		return List{}, err
	}
	return List{Object: "list", Data: data}, nil
}

// displayName recovers the API-key display name from its client id. AIWB derives the client id as
// compute_client_id(namespace, displayName) = "token-<namespace>-<displayName>", and the key Secret
// lives in that namespace, so stripping the "token-<namespace>-" prefix yields the display name.
// Falls back to the raw client id if the format is unexpected.
func displayName(clientID, namespace string) string {
	prefix := "token-" + namespace + "-"
	if name := strings.TrimPrefix(clientID, prefix); name != clientID {
		return name
	}
	return clientID
}

// keyBoundWorkloads returns the set of workload ids the presented key is bound to, read from the
// bound-<workload-id> labels on the key's own Secret. The set may include undeployed workloads;
// deployedModels intersects it with the live InferenceServices. Matched cluster-wide, the same way
// the ext_authz path resolves membership.
func keyBoundWorkloads(ctx context.Context, c client.Client, key string) (map[string]struct{}, string, error) {
	list := &unstructured.UnstructuredList{}
	list.SetGroupVersionKind(secretListGVK)
	if err := c.List(ctx, list, client.MatchingLabels{aigateway.APIKeyLabel: "true"}); err != nil {
		return nil, "", err
	}
	bound := map[string]struct{}{}
	owner := ""
	for i := range list.Items {
		data, found, err := unstructured.NestedStringMap(list.Items[i].Object, "data")
		if !found || err != nil {
			continue
		}
		clientID, ok := apikey.MatchClientID(data, key)
		if !ok {
			continue
		}
		owner = displayName(clientID, list.Items[i].GetNamespace())
		// The matched Secret is this key's Secret; its bound-<workload-id> labels are the models it
		// may use. A key has one Secret, but union across matches to stay correct regardless.
		for labelKey, val := range list.Items[i].GetLabels() {
			if val == "true" && strings.HasPrefix(labelKey, aigateway.BoundLabelPrefix) {
				bound[strings.TrimPrefix(labelKey, aigateway.BoundLabelPrefix)] = struct{}{}
			}
		}
	}
	return bound, owner, nil
}

// deployedModels returns one OpenAI model entry per (model, backend) for every managed
// InferenceService whose workload id is in the bound set. Each entry carries its backend workload
// UUID (so the caller can route by x-ai-eg-backend) and is owned_by the key's display name. Entries
// are deduped by (model, backend) and sorted by model then backend for a stable response — a model
// name served by multiple bound backends appears once per backend.
func deployedModels(ctx context.Context, c client.Client, cfg *config.ControllerConfig, bound map[string]struct{}, owner string) ([]Model, error) {
	list := &unstructured.UnstructuredList{}
	listGVK := aigateway.InferenceServiceGVK
	listGVK.Kind += "List"
	list.SetGroupVersionKind(listGVK)
	if err := c.List(ctx, list, client.MatchingLabels{cfg.ManagedLabelName: cfg.ManagedLabelValue}); err != nil {
		return nil, err
	}
	// The unified AI gateway is the single OpenAI base URL for every model; callers target a
	// specific backend with the x-ai-eg-backend header (the Backend field), not a per-model URL.
	endpoint := ""
	if cfg.AIRouteHostname != "" {
		endpoint = "https://" + cfg.AIRouteHostname + "/v1"
	}
	// One entry per (model, backend). If several InferenceServices collide on that pair, pick a
	// deterministic winner — earliest creation time, breaking ties by object name — so the kept
	// entry (and its Created value) does not depend on client.List() ordering, which is unspecified.
	type mbKey struct{ model, backend string }
	type entry struct {
		model  Model
		source string
	}
	seen := map[mbKey]entry{}
	for i := range list.Items {
		is := &list.Items[i]
		workloadID := is.GetLabels()[cfg.WorkloadIDLabel]
		if workloadID == "" {
			continue
		}
		if _, ok := bound[workloadID]; !ok {
			continue
		}
		modelName := is.GetAnnotations()[cfg.ModelNameAnnotation]
		if modelName == "" {
			continue
		}
		cand := entry{
			model: Model{
				ID:       modelName,
				Object:   "model",
				Created:  is.GetCreationTimestamp().Unix(),
				OwnedBy:  owner,
				Backend:  workloadID,
				Status:   readyStatus(is),
				Endpoint: endpoint,
			},
			source: is.GetName(),
		}
		k := mbKey{model: modelName, backend: workloadID}
		if cur, dup := seen[k]; dup {
			if cand.model.Created > cur.model.Created ||
				(cand.model.Created == cur.model.Created && cand.source >= cur.source) {
				continue
			}
		}
		seen[k] = cand
	}
	out := make([]Model, 0, len(seen))
	for _, e := range seen {
		out = append(out, e.model)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].ID != out[j].ID {
			return out[i].ID < out[j].ID
		}
		return out[i].Backend < out[j].Backend
	})
	return out, nil
}
