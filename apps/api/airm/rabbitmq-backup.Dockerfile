# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM alpine:3.24

# Install dependencies: curl and MinIO client
RUN apk add --no-cache curl && \
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
    # Set a writable directory for MinIO client
    MC_CONFIG_DIR="/tmp/.mc"

# Use CMD to run the script directly
CMD set -e && \
    echo "Fetching RabbitMQ definitions..." && \
    curl -s -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" "$RABBITMQ_URL/api/definitions" > /tmp/definitions.json && \
    echo "Generating timestamp and folder structure..." && \
    DATE_FOLDER=$(date +'%Y%m%d') && \
    TIMESTAMP=$(date +'%H%M%S') && \
    echo "Configuring MinIO Client..." && \
    mc alias set backup-minio "$S3_HOST" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" && \
    echo "Uploading to MinIO storage under folder: $DATE_FOLDER" && \
    mc cp /tmp/definitions.json "backup-minio/$S3_BUCKET/$DATE_FOLDER/definitions-$TIMESTAMP.json" && \
    echo "Upload complete."
