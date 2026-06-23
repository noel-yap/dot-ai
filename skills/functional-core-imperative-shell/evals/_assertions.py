"""FCIS refactor-quality assertion functions and their supporting helpers."""

from __future__ import annotations

import itertools
import re

from binom_eval import (
    EvalRun,
    ARROW_FN_RE,
    NAMED_FN_RE,
    code_blocks as _code_blocks,
    first_line as _first_line,
    missing_from as _missing_from,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PURE_CORE_IO_TOKENS = (
    "await ",
    "db.",
    "fetch(",
    "Date.now(",
    "Math.random(",
    "process.env",
    "console.",
    "emailService.",
)

ASYNC_FN_RE = re.compile(r"\basync\s+(?:function|\()")

_SHELL_FN_NAMES = frozenset({"processOrder"})
_REQUIRED_SHELL_IO_CALLS = (
    "db.getOrder",
    "emailService.send",
    "db.updateStatus",
)
_REQUIRED_TIER_NAMES = ("platinum", "gold", "itemcount")
_REQUIRED_DISCOUNT_PCTS = ("15", "10", "5")
_KIND_UNION_RE = re.compile(r"\bkind\s*:\s*['\"][\w-]+['\"]")
_KIND_TYPE_RE = re.compile(r"\btype\s+\w+\s*=[^;]*kind\s*:", re.DOTALL)
_SUSPICIOUS_SAGA_FN_RE = re.compile(r"function\s+(decide\w+|plan\w*Saga)\b")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _is_candidate_pure_block(block: str) -> bool:
    """Return True if the block looks like a pure-core function.

    A block qualifies if it is a sync named/arrow function, or is
    explicitly marked with '// pure core'.
    """
    return any(
        [
            "// pure core" in block.lower(),
            all(
                [
                    not ASYNC_FN_RE.search(block),
                    any(r.search(block) for r in (NAMED_FN_RE, ARROW_FN_RE)),
                ]
            ),
        ]
    )


def _candidate_pure_blocks(text: str) -> list[str]:
    """Filter code blocks down to the pure-core candidates."""
    return list(filter(_is_candidate_pure_block, _code_blocks(text)))


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _new_function_names(text: str) -> set[str]:
    """Collect function identifiers introduced by the refactor.

    Includes named and arrow functions, excluding known shell functions.
    """
    named = {
        m.group(1)
        for block in _code_blocks(text)
        for m in NAMED_FN_RE.finditer(block)
    } - _SHELL_FN_NAMES
    arrow = {
        m.group(1)
        for block in _code_blocks(text)
        for m in ARROW_FN_RE.finditer(block)
    }
    return named | arrow


def _leaking_tokens(block: str) -> list[str]:
    """Return which PURE_CORE_IO_TOKENS appear in a code block."""
    return list(filter(block.__contains__, PURE_CORE_IO_TOKENS))


def _io_leaks_in_pure_blocks(text: str) -> list[tuple[str, str]]:
    """Collect (token, first-line snippet) pairs for leaking I/O tokens.

    Covers every I/O token found inside a candidate pure-core block.
    """
    return list(
        itertools.chain.from_iterable(
            ((tok, _first_line(block)) for tok in _leaking_tokens(block))
            for block in _candidate_pure_blocks(text)
        )
    )


def _missing_io_calls(text: str) -> list[str]:
    """Return required shell I/O calls not present in text."""
    return _missing_from(_REQUIRED_SHELL_IO_CALLS, text)


def _missing_discount_elements(text: str) -> list[str]:
    """Return tier names and discount percentages missing from the output."""
    return _missing_from(_REQUIRED_TIER_NAMES, text.lower()) + _missing_from(
        _REQUIRED_DISCOUNT_PCTS, text
    )


def _block_has_kind_discriminator(block: str) -> bool:
    """Return True if the block uses a 'kind' field.

    The 'kind' field is the FCIS idiom for returning a decision as data.
    """
    return any(r.search(block) for r in (_KIND_UNION_RE, _KIND_TYPE_RE))


def _has_kind_discriminator(text: str) -> bool:
    """Return True if any code block in text contains a kind discriminator."""
    return any(map(_block_has_kind_discriminator, _code_blocks(text)))


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
# Assertion functions
# ---------------------------------------------------------------------------


def assert_introduces_pure_function(run: EvalRun) -> None:
    """Fail if the refactor adds no new named or arrow function."""
    assert _new_function_names(run.assistant_text), (
        "expected refactor to introduce at least one new named function "
        "alongside processOrder; saw none"
    )


def assert_pure_core_no_io(run: EvalRun) -> None:
    """Fail if no pure-core block is found, or if one leaks I/O tokens."""
    assert _candidate_pure_blocks(run.assistant_text), (
        "no candidate pure-core block found in claude output"
    )
    leaks = _io_leaks_in_pure_blocks(run.assistant_text)
    assert not leaks, "pure-core block(s) leak I/O tokens: " + ", ".join(
        f"{tok!r} in '{snippet}'" for tok, snippet in leaks
    )


def assert_shell_preserves_io(run: EvalRun) -> None:
    """Fail if the imperative shell drops any of the required I/O calls."""
    missing = _missing_io_calls(run.assistant_text)
    assert not missing, f"shell missing I/O calls: {missing}"


def assert_preserves_discount_rules(run: EvalRun) -> None:
    """Fail if discount tiers or percentages are missing from the refactor."""
    missing = _missing_discount_elements(run.assistant_text)
    assert not missing, f"discount rules missing from refactor: {missing}"


def assert_alert_decision_extracted(run: EvalRun) -> None:
    """Fail if the alert decision is not expressed as kind-tagged data."""
    assert _has_kind_discriminator(run.assistant_text), (
        "expected alert decision expressed as data (e.g. discriminated union "
        "with a 'kind' field) returned by a pure function"
    )


def assert_adds_retry_loop(run: EvalRun) -> None:
    """Fail if no retry loop or backoff construct is present in the output."""
    patterns = (
        r"for\s*\(\s*(?:let|const)\s+\w*attempt",
        r"while\s*\([^)]*(?:attempt|retries|retry)",
        r"\bbackoff\b",
        r"\bretry\b",
    )
    assert any(
        re.search(p, run.assistant_text, re.IGNORECASE) for p in patterns
    ), "no retry loop, retry helper, or backoff logic introduced"


def assert_preserves_compensation(run: EvalRun) -> None:
    """Fail if saga compensation calls (refund/release) are dropped."""
    text = run.assistant_text
    assert "paymentApi.refund" in text, (
        "compensation lost: paymentApi.refund missing"
    )
    assert "fulfillmentApi.release" in text, (
        "compensation lost: fulfillmentApi.release missing"
    )


def assert_no_pure_core_extraction(run: EvalRun) -> None:
    """Fail if FCIS framing or a pure-decision function appears."""
    text_lc = run.assistant_text.lower()
    assert "// pure core" not in text_lc, (
        "saga refactor introduced a '// pure core' marker; "
        "FCIS shouldn't apply here"
    )
    assert "functional core" not in text_lc, (
        "saga refactor uses 'functional core' framing; "
        "FCIS shouldn't apply here"
    )
    matches = _suspicious_saga_fn_names(run.assistant_text)
    assert not matches, (
        f"saga shouldn't grow a pure-core decision function, found: {matches}"
    )


def assert_skill_not_invoked(run: EvalRun) -> None:
    """Fail if the FCIS skill was invoked when it should have stayed silent."""
    assert not run.skill_invoked, (
        "FCIS skill was invoked on the saga prompt; "
        "this is the When-NOT-to-use case"
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
