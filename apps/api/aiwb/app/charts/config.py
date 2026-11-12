# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Configuration for Helm charts."""

import os

# ============================================================================
# Charts Configuration
# ============================================================================
FINETUNING_CHART_NAME = os.getenv("FINETUNING_CHART_NAME", "llm-finetune-silogen-engine")
VSCODE_CHART_NAME = os.getenv("VSCODE_CHART_NAME", "dev-workspace-vscode")
JUPYTERLAB_CHART_NAME = os.getenv("JUPYTERLAB_CHART_NAME", "dev-workspace-jupyterlab")
COMFYUI_CHART_NAME = os.getenv("COMFYUI_CHART_NAME", "dev-text2image-comfyui")
MLFLOW_CHART_NAME = os.getenv("MLFLOW_CHART_NAME", "dev-tracking-mlflow")
