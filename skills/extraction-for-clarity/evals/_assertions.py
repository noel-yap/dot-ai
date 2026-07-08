"""Extraction-for-clarity refactor-quality assertions and their helpers.

Every check grades a structural *property* of the refactor — new named
helpers appear, names carry intent, nesting shrinks, literals become
named constants, behavior tokens survive — rather than any phrase from
the SKILL.md, so the skill text cannot be tuned to pass these graders.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from binom_eval import ARROW_FN_RE, AssertionFailure, EvalRun, NAMED_FN_RE

# Add `skills/` to sys.path so shared modules are importable regardless of
# where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval_assertion_utils import (  # noqa: E402
    reply_sections,
    require_before_after,
)
from test_utils import (  # noqa: E402
    UPPER_CONST_RE,
    VAGUE_NAME_RE,
    max_brace_depth,
    strip_code,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Multi-word camelCase: at least one lower-to-upper transition.
CAMEL_HUMP_RE = re.compile(r"[a-z][A-Z]")

# Boolean predicate naming convention.
PREDICATE_NAME_RE = re.compile(r"^(?:is|has|can|should|needs)[A-Z0-9]")

# Distinctive literals from the shipping fixture's rate table. A faithful
# clarity refactor keeps every value (usually as a named constant); losing
# most of them means the rules changed.
SHIPPING_RATE_LITERALS = (
    "167",
    "4.1",
    "12.5",
    "1.18",
    "27.5",
    "1.35",
    "0.75",
    "0.92",
)
SHIPPING_MIN_LITERALS_PRESENT = 4
SHIPPING_ZONE_NAMES = ("remote", "island")

# Policy inputs from the permissions fixture; all must still participate.
PERMISSION_RULE_TOKENS = (
    "suspended",
    "archived",
    "locked",
    "allowTeamEdits",
    "draft",
)

# Negative case: the guard the prompt asks for, and the functions that
# must survive untouched.
LENGTH_GUARD_RE = re.compile(
    r"\.length\s*(?:===?\s*0|<\s*1)|!\s*\w+\.length"
)
STATS_FN_NAMES = frozenset({"mean", "median"})
MAX_INCIDENTAL_HELPERS = 1


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _declared_fn_names(code: str) -> set[str]:
    """Names of functions declared in ``code`` (named + const arrow)."""
    stripped = strip_code(code)
    return set(NAMED_FN_RE.findall(stripped)) | set(ARROW_FN_RE.findall(stripped))


def _new_helper_names(run: EvalRun) -> set[str]:
    """Function names declared in AFTER but not in BEFORE."""
    before, after = require_before_after(run)
    return _declared_fn_names(after) - _declared_fn_names(before)


def _after_text(run: EvalRun) -> str:
    """AFTER snippet code, for token-presence checks."""
    return require_before_after(run)[1]


# ---------------------------------------------------------------------------
# Assertion functions
# ---------------------------------------------------------------------------


def assert_extracts_named_helpers(run: EvalRun) -> None:
    """Fail unless the refactor declares >= 2 functions BEFORE lacked."""
    new_names = _new_helper_names(run)
    if len(new_names) < 2:
        raise AssertionFailure(
            "expected the refactor to extract at least two named helper "
            f"functions; found {sorted(new_names) or 'none'}",
            sections=reply_sections(run),
        )


def assert_helper_names_are_descriptive(run: EvalRun) -> None:
    """Fail when extracted names are vague or not intention-revealing."""
    new_names = _new_helper_names(run)
    if not new_names:
        raise AssertionFailure(
            "no newly extracted helper functions to evaluate names for",
            sections=reply_sections(run),
        )
    vague = sorted(n for n in new_names if VAGUE_NAME_RE.match(n))
    if vague:
        raise AssertionFailure(
            "extracted helper name(s) are vague and state no intent: "
            + ", ".join(vague),
            sections=reply_sections(run),
        )
    multi_word = [n for n in new_names if CAMEL_HUMP_RE.search(n)]
    if len(multi_word) < 2:
        raise AssertionFailure(
            "expected at least two multi-word camelCase helper names "
            f"(e.g. zoneSurcharge); found {sorted(multi_word) or 'none'} "
            f"among {sorted(new_names)}",
            sections=reply_sections(run),
        )


def assert_reduces_nesting(run: EvalRun) -> None:
    """Fail unless AFTER's max brace depth is strictly below BEFORE's."""
    before, after = require_before_after(run)
    before_depth = max_brace_depth(before)
    after_depth = max_brace_depth(after)
    if before_depth == 0:
        raise AssertionFailure(
            "BEFORE block contains no braces to measure nesting against",
            sections=reply_sections(run),
        )
    if after_depth >= before_depth:
        raise AssertionFailure(
            f"expected the refactor to reduce nesting: BEFORE depth "
            f"{before_depth}, AFTER depth {after_depth}",
            sections=(("AFTER block", after),),
        )


def assert_names_magic_numbers(run: EvalRun) -> None:
    """Fail unless AFTER declares >= 3 UPPER_SNAKE named constants."""
    consts = set(UPPER_CONST_RE.findall(strip_code(require_before_after(run)[1])))
    if len(consts) < 3:
        raise AssertionFailure(
            "expected at least three UPPER_SNAKE_CASE named constants for "
            f"the bare literals; found {sorted(consts) or 'none'}",
            sections=reply_sections(run),
        )


def assert_extracts_boolean_predicates(run: EvalRun) -> None:
    """Fail unless >= 1 new helper is a predicate (is/has/can/should)."""
    new_names = _new_helper_names(run)
    predicates = sorted(n for n in new_names if PREDICATE_NAME_RE.match(n))
    if not predicates:
        raise AssertionFailure(
            "expected at least one extracted predicate helper named "
            f"is*/has*/can*/should*; new helpers were {sorted(new_names)}",
            sections=reply_sections(run),
        )


def assert_preserves_shipping_rules(run: EvalRun) -> None:
    """Fail when the rate table or zone names got lost in the refactor."""
    after = _after_text(run)
    missing_zones = [z for z in SHIPPING_ZONE_NAMES if z not in after]
    present_literals = [t for t in SHIPPING_RATE_LITERALS if t in after]
    if missing_zones:
        raise AssertionFailure(
            "refactor lost shipping zone name(s): " + ", ".join(missing_zones),
            sections=reply_sections(run),
        )
    if len(present_literals) < SHIPPING_MIN_LITERALS_PRESENT:
        raise AssertionFailure(
            f"refactor kept only {len(present_literals)} of the "
            f"{len(SHIPPING_RATE_LITERALS)} distinctive rate literals "
            f"(need >= {SHIPPING_MIN_LITERALS_PRESENT}); the rate table "
            "appears altered",
            sections=reply_sections(run),
        )


def assert_preserves_permission_rules(run: EvalRun) -> None:
    """Fail when any policy input no longer participates in AFTER."""
    after = _after_text(run)
    missing = [t for t in PERMISSION_RULE_TOKENS if t not in after]
    if missing:
        raise AssertionFailure(
            "refactor dropped permission rule input(s): " + ", ".join(missing),
            sections=reply_sections(run),
        )


def assert_adds_empty_input_guard(run: EvalRun) -> None:
    """Fail unless AFTER throws RangeError behind a length check."""
    after = _after_text(run)
    if "RangeError" not in after:
        raise AssertionFailure(
            "expected the fix to throw RangeError on empty input; "
            "no RangeError found",
            sections=reply_sections(run),
        )
    if not LENGTH_GUARD_RE.search(strip_code(after)):
        raise AssertionFailure(
            "expected an empty-array length check guarding the throw "
            "(e.g. `values.length === 0`)",
            sections=reply_sections(run),
        )


def assert_no_refactor_ceremony(run: EvalRun) -> None:
    """Fail when a plain fix arrives wrapped in an uninvited refactor."""
    before, after = require_before_after(run)
    after_names = _declared_fn_names(after)
    missing = sorted(STATS_FN_NAMES - after_names)
    if missing:
        raise AssertionFailure(
            "the fix renamed or removed existing function(s): "
            + ", ".join(missing),
            sections=reply_sections(run),
        )
    new_names = after_names - _declared_fn_names(before)
    if len(new_names) > MAX_INCIDENTAL_HELPERS:
        raise AssertionFailure(
            "the fix introduced uninvited decomposition: new function(s) "
            + ", ".join(sorted(new_names))
            + f" (at most {MAX_INCIDENTAL_HELPERS} incidental helper is "
            "acceptable for a guard)",
            sections=reply_sections(run),
        )


def assert_skill_not_invoked(run: EvalRun) -> None:
    """Fail if the skill fired on the When-NOT-to-use case."""
    if run.skill_invoked:
        raise AssertionFailure(
            "extraction-for-clarity skill was invoked on the plain-fix "
            "prompt; this is the When-NOT-to-use case",
            sections=(("Tool uses", str(run.tool_uses)),),
        )


ASSERTION_HANDLERS = {
    "extracts-named-helpers": assert_extracts_named_helpers,
    "helper-names-are-descriptive": assert_helper_names_are_descriptive,
    "reduces-nesting": assert_reduces_nesting,
    "names-magic-numbers": assert_names_magic_numbers,
    "extracts-boolean-predicates": assert_extracts_boolean_predicates,
    "preserves-shipping-rules": assert_preserves_shipping_rules,
    "preserves-permission-rules": assert_preserves_permission_rules,
    "adds-empty-input-guard": assert_adds_empty_input_guard,
    "no-refactor-ceremony": assert_no_refactor_ceremony,
    "skill-not-invoked": assert_skill_not_invoked,
}
