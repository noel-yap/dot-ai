# Makefile for the skill eval suites.
#
# Each skill under skills/<name>/evals has fast unit tests (no API) plus
# end-to-end "claude eval" tests (real model calls, graded by a Beta-binomial
# posterior: an assertion passes once the posterior puts most of its mass at
# or above --live-eval-target-rate, over at most --live-eval-max-trials runs).
# The two are split by the `live_eval` marker: unit targets select
# `-m "not live_eval"`, eval targets select `-m live_eval`. The per-skill
# eval dirs reuse the module name _assertions but no longer
# collide: each evals dir is a namespace package whose siblings import
# relatively (see skills/pytest.ini), so every target collects all skills in
# one pytest session. Evals run in parallel via binom-eval's built-in
# concurrency: a single in-process semaphore (`--live-eval-concurrency`) caps
# total in-flight `claude -p` calls across every skill. Per binom-eval's
# README, do NOT add pytest-xdist (`-n`) on top -- each worker would get its
# own semaphore (total calls = workers x concurrency) and recompute the whole
# session-scoped fixture. Tune parallelism with CONCURRENCY instead. Each
# trial also runs in a throwaway copy of the repo (ISOLATE, on by default) so
# the file-editing skills can't clobber each other or the committed fixtures.
#
# The grading, runner, stream-json parser, and the pytest plugin (the
# `--live-eval-*` options, the `live_eval` marker, and the
# `live_eval_target_rate` fixture) come from the installed `binom-eval`
# package, pinned in pyproject.toml / uv.lock. No install step is needed:
# every target runs through `uv run`, which syncs the project venv on demand.
#
# Run from this directory (skills/). Examples:
#   make test                 # everything: unit tests then claude evals
#   make test-unit            # fast unit tests only, no API calls
#   make eval                 # all skills' claude evals in parallel (target 2/3, <=21 runs)
#   make eval-dependency-injection
#   make eval TARGET_RATE=0.8 MAX_TRIALS=12
#   make eval CONCURRENCY=2   # cap in-flight `claude -p` calls (default 5)
#   make eval SHOW_POSTERIOR=0  # omit P(rate >= p0 | k, n) lines from output
#   make eval MODEL=claude:haiku   # or any backend:model; see MODEL below
#   make eval ISOLATE=0       # run in the live tree (no per-trial copy)
#   make test-unit PYTEST_ARGS="-v"

SHELL := bash

# Every target runs through `uv run`, which resolves pyproject.toml against
# uv.lock and syncs this project's .venv before executing -- so results never
# depend on whichever python3/pytest happens to be first on PATH or on
# whatever is installed in the invoking shell's environment.
PYTEST      ?= uv run pytest
MAX_TRIALS  ?= 21
# True pass rate a good skill should clear (`--live-eval-target-rate`).
TARGET_RATE ?= $(shell awk 'BEGIN{print 2/3}')
# Print P(rate >= p0 | k, n) for each passing check (`--live-eval-show-posterior`).
SHOW_POSTERIOR ?= 1
# Ceiling on concurrent `claude -p` calls across the whole eval session,
# passed through to binom-eval's `--live-eval-concurrency`. One shared
# in-process semaphore bounds load and API-rate pressure no matter how many
# skills or trials are in flight; set it to 1 to run fully serially.
CONCURRENCY ?= 5
# Run each trial in a throwaway copy of the repo root (binom-eval's
# `--live-eval-isolate`). The runner drives `claude -p
# --dangerously-skip-permissions` against prompts that ask it to edit the
# sample files, so without isolation concurrent trials clobber one another and
# permanently mutate the fixtures under version control. On by default; set
# ISOLATE=0 only for read-only skills where the per-trial copy isn't worth it.
ISOLATE     ?= 1
# Backend and model for every trial, passed through to binom-eval's
# `--live-eval-model` (required by the plugin). Must be `backend:model`;
# known backends are `claude` and `cursor`. The cursor backend drives
# `cursor-agent` headlessly and authenticates via CURSOR_API_KEY (it runs
# under a throwaway HOME, so an interactive login is deliberately not used);
# the eval recipes resolve that key with sh-keyring's `set_key` (see below).
# Model ids come from `cursor-agent --list-models`. The claude backend needs
# ANTHROPIC_API_KEY and accepts CLI aliases (haiku, sonnet, opus) as well as
# full model IDs.
MODEL       ?= cursor:claude-opus-4-8-high
PYTEST_ARGS ?=

