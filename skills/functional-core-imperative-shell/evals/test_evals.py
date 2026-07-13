"""End-to-end Claude evals for the functional-core-imperative-shell skill.

For each entry in ``evals.json`` this module:

  1. Runs ``claude -p <prompt>`` up to ``--live-eval-max-trials`` times
     (default 21) in adaptive concurrent batches via the ``eval_runs``
     fixture in ``conftest.py``.
  2. Detects whether the FCIS skill was invoked by scanning the
     ``stream-json`` events for a ``Skill`` tool_use targeting our skill.
  3. Captures the full assistant text (the proposed refactor) and applies
     grep-style assertions for refactor quality.

Because the model is non-deterministic, each assertion is graded by a
Beta-binomial posterior over its true pass rate: the assertion passes when
the posterior puts most of its mass at or above ``--live-eval-target-rate``
(default 3/5) rather than on a single draw.

Three of the four evals reference ``samples/order_processor.ts`` — a clear
FCIS candidate where business decisions are entangled with database and
email I/O. The fourth references ``samples/pipeline_coordinator.ts``, a
saga where the I/O sequence *is* the logic. That one should NOT trigger
the skill (it is the canonical "When NOT to use" case from the SKILL.md),
and the test asserts both that the skill stayed quiet and that Claude
delivered the requested retry/backoff change without inventing a fake
pure core.

These tests carry the ``live_eval`` marker because each model call costs
time and money; select them with ``-m live_eval`` (see conftest.py) or via
``make eval-functional-core-imperative-shell``. The unit targets exclude them
with ``-m "not live_eval"``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from binom_eval import load_evals

from ._assertions import ASSERTION_HANDLERS
from eval_utils import run_eval_test

EVAL_DIR = Path(__file__).resolve().parent

_EVALS = load_evals(EVAL_DIR / "typescript/evals.json", ASSERTION_HANDLERS)
_EVALS_BY_ID = {ev["id"]: ev for ev in _EVALS}


@pytest.mark.live_eval
@pytest.mark.parametrize("eval_id", [ev["id"] for ev in _EVALS])
def test_eval(eval_id: str, eval_runs, live_eval_target_rate: float) -> None:
    run_eval_test(eval_id, eval_runs, _EVALS_BY_ID, ASSERTION_HANDLERS, live_eval_target_rate)
