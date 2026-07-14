include ../keyring.mk

# binom-eval v2.0.0 requires `--live-eval-model` to be `backend:model`;
# mirror skills/Makefile's default so both entrypoints target one harness.
MODEL ?= claude:claude-sonnet-5

.PHONY: install test test-unit test-integration

install:
	uv sync

test: test-unit test-integration

test-unit: install
	uv run pytest

test-integration: install
	$(KEYRING_PREFIX) uv run pytest -m live_eval --live-eval-model=$(MODEL)
