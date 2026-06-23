"""Unit tests for _assertions.py."""

from __future__ import annotations

import pytest
from ._assertions import (
    _block_has_kind_discriminator,
    _candidate_pure_blocks,
    _code_blocks,
    _has_kind_discriminator,
    _io_leaks_in_pure_blocks,
    _is_candidate_pure_block,
    _leaking_tokens,
    _missing_discount_elements,
    _missing_from,
    _missing_io_calls,
    _new_function_names,
    _suspicious_saga_fn_names,
    assert_no_pure_core_extraction,
    assert_pure_core_no_io,
    assert_skill_not_invoked,
)
from binom_eval import EvalRun


class TestCodeBlocks:
    def test_extracts_typescript_blocks(self) -> None:
        text = (
            "before\n```typescript\nconst x = 1;\n```\n"
            "between\n```ts\nconst y = 2;\n```\nafter"
        )
        assert _code_blocks(text) == ["const x = 1;\n", "const y = 2;\n"]

    def test_extracts_unlabelled_blocks(self) -> None:
        text = "```\nconst z = 3;\n```"
        assert _code_blocks(text) == ["const z = 3;\n"]


class TestIsCandidatePureBlock:
    def test_async_without_marker_returns_false(self) -> None:
        assert not _is_candidate_pure_block(
            "async function foo() { await bar(); }\n"
        )

    def test_sync_named_function_returns_true(self) -> None:
        assert _is_candidate_pure_block(
            "function decide(x: number) { return x > 0; }\n"
        )

    def test_pure_core_marker_returns_true_even_if_async(self) -> None:
        assert _is_candidate_pure_block(
            "// pure core\nasync function broken() { await x(); }\n"
        )

    def test_no_function_definition_returns_false(self) -> None:
        assert not _is_candidate_pure_block("const x: number = 1;\n")

    def test_arrow_function_returns_true(self) -> None:
        assert _is_candidate_pure_block(
            "const decide = (x: number) => x > 0;\n"
        )


class TestCandidatePureBlocks:
    def test_includes_matching_block(self) -> None:
        text = "```ts\nfunction decide(x: number) { return x > 0; }\n```"
        assert _candidate_pure_blocks(text) == [
            "function decide(x: number) { return x > 0; }\n"
        ]

    def test_excludes_non_matching_block(self) -> None:
        text = "```ts\nasync function foo() { await bar(); }\n```"
        assert _candidate_pure_blocks(text) == []


class TestNewFunctionNames:
    def test_empty_text_returns_empty_set(self) -> None:
        assert _new_function_names("") == set()

    def test_excludes_shell_function(self) -> None:
        text = "```ts\nfunction processOrder(id: string) {}\n```"
        assert _new_function_names(text) == set()

    def test_includes_non_shell_named_fn(self) -> None:
        text = "```ts\nfunction decide(o: Order) { return 'large'; }\n```"
        assert _new_function_names(text) == {"decide"}

    def test_includes_arrow_fn(self) -> None:
        text = "```ts\nconst decide = (o: Order) => 'large';\n```"
        assert _new_function_names(text) == {"decide"}


class TestLeakingTokens:
    def test_clean_block_returns_empty(self) -> None:
        assert _leaking_tokens("const x = 1;") == []

    def test_detects_await(self) -> None:
        assert "await " in _leaking_tokens("const r = await fetch(url);")

    def test_detects_db_prefix(self) -> None:
        assert "db." in _leaking_tokens("const row = db.getOrder(id);")


class TestIoLeaksInPureBlocks:
    def test_no_code_blocks_returns_empty(self) -> None:
        assert _io_leaks_in_pure_blocks("no code blocks here") == []

    def test_leaky_pure_block_returns_token_snippet_pairs(self) -> None:
        text = (
            "```ts\n"
            "// pure core\n"
            "function decide(id: string) { return await db.getOrder(id); }\n"
            "```"
        )
        leaks = _io_leaks_in_pure_blocks(text)
        tokens = [tok for tok, _ in leaks]
        assert "await " in tokens
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


class TestBlockHasKindDiscriminator:
    def test_union_literal(self) -> None:
        assert _block_has_kind_discriminator('const a = { kind: "large" };')

    def test_type_form(self) -> None:
        assert _block_has_kind_discriminator("type Alert = { kind: string; }")

    def test_absent_returns_false(self) -> None:
        assert not _block_has_kind_discriminator(
            "const x = { label: 'large' };"
        )


class TestHasKindDiscriminator:
    def test_no_code_blocks_returns_false(self) -> None:
        assert not _has_kind_discriminator("no code here")

    def test_matching_block_returns_true(self) -> None:
        assert _has_kind_discriminator('```ts\nreturn { kind: "large" };\n```')


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
    def test_passes_for_clean_block(self) -> None:
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

    def test_fails_when_block_awaits(self) -> None:
        run = EvalRun(
            eval_id="t",
            prompt="",
            skill_invoked=True,
            assistant_text=(
                "```ts\n"
                "// pure core\n"
                "function decide(o: { id: string }) {\n"
                "  const row = await db.getOrder(o.id);\n"
                "  return row;\n"
                "}\n"
                "```"
            ),
        )
        with pytest.raises(AssertionError, match="leak I/O tokens"):
            assert_pure_core_no_io(run)


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
        with pytest.raises(AssertionError):
            assert_skill_not_invoked(run)

    def test_passes_when_skill_not_invoked(self) -> None:
        run = EvalRun(
            eval_id="t", prompt="", skill_invoked=False, assistant_text=""
        )
        assert_skill_not_invoked(run)
