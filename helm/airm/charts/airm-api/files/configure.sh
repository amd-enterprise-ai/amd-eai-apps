#!/bin/bash

# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Fail a pipeline if any stage fails, not just the last one. Without this a failing
# curl is masked by a succeeding jq, so an empty/garbage payload flows downstream and
# is only caught (if at all) as a confusing "null" value much later.
set -o pipefail

#####################################################################################
echo ""
echo "Run configure script block..."
echo ""

# --- Configuration Variables ---
# Get values from bloom configmap mounted as env

CLUSTER_WORKBENCH_BASE_URL="https://aiwbui.${NEW_DOMAIN_NAME}/"
CLUSTER_KUBE_API_URL="https://k8s.${NEW_DOMAIN_NAME}"
USER_EMAIL="devuser@${NEW_DOMAIN_NAME}"
PROJECT_NAME="demo"
PROJECT_DESCRIPTION="demo"
TIMEOUT=300
SLEEP_INTERVAL=5
# Must match airm-agent's .Values.airm.agent.rabbitmq.userSecretName.
AGENT_SECRET_NAME="airm-rabbitmq-common-vhost-user"

# --- Input Validation ---
echo "Validating environment variables..."
echo "KEYCLOAK_CLIENT_ID: ${KEYCLOAK_CLIENT_ID}"
echo "NEW_DOMAIN_NAME: ${NEW_DOMAIN_NAME}"
echo "AIRM_API_URL: ${AIRM_API_URL}"

function check_env_variable() {
  if [ -z "${!1}" ]; then
    echo "ERROR: $1 environment variable is not set."
    exit 1
  fi
}

function check_success() {
    if [ "$1" -ne 0 ]; then
        echo "ERROR: $2"
        exit 1
    fi
}

check_env_variable "AIRM_API_URL"
check_env_variable "KEYCLOAK_URL"
check_env_variable "KEYCLOAK_REALM"
check_env_variable "KEYCLOAK_CLIENT_SECRET"
check_env_variable "KEYCLOAK_CLIENT_ID"
check_env_variable "KEYCLOAK_ADMIN_CLIENT_ID"
check_env_variable "KEYCLOAK_ADMIN_CLIENT_SECRET"
check_env_variable "USER_PASSWORD"
check_env_variable "AGENT_NAMESPACE"

function refresh_token() {
    TOKEN=$(curl -s -d "client_id=${KEYCLOAK_CLIENT_ID}" -d "username=${USER_EMAIL}" -d "password=${USER_PASSWORD}" -d 'grant_type=password' -d "client_secret=${KEYCLOAK_CLIENT_SECRET}" "${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" | jq -r '.access_token')
    if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
        echo "ERROR: Failed to obtain access token from Keycloak."
        exit 1
    fi
}

