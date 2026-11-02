// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package namespaces

import (
	"context"
	"strconv"
	"strings"
	"time"

	agent "github.com/silogen/agent/internal/common"
	"github.com/silogen/agent/internal/messaging"
	corev1 "k8s.io/api/core/v1"
	rbacv1 "k8s.io/api/rbac/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
)

type namespaceStatusEvent struct {
	NamespaceName string
	ProjectID     string
	Status        NamespaceStatus
	GpuPreemption *GpuPreemptionStatus
}

func extractProjectIDFromNamespace(ns *corev1.Namespace) string {
	if ns == nil || ns.Labels == nil {
		return ""
	}
	return ns.Labels[agent.ProjectIDLabel]
}

// mapK8sPhaseToNamespaceStatus maps Kubernetes namespace phase to NamespaceStatus.
func mapK8sPhaseToNamespaceStatus(phase string) NamespaceStatus {
	if phase == "" {
		return NamespaceStatusFailed
	}

	switch phase {
	case "Active":
		return NamespaceStatusActive
	case "Terminating":
		return NamespaceStatusTerminating
	case "Pending":
		return NamespaceStatusPending
	default:
		return NamespaceStatusFailed
	}
}

// BuildNamespaceManifest creates a Kubernetes namespace manifest with required labels.
func BuildNamespaceManifest(name, projectID string) *corev1.Namespace {
	return &corev1.Namespace{
		ObjectMeta: metav1.ObjectMeta{
			Name: name,
			Labels: map[string]string{
				agent.ProjectIDLabel: projectID,
				KueueManagedLabel:    "true",
			},
		},
	}
}

// GetNamespaceStatusReason returns a human-readable reason for the namespace status.
func GetNamespaceStatusReason(status NamespaceStatus) string {
	switch status {
	case NamespaceStatusDeleted:
		return "Namespace has been deleted"
	case NamespaceStatusActive:
		return "Namespace is active"
	case NamespaceStatusTerminating:
		return "Namespace is terminating"
	case NamespaceStatusPending:
		return "Namespace is pending"
	case NamespaceStatusDeleteFailed:
		return "Namespace deletion failed"
	case NamespaceStatusFailed:
		return "Unknown namespace phase: Unknown"
	default:
		return "Unknown namespace status"
	}
}

// HandleDeletion publishes a terminating status and removes the namespace finalizer.
//
// The caller must check that the object is being deleted before calling this function.
// If publishing fails, it returns the publish error and leaves the finalizer in place so the controller will retry.
func HandleDeletion(
	ctx context.Context,
	c client.Client,
	publisher messaging.MessagePublisher,
	obj client.Object,
) error {
	if !controllerutil.ContainsFinalizer(obj, namespaceFinalizer) {
		return nil
	}

	projectID := ""
	if labels := obj.GetLabels(); labels != nil {
		projectID = labels[agent.ProjectIDLabel]
	}

	event := namespaceStatusEvent{
		NamespaceName: obj.GetName(),
		ProjectID:     projectID,
		Status:        NamespaceStatusTerminating,
	}
	if err := publishNamespaceStatus(ctx, publisher, event); err != nil {
		return err
	}

	return agent.RemoveFinalizer(ctx, c, obj, namespaceFinalizer)
}

func gpuPreemptionStatusFromNamespace(ctx context.Context, ns *corev1.Namespace) *GpuPreemptionStatus {
	log := ctrl.LoggerFrom(ctx)
	s := &GpuPreemptionStatus{}
	if ns == nil || ns.Annotations == nil {
		return s
	}
	ann := ns.Annotations
	if v, ok := ann[KaiwoGpuPreemptionEnabledKey]; ok {
		if enabled, err := strconv.ParseBool(v); err == nil {
			s.Enabled = enabled
		} else {
			log.Info("ignoring unparseable gpu-preemption.enabled annotation",
				"namespace", ns.Name, "value", v)
		}
	}
	if v, ok := ann[KaiwoGpuPreemptionThresholdKey]; ok {
		if n, err := strconv.Atoi(v); err != nil {
			log.Info("ignoring unparseable gpu-preemption.threshold annotation",
				"namespace", ns.Name, "value", v)
		} else {
			s.Threshold = &n
		}
	}
	if v, ok := ann[KaiwoGpuPreemptionGracePeriodKey]; ok {
		if d, err := time.ParseDuration(v); err != nil {
			log.Info("ignoring unparseable gpu-preemption.grace-period annotation (expected Go duration e.g. 1800s)",
				"namespace", ns.Name, "value", v)
		} else {
			seconds := int(d / time.Second)
			s.GracePeriod = &seconds
		}
	}
	if v, ok := ann[KaiwoGpuPreemptionPolicyKey]; ok {
		var matched *GpuPreemptionPolicy
		for _, candidate := range AllGpuPreemptionPolicies {
			if strings.EqualFold(v, string(candidate)) {
				matched = &candidate
				break
			}
		}
		if matched != nil {
			s.Policy = matched
		} else {
			log.Info("ignoring unrecognized gpu-preemption.policy annotation (must be OnPressure or Always)",
				"namespace", ns.Name, "value", v)
		}
	}
	return s
}

