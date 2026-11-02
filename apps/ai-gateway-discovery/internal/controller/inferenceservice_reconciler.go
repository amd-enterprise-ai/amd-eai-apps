// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package controller

import (
	"context"
	"fmt"

	"github.com/go-logr/logr"
	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"github.com/silogen/ai-gateway-discovery/internal/common"
	"github.com/silogen/ai-gateway-discovery/internal/config"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/builder"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/handler"
)

// InferenceServiceReconciler watches InferenceService objects and manages the
// corresponding InferencePool and AIGatewayRoute per IS.
// It uses a finalizer to ensure cleanup when an InferenceService is deleted.
type InferenceServiceReconciler struct {
	client.Client
	Config *config.ControllerConfig
	Log    logr.Logger
}

func (r *InferenceServiceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := r.Log.WithValues("inferenceservice", req.NamespacedName)

	is := newInferenceService()
	if err := r.Get(ctx, req.NamespacedName, is); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	if !is.GetDeletionTimestamp().IsZero() {
		return r.handleDeletion(ctx, log, is)
	}

	modelName := r.resolveModelName(is)
	if modelName == "" {
		log.Info("skipping: model-name annotation absent", "annotation", r.Config.ModelNameAnnotation)
		return ctrl.Result{}, nil
	}

	if err := r.ensureFinalizer(ctx, is); err != nil {
		return ctrl.Result{}, err
	}

	entry := r.buildEntry(is, modelName)
	eppName := entry.ResourceName
	epp := aigateway.EPPRef{Name: eppName, Port: r.Config.EPPServicePort}

	if err := r.applyObj(ctx, aigateway.BuildInferencePool(entry, epp, r.Config.InferencePoolPort)); err != nil {
		log.Error(err, "failed to apply InferencePool", "name", entry.ResourceName)
		return ctrl.Result{}, err
	}

	if err := r.applyObj(ctx, aigateway.BuildEPPDeployment(entry, eppName, r.Config.EPPImage, r.Config.EPPServicePort)); err != nil {
		log.Error(err, "failed to apply EPP Deployment")
		return ctrl.Result{}, err
	}
	if err := r.applyObj(ctx, aigateway.BuildEPPService(entry, eppName, r.Config.EPPServicePort)); err != nil {
		log.Error(err, "failed to apply EPP Service")
		return ctrl.Result{}, err
	}

	if err := r.applyEPPRBAC(ctx, entry, eppName); err != nil {
		log.Error(err, "failed to apply EPP RBAC")
		return ctrl.Result{}, err
	}

	if err := r.applyObj(ctx, aigateway.BuildAIGatewayRoute(entry, r.Config)); err != nil {
		log.Error(err, "failed to apply AIGatewayRoute", "name", entry.ResourceName)
		return ctrl.Result{}, err
	}

	enforcing, err := r.reconcileSecurityPolicy(ctx, log, is, entry)
	if err != nil {
		log.Error(err, "failed to reconcile SecurityPolicy", "name", entry.ResourceName)
		return ctrl.Result{}, err
	}

	if err := r.reconcileCatchAllExtAuth(ctx, log, entry, enforcing); err != nil {
		log.Error(err, "failed to reconcile catch-all ext_authz SecurityPolicy", "name", entry.ResourceName)
		return ctrl.Result{}, err
	}

	if err := r.reconcileWorkloadsExtAuth(ctx, log, entry.ISNamespace); err != nil {
		log.Error(err, "failed to reconcile workloads ext_authz", "namespace", entry.ISNamespace)
		return ctrl.Result{}, err
	}

	log.Info("reconciled", "pool", entry.ResourceName, "model", entry.ModelName)
	return ctrl.Result{}, nil
}

// shouldEnforceAPIKey decides whether a model gets a native apiKeyAuth SecurityPolicy.
// Enforcement is always on and fleet-wide: every model with a workload-id is enforced.
// A single model can be explicitly excluded — e.g. to unblock it during rollout — by
// setting the opt-out annotation to "false". A missing workload-id means there is no
// aim-keys-<workload-id> Secret to reference, so the model is skipped.
func shouldEnforceAPIKey(cfg *config.ControllerConfig, annotations map[string]string, workloadID string) bool {
	if workloadID == "" {
		return false
	}
	return annotations[cfg.APIKeyAuthAnnotation] != "false"
}

