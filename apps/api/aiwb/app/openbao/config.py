# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Configuration for the OpenBao KV client (API-key token vault)."""

import os

# In-cluster OpenBao address. Default matches the cluster-forge deployment.
OPENBAO_ADDR = os.getenv("OPENBAO_ADDR", "http://openbao.cf-openbao.svc.cluster.local:8200")

# Token with write access to the API-key KV path. In local/dev this is the OpenBao root
# token (k8s Secret `openbao-keys`, key `root_token`) — the same token cluster-auth reuses.
# Production swaps in a token scoped to `<mount>/data/apikeys/*`.
OPENBAO_TOKEN = os.getenv("OPENBAO_TOKEN", "")

# KV v2 mount and path prefix for API-key tokens. ESO's readonly-user reads `secrets/data/*`,
# so `secrets/apikeys/<id>` is materializable without any read-policy change.
OPENBAO_KV_MOUNT = os.getenv("OPENBAO_KV_MOUNT", "secrets")
OPENBAO_API_KEY_PATH_PREFIX = os.getenv("OPENBAO_API_KEY_PATH_PREFIX", "apikeys")

# The ESO ClusterSecretStore that materializes per-backend Secrets from this OpenBao.
# Consumed by the ExternalSecret store module.
OPENBAO_SECRET_STORE_REF = os.getenv("OPENBAO_SECRET_STORE_REF", "openbao-secret-store")
