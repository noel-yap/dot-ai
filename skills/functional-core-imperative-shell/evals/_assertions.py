"""FCIS refactor-quality assertion functions and their supporting helpers.

Structural checks -- function extraction, I/O detection, returned-data shape,
discriminated unions -- run on a tree-sitter TypeScript parse via the shared
`ts_ast` module, so a check reflects the code's parse tree rather than surface
text. Presence checks for preserved rules and the saga When-NOT-to-use
guardrails stay as text scans.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from binom_eval import (
    AssertionFailure,
    EvalRun,
    code_blocks as _code_blocks,
    comment_mark_re as _comment_mark_re,
    missing_from as _missing_from,
)

# Add `skills/` to sys.path so shared modules are importable regardless of
# where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import ts_ast  # noqa: E402
from eval_assertion_utils import after_snippet  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# A stray '// pure core' comment is a misapplication signal on the saga
# (When-NOT-to-use) case: a decoration-tolerant '// ... pure core ...' match
# flags a response that wrongly reached for FCIS. Purity of the positive
# refactor is judged structurally (see `ts_ast`), not from this marker.
PURE_CORE_MARK_RE = _comment_mark_re("pure core")

_SHELL_FN_NAMES = frozenset({"processOrder"})
_REQUIRED_SHELL_IO_CALLS = (
    "db.getOrder",
    "emailService.send",
    "db.updateStatus",
)
_REQUIRED_TIER_NAMES = ("platinum", "gold", "itemcount")
_REQUIRED_DISCOUNT_PCTS = ("15", "10", "5")
_SUSPICIOUS_SAGA_FN_RE = re.compile(r"function\s+(decide\w+|plan\w*Saga)\b")

# An alert decision returned as data is an object literal carrying the alert
# payload -- a subject plus a body/message -- regardless of the wrapper
# (nullable struct, optional field, or discriminated union).
_ALERT_PAYLOAD_KEYSETS = ({"subject", "body"}, {"subject", "message"})


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------


def _refactored_code(text: str) -> str:
    """The AFTER snippet if the sentinels delimit one, else all fenced code.

    Refactor-quality checks target the refactored code, so grade the AFTER
    region when present; the fallback keeps marker-less unit inputs working.
    """
    after = after_snippet(text)
    if after is not None:
        return after
    return "\n".join(_code_blocks(text))


# ---------------------------------------------------------------------------
# Structural helpers (tree-sitter)
# ---------------------------------------------------------------------------


def _new_function_names(text: str) -> set[str]:
    """Names of functions the refactor introduces, excluding the shell."""
    names = {fn.name for fn in ts_ast.named_functions(_refactored_code(text))}
    return names - _SHELL_FN_NAMES


def _candidate_pure_functions(text: str) -> list[ts_ast.Function]:
    """Functions that should be pure: named, non-async, non-shell.

    The async shell (and the known ``processOrder`` orchestrator) may perform
    I/O and is excluded; every other introduced function is held to purity.
    """
    return [
        fn
        for fn in ts_ast.named_functions(_refactored_code(text))
        if not fn.is_async and fn.name not in _SHELL_FN_NAMES
    ]


def _io_leaks_in_pure_functions(text: str) -> list[tuple[str, str]]:
    """(token, first-line snippet) pairs for I/O performed in pure functions."""
    return [
        (token, ts_ast.first_line(fn.node))
        for fn in _candidate_pure_functions(text)
        for token in ts_ast.io_tokens(fn.node)
    ]


def _leaking_pure_functions(text: str) -> list[str]:
    """Source of each pure-core function that performs I/O."""
    return [
        ts_ast.node_text(fn.node)
        for fn in _candidate_pure_functions(text)
        if ts_ast.io_tokens(fn.node)
    ]


def _alert_returned_as_data(text: str) -> bool:
    """True if a pure function returns the alert decision as data.

    Accepts any wrapper: a discriminated union tagged with ``kind``, or a pure
    function that builds an alert payload object (a subject with a
    body/message) -- e.g. a nullable struct or an optional field.
    """
    code = _refactored_code(text)
    if ts_ast.has_kind_discriminant(code):
        return True
    return any(
        ts_ast.builds_object_with_keys(fn.node, keys)
        for fn in _candidate_pure_functions(text)
        for keys in _ALERT_PAYLOAD_KEYSETS
    )


# ---------------------------------------------------------------------------
# Text presence helpers
# ---------------------------------------------------------------------------


def _missing_io_calls(text: str) -> list[str]:
    """Return required shell I/O calls not present in text."""
    return _missing_from(_REQUIRED_SHELL_IO_CALLS, text)


def _missing_discount_elements(text: str) -> list[str]:
    """Return tier names and discount percentages missing from the output."""
    return _missing_from(_REQUIRED_TIER_NAMES, text.lower()) + _missing_from(
        _REQUIRED_DISCOUNT_PCTS, text
    )


def _suspicious_saga_fn_names(text: str) -> list[str]:
    """Find function names suggesting FCIS was misapplied to a saga.

    Matches names like decide* or plan*Saga.
    """
    return [
        m.group(0)
        for block in _code_blocks(text)
        for m in _SUSPICIOUS_SAGA_FN_RE.finditer(block)
    ]


# ---------------------------------------------------------------------------
# Failure-context helpers
# ---------------------------------------------------------------------------


def _reply_sections(run: EvalRun) -> tuple[tuple[str, str], ...]:
    """Label the run's full reply for AssertionFailure ``sections``."""
    return (("Assistant reply", run.assistant_text or "(empty)"),)