// reconcileSecurityPolicy applies the per-model SecurityPolicy listing every per-key Secret bound
// to the model (authorization = membership), and otherwise ensures any previously-created policy is
// removed. The opt-out annotation, or — critically — a model with no bound key (no key Secret
// carries its bound-<workload-id> label) reverts the model to the gateway backstop
// (default-deny / cluster-auth). Never leave a policy with an empty credentialRefs list.
// The Secret watch re-reconciles the model whenever a key in the namespace is bound or unbound.
func (r *InferenceServiceReconciler) reconcileSecurityPolicy(ctx context.Context, log logr.Logger, is *unstructured.Unstructured, entry aigateway.BackendEntry) (bool, error) {
	enforce := shouldEnforceAPIKey(r.Config, is.GetAnnotations(), entry.WorkloadID)
	var secretNames []string
	if enforce {
		names, err := r.listBoundKeySecrets(ctx, entry.ISNamespace, entry.WorkloadID)
		if err != nil {
			return false, fmt.Errorf("listing key Secrets for %q: %w", entry.ResourceName, err)
		}
		secretNames = names
		if len(secretNames) == 0 {
			log.Info("deferring apiKeyAuth: no key bound to this model", "name", entry.ResourceName)
			enforce = false
		}
	}
	if !enforce {
		if err := r.deleteGVK(ctx, aigateway.SecurityPolicyGVK, entry.ISNamespace, entry.ResourceName); err != nil {
			return false, fmt.Errorf("removing SecurityPolicy: %w", err)
		}
		return false, nil
	}
	log.Info("enforcing apiKeyAuth", "name", entry.ResourceName, "keys", len(secretNames))
	return true, r.applyObj(ctx, aigateway.BuildSecurityPolicy(entry, secretNames))
}

// reconcileCatchAllExtAuth manages the per-model catch-all ext_authz SecurityPolicy that closes the
// header-less/body-only cross-model auth bypass: a request with no routing header falls to the AI
// Gateway's shared catch-all rule and, without this override, is authorized against an arbitrary
// model's apiKeyAuth. The rule-scoped ext_authz SecurityPolicy re-authorizes it against the model in
// the body instead. It is stamped for every model actively enforcing apiKeyAuth (enforcing) — so
// opted-out or key-less models keep their gateway-backstop behavior on every path and get no extra
// authz. When the model stops enforcing, any prior catch-all policy is removed. The cross-namespace
// ReferenceGrant is created (never deleted here) because it is shared by every enforcing model in the
// namespace; an unused grant is inert.
func (r *InferenceServiceReconciler) reconcileCatchAllExtAuth(ctx context.Context, log logr.Logger, entry aigateway.BackendEntry, enforcing bool) error {
	if !enforcing {
		if err := r.deleteGVK(ctx, aigateway.SecurityPolicyGVK, entry.ISNamespace, entry.ResourceName+aigateway.CatchAllPolicySuffix); err != nil {
			return fmt.Errorf("removing catch-all SecurityPolicy: %w", err)
		}
		return nil
	}
	if err := r.applyObj(ctx, aigateway.BuildExtAuthReferenceGrant(entry.ISNamespace, r.Config.AuthzServiceName, r.Config.AuthzServiceNamespace)); err != nil {
		return fmt.Errorf("applying ext_authz ReferenceGrant: %w", err)
	}
	log.Info("enforcing body-only ext_authz on catch-all", "name", entry.ResourceName)
	return r.applyObj(ctx, aigateway.BuildCatchAllExtAuthSecurityPolicy(entry, r.Config.AuthzServiceName, r.Config.AuthzServiceNamespace, r.Config.AuthzPort, r.Config.BodyAuthMaxRequestBytes))
}

