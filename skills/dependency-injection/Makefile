include ../keyring.mk

.PHONY: install test test-unit test-integration

install:
	uv sync

test: test-unit test-integration

test-unit: install
	uv run pytest

test-integration: install
	$(KEYRING_PREFIX) uv run pytest -m live_eval --live-eval-model=claude-sonnet-4-6