function create_project() {
    PROJECT_ID=$(curl -s -X GET "${AIRM_API_URL}/v1/projects" -H 'accept: application/json' -H "Authorization: Bearer ${TOKEN}" | jq -r '.data[] | select(.name=="'$PROJECT_NAME'") | .id')

    for (( i=0; i<=TIMEOUT; i+=SLEEP_INTERVAL )); do
        CLUSTER_STATUS=$(curl -s -X GET "${AIRM_API_URL}/v1/clusters/$CLUSTER_ID" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json' | jq -r '.status')

        if [ "$CLUSTER_STATUS" == "healthy" ]; then
        echo "Cluster is healthy!"
        break # Exit the loop if the cluster is healthy
        fi
        echo "Cluster status: $CLUSTER_STATUS.  Waiting $SLEEP_INTERVAL seconds... ($i/$TIMEOUT seconds elapsed)"
        sleep $SLEEP_INTERVAL
    done

    if [ "$CLUSTER_STATUS" != "healthy" ]; then
        echo "ERROR: Cluster did not become healthy within $TIMEOUT seconds."
        exit 1
    fi

    if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "null" ]; then
        echo "Projects '$PROJECT_NAME' not found. Creating..."
        PROJECT_ID=$(curl -X 'POST' \
        "${AIRM_API_URL}/v1/projects" \
        -H 'accept: application/json' \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json' \
        -d '{
            "name": "'"$PROJECT_NAME"'",
            "description": "'"$PROJECT_DESCRIPTION"'",
            "clusterId": "'"$CLUSTER_ID"'",
            "quota": {
            "cpuMilliCores": 0,
            "memoryBytes": 0,
            "ephemeralStorageBytes": 0,
            "gpuCount": 0
            }
        }' | jq -r '.id')
        echo "$PROJECT_ID"
        check_success "$([[ "$PROJECT_ID" != "null" ]] && echo 0 || echo 1)" "Failed to create project"
    else
        echo "Project '$PROJECT_NAME' already exists with ID: $PROJECT_ID"
    fi
}

function add_minio_secret_and_storage_to_project() {
    for (( i=0; i<=TIMEOUT; i+=SLEEP_INTERVAL )); do
        PROJECT_STATUS=$(curl -s -X GET "${AIRM_API_URL}/v1/projects/$PROJECT_ID" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json' | jq -r '.status')

        if [ "$PROJECT_STATUS" == "Ready" ]; then
        echo "Project is ready!"
        break # Exit the loop if the project is ready
        fi
        echo "Project status: $PROJECT_STATUS.  Waiting $SLEEP_INTERVAL seconds... ($i/$TIMEOUT seconds elapsed)"
        sleep $SLEEP_INTERVAL
    done

    SECRET_NAME="minio-credentials-fetcher"
    STORAGE_NAME="minio-storage"

    SECRET_IN_PROJECT=$(curl -X 'GET' \
    "${AIRM_API_URL}/v1/projects/${PROJECT_ID}/secrets" \
    -H 'accept: application/json' \
    -H "Authorization: Bearer ${TOKEN}" | jq -r '.data[] | select(.secret.name=="'"$SECRET_NAME"'") | .id')
    EXTERNAL_SECRET_API_VERSION="v1beta1"
    EXTERNAL_SECRET_MANIFEST=$(cat <<EOF
apiVersion: external-secrets.io/${EXTERNAL_SECRET_API_VERSION}
kind: ExternalSecret
metadata:
  name: ${SECRET_NAME}
spec:
  data:
    - remoteRef:
        key: minio-api-access-key
        property: value
        conversionStrategy: Default
        decodingStrategy: None
        metadataPolicy: None
      secretKey: minio-access-key
    - remoteRef:
        key: minio-api-secret-key
        property: value
        conversionStrategy: Default
        decodingStrategy: None
        metadataPolicy: None
      secretKey: minio-secret-key
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: openbao-secret-store
  target:
    creationPolicy: Owner
    name: minio-credentials
EOF
)
    if [ -z "$SECRET_IN_PROJECT" ] || [ "$SECRET_IN_PROJECT" == "null" ]; then
        echo "Adding secret to project '$PROJECT_ID'..."
        ADD_SECRET_RESP=$(curl -w "%{http_code}" -o /dev/null -X 'POST' \
        "${AIRM_API_URL}/v1/secrets" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json' \
        -d '{
            "name": "'"$SECRET_NAME"'",
            "projectIds": ["'"$PROJECT_ID"'"],
            "type": "ExternalSecret",
            "useCase": "S3",
            "scope": "Organization",
            "manifest": '"$(echo "$EXTERNAL_SECRET_MANIFEST" | jq -Rs .)"'
        }')
        echo "$ADD_SECRET_RESP"
        check_success "$([[ "$ADD_SECRET_RESP" == "200" || "$ADD_SECRET_RESP" == "201" || "$ADD_SECRET_RESP" == "204" ]] && echo 0 || echo 1)" "Failed to add minio secret to project"
    else
        echo "Secret already exists in project '$PROJECT_ID'."
    fi

    # Check if secret exist and synced
    for (( i=0; i<=TIMEOUT; i+=SLEEP_INTERVAL )); do
        SECRET_RESP=$(curl -s -X GET "${AIRM_API_URL}/v1/secrets" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json')

        SECRET_STATUS=$(echo $SECRET_RESP | jq -r '.data[] | select(.name=="'"$SECRET_NAME"'") | .status')
        SECRET_ID=$(echo $SECRET_RESP | jq -r '.data[] | select(.name=="'"$SECRET_NAME"'") | .id')

        if [ "$SECRET_STATUS" == "Synced" ] || [ "$SECRET_STATUS" == "Unassigned" ]; then
            echo "Secret is ready!"
            break
        fi
        echo "Secret status: $SECRET_STATUS.  Waiting $SLEEP_INTERVAL seconds... ($i/$TIMEOUT seconds elapsed)"
        sleep $SLEEP_INTERVAL
    done

    STORAGE_IN_PROJECT=$(curl -X 'GET' \
    "${AIRM_API_URL}/v1/projects/${PROJECT_ID}/storages" \
    -H 'accept: application/json' \
    -H "Authorization: Bearer ${TOKEN}" | jq -r '.data[] | select(.storage.name=="'"$STORAGE_NAME"'") | .id')

    if [ -z "$STORAGE_IN_PROJECT" ] || [ "$STORAGE_IN_PROJECT" == "null" ]; then
        echo "Adding storage configuration to project '$PROJECT_ID'..."
        ADD_STORAGE_RESP=$(curl -w "%{http_code}" -o /dev/null -X 'POST' \
        "${AIRM_API_URL}/v1/storages" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json' \
        -d '{
            "name": "'"$STORAGE_NAME"'",
            "projectIds": ["'"$PROJECT_ID"'"],
            "secretId": "'"$SECRET_ID"'",
            "type": "S3",
            "scope": "Organization",
            "spec": {
                "bucketUrl": "http://minio.minio-tenant-default.svc.cluster.local:80",
                "accessKeyName": "minio-access-key",
                "secretKeyName": "minio-secret-key"
            }
        }')
        echo "$ADD_STORAGE_RESP"
        check_success "$([[ "$ADD_STORAGE_RESP" == "200" || "$ADD_STORAGE_RESP" == "201" || "$ADD_STORAGE_RESP" == "204" ]] && echo 0 || echo 1)" "Failed to add minio storage to project"
    else
        echo "Storage already exists in project '$PROJECT_ID'."
    fi
}

function add_user_to_project() {
    # Get project id
    USER_IN_PROJECT=$(curl -X 'GET' \
    "${AIRM_API_URL}/v1/users" \
    -H 'accept: application/json' \
    -H "Authorization: Bearer ${TOKEN}" | jq -r  '.data[] | select(.projects.id=="'"$PROJECT_ID"'" and .email=="'"$USER_EMAIL"'") | .id ')

    USER_ID=$(curl -X 'GET' \
    "${AIRM_API_URL}/v1/users" \
    -H 'accept: application/json' \
    -H "Authorization: Bearer ${TOKEN}" | jq -r  '.data[] | select(.email=="'"$USER_EMAIL"'") | .id ')

    # Add user to project if they are not already in it
    if [ -z "$USER_IN_PROJECT" ] || [ "$USER_IN_PROJECT" == "null" ]; then
        echo "Adding user '$USER_ID' to project '$PROJECT_ID'..."
        ADD_PROJECT_RESP=$(curl -w "%{http_code}" -o /dev/null -X 'POST' \
        "${AIRM_API_URL}/v1/projects/${PROJECT_ID}/users" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json' \
        -d '{"userIds": ["'"${USER_ID}"'"]}')
        echo "$ADD_PROJECT_RESP"
        check_success "$([[ "$ADD_PROJECT_RESP" == "200" || "$ADD_PROJECT_RESP" == "201" || "$ADD_PROJECT_RESP" == "204" ]] && echo 0 || echo 1)" "Failed to add user to project"
    else
        echo "User '$USER_ID' already exists in project '$PROJECT_ID'."
    fi
}

# Returns 0 if the in-cluster RabbitMQ secret is complete and still belongs to the
# given cluster ID. The API only ever returns userSecret once, at creation time, so a
# pre-existing cluster gives us no way to re-derive the password. The K8s secret is
# therefore the only copy; if it is absent, incomplete, or points at a different
# cluster, the credentials are unrecoverable and the cluster has to be recreated.
function agent_secret_matches_cluster() {
    local cluster_id="$1"
    local secret_json
    local secret_username
    local secret_password

    # Fetch once and pull both keys out locally: querying each key separately would
    # need two round trips and make "absent secret" hard to tell from "absent key".
    local kubectl_exit
    secret_json=$(kubectl get secret "$AGENT_SECRET_NAME" -n "$AGENT_NAMESPACE" -o json 2>&1)
    kubectl_exit=$?
    if [ "$kubectl_exit" -ne 0 ]; then
        # A missing secret (kubectl's own "NotFound" from the API server) is the
        # normal first-install case, but any other failure -- RBAC, connectivity, or
        # kubectl itself being unusable (exit 127) -- is not: treating those as
        # "missing" would delete and recreate a perfectly good cluster. Only the
        # former is recoverable here. Checking the exit code first means a shell-level
        # "command not found" (also exit 127) can never be misread as the API's
        # "NotFound", which the string match alone could not tell apart.
        if [ "$kubectl_exit" -ne 127 ] && { [[ "$secret_json" == *NotFound* ]] || [[ "$secret_json" == *"not found"* ]]; }; then
            echo "RabbitMQ agent secret '$AGENT_SECRET_NAME' does not exist in namespace '$AGENT_NAMESPACE'."
            return 1
        fi
        echo "ERROR: Could not read secret '$AGENT_SECRET_NAME' in namespace '$AGENT_NAMESPACE'."
        echo "ERROR: $secret_json"
        exit 1
    fi

    secret_username=$(printf '%s' "$secret_json" | jq -r '.data.username // empty' | base64 -d 2>/dev/null)
    # The agent needs both keys to authenticate. A secret carrying the right username
    # but an empty password is just as unusable as a stale one, and silently reusing
    # it would leave the agent unable to connect with no attempt at recovery.
    secret_password=$(printf '%s' "$secret_json" | jq -r '.data.password // empty' | base64 -d 2>/dev/null)

    if [ -z "$secret_username" ] || [ -z "$secret_password" ]; then
        echo "RabbitMQ agent secret is incomplete: username and password must both be set."
        return 1
    fi

    if [ "$secret_username" != "$cluster_id" ]; then
        echo "RabbitMQ agent secret is stale: it holds cluster ID '$secret_username', expected '$cluster_id'."
        return 1
    fi

    return 0
}

# Deletes a cluster so the normal create path can recreate it (and mint a fresh
# userSecret). The API refuses with 409 when the cluster still has projects
# attached; in that case recreating would destroy user data, so fail loudly and let
# an operator decide rather than continue with credentials we cannot repair.
function delete_stale_cluster() {
    local cluster_id="$1"
    local delete_code

    echo "Deleting cluster $cluster_id so it can be recreated with a fresh secret..."
    delete_code=$(curl -s -w "%{http_code}" -o /dev/null -X 'DELETE' \
        "${AIRM_API_URL}/v1/clusters/${cluster_id}" \
        -H 'accept: application/json' \
        -H "Authorization: Bearer ${TOKEN}")

    case "$delete_code" in
        200|204|404)
            echo "Cluster $cluster_id deleted (HTTP $delete_code)."
            ;;
        409)
            echo "ERROR: Cannot recover cluster $cluster_id."
            echo "ERROR: Its RabbitMQ credentials are lost (the K8s secret is missing or stale),"
            echo "ERROR: but the cluster still has projects attached so it cannot be recreated"
            echo "ERROR: automatically without destroying them."
            echo "ERROR: Operator action required: either restore the original"
            echo "ERROR: '$AGENT_SECRET_NAME' secret in the '$AGENT_NAMESPACE' namespace, or"
            echo "ERROR: migrate/remove the projects on cluster $cluster_id and re-run this job."
            exit 1
            ;;
        *)
            echo "ERROR: Failed to delete cluster $cluster_id (HTTP $delete_code)."
            exit 1
            ;;
    esac
}

function create_cluster() {
    # Check if cluster exists by kube API URL. Clusters are created without a name,
    # so a name-based lookup always misses and every retry would create a duplicate.
    # The API serializes responses as camelCase (kubeApiUrl). kubeApiUrl is not
    # guaranteed unique, and an environment may already hold duplicates from before
    # this check existed, so pick the most-recently-active match and avoid binding to
    # a stale/unhealthy duplicate. lastHeartbeatAt alone is not a total order: the
    # listing endpoint has no ORDER BY, and jq's max_by returns the *last* element on
    # ties (including when every key is null, i.e. no cluster has reported a
    # heartbeat yet). Sort by the (lastHeartbeatAt, createdAt, id) tuple and take the
    # final element so the choice is genuinely deterministic regardless of row order.
    # `// ""` keeps null keys from being compared against strings.
    local clusters_resp
    local http_code
    clusters_resp=$(curl -s -w "\n%{http_code}" -X GET "${AIRM_API_URL}/v1/clusters" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H 'Content-Type: application/json')
    http_code=$(printf '%s' "$clusters_resp" | tail -n1)
    if [ "$http_code" != "200" ]; then
        echo "ERROR: Failed to list clusters (HTTP $http_code)."
        exit 1
    fi

    CLUSTER_EXISTS=$(printf '%s' "$clusters_resp" | sed '$d' | jq -r --arg kubeApiUrl "$CLUSTER_KUBE_API_URL" '
        [.data[] | select(.kubeApiUrl == $kubeApiUrl)]
        | sort_by(.lastHeartbeatAt // "", .createdAt // "", .id)
        | last
        | .id // empty')
    check_success "$?" "Failed to parse cluster list response"

    if [ -n "$CLUSTER_EXISTS" ] && [ "$CLUSTER_EXISTS" != "null" ]; then
        echo "Cluster already exists with ID: $CLUSTER_EXISTS"
        # Reuse it only if we still hold its RabbitMQ credentials. The create path
        # below is the only place CLUSTER_SECRET is ever set, so a cluster we cannot
        # authenticate against must be deleted and recreated.
        if agent_secret_matches_cluster "$CLUSTER_EXISTS"; then
            echo "Reusing existing cluster $CLUSTER_EXISTS; agent secret is current."
            CLUSTER_ID=$CLUSTER_EXISTS
            return
        fi
        delete_stale_cluster "$CLUSTER_EXISTS"
    fi

    # Create cluster
    echo "Creating cluster..."
    CLUSTER=$(curl -X 'POST' \
    "${AIRM_API_URL}/v1/clusters" \
    -H 'accept: application/json' -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{
      "workbenchBaseUrl": "'"$CLUSTER_WORKBENCH_BASE_URL"'",
      "kubeApiUrl": "'"$CLUSTER_KUBE_API_URL"'"
    }')
    CLUSTER_ID=$(echo "$CLUSTER" | jq -r '.id')
    check_success "$([[ -n "$CLUSTER_ID" && "$CLUSTER_ID" != "null" ]] && echo 0 || echo 1)" "Failed to create cluster"
    CLUSTER_SECRET=$(echo "$CLUSTER" | jq -r '.userSecret')
    check_success "$([[ -n "$CLUSTER_SECRET" && "$CLUSTER_SECRET" != "null" ]] && echo 0 || echo 1)" "Cluster created without a user secret"
}

function create_secret_and_start_agent() {
    # CLUSTER_SECRET is only ever set by the create path, so this block runs exactly
    # when a cluster was just created -- either the first run, or a run that deleted
    # an unrecoverable cluster and recreated it. A reused cluster keeps the secret it
    # already has, which create_cluster has verified still matches.
    if [ -n "$CLUSTER_SECRET" ] && [ "$CLUSTER_SECRET" != "null" ]; then
      # Render-and-apply rather than plain `kubectl create`, which would abort with
      # "already exists" when a secret from a previous cluster is still present.
      kubectl create secret generic "$AGENT_SECRET_NAME" \
        --from-literal=username="$CLUSTER_ID" --from-literal=password="$CLUSTER_SECRET" \
        -n "$AGENT_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
      check_success "$?" "Failed to create/update RabbitMQ agent secret"

      restart_agent_for_new_credentials
    else
        echo "Cluster was not onboarded, skipping creating secrets"
    fi
}

# The agent consumes the RabbitMQ credentials as secretKeyRef environment
# variables, which are resolved once at pod start and never refreshed. Rewriting
# the secret therefore leaves a running agent authenticating with the previous
# cluster's credentials until something replaces the pod, so trigger that here.
# The agent is only co-located when the umbrella chart installs it; on a split
# install it lives on a remote compute cluster and is rolled out of band, so a
# missing deployment is not an error.
function restart_agent_for_new_credentials() {
    local deployments_json
    local agent_deployments

    # Distinguish "no agent here" from "could not look". Swallowing the error would
    # report a missing RBAC rule or a wrong namespace as an intentional split
    # install, leaving the agent running on the previous cluster's credentials.
    if ! deployments_json=$(kubectl get deployments -n "$AGENT_NAMESPACE" -o json 2>&1); then
        echo "ERROR: Could not list deployments in namespace '$AGENT_NAMESPACE'."
        echo "ERROR: $deployments_json"
        exit 1
    fi

    # Match on the secret reference rather than a label or name: the agent's
    # resource names are derived from the Helm release name, which is not fixed.
    agent_deployments=$(printf '%s' "$deployments_json" | jq -r --arg secret "$AGENT_SECRET_NAME" '
        .items[]
        | select([.spec.template.spec.containers[].env[]?.valueFrom.secretKeyRef.name] | index($secret))
        | "deployment/" + .metadata.name')
    check_success "$?" "Failed to parse deployment list"

    if [ -z "$agent_deployments" ]; then
        echo "No co-located agent deployment consumes '$AGENT_SECRET_NAME' in namespace '$AGENT_NAMESPACE'."
        echo "If the agent runs on a separate cluster, restart it there so it picks up the new credentials."
        return 0
    fi

    local agent_deployment
    while IFS= read -r agent_deployment; do
        echo "Restarting $agent_deployment to pick up the new RabbitMQ credentials..."
        if ! kubectl rollout restart "$agent_deployment" -n "$AGENT_NAMESPACE"; then
            echo "ERROR: Failed to restart $agent_deployment; it will keep using stale RabbitMQ credentials."
            exit 1
        fi

        # Bounded wait: surfaces a wedged rollout here instead of leaving the caller
        # to discover a disconnected agent later.
        if ! kubectl rollout status "$agent_deployment" -n "$AGENT_NAMESPACE" --timeout="${TIMEOUT}s"; then
            echo "ERROR: $agent_deployment did not become ready within ${TIMEOUT} seconds."
            exit 1
        fi
    done <<< "$agent_deployments"
}

function main() {
    refresh_token
    echo "create_cluster..."
    create_cluster

    echo "create_secret_and_start_agent..."
    create_secret_and_start_agent
    echo ""

    refresh_token
    echo "create_project..."
    create_project
    refresh_token
    echo "add_user_to_project..."
    add_user_to_project
    echo ""

    echo "add_minio_secret_and_storage_to_project..."
    add_minio_secret_and_storage_to_project
}

main