// reconcileWorkloadsExtAuth ensures the namespace-wide ext_authz SecurityPolicy (+ its
// cross-namespace ReferenceGrant) that guards the aim-engine workloads serving routes. One policy
// selects every workloads HTTPRoute in the namespace by the AIM-service label and routes it to the
// body-aware ext_authz handler, which authorizes on the path (which names the workload) and denies by
// default. Being namespace-wide it covers every workload — including routes this reconcile has not
// individually seen — so it needs no per-IS gating; and being static ext_authz (not credential-baked
// apiKeyAuth) a key bind never churns the shared https listener. Stamped idempotently; the shared
// ReferenceGrant is created, never deleted here (inert when unused).
//
// Always-on by design: the workloads route has no gateway backstop, so its guard must not be
// optional. The policy is namespace-named (not IS-owned), so Owns(SecurityPolicy) does not recreate
// it if it is deleted out-of-band; it is re-stamped on the next reconcile of any managed IS in the
// namespace.
func (r *InferenceServiceReconciler) reconcileWorkloadsExtAuth(ctx context.Context, log logr.Logger, namespace string) error {
	if err := r.applyObj(ctx, aigateway.BuildExtAuthReferenceGrant(namespace, r.Config.AuthzServiceName, r.Config.AuthzServiceNamespace)); err != nil {
		return fmt.Errorf("applying ext_authz ReferenceGrant: %w", err)
	}
	log.Info("enforcing workloads ext_authz", "namespace", namespace)
	// Target the dedicated workloads ext_authz port, not AuthzPort: the port is what tells the handler
	// this is a workloads request (authorize on the path's workload-id) vs an ai-gateway body request.
	return r.applyObj(ctx, aigateway.BuildWorkloadsExtAuthSecurityPolicy(namespace, r.Config.AuthzServiceName, r.Config.AuthzServiceNamespace, r.Config.WorkloadsAuthzPort))
}

// listBoundKeySecrets returns the names of the per-key Secrets bound to a model — those carrying
// its bound-<workload-id> label. An empty result is the normal "no key bound yet" state.
func (r *InferenceServiceReconciler) listBoundKeySecrets(ctx context.Context, namespace, workloadID string) ([]string, error) {
	list := &unstructured.UnstructuredList{}
	list.SetGroupVersionKind(secretListGVK)
	if err := r.List(ctx, list,
		client.InNamespace(namespace),
		client.MatchingLabels{aigateway.BoundLabel(workloadID): "true"},
	); err != nil {
		return nil, err
	}
	names := make([]string, 0, len(list.Items))
	for i := range list.Items {
		names = append(names, list.Items[i].GetName())
	}
	return names, nil
}

func (r *InferenceServiceReconciler) handleDeletion(ctx context.Context, log logr.Logger, is *unstructured.Unstructured) (ctrl.Result, error) {
	finalizers := is.GetFinalizers()
	if !containsString(finalizers, common.Finalizer) {
		return ctrl.Result{}, nil
	}

	name := resourceName(is.GetNamespace(), is.GetName())
	if err := r.deleteGVK(ctx, aigateway.InferencePoolGVK, is.GetNamespace(), name); err != nil {
		log.Error(err, "failed to delete InferencePool", "name", name)
		return ctrl.Result{}, err
	}
	r.deleteGVK(ctx, aigateway.EPPDeploymentGVK, is.GetNamespace(), name)                                 //nolint:errcheck
	r.deleteGVK(ctx, aigateway.EPPServiceGVK, is.GetNamespace(), name)                                    //nolint:errcheck
	r.deleteGVK(ctx, aigateway.SecurityPolicyGVK, is.GetNamespace(), name)                                //nolint:errcheck
	r.deleteGVK(ctx, aigateway.SecurityPolicyGVK, is.GetNamespace(), name+aigateway.CatchAllPolicySuffix) //nolint:errcheck
	r.deleteGVK(ctx, roleBindingGVK, is.GetNamespace(), name)                                             //nolint:errcheck
	r.deleteGVK(ctx, roleGVK, is.GetNamespace(), name)                                                    //nolint:errcheck

	if err := r.cleanupWorkloadsExtAuthIfLast(ctx, log, is); err != nil {
		return ctrl.Result{}, err
	}

	is.SetFinalizers(removeString(finalizers, common.Finalizer))
	if err := r.Update(ctx, is); err != nil {
		return ctrl.Result{}, fmt.Errorf("removing finalizer: %w", err)
	}

	log.Info("cleaned up InferencePool and EPP resources", "name", name)
	return ctrl.Result{}, nil
}

