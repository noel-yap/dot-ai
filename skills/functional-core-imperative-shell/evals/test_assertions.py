"""Unit tests for _assertions.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from ._assertions import (
    ASSERTION_HANDLERS,
    _alert_returned_as_data,
    _candidate_pure_functions,
    _code_blocks,
    _io_leaks_in_pure_functions,
    _missing_discount_elements,
    _missing_from,
    _missing_io_calls,
    _new_function_names,
    _suspicious_saga_fn_names,
    assert_alert_decision_extracted,
    assert_no_pure_core_extraction,
    assert_pure_core_no_io,
    assert_skill_not_invoked,
)
from binom_eval import (
    AssertionFailure,
    EvalRun,
    assert_handler_coverage,
    load_evals,
)


def _after(body: str) -> str:
    """Wrap an AFTER snippet in a sentinel-delimited TypeScript block."""
    return (
        "```typescript\n"
        "// <<<BEGIN AFTER>>> //\n"
        f"{body}\n"
        "// <<<END AFTER>>> //\n"
        "```"
    )


class TestCodeBlocks:
    def test_extracts_typescript_blocks(self) -> None:
        text = (
            "before\n```typescript\nconst x = 1;\n```\n"
            "between\n```ts\nconst y = 2;\n```\nafter"
        )
        assert _code_blocks(text) == ["const x = 1;", "const y = 2;"]

    def test_extracts_unlabelled_blocks(self) -> None:
        text = "```\nconst z = 3;\n```"
        assert _code_blocks(text) == ["const z = 3;"]


class TestNewFunctionNames:
    def test_empty_text_returns_empty_set(self) -> None:
        assert _new_function_names("") == set()

    def test_excludes_shell_function(self) -> None:
        text = "```ts\nasync function processOrder(id: string) {}\n```"
        assert _new_function_names(text) == set()

    def test_includes_non_shell_named_fn(self) -> None:
        text = "```ts\nfunction decide(o: Order) { return 'large'; }\n```"
        assert _new_function_names(text) == {"decide"}

    def test_includes_arrow_fn(self) -> None:
        text = "```ts\nconst decide = (o: Order) => 'large';\n```"
        assert _new_function_names(text) == {"decide"}


class TestCandidatePureFunctions:
    def test_excludes_async_shell_and_process_order(self) -> None:
        text = _after(
            "function calculateDiscount(o) { return 0; }\n"
            "async function processOrder(id) { await db.get(id); }"
        )
        assert [fn.name for fn in _candidate_pure_functions(text)] == [
            "calculateDiscount"
        ]

    def test_no_functions_returns_empty(self) -> None:
        assert _candidate_pure_functions("prose only, no code") == []


class TestIoLeaksInPureFunctions:
    def test_no_functions_returns_empty(self) -> None:
        assert _io_leaks_in_pure_functions("no code blocks here") == []

    def test_async_shell_is_not_scanned(self) -> None:
        # The async shell may perform I/O; only pure functions are held to it.
        text = (
            "```ts\n"
            "function decide(o) { return o.total > 100; }\n"
            "async function processOrder(id) {\n"
            "  const o = await db.getOrder(id);\n"
            "  if (decide(o)) await emailService.send(o.email);\n"
            "}\n"
            "```"
        )
        assert _io_leaks_in_pure_functions(text) == []

    def test_comment_mentions_of_io_are_not_leaks(self) -> None:
        text = (
            "```ts\n"
            "function decide(o) {\n"
            "  // no more await db. or emailService. calls here\n"
            "  return o.total > 100;\n"
            "}\n"
            "```"
        )
        assert _io_leaks_in_pure_functions(text) == []

    def test_leaky_pure_function_returns_token_snippet_pairs(self) -> None:
        text = (
            "```ts\n"
            "function decide(id) { return await db.getOrder(id); }\n"
            "```"
        )
        tokens = [tok for tok, _ in _io_leaks_in_pure_functions(text)]
        assert "await" in tokens
        assert "db." in tokens


class TestMissingFrom:
    def test_all_present_returns_empty(self) -> None:
        assert _missing_from(("a", "b"), "abc") == []

    def test_absent_needle_returned(self) -> None:
        assert _missing_from(("x",), "abc") == ["x"]

    def test_mixed_returns_only_absent(self) -> None:
        assert _missing_from(("a", "x"), "abc") == ["x"]


class TestMissingIoCalls:
    def test_all_present_returns_empty(self) -> None:
        text = "db.getOrder(...) emailService.send(...) db.updateStatus(...)"
        assert _missing_io_calls(text) == []

    def test_detects_missing_call(self) -> None:
        text = "db.getOrder(...) db.updateStatus(...)"
        assert _missing_io_calls(text) == ["emailService.send"]


class TestMissingDiscountElements:
    def test_all_present_returns_empty(self) -> None:
        text = "platinum gold itemCount 15 10 5"
        assert _missing_discount_elements(text) == []

    def test_detects_missing_tier(self) -> None:
        text = "gold itemCount 15 10 5"
        assert "platinum" in _missing_discount_elements(text)

    def test_detects_missing_percentage(self) -> None:
        text = "platinum gold itemCount 10 5"
        assert "15" in _missing_discount_elements(text)


class TestSuspiciousSagaFnNames:
    def test_empty_returns_empty(self) -> None:
        assert _suspicious_saga_fn_names("") == []

    def test_finds_decide_prefix(self) -> None:
        text = (
            "```ts\nfunction decideAlert(order: Order) { return 'none'; }\n```"
        )
        assert _suspicious_saga_fn_names(text) == ["function decideAlert"]

    def test_finds_plan_saga(self) -> None:
        text = "```ts\nfunction planPaymentSaga(id: string) {}\n```"
        assert _suspicious_saga_fn_names(text) == ["function planPaymentSaga"]

    def test_ignores_non_matching(self) -> None:
        text = "```ts\nfunction processOrder(id: string) {}\n```"
        assert _suspicious_saga_fn_names(text) == []


class TestAssertPureCoreNoIo:
    def test_passes_for_clean_function(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text=(
                "```ts\n"
                "function decide(o: { total: number }) {\n"
                "  return o.total > 1000 ? 'large' : 'small';\n"
                "}\n"
                "```"
            ),
        )
        assert_pure_core_no_io(run)

    def test_fails_when_pure_function_awaits(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text=(
                "```ts\n"
                "function decide(o: { id: string }) {\n"
                "  const row = await db.getOrder(o.id);\n"
                "  return row;\n"
                "}\n"
                "```"
            ),
        )
        with pytest.raises(AssertionFailure, match="leak I/O tokens") as exc:
            assert_pure_core_no_io(run)
        assert exc.value.sections[0][0] == "Leaking pure-core function"
        assert "db.getOrder" in exc.value.sections[0][1]

    def test_no_candidate_attaches_reply_section(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text="prose only, no code blocks",
        )
        with pytest.raises(AssertionFailure, match="no candidate") as exc:
            assert_pure_core_no_io(run)
        assert exc.value.sections == (
            ("Assistant reply", "prose only, no code blocks"),
        )

    def test_async_shell_alongside_pure_core_passes(self) -> None:
        # The complete refactor carries the async shell in the same block;
        # only the pure functions are held to purity, so the shell's I/O is
        # not a leak.
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text=(
                "```typescript\n"
                "function decide(o: { total: number }) {\n"
                "  return o.total > 1000 ? 'large' : 'small';\n"
                "}\n"
                "export async function processOrder() {\n"
                "  await db.getOrder();\n"
                "}\n"
                "```"
            ),
        )
        assert_pure_core_no_io(run)


class TestAssertAlertDecisionExtracted:
    def test_passes_for_kind_union(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text=_after(
                'type Alert = { kind: "none" } | { kind: "large"; email: string };\n'
                "function decideAlert(o) {\n"
                '  if (o.total > 1000) return { kind: "large", email: o.email };\n'
                '  return { kind: "none" };\n'
                "}"
            ),
        )
        assert_alert_decision_extracted(run)

    def test_passes_for_nullable_struct(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text=_after(
                "function determineAlert(o, f, d) {\n"
                '  if (f > 1000) return { subject: "x", body: "y" };\n'
                "  return null;\n"
                "}"
            ),
        )
        assert_alert_decision_extracted(run)

    def test_passes_for_optional_field_struct(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text=_after(
                "function calculateOrderDecision(o) {\n"
                "  let alert;\n"
                '  if (o.total > 1000) alert = { subject: "x", message: "y" };\n'
                "  return { discountPct: 0, finalTotal: 1, alert };\n"
                "}"
            ),
        )
        assert_alert_decision_extracted(run)

    def test_fails_when_decision_stays_in_shell(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text=_after(
                "export async function processOrder(id) {\n"
                "  const o = await db.getOrder(id);\n"
                "  if (o.total > 1000)\n"
                '    await emailService.send(o.email, "Large order alert", "b");\n'
                "}"
            ),
        )
        with pytest.raises(AssertionFailure, match="alert decision"):
            assert_alert_decision_extracted(run)

    def test_helper_false_without_pure_decision(self) -> None:
        assert not _alert_returned_as_data("prose only, no code")


class TestAssertNoPureCoreExtraction:
    def test_flags_pure_core_marker(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=False,
            assistant_text=(
                "```ts\n// pure core\nfunction f() {}\n// end pure core\n```"
            ),
        )
        with pytest.raises(AssertionError, match="pure core"):
            assert_no_pure_core_extraction(run)

    def test_flags_decorated_pure_core_marker(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=False,
            assistant_text=(
                "```typescript\n"
                "// --- pure core ---\n"
                "function f() {}\n"
                "// --- end pure core ---\n"
                "```"
            ),
        )
        with pytest.raises(AssertionError, match="pure core"):
            assert_no_pure_core_extraction(run)

    def test_passes_for_plain_retry(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=False,
            assistant_text=(
                "```ts\n"
                "for (let attempt = 0; attempt < 3; attempt++) {\n"
                "  try { await fulfillmentApi.reserve(orderId); break; }\n"
                "  catch (e) { await sleep(100 * 2 ** attempt); }\n"
                "}\n"
                "```"
            ),
        )
        assert_no_pure_core_extraction(run)


class TestAssertSkillNotInvoked:
    def test_fails_when_skill_invoked(self) -> None:
        run = EvalRun(
            eval_id="t", prompt="", skill_invoked=True, assistant_text=""
        )
        with pytest.raises(AssertionFailure) as exc:
            assert_skill_not_invoked(run)
        assert exc.value.sections == (("Tool uses", "[]"),)

    def test_passes_when_skill_not_invoked(self) -> None:
        run = EvalRun(
            eval_id="t", prompt="", skill_invoked=False, assistant_text=""
        )
        assert_skill_not_invoked(run)


def test_every_assertion_has_a_handler() -> None:
    """Every assertion id in evals.json has a registered handler.

    Guards against dropping or renaming a handler while an eval still
    references it: assert_handler_coverage names every gap eagerly rather
    than failing mid-live-run.
    """
    evals_path = Path(__file__).resolve().parent / "typescript" / "evals.json"
    assert_handler_coverage(load_evals(evals_path), ASSERTION_HANDLERS)
