"""End-to-end Claude evals for the extraction-for-clarity skill.

For each entry in ``evals.json`` this module runs live agent trials via
the ``eval_runs`` fixture in ``conftest.py`` and grades the responses
with the structural assertions in ``_assertions.py`` — new named
helpers, intention-revealing names, reduced nesting, named constants,
and preserved behavior tokens.

Three of the four evals reference samples exhibiting the
extraction-for-clarity smells (comment-labeled sections, an if/else
staircase with magic numbers, a boolean/ternary tangle). The fourth
references ``samples/stats.ts``, already-clear code whose prompt asks
for a plain bug fix: the skill should NOT fire, and the fix should
arrive without uninvited decomposition — the canonical "When NOT to
use" case.

The test functions come from binom-eval's ``register_live_eval_tests``:
``test_eval_assertion`` (one node per eval/assertion pair),
``test_eval_expectation`` (per-eval rollup), and
``test_should_trigger_evals_invoked_skill`` (the trigger rollup).

These tests carry the ``live_eval`` marker because each model call costs
time and money; select them with ``-m live_eval`` (see conftest.py) or via
``make eval-extraction-for-clarity``. The unit targets exclude them with
``-m "not live_eval"``.
"""

from __future__ import annotations

from pathlib import Path

from binom_eval import register_live_eval_tests

from ._assertions import ASSERTION_HANDLERS

EVAL_DIR = Path(__file__).resolve().parent
SKILL_NAME = EVAL_DIR.parent.name

register_live_eval_tests(
    globals(),
    evals_path=EVAL_DIR / "evals.json",
    handlers=ASSERTION_HANDLERS,
    subject_name=SKILL_NAME,
)