// cleanupWorkloadsExtAuthIfLast removes the namespace-wide workloads ext_authz SecurityPolicy once no
// managed InferenceService is left serving in the namespace. The policy is namespace-named (not
// IS-owned), so nothing else garbage-collects it: left behind it guards nothing (there are no serving
// routes) yet still attaches to any labelled route, and — since it is only ever (re-)stamped during a
// managed IS reconcile — a namespace with no IS can never have it corrected or removed by any other
// path. So the last IS to go must take it with it.
//
// "Last" ignores InferenceServices that are themselves being deleted (non-zero deletionTimestamp),
// including this one: if two ISes are deleted concurrently, both see zero live ISes and both delete
// the policy — which is safe because deleteGVK is idempotent (NotFound is ignored).
func (r *InferenceServiceReconciler) cleanupWorkloadsExtAuthIfLast(ctx context.Context, log logr.Logger, is *unstructured.Unstructured) error {
	list := &unstructured.UnstructuredList{}
	listGVK := aigateway.InferenceServiceGVK
	listGVK.Kind += "List"
	list.SetGroupVersionKind(listGVK)
	if err := r.List(ctx, list,
		client.InNamespace(is.GetNamespace()),
		client.MatchingLabels{r.Config.ManagedLabelName: r.Config.ManagedLabelValue},
	); err != nil {
		return fmt.Errorf("listing InferenceServices to check for last-in-namespace: %w", err)
	}
	for i := range list.Items {
		if list.Items[i].GetDeletionTimestamp().IsZero() {
			return nil // another managed IS is still serving — keep the workloads guard
		}
	}
	log.Info("removing workloads ext_authz: no managed InferenceService left in namespace", "namespace", is.GetNamespace())
	return r.deleteGVK(ctx, aigateway.SecurityPolicyGVK, is.GetNamespace(), aigateway.WorkloadsExtAuthPolicyName)
}

func (r *InferenceServiceReconciler) ensureFinalizer(ctx context.Context, is *unstructured.Unstructured) error {
	finalizers := is.GetFinalizers()
	if containsString(finalizers, common.Finalizer) {
		return nil
	}
	is.SetFinalizers(append(finalizers, common.Finalizer))
	if err := r.Update(ctx, is); err != nil {
		return fmt.Errorf("adding finalizer: %w", err)
	}
	return nil
}

func (r *InferenceServiceReconciler) resolveModelName(is *unstructured.Unstructured) string {
	return is.GetAnnotations()[r.Config.ModelNameAnnotation]
}

func (r *InferenceServiceReconciler) buildEntry(is *unstructured.Unstructured, modelName string) aigateway.BackendEntry {
	return aigateway.BackendEntry{
		ResourceName: resourceName(is.GetNamespace(), is.GetName()),
		ISName:       is.GetName(),
		ISNamespace:  is.GetNamespace(),
		ISUID:        is.GetUID(),
		ModelName:    modelName,
		WorkloadID:   is.GetLabels()[r.Config.WorkloadIDLabel],
	}
}

var (
	roleGVK        = schema.GroupVersionKind{Group: "rbac.authorization.k8s.io", Version: "v1", Kind: "Role"}
	roleBindingGVK = schema.GroupVersionKind{Group: "rbac.authorization.k8s.io", Version: "v1", Kind: "RoleBinding"}
	secretGVK      = schema.GroupVersionKind{Version: "v1", Kind: "Secret"}
	secretListGVK  = schema.GroupVersionKind{Version: "v1", Kind: "SecretList"}
)

