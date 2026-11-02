// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package nodes

import (
	"testing"

	agent "github.com/silogen/agent/internal/common"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func TestParseGPUVRAM(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected int64
	}{
		{
			name:     "empty string",
			input:    "",
			expected: 0,
		},
		{
			name:     "plain number",
			input:    "16777216",
			expected: 16777216,
		},
		{
			name:     "binary Ki",
			input:    "16Ki",
			expected: 16 * 1024,
		},
		{
			name:     "binary Mi",
			input:    "512Mi",
			expected: 512 * 1024 * 1024,
		},
		{
			name:     "binary Gi",
			input:    "16Gi",
			expected: 16 * 1024 * 1024 * 1024,
		},
		{
			name:     "binary Ti",
			input:    "1Ti",
			expected: 1024 * 1024 * 1024 * 1024,
		},
		{
			name:     "AMD style K (binary semantics)",
			input:    "16K",
			expected: 16 * 1024,
		},
		{
			name:     "AMD style M (binary semantics)",
			input:    "512M",
			expected: 512 * 1024 * 1024,
		},
		{
			name:     "AMD style G (binary semantics)",
			input:    "16G",
			expected: 16 * 1024 * 1024 * 1024,
		},
		{
			name:     "AMD style T (binary semantics)",
			input:    "1T",
			expected: 1024 * 1024 * 1024 * 1024,
		},
		{
			name:     "float with G suffix",
			input:    "16.5G",
			expected: int64(16.5 * 1024 * 1024 * 1024),
		},
		{
			name:     "invalid format",
			input:    "invalid",
			expected: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := parseGPUVRAM(tt.input)
			if result != tt.expected {
				t.Errorf("parseGPUVRAM(%q) = %d, want %d", tt.input, result, tt.expected)
			}
		})
	}
}

func TestGetNodeStatus(t *testing.T) {
	tests := []struct {
		name            string
		node            *corev1.Node
		expectedStatus  string
		expectedIsReady bool
	}{
		{
			name: "ready node",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Conditions: []corev1.NodeCondition{
						{
							Type:   corev1.NodeReady,
							Status: corev1.ConditionTrue,
						},
					},
				},
			},
			expectedStatus:  "Ready",
			expectedIsReady: true,
		},
		{
			name: "not ready node",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Conditions: []corev1.NodeCondition{
						{
							Type:   corev1.NodeReady,
							Status: corev1.ConditionFalse,
						},
					},
				},
			},
			expectedStatus:  "NotReady",
			expectedIsReady: false,
		},
		{
			name: "ready but unschedulable node",
			node: &corev1.Node{
				Spec: corev1.NodeSpec{
					Unschedulable: true,
				},
				Status: corev1.NodeStatus{
					Conditions: []corev1.NodeCondition{
						{
							Type:   corev1.NodeReady,
							Status: corev1.ConditionTrue,
						},
					},
				},
			},
			expectedStatus:  "Ready, SchedulingDisabled",
			expectedIsReady: false,
		},
		{
			name: "node with disk pressure",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Conditions: []corev1.NodeCondition{
						{
							Type:   corev1.NodeReady,
							Status: corev1.ConditionTrue,
						},
						{
							Type:   corev1.NodeDiskPressure,
							Status: corev1.ConditionTrue,
						},
					},
				},
			},
			expectedStatus:  "Ready, DiskPressure",
			expectedIsReady: true,
		},
		{
			name: "node with memory pressure",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Conditions: []corev1.NodeCondition{
						{
							Type:   corev1.NodeReady,
							Status: corev1.ConditionTrue,
						},
						{
							Type:   corev1.NodeMemoryPressure,
							Status: corev1.ConditionTrue,
						},
					},
				},
			},
			expectedStatus:  "Ready, MemoryPressure",
			expectedIsReady: true,
		},
		{
			name: "node with no conditions",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Conditions: []corev1.NodeCondition{},
				},
			},
			expectedStatus:  "Unknown",
			expectedIsReady: false,
		},
		{
			name:            "node with nil conditions",
			node:            &corev1.Node{},
			expectedStatus:  "Unknown",
			expectedIsReady: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			status, isReady := getNodeStatus(tt.node)
			if status != tt.expectedStatus {
				t.Errorf("getNodeStatus() status = %q, want %q", status, tt.expectedStatus)
			}
			if isReady != tt.expectedIsReady {
				t.Errorf("getNodeStatus() isReady = %v, want %v", isReady, tt.expectedIsReady)
			}
		})
	}
}

