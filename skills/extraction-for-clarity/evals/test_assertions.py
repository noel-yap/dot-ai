"""Unit tests for _assertions.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from binom_eval import (
    AssertionFailure,
    BEGIN_AFTER_MARKER,
    BEGIN_BEFORE_MARKER,
    END_AFTER_MARKER,
    END_BEFORE_MARKER,
    EvalRun,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval_assertion_utils import (  # noqa: E402
    before_snippet,
    extract_before_after,
)

from ._assertions import (
    _declared_fn_names,
    _new_helper_names,
    assert_adds_empty_input_guard,
    assert_extracts_boolean_predicates,
    assert_extracts_named_helpers,
    assert_helper_names_are_descriptive,
    assert_names_magic_numbers,
    assert_no_refactor_ceremony,
    assert_preserves_permission_rules,
    assert_preserves_shipping_rules,
    assert_reduces_nesting,
    assert_skill_not_invoked,
)


def _run(text: str, skill_invoked: bool = False) -> EvalRun:
    return EvalRun(
        eval_id="t", prompt="", skill_invoked=skill_invoked, assistant_text=text
    )


def _blocks(before: str, after: str) -> str:
    return (
        "```typescript\n"
        f"{BEGIN_BEFORE_MARKER}\n{before}\n{END_BEFORE_MARKER}\n"
        f"{BEGIN_AFTER_MARKER}\n{after}\n{END_AFTER_MARKER}\n"
        "```\n"
    )


# ---------------------------------------------------------------------------
# Block selection
# ---------------------------------------------------------------------------


class TestBlockSelection:
    def test_before_snippet_found_by_marker(self) -> None:
        text = _blocks("function f() {}", "function f() {}")
        assert before_snippet(text) is not None

    def test_after_snippet_prefer_marker(self) -> None:
        text = _blocks("function f() {}", "function g() {}")
        after = extract_before_after(text)[1]
        assert after is not None
        assert "function g" in after

    def test_after_snippet_requires_marker(self) -> None:
        text = (
            "```typescript\n"
            f"{BEGIN_BEFORE_MARKER}\nfunction f() {{}}\n{END_BEFORE_MARKER}\n"
            "```\n"
            "```typescript\nfunction g() {}\n```\n"
        )
        assert extract_before_after(text)[1] is None


# ---------------------------------------------------------------------------
# Function-name extraction
# ---------------------------------------------------------------------------


class TestDeclaredFnNames:
    def test_named_function(self) -> None:
        assert _declared_fn_names("function zoneRate() {}") == {"zoneRate"}

    def test_const_arrow_function(self) -> None:
        names = _declared_fn_names("const baseFare = (x: number) => x * 2;")
        assert names == {"baseFare"}

    def test_name_in_comment_is_ignored(self) -> None:
        assert _declared_fn_names("// function ghost() {}") == set()

    def test_new_helper_names_subtracts_before(self) -> None:
        run = _run(
            _blocks(
                "function keep() {}",
                "function keep() {}\nfunction added() {}",
            )
        )
        assert _new_helper_names(run) == {"added"}

    def test_new_helper_names_requires_before_block(self) -> None:
        run = _run("```typescript\nfunction g() {}\n```\n")
        with pytest.raises(AssertionFailure, match="BEGIN BEFORE"):
            _new_helper_names(run)


# ---------------------------------------------------------------------------
# Assertion handlers
# ---------------------------------------------------------------------------


BEFORE_TANGLE = """
export function quote(x: number, zone: string): number {
  let total = x * 4.1;
  if (zone === "remote") {
    if (total < 40) {
      total += 12.5;
    } else {
      total = total * 1.18;
    }
  } else if (zone === "island") {
    if (total < 40) {
      total += 27.5;
    } else {
      total = total * 1.35;
    }
  }
  if (x >= 12) {
    total = total * 0.92;
  }
  return total * 167 * 0.75 / 167 / 0.75;
}
"""

AFTER_CLEAN = """
const BASE_RATE_PER_KG = 4.1;
const SMALL_ORDER_THRESHOLD = 40;
const REMOTE_FLAT_SURCHARGE = 12.5;
const REMOTE_MULTIPLIER = 1.18;
const ISLAND_FLAT_SURCHARGE = 27.5;
const ISLAND_MULTIPLIER = 1.35;
const BULK_DISCOUNT_MULTIPLIER = 0.92;
const DIM_WEIGHT_DIVISOR = 167;
const FRAGILE_RATE = 0.75;

