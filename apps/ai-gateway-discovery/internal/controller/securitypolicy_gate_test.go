// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package controller

import (
	"testing"

	"github.com/silogen/ai-gateway-discovery/internal/config"
)

// TestShouldEnforceAPIKey is the safety property: enforcement is always on, so every model
// with a workload-id is enforced (fleet-wide), unless it carries the opt-out annotation
// "false". A missing workload-id always means no policy.
func TestShouldEnforceAPIKey(t *testing.T) {
	const ann = "aim.eai.amd.com/api-key-auth"
	const wl = "wl-uuid"

	cases := []struct {
		name        string
		annotations map[string]string
		workloadID  string
		want        bool
	}{
		{"no annotation -> enforced fleet-wide", map[string]string{}, wl, true},
		{"nil annotations -> enforced", nil, wl, true},
		{"annotation true -> enforced", map[string]string{ann: "true"}, wl, true},
		{"annotation empty -> enforced", map[string]string{ann: ""}, wl, true},
		{"opt-out false -> excluded", map[string]string{ann: "false"}, wl, false},
		{"no workload id -> skipped", map[string]string{ann: "true"}, "", false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cfg := &config.ControllerConfig{APIKeyAuthAnnotation: ann}
			if got := shouldEnforceAPIKey(cfg, tc.annotations, tc.workloadID); got != tc.want {
				t.Errorf("shouldEnforceAPIKey = %v, want %v", got, tc.want)
			}
		})
	}
}
