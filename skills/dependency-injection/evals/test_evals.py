"""End-to-end Claude evals for the dependency-injection skill.

For each entry in ``evals.json`` this module:

  1. Runs ``claude -p <prompt>`` up to ``--live-eval-max-trials`` times
     (default 21) in adaptive concurrent batches via the ``eval_runs``
     fixture in ``conftest.py``.
  2. Detects whether the DI skill was invoked by scanning the
     ``stream-json`` events for a ``Skill`` tool_use targeting our skill.
  3. Captures the full assistant text (the proposed refactor) and applies
     grep-style assertions for refactor quality.

Because the model is non-deterministic, each assertion is graded by a
Beta-binomial posterior over its true pass rate: the assertion passes when
the posterior puts most of its mass at or above ``--live-eval-target-rate``
(default 3/5) rather than on a single draw.

Three of the four evals reference samples that exhibit the DI smell —
hardcoded module imports, hidden globals (Date.now / Math.random /
process.env), or a singleton couple. The fourth references
``samples/pure_calculator.ts``, a pure function with no I/O at all. That
one should NOT trigger the skill (it is the canonical "When NOT to use"
case from the SKILL.md), and the test asserts both that the skill stayed
quiet and that Claude added tests without inventing DI ceremony.

These tests carry the ``live_eval`` marker because each model call costs
time and money; select them with ``-m live_eval`` (see conftest.py) or via
``make eval-dependency-injection``. The unit targets exclude them with
``-m "not live_eval"``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from binom_eval import assert_eval_passed, load_evals, trial_outcomes

from ._assertions import ASSERTION_HANDLERS

EVAL_DIR = Path(__file__).resolve().parent

_EVALS = load_evals(EVAL_DIR / "evals.json", ASSERTION_HANDLERS)
_EVALS_BY_ID = {ev["id"]: ev for ev in _EVALS}


def _check_skill_invoked(run: object) -> None:
    assert run.skill_invoked, "skill was not invoked"


@pytest.mark.live_eval
@pytest.mark.parametrize("eval_id", [ev["id"] for ev in _EVALS])
def test_eval(eval_id: str, eval_runs, live_eval_target_rate: float) -> None:
    ev = _EVALS_BY_ID[eval_id]
    runs = eval_runs[eval_id]
    for assertion in ev.get("assertions", []):
        handler = ASSERTION_HANDLERS[assertion["id"]]
        outcomes = trial_outcomes(runs, handler)
        assert_eval_passed(outcomes, live_eval_target_rate, f"{eval_id}::{assertion['id']}")
    if ev.get("should_trigger"):
        outcomes = trial_outcomes(runs, _check_skill_invoked)
        assert_eval_passed(outcomes, live_eval_target_rate, f"{eval_id}::trigger")