// applyEPPRBAC creates a Role and RoleBinding in the IS namespace granting the
// default ServiceAccount (used by inference-epp) the permissions it needs to
// watch InferencePools, Pods, and InferenceModelRewrites.
func (r *InferenceServiceReconciler) applyEPPRBAC(ctx context.Context, entry aigateway.BackendEntry, eppName string) error {
	role := &unstructured.Unstructured{}
	role.SetGroupVersionKind(roleGVK)
	role.SetName(eppName)
	role.SetNamespace(entry.ISNamespace)
	_ = unstructured.SetNestedSlice(role.Object, []interface{}{
		map[string]interface{}{
			"apiGroups": []interface{}{""},
			"resources": []interface{}{"pods"},
			"verbs":     []interface{}{"get", "list", "watch"},
		},
		map[string]interface{}{
			"apiGroups": []interface{}{"inference.networking.k8s.io"},
			"resources": []interface{}{"inferencepools"},
			"verbs":     []interface{}{"get", "list", "watch"},
		},
		map[string]interface{}{
			"apiGroups": []interface{}{"inference.networking.x-k8s.io"},
			"resources": []interface{}{"inferencemodelrewrites", "inferenceobjectives"},
			"verbs":     []interface{}{"get", "list", "watch"},
		},
	}, "rules")
	if err := r.applyObj(ctx, role); err != nil {
		return fmt.Errorf("applying EPP Role: %w", err)
	}

	rb := &unstructured.Unstructured{}
	rb.SetGroupVersionKind(roleBindingGVK)
	rb.SetName(eppName)
	rb.SetNamespace(entry.ISNamespace)
	_ = unstructured.SetNestedSlice(rb.Object, []interface{}{
		map[string]interface{}{
			"kind":      "ServiceAccount",
			"name":      "default",
			"namespace": entry.ISNamespace,
		},
	}, "subjects")
	_ = unstructured.SetNestedMap(rb.Object, map[string]interface{}{
		"apiGroup": "rbac.authorization.k8s.io",
		"kind":     "Role",
		"name":     eppName,
	}, "roleRef")
	return r.applyObj(ctx, rb)
}

func (r *InferenceServiceReconciler) applyObj(ctx context.Context, obj *unstructured.Unstructured) error {
	return r.Patch(ctx, obj, client.Apply, client.FieldOwner(common.FieldManager), client.ForceOwnership)
}

func (r *InferenceServiceReconciler) deleteGVK(ctx context.Context, gvk schema.GroupVersionKind, namespace, name string) error {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(gvk)
	obj.SetNamespace(namespace)
	obj.SetName(name)
	err := r.Delete(ctx, obj)
	if errors.IsNotFound(err) {
		return nil
	}
	return err
}

func (r *InferenceServiceReconciler) SetupWithManager(mgr ctrl.Manager) error {
	is := newInferenceService()
	secret := &unstructured.Unstructured{}
	secret.SetGroupVersionKind(secretGVK)
	securityPolicy := &unstructured.Unstructured{}
	securityPolicy.SetGroupVersionKind(aigateway.SecurityPolicyGVK)
	return ctrl.NewControllerManagedBy(mgr).
		For(is, builder.WithPredicates(hasManagedLabel(r.Config.ManagedLabelName, r.Config.ManagedLabelValue))).
		// Own the generated apiKeyAuth SecurityPolicy so it self-heals: if it is deleted or
		// drifts out-of-band, the owning InferenceService is re-reconciled and the policy is
		// recreated. Without this the route silently reverts to the gateway default-deny (a
		// keyed model would then 403 even valid keys until the next InferenceService event).
		// The SecurityPolicy carries a controller owner-ref to the InferenceService.
		Owns(securityPolicy).
		// Watch the per-key API-key Secrets so models are re-reconciled when a key is bound or
		// unbound (its bound-<workload-id> labels change) or the key is created/deleted. Filtered
		// to Secrets carrying the api-key contract label so unrelated Secrets are ignored.
		Watches(secret, handler.EnqueueRequestsFromMapFunc(r.mapSecretToInferenceServices), builder.WithPredicates(isApiKeySecret())).
		// Self-heal the namespace-wide workloads ext_authz SecurityPolicy. It is namespace-named,
		// not IS-owned, so Owns() above does not cover it: if it is deleted out-of-band the workloads
		// route would be left unguarded (the shared https gateway has no default-deny backstop) until
		// some other IS event in the namespace happened to re-stamp it. This watch re-stamps it
		// promptly. Scoped to Delete of that one policy so it never fires on the controller's own SSA
		// writes (which are Updates) — no self-triggered reconcile storm. (Drift short of deletion is
		// covered by ForceOwnership on the next reconcile and the manager's periodic resync.)
		Watches(securityPolicy, handler.EnqueueRequestsFromMapFunc(r.mapWorkloadsPolicyToInferenceServices), builder.WithPredicates(isWorkloadsExtAuthPolicyDelete())).
		Complete(r)
}