function zoneSurcharge(total: number, zone: string): number {
  if (zone === "remote") {
    return total < SMALL_ORDER_THRESHOLD
      ? total + REMOTE_FLAT_SURCHARGE
      : total * REMOTE_MULTIPLIER;
  }
  if (zone === "island") {
    return total < SMALL_ORDER_THRESHOLD
      ? total + ISLAND_FLAT_SURCHARGE
      : total * ISLAND_MULTIPLIER;
  }
  return total;
}

function bulkDiscount(total: number, units: number): number {
  return units >= 12 ? total * BULK_DISCOUNT_MULTIPLIER : total;
}

export function quote(x: number, zone: string): number {
  const base = x * BASE_RATE_PER_KG;
  return bulkDiscount(zoneSurcharge(base, zone), x);
}
"""


# A `name-the-conditional` refactor that names each rule with an explaining
# variable rather than an extracted function -- a first-class clarity move
# the grader must credit the same as function extraction. Mirrors the shape
# of a real model response to the document_permissions fixture.
BEFORE_CONDITIONAL = """
export function canEditDocument(user: User, doc: Doc): boolean {
  return (
    !user.suspended &&
    doc.status !== "archived" &&
    (user.role === "admin"
      ? !doc.locked || doc.ownerId === user.id
      : user.role === "editor"
        ? !doc.locked &&
          (doc.ownerId === user.id ||
            (doc.allowTeamEdits &&
              user.teamIds.includes(doc.teamId) &&
              doc.status === "draft"))
        : false)
  );
}
"""

AFTER_CONDITIONAL_VARS = """
export function canEditDocument(user: User, doc: Doc): boolean {
  const userIsActive = !user.suspended;
  const documentIsEditable = doc.status !== "archived";
  const isOwner = doc.ownerId === user.id;
  const canEditAsTeamMember =
    doc.allowTeamEdits &&
    user.teamIds.includes(doc.teamId) &&
    doc.status === "draft";
  const adminCanEdit = !doc.locked || isOwner;
  const editorCanEdit = !doc.locked && (isOwner || canEditAsTeamMember);
  const roleGrantsEditPermission =
    user.role === "admin"
      ? adminCanEdit
      : user.role === "editor"
        ? editorCanEdit
        : false;
  return userIsActive && documentIsEditable && roleGrantsEditPermission;
}
"""


class TestAssertExtractsNamedHelpers:
    def test_passes_with_two_new_helpers(self) -> None:
        assert_extracts_named_helpers(_run(_blocks(BEFORE_TANGLE, AFTER_CLEAN)))

    def test_passes_with_explaining_variables(self) -> None:
        assert_extracts_named_helpers(
            _run(_blocks(BEFORE_CONDITIONAL, AFTER_CONDITIONAL_VARS))
        )

    def test_fails_with_no_new_helpers(self) -> None:
        text = _blocks("function f() {}", "function f() { return 1; }")
        with pytest.raises(AssertionFailure, match="at least two"):
            assert_extracts_named_helpers(_run(text))


class TestAssertHelperNamesAreDescriptive:
    def test_passes_with_intentful_names(self) -> None:
        assert_helper_names_are_descriptive(
            _run(_blocks(BEFORE_TANGLE, AFTER_CLEAN))
        )

    def test_passes_with_explaining_variable_names(self) -> None:
        assert_helper_names_are_descriptive(
            _run(_blocks(BEFORE_CONDITIONAL, AFTER_CONDITIONAL_VARS))
        )

    def test_fails_on_vague_name(self) -> None:
        text = _blocks(
            "function f() {}",
            "function helper1() {}\nfunction zoneSurcharge() {}\n"
            "function bulkDiscount() {}",
        )
        with pytest.raises(AssertionFailure, match="vague"):
            assert_helper_names_are_descriptive(_run(text))

    def test_fails_on_vague_explaining_variable(self) -> None:
        text = _blocks(
            "function f() {}",
            "const data = a === b;\nconst tmp = c && d;",
        )
        with pytest.raises(AssertionFailure, match="vague"):
            assert_helper_names_are_descriptive(_run(text))

    def test_fails_when_names_are_single_word(self) -> None:
        text = _blocks(
            "function f() {}",
            "function surcharge() {}\nfunction discount() {}",
        )
        with pytest.raises(AssertionFailure, match="multi-word"):
            assert_helper_names_are_descriptive(_run(text))


class TestAssertReducesNesting:
    def test_passes_when_depth_shrinks(self) -> None:
        assert_reduces_nesting(_run(_blocks(BEFORE_TANGLE, AFTER_CLEAN)))

    def test_fails_when_depth_unchanged(self) -> None:
        same = "function f() { if (a) { if (b) { g(); } } }"
        with pytest.raises(AssertionFailure, match="reduce nesting"):
            assert_reduces_nesting(_run(_blocks(same, same)))

    def test_fails_without_before_block(self) -> None:
        with pytest.raises(AssertionFailure, match="BEGIN BEFORE"):
            assert_reduces_nesting(
                _run("```typescript\nfunction g() {}\n```\n")
            )


class TestAssertNamesMagicNumbers:
    def test_passes_with_named_constants(self) -> None:
        assert_names_magic_numbers(_run(_blocks(BEFORE_TANGLE, AFTER_CLEAN)))

    def test_fails_without_constants(self) -> None:
        text = _blocks(
            "function f() {}",
            "function g() { return 4.1 * 167; }",
        )
        with pytest.raises(AssertionFailure, match="named constants"):
            assert_names_magic_numbers(_run(text))


class TestAssertExtractsBooleanPredicates:
    def test_passes_with_predicate_helper(self) -> None:
        text = _blocks(
            "function f() {}",
            "function isOwner(u: U, d: D) { return d.ownerId === u.id; }\n"
            "function canTeamEdit(u: U, d: D) { return d.allowTeamEdits; }",
        )
        assert_extracts_boolean_predicates(_run(text))

    def test_passes_with_predicate_explaining_variable(self) -> None:
        assert_extracts_boolean_predicates(
            _run(_blocks(BEFORE_CONDITIONAL, AFTER_CONDITIONAL_VARS))
        )

    def test_fails_without_predicate_names(self) -> None:
        text = _blocks(
            "function f() {}",
            "function ownerCheck() {}\nfunction teamCheck() {}",
        )
        with pytest.raises(AssertionFailure, match="predicate"):
            assert_extracts_boolean_predicates(_run(text))

    def test_fails_when_explaining_variables_are_not_predicate_named(
        self,
    ) -> None:
        text = _blocks(
            "function f() {}",
            "const ownerMatch = d.ownerId === u.id;\n"
            "const teamMatch = d.teamId === u.teamId;",
        )
        with pytest.raises(AssertionFailure, match="predicate"):
            assert_extracts_boolean_predicates(_run(text))


class TestAssertPreservesShippingRules:
    def test_passes_when_rate_table_survives(self) -> None:
        text = _blocks(BEFORE_TANGLE, AFTER_CLEAN)
        assert_preserves_shipping_rules(_run(text))

    def test_fails_when_literals_vanish(self) -> None:
        text = _blocks(
            BEFORE_TANGLE,
            'function quote() { return "remote" + "island"; }',
        )
        with pytest.raises(AssertionFailure, match="rate literals"):
            assert_preserves_shipping_rules(_run(text))

    def test_fails_when_zone_names_vanish(self) -> None:
        text = _blocks(
            BEFORE_TANGLE,
            "function quote() { return 167 * 4.1 * 12.5 * 1.35; }",
        )
        with pytest.raises(AssertionFailure, match="zone name"):
            assert_preserves_shipping_rules(_run(text))


class TestAssertPreservesPermissionRules:
    def test_passes_when_all_inputs_participate(self) -> None:
        text = _blocks(
            "function f() {}",
            "function canEdit(u: U, d: D) {\n"
            "  if (u.suspended) return false;\n"
            '  if (d.status === "archived") return false;\n'
            "  if (d.locked) return false;\n"
            '  return d.allowTeamEdits && d.status === "draft";\n'
            "}",
        )
        assert_preserves_permission_rules(_run(text))

    def test_fails_when_input_dropped(self) -> None:
        text = _blocks(
            "function f() {}",
            "function canEdit(u: U, d: D) { return !u.suspended; }",
        )
        with pytest.raises(AssertionFailure, match="dropped permission"):
            assert_preserves_permission_rules(_run(text))


class TestAssertAddsEmptyInputGuard:
    def test_passes_with_guard_and_throw(self) -> None:
        text = _blocks(
            "function mean() {}",
            "function mean(values: readonly number[]) {\n"
            "  if (values.length === 0) {\n"
            '    throw new RangeError("empty input");\n'
            "  }\n"
            "  return 0;\n"
            "}",
        )
        assert_adds_empty_input_guard(_run(text))

    def test_fails_without_range_error(self) -> None:
        text = _blocks(
            "function mean() {}",
            "function mean(v: number[]) { if (v.length === 0) return 0; }",
        )
        with pytest.raises(AssertionFailure, match="RangeError"):
            assert_adds_empty_input_guard(_run(text))

    def test_fails_without_length_check(self) -> None:
        text = _blocks(
            "function mean() {}",
            'function mean() { throw new RangeError("empty input"); }',
        )
        with pytest.raises(AssertionFailure, match="length check"):
            assert_adds_empty_input_guard(_run(text))


class TestAssertNoRefactorCeremony:
    def test_passes_for_plain_fix(self) -> None:
        text = _blocks(
            "function mean() {}\nfunction median() {}",
            "function mean() {}\nfunction median() {}",
        )
        assert_no_refactor_ceremony(_run(text))

    def test_passes_with_one_shared_guard_helper(self) -> None:
        text = _blocks(
            "function mean() {}\nfunction median() {}",
            "function assertNonEmpty() {}\n"
            "function mean() {}\nfunction median() {}",
        )
        assert_no_refactor_ceremony(_run(text))

    def test_fails_when_functions_renamed_away(self) -> None:
        text = _blocks(
            "function mean() {}\nfunction median() {}",
            "function computeMean() {}\nfunction computeMedian() {}",
        )
        with pytest.raises(AssertionFailure, match="renamed or removed"):
            assert_no_refactor_ceremony(_run(text))

    def test_fails_on_uninvited_decomposition(self) -> None:
        text = _blocks(
            "function mean() {}\nfunction median() {}",
            "function mean() {}\nfunction median() {}\n"
            "function sortAscending() {}\nfunction middleIndex() {}",
        )
        with pytest.raises(AssertionFailure, match="uninvited"):
            assert_no_refactor_ceremony(_run(text))


class TestAssertSkillNotInvoked:
    def test_passes_when_not_invoked(self) -> None:
        assert_skill_not_invoked(_run("", skill_invoked=False))

    def test_fails_when_invoked(self) -> None:
        with pytest.raises(AssertionFailure, match="When-NOT-to-use") as exc:
            assert_skill_not_invoked(_run("", skill_invoked=True))
        assert exc.value.sections == (("Tool uses", "[]"),)
