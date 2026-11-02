// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package aigateway

import (
	"fmt"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
)

var (
	EPPDeploymentGVK = schema.GroupVersionKind{Group: "apps", Version: "v1", Kind: "Deployment"}
	EPPServiceGVK    = schema.GroupVersionKind{Group: "", Version: "v1", Kind: "Service"}
)

// eppConfigText is the EndpointPickerConfig passed to the picker. See the args below for why
// two parsers are registered and why their order matters.
const eppConfigText = `{"apiVersion":"llm-d.ai/v1alpha1","kind":"EndpointPickerConfig","plugins":[{"name":"core-metrics-extractor","type":"core-metrics-extractor","parameters":{"engineConfigs":[{"name":"vllm","queuedRequestsSpec":"vllm:num_requests_waiting","runningRequestsSpec":"vllm:num_requests_running","kvUsageSpec":"vllm:kv_cache_usage_perc","loraSpec":"","cacheInfoSpec":"vllm:cache_config_info"}]}},{"name":"openai-parser","type":"openai-parser","parameters":{}},{"name":"passthrough-parser","type":"passthrough-parser","parameters":{}}],"requestHandler":{"parsers":[{"pluginRef":"openai-parser"},{"pluginRef":"passthrough-parser"}]}}`

// BuildEPPDeployment constructs an EPP Deployment for the given InferenceService.
// Each IS gets its own EPP deployment named after entry.ResourceName so multiple
// ISes in the same namespace each watch their own InferencePool.
func BuildEPPDeployment(entry BackendEntry, eppName, image string, grpcPort int32) *unstructured.Unstructured {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(EPPDeploymentGVK)
	obj.SetName(eppName)
	obj.SetNamespace(entry.ISNamespace)

	_ = unstructured.SetNestedField(obj.Object, int64(1), "spec", "replicas")
	_ = unstructured.SetNestedMap(obj.Object, map[string]interface{}{
		"app": eppName,
	}, "spec", "selector", "matchLabels")
	_ = unstructured.SetNestedMap(obj.Object, map[string]interface{}{
		"app": eppName,
	}, "spec", "template", "metadata", "labels")
	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{
			"name":  "epp",
			"image": image,
			"args": []interface{}{
				fmt.Sprintf("--pool-name=%s", entry.ResourceName),
				fmt.Sprintf("--pool-namespace=%s", entry.ISNamespace),
				// Only inference.networking.k8s.io/v1 is supported; set it explicitly
				// rather than relying on the binary's default.
				"--pool-group=inference.networking.k8s.io",
				fmt.Sprintf("--grpc-port=%d", grpcPort),
				"--grpc-health-port=9003",
				"--metrics-port=9090",
				// Two parsers, in this order. openai-parser claims the JSON endpoints
				// (chat/completions, completions, embeddings, responses, conversations,
				// images/generations) and parses their bodies as before.
				// passthrough-parser claims no paths, which registers it as the fallback
				// for everything else, and it returns the body unread. That is what lets
				// multipart endpoints such as /v1/audio/transcriptions through: the
				// OpenAI parser JSON-unmarshals every body it handles and fails on the
				// leading "--" of a multipart boundary. Order matters — a fallback
				// swallows all remaining traffic, so anything after it is never reached.
				//
				// loraSpec is "" because vLLM without LoRA adapters does not expose
				// vllm:lora_requests_info, and the extractor otherwise fails every poll.
				"--config-text=" + eppConfigText,
			},
			"ports": []interface{}{
				map[string]interface{}{"name": "grpc", "containerPort": int64(grpcPort)},
				map[string]interface{}{"name": "grpc-health", "containerPort": int64(9003)},
				map[string]interface{}{"name": "metrics", "containerPort": int64(9090)},
			},
			"resources": map[string]interface{}{
				"requests": map[string]interface{}{
					"cpu":    "50m",
					"memory": "64Mi",
				},
				"limits": map[string]interface{}{
					"memory": "128Mi",
				},
			},
		},
	}, "spec", "template", "spec", "containers")

	return obj
}

// BuildEPPService constructs the EPP Service that InferencePool's endpointPickerRef
// targets. Named after eppName so each IS has its own service.
func BuildEPPService(entry BackendEntry, eppName string, port int32) *unstructured.Unstructured {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(EPPServiceGVK)
	obj.SetName(eppName)
	obj.SetNamespace(entry.ISNamespace)

	_ = unstructured.SetNestedMap(obj.Object, map[string]interface{}{
		"app": eppName,
	}, "spec", "selector")
	_ = unstructured.SetNestedSlice(obj.Object, []interface{}{
		map[string]interface{}{
			"name":       "grpc",
			"port":       int64(port),
			"targetPort": int64(port),
			"protocol":   "TCP",
		},
	}, "spec", "ports")

	return obj
}