func TestGetGPUInfo(t *testing.T) {
	tests := []struct {
		name     string
		node     *corev1.Node
		expected *GPUInformation
	}{
		{
			name: "node with no GPU",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{},
				},
			},
			expected: nil,
		},
		{
			name: "node with GPU zero count",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						GPUCapacityKey: resource.MustParse("0"),
					},
				},
			},
			expected: nil,
		},
		{
			name: "node with GPU and full labels",
			node: &corev1.Node{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						GPUDeviceIDLabel:    "0x740f",
						GPUProductNameLabel: "AMD_Instinct_MI250X",
						GPUVRAMLabel:        "64G",
					},
				},
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						GPUCapacityKey: resource.MustParse("8"),
					},
				},
			},
			expected: &GPUInformation{
				Count:              8,
				GPUType:            "0x740f",
				Vendor:             agent.GPUVendorAMD,
				VRAMBytesPerDevice: 64 * 1024 * 1024 * 1024,
				ProductName:        "AMD Instinct MI250X",
			},
		},
		{
			name: "node with GPU and beta labels",
			node: &corev1.Node{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						GPUDeviceIDLabelBeta:    "0x740f",
						GPUProductNameLabelBeta: "AMD_Instinct_MI300X",
						GPUVRAMLabelBeta:        "192Gi",
					},
				},
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						GPUCapacityKey: resource.MustParse("8"),
					},
				},
			},
			expected: &GPUInformation{
				Count:              8,
				GPUType:            "0x740f",
				Vendor:             agent.GPUVendorAMD,
				VRAMBytesPerDevice: 192 * 1024 * 1024 * 1024,
				ProductName:        "AMD Instinct MI300X",
			},
		},
		{
			name: "node with GPU but no labels",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						GPUCapacityKey: resource.MustParse("4"),
					},
				},
			},
			expected: &GPUInformation{
				Count:              4,
				GPUType:            "Unknown",
				Vendor:             agent.GPUVendorAMD,
				VRAMBytesPerDevice: 0,
				ProductName:        "Unknown",
			},
		},
		{
			name: "NVIDIA node with GFD labels",
			node: &corev1.Node{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						NVIDIAGPUProductLabel: "NVIDIA-RTX-6000-Ada-Generation",
						NVIDIAGPUMemoryLabel:  "49140",
						NVIDIAGPUFamilyLabel:  "ada-lovelace",
					},
				},
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						NVIDIAGPUCapacityKey: resource.MustParse("4"),
					},
				},
			},
			expected: &GPUInformation{
				Count:              4,
				GPUType:            "ada-lovelace",
				Vendor:             agent.GPUVendorNVIDIA,
				VRAMBytesPerDevice: 49140 * 1024 * 1024,
				ProductName:        "NVIDIA RTX 6000 Ada Generation",
			},
		},
		{
			name: "NVIDIA node without GFD labels",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						NVIDIAGPUCapacityKey: resource.MustParse("2"),
					},
				},
			},
			expected: &GPUInformation{
				Count:              2,
				GPUType:            "Unknown",
				Vendor:             agent.GPUVendorNVIDIA,
				VRAMBytesPerDevice: 0,
				ProductName:        "Unknown",
			},
		},
		{
			name: "NVIDIA node with invalid memory label",
			node: &corev1.Node{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						NVIDIAGPUMemoryLabel: "not-a-number",
					},
				},
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						NVIDIAGPUCapacityKey: resource.MustParse("1"),
					},
				},
			},
			expected: &GPUInformation{
				Count:              1,
				GPUType:            "Unknown",
				Vendor:             agent.GPUVendorNVIDIA,
				VRAMBytesPerDevice: 0,
				ProductName:        "Unknown",
			},
		},
		{
			name: "NVIDIA node with zero GPUs",
			node: &corev1.Node{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						NVIDIAGPUProductLabel: "NVIDIA-RTX-6000-Ada-Generation",
					},
				},
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						NVIDIAGPUCapacityKey: resource.MustParse("0"),
					},
				},
			},
			expected: nil,
		},
		{
			name: "GFD labels without device plugin capacity",
			node: &corev1.Node{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						NVIDIAGPUProductLabel: "NVIDIA-RTX-6000-Ada-Generation",
						NVIDIAGPUMemoryLabel:  "49140",
					},
				},
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{},
				},
			},
			expected: nil,
		},
		{
			name: "AMD capacity takes precedence over NVIDIA",
			node: &corev1.Node{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						GPUProductNameLabel: "AMD_Instinct_MI300X",
					},
				},
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						GPUCapacityKey:       resource.MustParse("8"),
						NVIDIAGPUCapacityKey: resource.MustParse("4"),
					},
				},
			},
			expected: &GPUInformation{
				Count:              8,
				GPUType:            "Unknown",
				Vendor:             agent.GPUVendorAMD,
				VRAMBytesPerDevice: 0,
				ProductName:        "AMD Instinct MI300X",
			},
		},
		{
			name: "zero AMD capacity falls back to NVIDIA",
			node: &corev1.Node{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						NVIDIAGPUProductLabel: "NVIDIA-RTX-6000-Ada-Generation",
						NVIDIAGPUMemoryLabel:  "49140",
						NVIDIAGPUFamilyLabel:  "ada-lovelace",
					},
				},
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						GPUCapacityKey:       resource.MustParse("0"),
						NVIDIAGPUCapacityKey: resource.MustParse("4"),
					},
				},
			},
			expected: &GPUInformation{
				Count:              4,
				GPUType:            "ada-lovelace",
				Vendor:             agent.GPUVendorNVIDIA,
				VRAMBytesPerDevice: 49140 * 1024 * 1024,
				ProductName:        "NVIDIA RTX 6000 Ada Generation",
			},
		},
		{
			name: "zero AMD capacity and no NVIDIA capacity reports no GPU",
			node: &corev1.Node{
				Status: corev1.NodeStatus{
					Capacity: corev1.ResourceList{
						GPUCapacityKey: resource.MustParse("0"),
					},
				},
			},
			expected: nil,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := getGPUInfo(tt.node)
			if tt.expected == nil {
				if result != nil {
					t.Errorf("getGPUInfo() = %+v, want nil", result)
				}
				return
			}
			if result == nil {
				t.Errorf("getGPUInfo() = nil, want %+v", tt.expected)
				return
			}
			if result.Count != tt.expected.Count {
				t.Errorf("getGPUInfo().Count = %d, want %d", result.Count, tt.expected.Count)
			}
			if result.GPUType != tt.expected.GPUType {
				t.Errorf("getGPUInfo().GPUType = %q, want %q", result.GPUType, tt.expected.GPUType)
			}
			if result.Vendor != tt.expected.Vendor {
				t.Errorf("getGPUInfo().Vendor = %q, want %q", result.Vendor, tt.expected.Vendor)
			}
			if result.VRAMBytesPerDevice != tt.expected.VRAMBytesPerDevice {
				t.Errorf("getGPUInfo().VRAMBytesPerDevice = %d, want %d", result.VRAMBytesPerDevice, tt.expected.VRAMBytesPerDevice)
			}
			if result.ProductName != tt.expected.ProductName {
				t.Errorf("getGPUInfo().ProductName = %q, want %q", result.ProductName, tt.expected.ProductName)
			}
		})
	}
}

