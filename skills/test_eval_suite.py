"""Unit tests for eval-suite wiring (binom-eval expansion, shared graders)."""

from __future__ import annotations

from pathlib import Path

import pytest
from binom_eval import (
    AssertionFailure,
    BEGIN_AFTER_MARKER,
    BEGIN_BEFORE_MARKER,
    END_AFTER_MARKER,
    END_BEFORE_MARKER,
    BEFORE_AFTER_PROMPT_INSTRUCTION,
    EvalRun,
    expand_evals,
)

from eval_assertion_utils import extract_before_after, require_before_after

SKILLS_DIR = Path(__file__).resolve().parent


def _bracketed(before: str, after: str) -> str:
    return (
        "```typescript\n"
        f"{BEGIN_BEFORE_MARKER}\n{before}\n{END_BEFORE_MARKER}\n"
        f"{BEGIN_AFTER_MARKER}\n{after}\n{END_AFTER_MARKER}\n"
        "```\n"
    )


class TestExpandEvals:
    def test_trigger_eval_gets_skill_constraint_and_markers(self) -> None:
        evals = expand_evals(
            SKILLS_DIR / "extraction-for-clarity/evals/typescript/evals.json"
        )
        prompt = evals[0]["prompt"]
        assert "Use only the `extraction-for-clarity` skill." in prompt
        assert BEFORE_AFTER_PROMPT_INSTRUCTION in prompt
        assert "quoteShipping" in prompt

    def test_non_trigger_eval_gets_markers_without_skill_constraint(self) -> None:
        evals = expand_evals(
            SKILLS_DIR / "extraction-for-clarity/evals/typescript/evals.json"
        )
        prompt = next(e["prompt"] for e in evals if e["id"] == "plain-fix-no-extraction")
        assert BEFORE_AFTER_PROMPT_INSTRUCTION in prompt
        assert "Use only the" not in prompt


class TestEvalAssertionUtils:
    def test_require_before_after_returns_snippets(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=False,
            assistant_text=_bracketed("function f() {}", "function g() {}"),
        )
        before, after = require_before_after(run)
        assert "function f" in before
        assert "function g" in after

    def test_require_before_after_fails_without_markers(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=False,
            assistant_text="```typescript\nfunction g() {}\n```\n",
        )
        with pytest.raises(AssertionFailure, match="BEGIN BEFORE"):
            require_before_after(run)

    def test_extract_before_after_is_none_without_markers(self) -> None:
        text = "```typescript\nfunction g() {}\n```\n"
        assert extract_before_after(text) == (None, None)

    def test_extract_before_after_markers_outside_fences(self) -> None:
        # Regression: a reply that puts the marker lines *outside* the
        # ```typescript fences (obeying "each in its own code block")
        # must still parse to clean code, not (None, None).
        fence = "```"
        text = (
            f"{BEGIN_BEFORE_MARKER}\n"
            f"{fence}typescript\nfunction f() {{}}\n{fence}\n"
            f"{END_BEFORE_MARKER}\n"
            f"{BEGIN_AFTER_MARKER}\n"
            f"{fence}typescript\nfunction g() {{}}\n{fence}\n"
            f"{END_AFTER_MARKER}\n"
        )
        before, after = extract_before_after(text)
        assert before == "function f() {}"
        assert after == "function g() {}"
