"""Shared helpers for per-skill ``evals/test_evals.py`` suites.

Every skill under ``skills/<name>/evals/test_evals.py`` runs the same
``test_eval`` body: check failing assertions, then optionally verify the
skill was triggered. The shared logic lives here so adding a new skill
only requires wiring up ``_EVALS_BY_ID`` and ``ASSERTION_HANDLERS``.

Import pattern (after the skills root is on sys.path via _assertions.py):

    from eval_utils import run_eval_test
"""

from __future__ import annotations

from binom_eval import (
    failing_assertions,
    trial_outcomes,
    trial_outcomes_failure_message,
    trial_outcomes_passed,
)


def _check_skill_invoked(run: object) -> None:
    assert run.skill_invoked, "skill was not invoked"  # type: ignore[union-attr]


def run_eval_test(
    eval_id: str,
    eval_runs: object,
    evals_by_id: dict,
    assertion_handlers: dict,
    live_eval_target_rate: float,
) -> None:
    """Run a single eval entry: assert quality checks, then assert trigger."""
    ev = evals_by_id[eval_id]
    runs = eval_runs[eval_id]  # type: ignore[index]
    failures = failing_assertions(
        runs, ev.get("assertions", []), assertion_handlers, live_eval_target_rate
    )
    assert not failures, (
        f"{eval_id}: "
        + ", ".join(f"{a_id} {p}/{t} P={pg:.3f}" for a_id, p, t, pg in failures)
    )
    if ev.get("should_trigger"):
        outcomes = trial_outcomes(runs, _check_skill_invoked)
        assert trial_outcomes_passed(outcomes, live_eval_target_rate), (
            trial_outcomes_failure_message(outcomes, live_eval_target_rate, f"{eval_id}::trigger")
        )
