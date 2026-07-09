"""Shared before/after refactor helpers for per-skill eval assertion modules.

binom-eval v1.5+ defines the canonical sentinel markers and
``before_after_snippets``; this module wires them to ``EvalRun`` grading
so each skill's ``_assertions.py`` stays focused on domain checks.
"""

from __future__ import annotations

from binom_eval import (
    AssertionFailure,
    EvalRun,
    before_after_snippets,
    code_blocks,
)

MISSING_BEFORE_MSG = (
    "no `// <<<BEGIN BEFORE>>> //`-delimited region found in the model output"
)
MISSING_AFTER_MSG = (
    "no `// <<<BEGIN AFTER>>> //`-delimited region found in the model output"
)


def _strip_fences(snippet: str | None) -> str | None:
    """Reduce a region to its fenced TypeScript body when it wraps one.

    When the model places the marker lines *outside* the ```typescript
    fences, the extracted region still contains the fence lines; collapse
    it to the block bodies so downstream assertions see only code. A region
    that carries no fence (markers were inside the block) is returned as-is.
    """
    if snippet is None:
        return None
    blocks = code_blocks(snippet)
    return "\n".join(blocks) if blocks else snippet


def extract_before_after(text: str) -> tuple[str | None, str | None]:
    """Return the bracketed BEFORE and AFTER snippets from model output.

    Runs binom-eval's delimiter extractor on the raw reply so the marker
    lines are honored whether the model placed them inside the
    ```typescript fences or wrapped a fenced block with them; any residual
    fence is then stripped so downstream assertions see only code.
    """
    before, after = before_after_snippets(text)
    return _strip_fences(before), _strip_fences(after)


def reply_sections(run: EvalRun) -> tuple[tuple[str, str], ...]:
    """Label the run's full reply for ``AssertionFailure`` ``sections``."""
    return (("Assistant reply", run.assistant_text or "(empty)"),)


def require_before_after(run: EvalRun) -> tuple[str, str]:
    """The response's BEFORE and AFTER snippets, or a structured failure."""
    before, after = extract_before_after(run.assistant_text)
    if not before:
        raise AssertionFailure(MISSING_BEFORE_MSG, sections=reply_sections(run))
    if not after:
        raise AssertionFailure(MISSING_AFTER_MSG, sections=reply_sections(run))
    return before, after


def after_snippet(text: str) -> str | None:
    """Refactored code between the ``// <<<BEGIN AFTER>>> //`` sentinels."""
    return extract_before_after(text)[1]


def before_snippet(text: str) -> str | None:
    """Original code between the ``// <<<BEGIN BEFORE>>> //`` sentinels."""
    return extract_before_after(text)[0]