def _block_sections(
    label: str, blocks: list[str]
) -> tuple[tuple[str, str], ...]:
    """Label each offending code region for AssertionFailure ``sections``."""
    return tuple((label, block) for block in blocks)


# ---------------------------------------------------------------------------
# Assertion functions
# ---------------------------------------------------------------------------


def assert_introduces_pure_function(run: EvalRun) -> None:
    """Fail if the refactor adds no new named function."""
    if not _new_function_names(run.assistant_text):
        raise AssertionFailure(
            "expected refactor to introduce at least one new named function "
            "alongside processOrder; saw none",
            sections=_reply_sections(run),
        )


def assert_pure_core_no_io(run: EvalRun) -> None:
    """Fail if no pure-core function is found, or if one leaks I/O tokens."""
    if not _candidate_pure_functions(run.assistant_text):
        raise AssertionFailure(
            "no candidate pure-core function found in the model output",
            sections=_reply_sections(run),
        )
    leaks = _io_leaks_in_pure_functions(run.assistant_text)
    if leaks:
        raise AssertionFailure(
            "pure-core function(s) leak I/O tokens: "
            + ", ".join(f"{tok!r} in '{snippet}'" for tok, snippet in leaks),
            sections=_block_sections(
                "Leaking pure-core function",
                _leaking_pure_functions(run.assistant_text),
            ),
        )


def assert_shell_preserves_io(run: EvalRun) -> None:
    """Fail if the imperative shell drops any of the required I/O calls."""
    missing = _missing_io_calls(run.assistant_text)
    if missing:
        raise AssertionFailure(
            f"shell missing I/O calls: {missing}",
            sections=_reply_sections(run),
        )


def assert_preserves_discount_rules(run: EvalRun) -> None:
    """Fail if discount tiers or percentages are missing from the refactor."""
    missing = _missing_discount_elements(run.assistant_text)
    if missing:
        raise AssertionFailure(
            f"discount rules missing from refactor: {missing}",
            sections=_reply_sections(run),
        )


def assert_alert_decision_extracted(run: EvalRun) -> None:
    """Fail if the alert decision is not returned as data by a pure function."""
    if not _alert_returned_as_data(run.assistant_text):
        raise AssertionFailure(
            "expected alert decision expressed as data (e.g. discriminated "
            "union with a 'kind' field) returned by a pure function",
            sections=_reply_sections(run),
        )


def assert_adds_retry_loop(run: EvalRun) -> None:
    """Fail if no retry loop or backoff construct is present in the output."""
    patterns = (
        r"for\s*\(\s*(?:let|const)\s+\w*attempt",
        r"while\s*\([^)]*(?:attempt|retries|retry)",
        r"\bbackoff\b",
        r"\bretry\b",
    )
    if not any(
        re.search(p, run.assistant_text, re.IGNORECASE) for p in patterns
    ):
        raise AssertionFailure(
            "no retry loop, retry helper, or backoff logic introduced",
            sections=_reply_sections(run),
        )


def assert_preserves_compensation(run: EvalRun) -> None:
    """Fail if saga compensation calls (refund/release) are dropped."""
    text = run.assistant_text
    if "paymentApi.refund" not in text:
        raise AssertionFailure(
            "compensation lost: paymentApi.refund missing",
            sections=_reply_sections(run),
        )
    if "fulfillmentApi.release" not in text:
        raise AssertionFailure(
            "compensation lost: fulfillmentApi.release missing",
            sections=_reply_sections(run),
        )


def assert_no_pure_core_extraction(run: EvalRun) -> None:
    """Fail if FCIS framing or a pure-decision function appears."""
    text_lc = run.assistant_text.lower()
    if PURE_CORE_MARK_RE.search(run.assistant_text):
        raise AssertionFailure(
            "saga refactor introduced a '// pure core' marker; "
            "FCIS shouldn't apply here",
            sections=_reply_sections(run),
        )
    if "functional core" in text_lc:
        raise AssertionFailure(
            "saga refactor uses 'functional core' framing; "
            "FCIS shouldn't apply here",
            sections=_reply_sections(run),
        )
    matches = _suspicious_saga_fn_names(run.assistant_text)
    if matches:
        raise AssertionFailure(
            "saga shouldn't grow a pure-core decision function, "
            f"found: {matches}",
            sections=_reply_sections(run),
        )


def assert_skill_not_invoked(run: EvalRun) -> None:
    """Fail if the FCIS skill was invoked when it should have stayed silent."""
    if run.skill_invoked:
        raise AssertionFailure(
            "FCIS skill was invoked on the saga prompt; "
            "this is the When-NOT-to-use case",
            sections=(("Tool uses", str(run.tool_uses)),),
        )


ASSERTION_HANDLERS = {
    "refactor-introduces-pure-function": assert_introduces_pure_function,
    "pure-core-has-no-io-tokens": assert_pure_core_no_io,
    "shell-still-performs-io": assert_shell_preserves_io,
    "preserves-discount-rules": assert_preserves_discount_rules,
    "alert-decision-extracted": assert_alert_decision_extracted,
    "adds-retry-loop": assert_adds_retry_loop,
    "preserves-compensation": assert_preserves_compensation,
    "no-pure-core-extraction": assert_no_pure_core_extraction,
    "skill-not-invoked": assert_skill_not_invoked,
}
