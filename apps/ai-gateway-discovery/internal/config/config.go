// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package config

import (
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/silogen/ai-gateway-discovery/internal/common"
)

type ControllerConfig struct {
	ManagedLabelName  string
	ManagedLabelValue string

	// ModelNameAnnotation is the IS annotation key set by AIM-engine with the
	// actual vLLM-served model name (HF model ID), used as the x-ai-eg-model
	// route match value.
	ModelNameAnnotation string

	// WorkloadIDLabel is the InferenceService label carrying the AIM workload UUID. It is the
	// x-ai-eg-backend routing id and the suffix of the bound-<workload-id> membership label, so
	// routing, the per-model SecurityPolicy, and the body-path ext_authz agree on key membership.
	WorkloadIDLabel string

	TargetNamespace  string
	GatewayName      string
	GatewayNamespace string

	// AIRouteHostname is the Host header value added to every AIGatewayRoute.
	// Required — without it the route matches all hostnames on the shared Gateway.
	AIRouteHostname string
	HealthPort      int

	// AuthzPort is the port the body-aware ext_authz HTTP handler serves on. Envoy
	// Gateway's extAuth calls it to authorize header-less (model-in-body) requests.
	AuthzPort int

	// WorkloadsAuthzPort is the separate port the workloads ext_authz handler serves on. The
	// workloads SecurityPolicy's backendRef targets this port; requests arriving here are authorized
	// on the path's workload-id. Keeping it distinct from AuthzPort is how the handler tells the
	// workloads family from the ai-gateway (body) family — the port is chosen by the policy, not the
	// client, so unlike a path-based classifier it cannot be forged.
	WorkloadsAuthzPort int

	// AuthzServiceName / AuthzServiceNamespace identify this controller's ext_authz Service, used
	// as the extAuth backendRef in the per-model catch-all SecurityPolicy. They default to the
	// controller's own Service; the SecurityPolicy lives in the workload namespace and references
	// this Service cross-namespace (needs a ReferenceGrant).
	AuthzServiceName      string
	AuthzServiceNamespace string

	// BodyAuthMaxRequestBytes is the request-body ceiling on the header-less path: it is
	// rendered into each per-model catch-all SecurityPolicy and caps what the handler reads.
	// Keep it equal to the gateway-scoped policy's ceiling (see DefaultBodyAuthMaxRequestBytes).
	BodyAuthMaxRequestBytes int

	// EPP image and port for the inference-epp Deployment and Service the
	// controller creates in each InferenceService namespace.
	EPPImage          string
	EPPServicePort    int32
	InferencePoolPort int32

	// APIKeyAuthAnnotation is the per-model opt-out annotation key. Native apiKeyAuth
	// enforcement is always on (fleet-wide): every model with a workload-id is enforced;
	// setting this annotation to "false" excludes that one model (e.g. to unblock a rollout).
	APIKeyAuthAnnotation string

	// RequestTimeout and BackendRequestTimeout are Gateway API duration strings
	// (e.g. "30m", "90s") set on every generated AIGatewayRoute rule. They guard
	// against Envoy AI Gateway's 60s nil-default that 504s long LLM completions.
	RequestTimeout        string
	BackendRequestTimeout string
}

func Load() (*ControllerConfig, error) {
	cfg := &ControllerConfig{
		ManagedLabelName:        getEnv("MANAGED_LABEL_NAME", common.DefaultManagedLabelName),
		ManagedLabelValue:       getEnv("MANAGED_LABEL_VALUE", common.DefaultManagedLabelValue),
		ModelNameAnnotation:     getEnv("MODEL_NAME_ANNOTATION", common.DefaultModelNameAnnotation),
		WorkloadIDLabel:         getEnv("WORKLOAD_ID_LABEL", common.DefaultWorkloadIDLabel),
		TargetNamespace:         getEnv("TARGET_NAMESPACE", common.DefaultTargetNamespace),
		GatewayName:             getEnv("GATEWAY_NAME", common.DefaultGatewayName),
		GatewayNamespace:        getEnv("GATEWAY_NAMESPACE", common.DefaultGatewayNamespace),
		AIRouteHostname:         os.Getenv("AI_ROUTE_HOSTNAME"),
		HealthPort:              getEnvAsInt("HEALTH_PORT", common.DefaultHealthPort),
		AuthzPort:               getEnvAsInt("AUTHZ_PORT", common.DefaultAuthzPort),
		WorkloadsAuthzPort:      getEnvAsInt("WORKLOADS_AUTHZ_PORT", common.DefaultWorkloadsAuthzPort),
		AuthzServiceName:        getEnv("AUTHZ_SERVICE_NAME", common.DefaultAuthzServiceName),
		AuthzServiceNamespace:   getEnv("AUTHZ_SERVICE_NAMESPACE", common.DefaultAuthzServiceNamespace),
		BodyAuthMaxRequestBytes: getEnvAsInt("BODY_AUTH_MAX_REQUEST_BYTES", common.DefaultBodyAuthMaxRequestBytes),
		EPPImage:                getEnv("EPP_IMAGE", common.DefaultEPPImage),
		EPPServicePort:          int32(getEnvAsInt("EPP_SERVICE_PORT", common.DefaultEPPServicePort)),
		InferencePoolPort:       int32(getEnvAsInt("INFERENCE_POOL_PORT", common.DefaultInferencePoolPort)),
		APIKeyAuthAnnotation:    getEnv("API_KEY_AUTH_ANNOTATION", common.DefaultAPIKeyAuthAnnotation),
		RequestTimeout:          getEnv("REQUEST_TIMEOUT", common.DefaultRequestTimeout),
		BackendRequestTimeout:   getEnv("BACKEND_REQUEST_TIMEOUT", common.DefaultBackendRequestTimeout),
	}

	if cfg.ManagedLabelName == "" {
		return nil, fmt.Errorf("MANAGED_LABEL_NAME must not be empty")
	}

	// A non-positive ceiling would render maxRequestBytes: 0 into every catch-all policy and
	// reject the whole header-less path, so refuse to start rather than publish it.
	if cfg.BodyAuthMaxRequestBytes <= 0 {
		return nil, fmt.Errorf("BODY_AUTH_MAX_REQUEST_BYTES must be a positive integer, got %d", cfg.BodyAuthMaxRequestBytes)
	}
	if cfg.GatewayName == "" {
		return nil, fmt.Errorf("GATEWAY_NAME must not be empty")
	}
	if cfg.AIRouteHostname == "" {
		return nil, fmt.Errorf("AI_ROUTE_HOSTNAME must not be empty: without a host filter the route matches all traffic on the shared Gateway")
	}
	if cfg.EPPImage == "" {
		return nil, fmt.Errorf("EPP_IMAGE must not be empty")
	}
	if _, err := time.ParseDuration(cfg.RequestTimeout); err != nil {
		return nil, fmt.Errorf("REQUEST_TIMEOUT %q is not a valid duration: %w", cfg.RequestTimeout, err)
	}
	if _, err := time.ParseDuration(cfg.BackendRequestTimeout); err != nil {
		return nil, fmt.Errorf("BACKEND_REQUEST_TIMEOUT %q is not a valid duration: %w", cfg.BackendRequestTimeout, err)
	}

	return cfg, nil
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvAsInt(name string, defaultVal int) int {
	if val, err := strconv.Atoi(os.Getenv(name)); err == nil {
		return val
	}
	return defaultVal
}
