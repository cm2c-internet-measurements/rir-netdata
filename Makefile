# rir-netdata: common tasks. Run `make help` for the list.

IMAGE   ?= carlosm3012/rir-netdata
ENGINE  ?= docker
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)

.PHONY: help sync test run build push image-run clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

sync:  ## Install dependencies into .venv
	uv sync

test:  ## Lint, check formatting and run the offline tests
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest

run:  ## Build today's database locally into var/
	uv run rir-netdata get

build:  ## Build the container image (ENGINE=podman to use podman)
	$(ENGINE) build -t $(IMAGE):$(VERSION) -t $(IMAGE):latest .

push: build  ## Push the image to the registry
	$(ENGINE) push $(IMAGE):$(VERSION)
	$(ENGINE) push $(IMAGE):latest

image-run:  ## Run the container image: database to ./var, download cache in ./tmp
	mkdir -p var tmp
	$(ENGINE) run --rm -v "$(CURDIR)/var:/data/var" -v "$(CURDIR)/tmp:/data/tmp" $(IMAGE):$(VERSION)

clean:  ## Remove the download cache and caches from tools
	rm -rf tmp/*-latest tmp/*.gz tmp/*.csv .pytest_cache .ruff_cache
