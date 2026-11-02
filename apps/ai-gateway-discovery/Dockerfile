# syntax=docker/dockerfile:1
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

FROM golang:1.25-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . ./
# One image, two entrypoints: the reconciler (cmd/controller) and the ext_authz data path
# (cmd/authz). They share internal/, so a single build keeps their versions in lockstep; the helm
# chart selects which binary each Deployment runs.
RUN CGO_ENABLED=0 GOOS=linux go build -o controller ./cmd/controller && \
    CGO_ENABLED=0 GOOS=linux go build -o authz ./cmd/authz

FROM alpine:3.23

RUN addgroup -S -g 65532 controller && adduser -S -u 65532 -G controller controller

COPY --from=builder /app/controller /controller
COPY --from=builder /app/authz /authz

USER 65532

ENTRYPOINT ["/controller"]
