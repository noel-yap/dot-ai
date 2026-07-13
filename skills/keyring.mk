# Resolves ANTHROPIC_API_KEY for the live-eval integration tests.
#
# CI exports ANTHROPIC_API_KEY from repository secrets, so we use it as-is and
# never invoke sh-keyring -- the library is macOS-only (its Keychain cache uses
# the `security` CLI and BSD `date`), so sourcing it on GitHub's Linux runners
# would be pointless at best. GitHub Actions sets CI=true.
#
# Locally, source sh-keyring and let set_key resolve the value, trying sources
# in order: environment -> macOS Keychain -> 1Password -> AWS Secrets Manager,
# caching any remote hit back into the Keychain for the next run. set_key both
# resolves and exports the variable, so the prefix runs in the same shell as the
# test command below.
#
# Recipes that resolve the key must run under bash (set_key is a bash library;
# the default /bin/sh lacks `source`, `local`, and `printf -v`).
SHELL := bash

ifdef CI
KEYRING_PREFIX :=
else
KEYRING_SHLIB := $(shell git rev-parse --show-toplevel)/vendor/sh-keyring/sh-keyring.shlib
KEYRING_PREFIX := source "$(KEYRING_SHLIB)" && set_key ANTHROPIC_API_KEY &&
endif
