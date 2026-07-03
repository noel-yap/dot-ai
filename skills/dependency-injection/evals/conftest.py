"""Pytest config for dependency-injection skill Claude evals.

The `--live-eval-max-trials` / `--live-eval-target-rate` options and the
`live_eval` marker are registered by the installed `binom-eval` pytest plugin.
This file only wires the session-scoped `eval_runs` fixture for this skill.

Run the full eval set with:

    pytest skills/dependency-injection/evals -m live_eval

Each assertion is graded by a Beta-binomial posterior over its true pass
rate: it passes once the posterior puts most of its mass at or above
`--live-eval-target-rate` (default 3/5). To save cost the runs are adaptive:
trials run in concurrent batches and re-grade after each, stopping as soon
as the posterior locks PASS or FAIL — capping cost at `--live-eval-max-trials`
runs (default 21) while usually spending far fewer. To demand a higher true
rate over a smaller budget:

    pytest skills/dependency-injection/evals -m live_eval \
        --live-eval-target-rate 0.8 --live-eval-max-trials 12

Evals are non-deterministic by design and are never cached: every trial is
a fresh live `claude -p` call so the suite measures run-to-run variance.
Deterministic checks belong in the per-skill unit suites, not here.

Multiple skills' eval dirs can be collected in one pytest session: each
`evals` dir is a namespace package (no `__init__.py`) and its sibling
modules are imported relatively (`from ._assertions import ...`), so
`_assertions` is namespaced per skill rather than colliding in `sys.modules`.
See `skills/pytest.ini` (`consider_namespace_packages`).
"""

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
    repo_root=EVAL_DIR.parents[2],
)