func TestMapNodeToClusterNode(t *testing.T) {
	node := &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{
			Name: "test-node-1",
			Labels: map[string]string{
				GPUDeviceIDLabel:    "0x740f",
				GPUProductNameLabel: "AMD_Instinct_MI250X",
				GPUVRAMLabel:        "64G",
			},
		},
		Spec: corev1.NodeSpec{
			Unschedulable: false,
		},
		Status: corev1.NodeStatus{
			Allocatable: corev1.ResourceList{
				corev1.ResourceCPU:              resource.MustParse("96"),
				corev1.ResourceMemory:           resource.MustParse("512Gi"),
				corev1.ResourceEphemeralStorage: resource.MustParse("1Ti"),
				GPUCapacityKey:                  resource.MustParse("8"),
			},
			Capacity: corev1.ResourceList{
				GPUCapacityKey: resource.MustParse("8"),
			},
			Conditions: []corev1.NodeCondition{
				{
					Type:   corev1.NodeReady,
					Status: corev1.ConditionTrue,
				},
			},
		},
	}

	result := mapNodeToClusterNode(node)

	if result.Name != "test-node-1" {
		t.Errorf("Name = %q, want %q", result.Name, "test-node-1")
	}

	if result.CPUMilliCores != 96000 {
		t.Errorf("CPUMilliCores = %d, want %d", result.CPUMilliCores, 96000)
	}

	expectedMemory := int64(512 * 1024 * 1024 * 1024)
	if result.MemoryBytes != expectedMemory {
		t.Errorf("MemoryBytes = %d, want %d", result.MemoryBytes, expectedMemory)
	}

	expectedStorage := int64(1024 * 1024 * 1024 * 1024)
	if result.EphemeralStorageBytes != expectedStorage {
		t.Errorf("EphemeralStorageBytes = %d, want %d", result.EphemeralStorageBytes, expectedStorage)
	}

	if result.Status != "Ready" {
		t.Errorf("Status = %q, want %q", result.Status, "Ready")
	}

	if !result.IsReady {
		t.Errorf("IsReady = %v, want %v", result.IsReady, true)
	}

	if result.GPUInformation == nil {
		t.Fatal("GPUInformation is nil, expected non-nil")
	}
	if result.GPUInformation.Count != 8 {
		t.Errorf("GPUInformation.Count = %d, want %d", result.GPUInformation.Count, 8)
	}
	if result.GPUInformation.GPUType != "0x740f" {
		t.Errorf("GPUInformation.GPUType = %q, want %q", result.GPUInformation.GPUType, "0x740f")
	}
	expectedVRAM := int64(64 * 1024 * 1024 * 1024)
	if result.GPUInformation.VRAMBytesPerDevice != expectedVRAM {
		t.Errorf("GPUInformation.VRAMBytesPerDevice = %d, want %d", result.GPUInformation.VRAMBytesPerDevice, expectedVRAM)
	}
}

func TestMapNodeToClusterNodeWithoutGPU(t *testing.T) {
	node := &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{
			Name: "cpu-node-1",
		},
		Status: corev1.NodeStatus{
			Allocatable: corev1.ResourceList{
				corev1.ResourceCPU:              resource.MustParse("32"),
				corev1.ResourceMemory:           resource.MustParse("128Gi"),
				corev1.ResourceEphemeralStorage: resource.MustParse("500Gi"),
			},
			Conditions: []corev1.NodeCondition{
				{
					Type:   corev1.NodeReady,
					Status: corev1.ConditionTrue,
				},
			},
		},
	}

	result := mapNodeToClusterNode(node)

	if result.GPUInformation != nil {
		t.Errorf("GPUInformation = %+v, want nil", result.GPUInformation)
	}

	if result.Name != "cpu-node-1" {
		t.Errorf("Name = %q, want %q", result.Name, "cpu-node-1")
	}
	if result.CPUMilliCores != 32000 {
		t.Errorf("CPUMilliCores = %d, want %d", result.CPUMilliCores, 32000)
	}
}
