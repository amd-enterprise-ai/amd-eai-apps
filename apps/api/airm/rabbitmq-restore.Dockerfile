# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM alpine:3.24

# Install dependencies: curl, MinIO client, and jq for JSON handling
RUN apk add --no-cache curl jq && \
    curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/bin/mc && \
    chmod +x /usr/bin/mc

# Set environment variables
ENV RABBITMQ_URL="" \
    RABBITMQ_USER="" \
    RABBITMQ_PASSWORD="" \
    S3_BUCKET="" \
    S3_HOST="" \
    S3_ACCESS_KEY="" \
    S3_SECRET_KEY="" \
    MC_CONFIG_DIR="/tmp/.mc"

# Use CMD to run the script directly
CMD set -e && \
    echo "Configuring MinIO Client..." && \
    mc alias set backup-minio "$S3_HOST" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" && \
    echo "Finding latest backup..." && \
    LATEST_BACKUP=$(mc ls --recursive "backup-minio/$S3_BUCKET" | sort -r | head -n 1 | awk '{print $NF}') && \
    if [ -z "$LATEST_BACKUP" ]; then \
        echo "No backup found" && exit 1; \
    fi && \
    echo "Downloading backup from: $LATEST_BACKUP" && \
    mc cp "backup-minio/$S3_BUCKET/$LATEST_BACKUP" /tmp/definitions.json && \
    echo "Restoring definitions to RabbitMQ..." && \
    curl -X POST -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" \
         -H "Content-Type: application/json" \
         --data @/tmp/definitions.json \
         "$RABBITMQ_URL/api/definitions" && \
    echo "Restore complete."
