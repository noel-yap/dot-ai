# Top-level Makefile for the .ai repo.
#
# Skill eval workflows live in skills/Makefile; this file forwards to them so
# you can run everything from the repo root:
#   make install
#   make test
#   make test-unit
#   make eval
#   make eval-dependency-injection
#
# Vars (passed through to skills/): MODEL MAX_TRIALS TARGET_RATE CONCURRENCY
# ISOLATE PYTEST_ARGS

SKILLS := skills

.DEFAULT_GOAL := help

.PHONY: help install test test-unit eval clean

help: ## Show skill eval targets (delegates to skills/)
	@$(MAKE) -C $(SKILLS) help

install: ## Sync the skills project venv from uv.lock
	@$(MAKE) -C $(SKILLS) install

test: ## Run unit tests then live evals
	@$(MAKE) -C $(SKILLS) test

test-unit: ## Run fast unit tests only (no API calls)
	@$(MAKE) -C $(SKILLS) test-unit

eval: ## Run all skill live evals (real model calls)
	@$(MAKE) -C $(SKILLS) eval

clean: ## Remove install stamps and pytest caches under skills/
	@$(MAKE) -C $(SKILLS) clean

.PHONY: eval-%
eval-%: ## Run live evals for one skill (e.g. make eval-dependency-injection)
	@$(MAKE) -C $(SKILLS) eval-$*
