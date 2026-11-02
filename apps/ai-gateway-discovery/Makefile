# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

IMAGE_REPO ?= silogenai/ai-gateway-discovery
IMAGE_TAG  ?= latest

LOCALBIN ?= $(shell pwd)/bin
$(LOCALBIN):
	mkdir -p $(LOCALBIN)

GOLANGCI_LINT         ?= $(LOCALBIN)/golangci-lint
GOLANGCI_LINT_VERSION ?= v1.63.4

.PHONY: build
build:
	go build ./cmd/controller ./cmd/authz

.PHONY: test
test:
	go test ./...

.PHONY: test-coverage
test-coverage:
	go test -coverprofile=coverage.out ./...

.PHONY: vet
vet:
	go vet ./...

.PHONY: tidy
tidy:
	go mod tidy

.PHONY: lint
lint: golangci-lint
	$(GOLANGCI_LINT) run --allow-parallel-runners

.PHONY: golangci-lint
golangci-lint: $(GOLANGCI_LINT)
$(GOLANGCI_LINT): $(LOCALBIN)
	$(call go-install-tool,$(GOLANGCI_LINT),github.com/golangci/golangci-lint/cmd/golangci-lint,$(GOLANGCI_LINT_VERSION))

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

.PHONY: docker-build
docker-build:
	docker build -t $(IMAGE_REPO):$(IMAGE_TAG) .

.PHONY: docker-push
docker-push:
	docker push $(IMAGE_REPO):$(IMAGE_TAG)
