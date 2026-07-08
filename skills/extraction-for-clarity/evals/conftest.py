"""Pytest config for extraction-for-clarity skill Claude evals.

The `--live-eval-max-trials` / `--live-eval-target-rate` options and the
`live_eval` marker are registered by the installed `binom-eval` pytest plugin.
This file only wires the session-scoped `eval_runs` fixture for this skill.

Run the full eval set with:

    pytest skills/extraction-for-clarity/evals -m live_eval

Each assertion is graded by a Beta-binomial posterior over its true pass
rate; see `skills/README.md` and binom-eval's own docs for the grading
model and the adaptive trial loop.
"""

from __future__ import annotations

from pathlib import Path

from binom_eval import bind_eval_runs_fixture

from ._assertions import ASSERTION_HANDLERS

EVAL_DIR = Path(__file__).resolve().parent
SKILL_NAME = EVAL_DIR.parent.name

EVAL_LANG_DIR = EVAL_DIR / "typescript"

eval_runs = bind_eval_runs_fixture(
    EVAL_LANG_DIR,
    SKILL_NAME,
    ASSERTION_HANDLERS,
    repo_root=EVAL_DIR.parents[2],
)
