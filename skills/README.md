# Skill evals

This directory holds one eval suite per skill, built on the
[**binom-eval**](https://github.com/noel-yap/binom-eval) package — the
skill-independent harness (Beta-binomial grading, the `claude -p` runner, the
stream-json parser, and a pytest plugin). Each skill adds a thin `evals/`
package that binds the harness to its own skill name, sample files, and
assertions.

`binom-eval` is a dependency, pinned in `pyproject.toml` and locked in
`uv.lock`. No install step is needed: every make target runs through
`uv run`, which syncs the project venv from the lockfile on demand — so the
suite is independent of whatever is installed in the invoking shell's
environment. To upgrade the pin: bump the tag in `pyproject.toml`, run
`uv lock`, and commit both files.

This README explains how to stand up an eval suite for a **new skill**.

## What evals are (and aren't)

An eval runs the real `claude -p` CLI against a prompt, captures the
stream-json transcript, and checks the response with grep-style assertions.
The statistics behind the verdict — the Beta-binomial posterior, the target
rate, the adaptive trial loop — are binom-eval's job and are documented in
[its README](https://github.com/noel-yap/binom-eval); here we only cover what
a skill author has to write.

> Deterministic logic (your assertion helpers, regexes, parsing) belongs in
> ordinary unit tests, **not** in evals. Evals are only for "does the model,
> with this skill available, actually do the right thing often enough?"
>
> Evals are **expensive**: each trial is a real `claude -p` invocation that
> costs API tokens (and money) and takes seconds to minutes. They are isolated
> behind the `live_eval` marker (run only via `-m live_eval` / the `make eval`
> targets, never by the unit targets), so keep the eval set small and
> high-signal — anything checkable without the model belongs in the
> deterministic unit tests.

## How the `binom_eval` package fits together

`binom_eval` re-exports everything from its `__init__`, so you always
`from binom_eval import ...` regardless of which submodule a name lives in. The
full list of exported symbols is in binom-eval's
[Public API table](https://github.com/noel-yap/binom-eval#public-api); the
names a skill actually touches appear in the templates below.

The pytest hooks and the `live_eval_target_rate` fixture are registered
automatically by the installed `binom-eval` package (a pytest plugin via its
`pytest11` entry point), so the `--live-eval-max-trials` /
`--live-eval-target-rate` options and the `live_eval` marker are available
across the whole tree with no conftest wiring. **A new skill never touches the
`binom_eval` package** — it only adds files under its own `evals/`.

The one entry points a skill calls directly are **`bind_eval_runs_fixture`**
(in `conftest.py`) and **`register_live_eval_tests`** (in `test_evals.py`).
Together they wire the session-scoped `eval_runs` fixture and register the
standard live-eval pytest nodes — no hand-written test class needed.

## Directory layout for a new skill

```
skills/<skill-name>/
└── evals/
    ├── evals.json        # the eval cases + per-eval assertion ids
    ├── samples/          # input files the prompts point at
    │   └── *.ts
    ├── _assertions.py    # assertion functions + ASSERTION_HANDLERS registry
    ├── conftest.py       # wires the `eval_runs` fixture
    ├── test_evals.py     # the live evals (marked `live_eval`; run via -m live_eval)
    └── test_assertions.py# unit tests for _assertions.py (fast, deterministic)
```

> **Note:** every skill's `evals/` reuses the module name `_assertions`. They
> no longer collide: `skills/pytest.ini` sets `--import-mode=importlib` with
> `consider_namespace_packages = true`, and the sibling imports are relative
> (`from ._assertions import ...`), so pytest names each skill's modules by
> their full path (`<skill>.evals._assertions`) instead of a bare
> `_assertions` key in `sys.modules`. Several skills' eval dirs are therefore
> collected in **one** pytest session, and binom-eval's built-in concurrency
> (`--live-eval-concurrency`) runs their `claude -p` trials in parallel under
> a single shared cap.

## Step by step

### 1. `evals.json` — the cases

The skill identity is derived from the directory name (see `conftest.py`
below), so `evals.json` holds only the cases:

```json
{
  "evals": [
    {
      "id": "descriptive-case-id",
      "should_trigger": true,
      "file": "skills/<skill-name>/evals/samples/example.ts",
      "prompt": "A realistic user request that points at the sample file ...",
      "expected_output": "Prose describing what a good response looks like (human reference; not asserted directly).",
      "assertions": [
        { "id": "some-assertion-id", "description": "What this assertion checks." }
      ]
    }
  ]
}
```

- `should_trigger: true` adds an automatic check that the skill's `Skill`
  tool actually fired. Use `should_trigger: false` for a "When NOT to use"
  case and add a `skill-not-invoked` assertion.
- Each `assertions[].id` must have a handler registered in `_assertions.py`
  (next step) — `load_evals` enforces this when the `eval_runs` fixture is
  built, raising a `KeyError` that names every gap before any trials run.
  `expected_output` is documentation only.
- Put the input files the prompt references under `samples/`.

### 2. `_assertions.py` — the checks

Each handler takes an `EvalRun` (from `binom_eval`) and **raises
`AssertionError`** on failure (its message becomes the per-trial failure
detail). Register every handler in an `ASSERTION_HANDLERS` dict keyed by the
`assertion.id` from `evals.json`. Use `code_blocks`, `first_line`, and
`missing_from` from `binom_eval` for text wrangling.

```python
from __future__ import annotations

from binom_eval import EvalRun, code_blocks, missing_from


def assert_does_the_thing(run: EvalRun) -> None:
    """Fail if the response is missing the required tokens."""
    missing = missing_from(("expectedToken",), run.assistant_text)
    assert not missing, f"response missing: {missing}"


def assert_skill_not_invoked(run: EvalRun) -> None:
    """For a should_trigger:false eval."""
    assert not run.skill_invoked, "skill fired on a When-NOT-to-use case"


ASSERTION_HANDLERS = {
    "some-assertion-id": assert_does_the_thing,
    "skill-not-invoked": assert_skill_not_invoked,
}
```

### 3. `conftest.py` — wire the fixture

Identical for every skill except the imports resolve to this skill's modules.
Sibling modules are imported relatively (`from ._assertions import ...`);
paired with `consider_namespace_packages` in `skills/pytest.ini` this keeps
each skill's `_assertions` namespaced, so several skills' eval dirs can be
collected in one pytest session without colliding.

```python
from __future__ import annotations

from pathlib import Path

from binom_eval import bind_eval_runs_fixture

from ._assertions import ASSERTION_HANDLERS

EVAL_DIR = Path(__file__).resolve().parent
SKILL_NAME = EVAL_DIR.parent.name

eval_runs = bind_eval_runs_fixture(
    EVAL_DIR,
    SKILL_NAME,
    ASSERTION_HANDLERS,
    repo_root=EVAL_DIR.parents[2],   # omit when prompts run in EVAL_DIR only
)
```

`bind_eval_runs_fixture` returns a session-scoped fixture. For each eval it
runs `run_eval_adaptive`, which fires trials in concurrent batches and stops
as soon as the posterior locks PASS or FAIL, yielding
`{eval_id: [EvalRun, ...]}`.

### 4. `test_evals.py` — the live evals

One call registers the standard live-eval pytest nodes (all marked
`live_eval`, so unit targets exclude them via `-m "not live_eval"` and eval
targets select them via `-m live_eval`). The target pass rate comes from the
`live_eval_target_rate` fixture (provided by the `binom-eval` plugin).

```python
from __future__ import annotations

from pathlib import Path

from binom_eval import register_live_eval_tests

from ._assertions import ASSERTION_HANDLERS

EVAL_DIR = Path(__file__).resolve().parent

register_live_eval_tests(
    globals(),
    evals_path=EVAL_DIR / "evals.json",
    handlers=ASSERTION_HANDLERS,
    subject_name=EVAL_DIR.parent.name,
    trigger="skill",               # or "agent" for agent suites
)
```

### 5. Unit tests (fast, no API)

- **`test_assertions.py`** — exercise each assertion handler against
  hand-written `EvalRun(assistant_text=...)` fixtures covering pass and
  fail cases. This is where the *deterministic* coverage lives.

## How grading works

The verdict is a Beta-binomial posterior over each assertion's true pass rate,
graded adaptively against a target rate (default **2/3**) over a trial budget
(default **21**). The model, the verdict band, and the reasoning behind every
default (`TARGET_RATE`, `MAX_TRIALS`, `BATCH_FLOOR`, the band, the prior, the
tiebreak) are documented in binom-eval's
[**Why these defaults**](https://github.com/noel-yap/binom-eval#why-these-defaults)
section. `TARGET_RATE` and `MAX_TRIALS` are overridable per run from the CLI /
Makefile (below); the rest are module constants in `binom_eval.grading`.

## Running

From `skills/` (a `Makefile` wraps the common cases):

```sh
make test                  # everything: unit tests then live evals
make test-unit             # fast unit tests for all skills, no API calls
make eval                  # every skill's live evals, in parallel (target 2/3, <=21 runs)
make eval-<skill-name>     # one skill's live evals
make eval TARGET_RATE=0.8 MAX_TRIALS=12
make eval CONCURRENCY=2    # cap in-flight agent calls (default 5)
make eval SHOW_POSTERIOR=0 # omit per-check posterior lines from output
make eval ISOLATE=0        # run in the live tree (no per-trial copy)
make eval MODEL=claude:haiku   # pick another backend:model
```

Trials run on the backend and model in `MODEL` (default
`cursor:claude-opus-4-8-high`, i.e. `cursor-agent` driving Opus 4.8). The
cursor backend needs the `cursor-agent` CLI on `PATH` and authenticates via
`CURSOR_API_KEY` — live runs execute under a throwaway `HOME`, so an
interactive login is deliberately not used. The eval targets resolve that key
with `set_key` from [sh-keyring](https://github.com/noel-yap/sh-keyring)
(vendored as a git submodule at `vendor/sh-keyring`), which checks the env,
the macOS Keychain, 1Password, and AWS Secrets Manager in that order. Model
ids come from `cursor-agent --list-models`.
The claude backend (`MODEL=claude:<model>`) runs `claude -p` with isolated
settings (`--bare`) and authenticates only via `ANTHROPIC_API_KEY`.

`make eval` runs every skill's trials concurrently under binom-eval's built-in
parallelism: one shared in-process semaphore (`--live-eval-concurrency`,
default 5) bounds total in-flight `claude -p` calls across the whole session.
Lower `CONCURRENCY` to stay under an API rate limit, or set it to `1` to run
fully serially. Per binom-eval's README, do **not** add pytest-xdist (`-n`) on
top: each worker would get its own semaphore (total calls = workers ×
concurrency) and recompute the session-scoped fixture.

Each trial runs against a throwaway copy of the repo root
(`--live-eval-isolate`, on by default — `ISOLATE=0` to opt out). The runner
drives `claude -p --dangerously-skip-permissions` against prompts that ask it
to edit the sample files, so without isolation concurrent trials would clobber
one another and mutate the committed fixtures.

Or call pytest directly. Several skills' eval dirs are collected in one
session and parallelised by the built-in semaphore. The `live_eval` marker is
the unit/eval split:

```sh
# fast unit tests for a skill (excludes the live_eval tests)
python3 -m pytest skills/<skill-name>/evals -m "not live_eval"

# live evals (requires the `claude` CLI on PATH; makes real model calls)
python3 -m pytest skills/<skill-name>/evals -m live_eval

# cheaper budget while iterating
python3 -m pytest skills/<skill-name>/evals -m live_eval \
    --live-eval-max-trials 6
```

With `-m "not live_eval"` the live evals are excluded, so the unit tests
(`test_assertions.py`) run fast and offline.

## Checklist for a new skill

1. `evals/evals.json` with cases + assertion ids (and `samples/`).
2. `_assertions.py` with one handler per assertion id + `ASSERTION_HANDLERS`.
3. `conftest.py` calling `bind_eval_runs_fixture`.
4. `test_evals.py` calling `register_live_eval_tests`.
5. `test_assertions.py` (deterministic unit coverage).
6. `make eval-<skill-name>` passes; `make` (unit) stays green.