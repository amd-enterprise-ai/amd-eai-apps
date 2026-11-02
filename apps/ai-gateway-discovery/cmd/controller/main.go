// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Command controller runs the ai-gateway-discovery reconciler only. The ext_authz data path lives in
// the separate authz binary (cmd/authz) so a reconciler concern can never take down the fail-closed
// authenticator; see the authz command and helm chart for the topology.
package main

import (
	"fmt"
	"os"

	"github.com/silogen/ai-gateway-discovery/internal/config"
	"github.com/silogen/ai-gateway-discovery/internal/controller"
	"github.com/silogen/ai-gateway-discovery/internal/managerutil"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"
)

var scheme = runtime.NewScheme()

func init() {
	// Only standard Kubernetes types are needed; InferenceService and Envoy AI
	// Gateway resources are accessed entirely via unstructured.Unstructured.
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
}

func main() {
	logger := zap.New(zap.UseDevMode(false))
	ctrl.SetLogger(logger)

	cfg, err := config.Load()
	if err != nil {
		logger.Error(err, "failed to load config")
		os.Exit(1)
	}

	// Leader election so only one replica reconciles (server-side apply is idempotent, but a single
	// writer avoids duplicate work and status-write churn). ReleaseOnCancel hands the lease back on
	// graceful shutdown so a new leader takes over promptly. The scoped cache keeps the reconciler's
	// Secret watch from caching every Secret in the cluster (see managerutil.ScopedCacheOptions).
	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme:                        scheme,
		LeaderElection:                true,
		LeaderElectionID:              "ai-gateway-discovery.eai.amd.com",
		LeaderElectionReleaseOnCancel: true,
		HealthProbeBindAddress:        fmt.Sprintf(":%d", cfg.HealthPort),
		Metrics: metricsserver.Options{
			BindAddress: "0",
		},
		Cache: managerutil.ScopedCacheOptions(),
	})
	if err != nil {
		logger.Error(err, "failed to create manager")
		os.Exit(1)
	}

	if err := (&controller.InferenceServiceReconciler{
		Client: mgr.GetClient(),
		Config: cfg,
		Log:    logger.WithName("InferenceServiceReconciler"),
	}).SetupWithManager(mgr); err != nil {
		logger.Error(err, "failed to setup InferenceServiceReconciler")
		os.Exit(1)
	}

	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		logger.Error(err, "failed to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		logger.Error(err, "failed to set up ready check")
		os.Exit(1)
	}

	logger.Info("starting AiGatewayDiscovery",
		"targetNamespace", cfg.TargetNamespace,
		"managedLabel", cfg.ManagedLabelName+"="+cfg.ManagedLabelValue,
	)

	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		logger.Error(err, "manager exited with error")
		os.Exit(1)
	}
}
