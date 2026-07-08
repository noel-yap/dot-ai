# AGENT.md

Guidance for AI agents working in this repository.

## Layout

- `skills/` — Claude Code refactoring skills, one directory per skill:
  - `dependency-injection/`
  - `extraction-for-clarity/`
  - `functional-core-imperative-shell/`

  Each skill directory holds a `SKILL.md` (the skill itself), `evals/`
  (live Beta-binomial evals graded by structural assertions), and
  `tests/` (deterministic structural tests of the SKILL.md). Shared
  assertion/test helpers live in `skills/test_utils.py` and
  `skills/eval_assertion_utils.py` (the latter wraps binom-eval's
  before/after snippet extraction); the eval harness comes from the
  pinned `binom-eval` package. See
  `skills/README.md` for how to stand up a new skill's eval suite.
- `commands/` — Claude Code slash commands (`/commit`, `/release`,
  `/unit-test`).
- `vendor/sh-keyring/` — git submodule providing keyring shell helpers
  used by the skills Makefile.

## Commands

Run from the repo root (forwards to `skills/Makefile`) or from `skills/`:

```sh
make test-unit             # fast deterministic tests, no API calls
make eval                  # all skills' live evals (spawns `claude -p`)
make eval-<skill-name>     # one skill's live evals
make test                  # unit tests then live evals
```

Live evals cost API calls; prefer `make test-unit` while iterating.
