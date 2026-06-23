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
# package, pinned in requirements.txt. Run `make install` first.
#
# Run from this directory (skills/). Examples:
#   make install              # install pinned binom-eval into the active env
#   make test                 # everything: unit tests then claude evals
#   make test-unit            # fast unit tests only, no API calls
#   make eval                 # all skills' claude evals in parallel (target 3/5, <=21 runs)
#   make eval-dependency-injection
#   make eval TARGET_RATE=0.8 MAX_TRIALS=12
#   make eval CONCURRENCY=2   # cap in-flight `claude -p` calls (default 5)
#   make eval ISOLATE=0       # run in the live tree (no per-trial copy)
#   make test-unit PYTEST_ARGS="-v"

PYTHON      ?= python3
PYTEST      ?= $(PYTHON) -m pytest
PIP         ?= uv pip install
MAX_TRIALS  ?= 21
TARGET_RATE ?= 0.6
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
PYTEST_ARGS ?=

# Stamp file recording a successful install. Depends on requirements.txt, so
# `install` re-runs only when the pins change; test targets depend on the
# stamp so they install on demand without reinstalling every time. The stamp
# is keyed to a stable hash of the active interpreter's sys.prefix, so each
# virtualenv gets its own stamp and switching envs forces a reinstall.
ENV_ID        := $(shell $(PYTHON) -c 'import sys,hashlib; print(hashlib.sha1(sys.prefix.encode()).hexdigest()[:12])')
INSTALL_STAMP := .install.$(ENV_ID).stamp

UNIT_FLAGS := -m "not live_eval"
# `--live-eval-isolate` unless ISOLATE=0 (any non-zero value keeps it on).
ISOLATE_FLAG := $(if $(filter-out 0,$(ISOLATE)),--live-eval-isolate,)
EVAL_FLAGS := -m live_eval --live-eval-max-trials $(MAX_TRIALS) --live-eval-target-rate $(TARGET_RATE) --live-eval-concurrency $(CONCURRENCY) $(ISOLATE_FLAG)

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
	@echo "Vars: MAX_TRIALS=$(MAX_TRIALS) TARGET_RATE=$(TARGET_RATE) CONCURRENCY=$(CONCURRENCY) ISOLATE=$(ISOLATE) PYTEST_ARGS='$(PYTEST_ARGS)'"

install: $(INSTALL_STAMP) ## Install the pinned binom-eval (+pytest) into the active environment

$(INSTALL_STAMP): requirements.txt
	$(PIP) -r requirements.txt
	@touch $@

test: test-unit eval ## Run everything: unit tests then claude evals (real model calls)

test-unit: $(INSTALL_STAMP) ## Run every skill's unit tests (excludes live_eval)
	$(PYTEST) . $(UNIT_FLAGS) $(PYTEST_ARGS)

eval: $(INSTALL_STAMP) ## Run every skill's claude evals in parallel (real model calls; set MAX_TRIALS/TARGET_RATE/CONCURRENCY)
	$(PYTEST) $(SKILL_DIRS) $(EVAL_FLAGS) $(PYTEST_ARGS)

eval-%: $(INSTALL_STAMP) ## Run claude evals for one skill: make eval-<skill>
	$(PYTEST) "$*/evals" $(EVAL_FLAGS) $(PYTEST_ARGS)

clean: ## Remove the install stamp and pytest / __pycache__ caches under skills/
	rm -f .install.*.stamp
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