// mapSecretToInferenceServices maps an api-key Secret event to reconcile requests for every managed
// InferenceService in the Secret's namespace. A binding change (a bound-<workload-id> label added
// or removed on a key Secret) can affect any model, and each reconcile recomputes its
// credentialRefs from the current label state, so a namespace-wide sweep is both correct and
// simplest — the alternative (diffing old/new labels) is only an optimization, bounded here by the
// number of models per namespace.
func (r *InferenceServiceReconciler) mapSecretToInferenceServices(ctx context.Context, obj client.Object) []ctrl.Request {
	return r.enqueueManagedInferenceServices(ctx, obj.GetNamespace(), "secret", obj.GetName())
}

// mapWorkloadsPolicyToInferenceServices re-stamps the deleted namespace-wide workloads ext_authz
// policy: it enqueues the managed InferenceServices in the policy's namespace, and
// reconcileWorkloadsExtAuth recreates the policy (+ shared ReferenceGrant) on the next reconcile.
func (r *InferenceServiceReconciler) mapWorkloadsPolicyToInferenceServices(ctx context.Context, obj client.Object) []ctrl.Request {
	return r.enqueueManagedInferenceServices(ctx, obj.GetNamespace(), "workloads-extauth", obj.GetName())
}

// enqueueManagedInferenceServices returns reconcile requests for every managed InferenceService in
// the namespace — a namespace-wide sweep so the affected controller state is recomputed from current
// cluster state. Shared by the Secret and workloads-policy watches.
func (r *InferenceServiceReconciler) enqueueManagedInferenceServices(ctx context.Context, namespace, trigger, name string) []ctrl.Request {
	list := &unstructured.UnstructuredList{}
	listGVK := aigateway.InferenceServiceGVK
	listGVK.Kind += "List"
	list.SetGroupVersionKind(listGVK)
	if err := r.List(ctx, list,
		client.InNamespace(namespace),
		client.MatchingLabels{r.Config.ManagedLabelName: r.Config.ManagedLabelValue},
	); err != nil {
		r.Log.Error(err, "mapping event to InferenceServices", "trigger", trigger, "name", name, "namespace", namespace)
		return nil
	}

	reqs := make([]ctrl.Request, 0, len(list.Items))
	for i := range list.Items {
		reqs = append(reqs, ctrl.Request{NamespacedName: types.NamespacedName{
			Namespace: list.Items[i].GetNamespace(),
			Name:      list.Items[i].GetName(),
		}})
	}
	return reqs
}

// newInferenceService returns an unstructured object set up for KServe InferenceService.
func newInferenceService() *unstructured.Unstructured {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(aigateway.InferenceServiceGVK)
	return obj
}

func containsString(slice []string, s string) bool {
	for _, v := range slice {
		if v == s {
			return true
		}
	}
	return false
}

func removeString(slice []string, s string) []string {
	out := make([]string, 0, len(slice))
	for _, v := range slice {
		if v != s {
			out = append(out, v)
		}
	}
	return out
}
