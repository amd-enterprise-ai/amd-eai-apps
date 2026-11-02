// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Command authz is the ext_authz data-path binary, split out of the controller so the fail-closed
// authenticator for workloads and header-less inference gets its own availability contract: every
// replica serves (no leader election), the cache is scoped so unrelated Secret volume cannot OOM it,
// and readiness does not go green until it can actually answer. It shares the controller's image and
// internal packages; only the entrypoint differs.
package main

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/silogen/ai-gateway-discovery/internal/authz"
	"github.com/silogen/ai-gateway-discovery/internal/config"
	"github.com/silogen/ai-gateway-discovery/internal/managerutil"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/cache"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	"sigs.k8s.io/controller-runtime/pkg/manager"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"
)

var scheme = runtime.NewScheme()

func init() {
	// Only standard Kubernetes types are needed; InferenceService and Envoy AI
	// Gateway resources are accessed entirely via unstructured.Unstructured.
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
}

// errNotReady is returned by the readiness check until the listeners are bound and the cache has
// synced. Because every calling SecurityPolicy is failOpen:false, a pod that answered before its
// cache synced would deny valid keys; keeping it out of the Service Endpoints until then turns a
// cold start into "no traffic routed here yet" instead of "spurious 401s".
var errNotReady = errors.New("authz not ready: listeners bound and cache not yet synced")

func main() {
	logger := zap.New(zap.UseDevMode(false))
	ctrl.SetLogger(logger)

	cfg, err := config.Load()
	if err != nil {
		logger.Error(err, "failed to load config")
		os.Exit(1)
	}

	// No leader election: this binary only serves ext_authz, it reconciles nothing, so every replica
	// must answer. Metrics server off (nothing to export here yet).
	//
	// Client.Cache.Unstructured = true is load-bearing: the handler reads Secrets and
	// InferenceServices as unstructured, and controller-runtime's cache-backed client does a LIVE
	// apiserver lookup for unstructured objects unless this is set. Without it every ext_authz check
	// is a cluster-wide LIST against the apiserver, the scoped cache is inert, and the readiness gate
	// is a no-op. With it (plus the informer prewarm below) the fail-closed data path serves from a
	// local cache and stays up through an apiserver blip instead of denying every request.
	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme:                 scheme,
		LeaderElection:         false,
		HealthProbeBindAddress: fmt.Sprintf(":%d", cfg.HealthPort),
		Metrics:                metricsserver.Options{BindAddress: "0"},
		Cache:                  managerutil.ScopedCacheOptions(),
		Client:                 client.Options{Cache: &client.CacheOptions{Unstructured: true}},
	})
	if err != nil {
		logger.Error(err, "failed to create manager")
		os.Exit(1)
	}

	handler := &authz.Handler{Client: mgr.GetClient(), Config: cfg, Log: logger.WithName("authz")}

	// Bind the listeners now so a port clash fails the process immediately (before readiness can ever
	// go green) rather than surfacing as silent unreadiness later. See internal/authz for why the two
	// families are separated by port: AuthzPort → ServeHTTP (ai-gateway body/models), WorkloadsAuthzPort
	// → ServeWorkloads (workloads route).
	aiGatewayLn, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.AuthzPort))
	if err != nil {
		logger.Error(err, "failed to bind ai-gateway authz listener", "port", cfg.AuthzPort)
		os.Exit(1)
	}
	workloadsLn, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.WorkloadsAuthzPort))
	if err != nil {
		logger.Error(err, "failed to bind workloads authz listener", "port", cfg.WorkloadsAuthzPort)
		os.Exit(1)
	}

	newAuthzServer := func(h http.Handler) *http.Server {
		return &http.Server{
			Handler:           h,
			ReadHeaderTimeout: 10 * time.Second,
			ReadTimeout:       15 * time.Second,
			WriteTimeout:      15 * time.Second,
			IdleTimeout:       60 * time.Second,
			MaxHeaderBytes:    1 << 20, // 1 MiB, bound header size on this listener
		}
	}
	aiGatewaySrv := newAuthzServer(handler)
	workloadsSrv := newAuthzServer(http.HandlerFunc(handler.ServeWorkloads))

	// ready gates the readiness probe. It flips true only after the cache has synced, so this pod
	// joins the Service Endpoints (and starts receiving ext_authz checks) with a warm cache.
	var ready atomic.Bool
	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		logger.Error(err, "failed to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", func(*http.Request) error {
		if ready.Load() {
			return nil
		}
		return errNotReady
	}); err != nil {
		logger.Error(err, "failed to set up ready check")
		os.Exit(1)
	}

	if err := mgr.Add(manager.RunnableFunc(func(ctx context.Context) error {
		// Prewarm the informers the handler reads from. This binary registers no controller, so
		// nothing else creates these informers; without this the cache holds zero informers,
		// WaitForCacheSync returns immediately, and the readiness gate below is a no-op (and the
		// first real request pays the cold sync). BlockUntilSynced makes each one populate before we
		// go Ready, so the pod only joins the Service Endpoints with a warm cache.
		for _, obj := range managerutil.CachedReadObjects() {
			if _, err := mgr.GetCache().GetInformer(ctx, obj, cache.BlockUntilSynced(true)); err != nil {
				return fmt.Errorf("prewarming informer: %w", err)
			}
		}
		// Serve only once the cache is warm — otherwise the handler would authorize against an empty
		// key/InferenceService cache and deny valid requests.
		if !mgr.GetCache().WaitForCacheSync(ctx) {
			return errors.New("cache failed to sync")
		}
		go func() {
			<-ctx.Done()
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			// Shut both down concurrently so each gets the full timeout window under drain load.
			var wg sync.WaitGroup
			wg.Add(2)
			go func() { defer wg.Done(); _ = aiGatewaySrv.Shutdown(shutdownCtx) }()
			go func() { defer wg.Done(); _ = workloadsSrv.Shutdown(shutdownCtx) }()
			wg.Wait()
		}()

		errs := make(chan error, 2)
		go func() {
			logger.Info("starting ext_authz server", "port", cfg.AuthzPort, "family", "ai-gateway")
			errs <- aiGatewaySrv.Serve(aiGatewayLn)
		}()
		go func() {
			logger.Info("starting ext_authz server", "port", cfg.WorkloadsAuthzPort, "family", "workloads")
			errs <- workloadsSrv.Serve(workloadsLn)
		}()
		ready.Store(true)
		logger.Info("authz ready", "cacheSynced", true)

		if err := <-errs; err != nil && err != http.ErrServerClosed {
			return err
		}
		return nil
	})); err != nil {
		logger.Error(err, "failed to add ext_authz servers")
		os.Exit(1)
	}

	logger.Info("starting AiGatewayAuthz",
		"authzPort", cfg.AuthzPort,
		"workloadsAuthzPort", cfg.WorkloadsAuthzPort,
	)

	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		logger.Error(err, "manager exited with error")
		os.Exit(1)
	}
}
