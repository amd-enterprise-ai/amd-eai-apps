# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

.PHONY: build build-agent build-webhook run run-agent run-webhook dev dev-agent dev-webhook test test-verbose test-coverage test-coverage-html clean tidy format lint lint-fix vendor

## Location to install dependencies to
LOCALBIN ?= $(shell pwd)/bin
$(LOCALBIN):
	mkdir -p $(LOCALBIN)

## Tool Binaries
GOLANGCI_LINT ?= $(LOCALBIN)/golangci-lint
AIR ?= $(LOCALBIN)/air

## Tool Versions
GOLANGCI_LINT_VERSION ?= v2.12.2
AIR_VERSION ?= v1.61.7

build: build-agent build-webhook

build-agent:
	go build -o bin/agent ./cmd/agent

build-webhook:
	go build -o bin/webhook ./cmd/webhooks

run: run-agent

run-agent:
	go run ./cmd/agent

run-webhook:
	go run ./cmd/webhooks

dev: dev-agent

dev-agent: air
	$(AIR)

dev-webhook: air
	AIR_CMD="./cmd/webhooks" $(AIR)

test:
	go test ./...

test-verbose:
	go test ./... -v

test-coverage:
	go test ./... -coverprofile=coverage.out
	go tool cover -func=coverage.out

test-coverage-html:
	go test ./... -coverprofile=coverage.out
	go tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report generated: coverage.html"

clean:
	rm -rf bin/ tmp/
	rm -f coverage.out coverage.html

tidy:
	go mod tidy

# Populate gitignored vendor/ for local dev and kind Air (mounted /code). Not used in CI/Docker image builds.
vendor:
	go mod vendor

# Format the codebase using gofmt (standard Go formatter)
format:
	@echo "Formatting Go code..."
	gofmt -w .
	@echo "Formatting complete!"

# Lint the codebase using golangci-lint
lint: golangci-lint
	$(GOLANGCI_LINT) run --allow-parallel-runners

# Lint and automatically fix issues where possible
lint-fix: golangci-lint
	$(GOLANGCI_LINT) run --fix --allow-parallel-runners

##@ Dependencies

.PHONY: golangci-lint
golangci-lint: $(GOLANGCI_LINT) ## Download golangci-lint locally if necessary.
$(GOLANGCI_LINT): $(LOCALBIN)
	$(call go-install-tool,$(GOLANGCI_LINT),github.com/golangci/golangci-lint/v2/cmd/golangci-lint,$(GOLANGCI_LINT_VERSION))

.PHONY: air
air: $(AIR) ## Download air locally if necessary.
$(AIR): $(LOCALBIN)
	$(call go-install-tool,$(AIR),github.com/air-verse/air,$(AIR_VERSION))

# go-install-tool will 'go install' any package with custom target and name of binary, if it doesn't exist
# $1 - target path with name of binary
# $2 - package url which can be installed
# $3 - specific version of package
define go-install-tool
@[ -f "$(1)-$(3)" ] || { \
set -e; \
package=$(2)@$(3) ;\
echo "Downloading $${package}" ;\
rm -f $(1) || true ;\
GOBIN=$(LOCALBIN) go install $${package} ;\
mv $(1) $(1)-$(3) ;\
} ;\
ln -sf $(1)-$(3) $(1)
endef
