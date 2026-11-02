# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

AMD_GPU_DEVICE_ID_LABEL = "amd.com/gpu.device-id"
AMD_GPU_DEVICE_ID_LABEL_BETA = "beta.amd.com/gpu.device-id"
AMD_GPU_PRODUCT_NAME_LABEL = "amd.com/gpu.product-name"
AMD_GPU_PRODUCT_NAME_LABEL_BETA = "beta.amd.com/gpu.product-name"
AMD_GPU_RESOURCE = "amd.com/gpu"
NVIDIA_GPU_RESOURCE = "nvidia.com/gpu"
AIM_ACCELERATOR_LABEL_PREFIX = "feature.node.kubernetes.io/aim-accelerator."
AIM_ACCELERATOR_EXCLUDED_SUFFIX_PREFIXES = ("CPU", "GPU", "APU", "EPYC_", "partitioning-scheme.", "vendor.")

KUEUE_API_GROUP = "kueue.x-k8s.io"
KUEUE_API_VERSION = "v1beta1"
KUEUE_CLUSTER_QUEUE_PLURAL = "clusterqueues"
KUEUE_LOCAL_QUEUE_PLURAL = "localqueues"