func mergeKaiwoAnnotations(existing, manifestAnnotations map[string]string) map[string]string {
	const kaiwoPrefix = "kaiwo.silogen.ai/"
	out := make(map[string]string)
	for k, v := range existing {
		out[k] = v
	}
	for k, v := range manifestAnnotations {
		if strings.HasPrefix(k, kaiwoPrefix) {
			out[k] = v
		}
	}
	for k := range existing {
		if strings.HasPrefix(k, kaiwoPrefix) {
			if _, ok := manifestAnnotations[k]; !ok {
				delete(out, k)
			}
		}
	}
	return out
}

func publishNamespaceStatus(
	ctx context.Context,
	publisher messaging.MessagePublisher,
	event namespaceStatusEvent,
) error {
	log := ctrl.LoggerFrom(ctx)
	if event.ProjectID == "" {
		msg := &UnmanagedNamespaceMessage{
			MessageType:     messaging.MessageTypeUnmanagedNamespace,
			NamespaceName:   event.NamespaceName,
			NamespaceStatus: event.Status,
		}
		if err := publisher.Publish(ctx, msg); err != nil {
			return err
		}
		log.Info("published unmanaged namespace status",
			"namespace", event.NamespaceName,
			"status", event.Status,
		)
		return nil
	}

	reason := GetNamespaceStatusReason(event.Status)
	msg := &ProjectNamespaceStatusMessage{
		MessageType:   messaging.MessageTypeProjectNamespaceStatus,
		ProjectID:     event.ProjectID,
		Status:        event.Status,
		StatusReason:  &reason,
		GpuPreemption: event.GpuPreemption,
	}
	if err := publisher.Publish(ctx, msg); err != nil {
		return err
	}
	log.Info("published namespace status",
		"namespace", event.NamespaceName,
		"project_id", event.ProjectID,
		"status", event.Status,
	)
	return nil
}

func handleDeleted(ctx context.Context, publisher messaging.MessagePublisher, namespaceName string) (ctrl.Result, error) {
	log := ctrl.LoggerFrom(ctx)

	log.Info("namespace completely deleted from cluster", "namespace", namespaceName)
	if err := publishNamespaceDeletedMessage(ctx, publisher, namespaceName); err != nil {
		log.Error(err, "failed to publish deletion status")
		return ctrl.Result{}, err
	}

	log.Info("namespace deletion status published successfully", "namespace", namespaceName)
	return ctrl.Result{}, nil
}

func publishNamespaceDeletedMessage(ctx context.Context, publisher messaging.MessagePublisher, namespaceName string) error {
	log := ctrl.LoggerFrom(ctx)

	msg := &NamespaceDeletedMessage{
		MessageType:   messaging.MessageTypeNamespaceDeleted,
		NamespaceName: namespaceName,
	}
	if err := publisher.Publish(ctx, msg); err != nil {
		return err
	}
	log.Info("published namespace deletion by name",
		"namespace", namespaceName,
	)
	return nil
}

func ensureRoleBinding(ctx context.Context, c client.Client, ns *corev1.Namespace) (bool, error) {
	rbName := "project-member-role-binding"
	rb := &rbacv1.RoleBinding{}
	err := c.Get(ctx, client.ObjectKey{Namespace: ns.Name, Name: rbName}, rb)

	if err == nil {
		return false, nil
	}

	if !errors.IsNotFound(err) {
		return false, err
	}

	rb = &rbacv1.RoleBinding{
		ObjectMeta: metav1.ObjectMeta{
			Name:      rbName,
			Namespace: ns.Name,
			OwnerReferences: []metav1.OwnerReference{{
				APIVersion: coreV1APIVersion,
				Kind:       "Namespace",
				Name:       ns.Name,
				UID:        ns.UID,
			}},
		},
		RoleRef: rbacv1.RoleRef{
			APIGroup: rbacv1.GroupName,
			Kind:     "ClusterRole",
			Name:     "airm-project-member",
		},
		Subjects: []rbacv1.Subject{
			// Backwards compatibility, since the prefix was previously 'oidc'
			{
				Kind:     rbacv1.GroupKind,
				Name:     "oidc" + ns.Name,
				APIGroup: rbacv1.GroupName,
			},
			// The kubernetes cluster applies an OIDC prefix of 'oidc:', so we adjust the group to expect that
			{
				Kind:     rbacv1.GroupKind,
				Name:     "oidc:" + ns.Name,
				APIGroup: rbacv1.GroupName,
			},
		},
	}

	if err := c.Create(ctx, rb); err != nil {
		if errors.IsAlreadyExists(err) {
			return false, nil
		}
		return false, err
	}
	return true, nil
}