# sh-keyring is vendored as a git submodule; sourcing it provides `set_key`,
# which resolves and exports a secret from the env, macOS Keychain, 1Password,
# or AWS Secrets Manager. The eval recipes use it to resolve CURSOR_API_KEY in
# the same bash shell that runs pytest, so the live runs inherit the key.
SH_KEYRING := ../vendor/sh-keyring/sh-keyring.shlib

$(SH_KEYRING):
	git -C .. submodule sync vendor/sh-keyring
	git -C .. submodule update --init vendor/sh-keyring

UNIT_FLAGS := -m "not live_eval"
# `--live-eval-isolate` unless ISOLATE=0 (any non-zero value keeps it on).
ISOLATE_FLAG := $(if $(filter-out 0,$(ISOLATE)),--live-eval-isolate,)
# `--live-eval-show-posterior` unless SHOW_POSTERIOR=0.
SHOW_POSTERIOR_FLAG := $(if $(filter-out 0,$(SHOW_POSTERIOR)),--live-eval-show-posterior,)
EVAL_FLAGS := -m live_eval --live-eval-model $(MODEL) --live-eval-max-trials $(MAX_TRIALS) --live-eval-target-rate $(TARGET_RATE) --live-eval-concurrency $(CONCURRENCY) --live-eval-failure-max-chars=0 $(ISOLATE_FLAG) $(SHOW_POSTERIOR_FLAG)

# Eval dirs discovered from the tree, e.g. "dependency-injection/evals".
SKILL_DIRS := $(patsubst %/,%,$(dir $(wildcard */evals/evals.json)))
# Skill names, e.g. "dependency-injection".
SKILLS := $(patsubst %/evals,%,$(SKILL_DIRS))

.DEFAULT_GOAL := help

.PHONY: help install test test-unit eval clean

help: ## Show this help
	@echo "Skill eval suite targets:"
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Per-skill claude evals: make eval-<skill>"
	@echo "Discovered skills:      $(SKILLS)"
	@echo "Vars: MODEL=$(MODEL) MAX_TRIALS=$(MAX_TRIALS) TARGET_RATE=$(TARGET_RATE) CONCURRENCY=$(CONCURRENCY) ISOLATE=$(ISOLATE) SHOW_POSTERIOR=$(SHOW_POSTERIOR) PYTEST_ARGS='$(PYTEST_ARGS)'"

install: ## Sync the project venv from uv.lock (uv run also does this on demand)
	uv sync

test: test-unit eval ## Run everything: unit tests then claude evals (real model calls)

test-unit: ## Run every skill's unit tests (excludes live_eval)
	$(PYTEST) . $(UNIT_FLAGS) $(PYTEST_ARGS)

eval: $(SH_KEYRING) ## Run every skill's live evals in parallel (real model calls; set MODEL/MAX_TRIALS/TARGET_RATE/CONCURRENCY)
	@source '$(SH_KEYRING)' && set_key CURSOR_API_KEY && \
	$(PYTEST) $(SKILL_DIRS) $(EVAL_FLAGS) $(PYTEST_ARGS)

eval-%: $(SH_KEYRING) ## Run live evals for one skill: make eval-<skill>
	@source '$(SH_KEYRING)' && set_key CURSOR_API_KEY && \
	$(PYTEST) "$*/evals" $(EVAL_FLAGS) $(PYTEST_ARGS)

clean: ## Remove install stamps and pytest / __pycache__ caches under skills/
	rm -f .install.stamp .install.*.stamp
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
