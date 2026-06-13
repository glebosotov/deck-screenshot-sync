SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

ZIP ?= build/decky/game-media-sync-decky.zip
DECKY_DIR := decky

.PHONY: help install test lint format format-check check ci nix-check decky-install decky-build decky-typecheck decky-package decky-verify-zip decky-release-check clean

help:
	@awk 'BEGIN {FS = ":.*## "; print "Targets:"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install Python dev dependencies with uv.
	uv sync --extra dev

test: ## Run unit tests.
	uv run pytest

lint: ## Run Ruff lint checks.
	uv run ruff check

format: ## Format Python files with Ruff.
	uv run ruff format

format-check: ## Check Python formatting.
	uv run ruff format --check

check: lint format-check test decky-typecheck decky-release-check ## Run local checks and verify the Decky ZIP.

ci: ## Run checks inside the Nix dev shell, then evaluate the flake.
	nix develop path:$(CURDIR) -c make check
	nix flake check path:$(CURDIR)

nix-check: ## Evaluate the Nix flake.
	nix flake check path:$(CURDIR)

decky-install: ## Install Decky frontend dependencies from the lockfile.
	pnpm --dir $(DECKY_DIR) install --frozen-lockfile

decky-build: decky-install ## Build the Decky frontend bundle.
	pnpm --dir $(DECKY_DIR) run build

decky-typecheck: ## Typecheck the Decky frontend.
	pnpm --dir $(DECKY_DIR) run typecheck

decky-package: ## Build the sideloadable Decky ZIP.
	python scripts/package_decky.py

decky-verify-zip: ## Verify the Decky ZIP layout and bundled files.
	python scripts/verify_decky_zip.py $(ZIP)

decky-release-check: decky-package decky-verify-zip ## Build and verify the release ZIP.

clean: ## Remove generated Decky build outputs.
	rm -rf build/decky decky/dist
