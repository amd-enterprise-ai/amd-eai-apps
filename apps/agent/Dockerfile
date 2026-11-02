# syntax=docker/dockerfile:1
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Build stage
FROM golang:1.27-alpine AS builder

WORKDIR /app

COPY apps/agent/go.mod apps/agent/go.sum ./
RUN go mod download

COPY apps/agent/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -o agent ./cmd/agent && \
    CGO_ENABLED=0 GOOS=linux go build -o webhook ./cmd/webhooks && \
    CGO_ENABLED=0 GOOS=linux go build -o cleanup ./cmd/cleanup

FROM alpine:3.24

COPY --from=builder /app/agent /agent
COPY --from=builder /app/webhook /webhook
COPY --from=builder /app/cleanup /cleanup

# Default to agent, but can be overridden in Kubernetes with command: ["/webhook"] or ["/cleanup"]
ENTRYPOINT ["/agent"]
