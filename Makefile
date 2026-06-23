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
# Vars (passed through to skills/): MAX_TRIALS TARGET_RATE CONCURRENCY ISOLATE
# PYTEST_ARGS PYTHON

PYTHON ?= python3
SKILLS := skills

.DEFAULT_GOAL := help

# Mirrors the stamp path from skills/Makefile so top-level targets can depend
# on it directly; install only reruns when requirements.txt changes.
ENV_ID        := $(shell $(PYTHON) -c 'import sys,hashlib; print(hashlib.sha1(sys.prefix.encode()).hexdigest()[:12])')
INSTALL_STAMP := $(SKILLS)/.install.$(ENV_ID).stamp

.PHONY: help test test-unit eval clean

help: ## Show skill eval targets (delegates to skills/)
	@$(MAKE) -C $(SKILLS) help

install: $(INSTALL_STAMP) ## Install pinned deps into the active Python environment

$(INSTALL_STAMP): $(SKILLS)/requirements.txt
	@$(MAKE) -C $(SKILLS) install

test: $(INSTALL_STAMP) ## Run unit tests then claude evals
	@$(MAKE) -C $(SKILLS) test

test-unit: $(INSTALL_STAMP) ## Run fast unit tests only (no API calls)
	@$(MAKE) -C $(SKILLS) test-unit

eval: $(INSTALL_STAMP) ## Run all skill claude evals (real model calls)
	@$(MAKE) -C $(SKILLS) eval

clean: ## Remove install stamps and pytest caches under skills/
	@$(MAKE) -C $(SKILLS) clean

.PHONY: eval-%
eval-%: $(INSTALL_STAMP) ## Run claude evals for one skill (e.g. make eval-dependency-injection)
	@$(MAKE) -C $(SKILLS) eval-$*
