#!/bin/sh

# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

set -e

export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=local-dev-access

# Check if 'local-testing' secrets engine is enabled
if ! vault secrets list -format=json | grep -q '"local-testing/"'; then
  echo "Enabling KV v2 secrets engine at path 'local-testing'"
  vault secrets enable -path=local-testing -version=2 kv
else
  echo "Secrets engine at 'local-testing/' already enabled. Skipping."
fi

# Check if the secret already exists
if vault kv get local-testing/test > /dev/null 2>&1; then
  echo "Secret at 'local-testing/test' already exists. Skipping write."
else
  echo "Writing initial secrets to 'local-testing/test'"
  vault kv put local-testing/test secret1="secret-1-content" secret2="secret-2-content"
fi
