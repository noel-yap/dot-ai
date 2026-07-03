"""FCIS refactor-quality assertion functions and their supporting helpers."""

from __future__ import annotations

import itertools
import re

from binom_eval import (
    AssertionFailure,
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

# Marked pure-core region per the SKILL convention: '// pure core ...' up to
# '// end pure core', or to the end of the block when the close marker is
# omitted. Complete-file responses carry the shell in the same code block, so
# only the marked region -- not the whole block -- may be held to purity.
PURE_CORE_REGION_RE = re.compile(
    r"//\s*pure\s+core[^\n]*\n(.*?)(?://\s*end\s+pure\s+core|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

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


def _strip_comments(code: str) -> str:
    """Drop // line comments and /* */ block comments before token scans.

    Prose in comments legitimately mentions I/O collaborators ("the
    decisions no longer touch db or emailService"), so only code may
    trip the leak tokens.
    """
    return _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", code))


def _candidate_pure_blocks(text: str) -> list[str]:
    """Extract the pure-core candidate regions from the code blocks.

    Blocks carrying a '// pure core' marker contribute only their marked
    regions (a complete-file block also contains the shell); unmarked
    blocks qualify wholesale when they look like a sync function.
    """
    candidates: list[str] = []
    for block in _code_blocks(text):
        regions = PURE_CORE_REGION_RE.findall(block)
        if regions:
            candidates.extend(regions)
        elif _is_candidate_pure_block(block):
            candidates.append(block)
    return candidates


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
    """Return which PURE_CORE_IO_TOKENS appear in a code block's code."""
    code = _strip_comments(block)
    return list(filter(code.__contains__, PURE_CORE_IO_TOKENS))


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
# Failure-context helpers
# ---------------------------------------------------------------------------


def _reply_sections(run: EvalRun) -> tuple[tuple[str, str], ...]:
    """Label the run's full reply for AssertionFailure ``sections``."""
    return (("Assistant reply", run.assistant_text or "(empty)"),)


def _block_sections(
    label: str, blocks: list[str]
) -> tuple[tuple[str, str], ...]:
    """Label each offending code block for AssertionFailure ``sections``."""
    return tuple((label, block) for block in blocks)


def _leaking_pure_blocks(text: str) -> list[str]:
    """Candidate pure-core blocks containing at least one I/O token."""
    return [b for b in _candidate_pure_blocks(text) if _leaking_tokens(b)]


# ---------------------------------------------------------------------------
# Assertion functions
# ---------------------------------------------------------------------------


def assert_introduces_pure_function(run: EvalRun) -> None:
    """Fail if the refactor adds no new named or arrow function."""
    if not _new_function_names(run.assistant_text):
        raise AssertionFailure(
            "expected refactor to introduce at least one new named function "
            "alongside processOrder; saw none",
            sections=_reply_sections(run),
        )


def assert_pure_core_no_io(run: EvalRun) -> None:
    """Fail if no pure-core block is found, or if one leaks I/O tokens."""
    if not _candidate_pure_blocks(run.assistant_text):
        raise AssertionFailure(
            "no candidate pure-core block found in the model output",
            sections=_reply_sections(run),
        )
    leaks = _io_leaks_in_pure_blocks(run.assistant_text)
    if leaks:
        raise AssertionFailure(
            "pure-core block(s) leak I/O tokens: "
            + ", ".join(f"{tok!r} in '{snippet}'" for tok, snippet in leaks),
            sections=_block_sections(
                "Leaking pure-core block",
                _leaking_pure_blocks(run.assistant_text),
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
    """Fail if the alert decision is not expressed as kind-tagged data."""
    if not _has_kind_discriminator(run.assistant_text):
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
    if "// pure core" in text_lc:
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
