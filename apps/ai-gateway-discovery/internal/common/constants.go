// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package common

const (
	Finalizer = "aigateway.silogen.ai/finalizer"

	DefaultManagedLabelName  = "app.kubernetes.io/managed-by"
	DefaultManagedLabelValue = "aim-engine"

	// DefaultModelNameAnnotation is the IS annotation key set by AIM-engine with
	// the actual vLLM-served model name (HF model ID).
	DefaultModelNameAnnotation = "aim.eai.amd.com/model-id"

	// DefaultWorkloadIDLabel is the AIM service UUID label on the InferenceService. It is both
	// the x-ai-eg-backend routing id and the suffix of the model's bound-<workload-id> membership
	// label, so routing, the per-model SecurityPolicy, and the body-path ext_authz all agree on
	// which keys a model accepts. Overridable via WORKLOAD_ID_LABEL for environments where AIM
	// stamps a different label key.
	DefaultWorkloadIDLabel = "airm.silogen.ai/workload-id"

	DefaultTargetNamespace  = "envoy-ai-gateway-system"
	DefaultGatewayName      = "https"
	DefaultGatewayNamespace = "envoy-gateway-system"

	DefaultHealthPort        = 8081
	DefaultInferencePoolPort = 8000

	// DefaultAuthzPort is the port the body-aware ext_authz HTTP handler listens on.
	// Envoy Gateway's extAuth (with bodyToExtAuth) calls it to authorize header-less
	// (standard OpenAI, model-in-body) inference requests the native per-route
	// apiKeyAuth cannot reach.
	DefaultAuthzPort = 8083

	// DefaultWorkloadsAuthzPort is the SEPARATE port the workloads ext_authz handler listens on.
	// The workloads SecurityPolicy targets this port, the ai-gateway policies target DefaultAuthzPort,
	// and the handler authorizes each family differently (workloads by path workload-id; ai-gateway by
	// request body). The port — set by each policy's backendRef, not by the client — is what tells the
	// two families apart. Path shape cannot: a client on ai.<domain> controls its URL, so any
	// path-based classifier is forgeable, but it cannot choose which port its ext_authz check hits.
	DefaultWorkloadsAuthzPort = 8084

	// DefaultAuthzServiceName / DefaultAuthzServiceNamespace are the controller's own ext_authz
	// Service, referenced by the per-model catch-all SecurityPolicy's extAuth backendRef. Match the
	// chart's Service name and the deploy namespace.
	DefaultAuthzServiceName      = "ai-gateway-discovery"
	DefaultAuthzServiceNamespace = "ai-gateway-discovery"

	// DefaultBodyAuthMaxRequestBytes is the request-body ceiling on the header-less path. It is
	// rendered into the per-model catch-all SecurityPolicy's bodyToExtAuth.maxRequestBytes and
	// bounds what the handler reads. Envoy answers a larger body with HTTP 413 and skips
	// authorization entirely (this beats failOpen), so it is a hard request-size limit for
	// standard OpenAI/Anthropic clients, which put the model in the body. The Envoy Gateway
	// default of 64KiB rejects ordinary large-context turns (~200k tokens is ~1MB).
	//
	// Must match aiGateway.bodyAuthMaxRequestBytes on the envoy-gateway-config chart, which sets
	// the same ceiling on the gateway-scoped policy; cluster-forge root/values.yaml drives both
	// from one value. These catch-all policies are rule-scoped and override the gateway-scoped
	// one per route, so if the two disagree the lower is what a request actually gets.
	DefaultBodyAuthMaxRequestBytes = 4 * 1024 * 1024

	DefaultEPPServicePort = 9002
	// DefaultEPPImage is the endpoint picker. It moved: gateway-api-inference-extension deleted
	// its scoring picker in v1.6, and the maintained successor is llm-d/llm-d-router. Same binary
	// lineage, same flags, and it still reads InferencePool from inference.networking.k8s.io/v1,
	// so the pinned CRD bundle is unaffected.
	DefaultEPPImage = "ghcr.io/llm-d/llm-d-router-endpoint-picker:v0.10.0"

	FieldManager = "ai-gateway-discovery"

	// DefaultAPIKeyAuthAnnotation is the per-model opt-out for native apiKeyAuth
	// enforcement. With the global flag on, every model with a workload-id is enforced;
	// setting this annotation to "false" on the InferenceService excludes that one model.
	DefaultAPIKeyAuthAnnotation = "aim.eai.amd.com/api-key-auth"

	// Default timeouts applied to every generated AIGatewayRoute rule. LLM
	// completions routinely exceed Envoy AI Gateway's 60s nil-default (HTTP 504),
	// so both are set to 30m out of the box; override via the Helm chart.
	DefaultRequestTimeout        = "30m"
	DefaultBackendRequestTimeout = "30m"
)
