"""Unit tests for _assertions.py."""

from __future__ import annotations

import pytest
from ._assertions import (
    _adds_deps_param_to_pure_fn,
    _adds_test_code,
    _all_leaks_in_block,
    _bare_token_leaks,
    _candidate_sut_blocks,
    _code_blocks,
    _has_composition_root,
    _has_constructor_with_deps,
    _has_deps_parameter,
    _has_production_default_dep,
    _introduces_di_interface,
    _introduces_injection_seam,
    _introduces_narrow_interface,
    _preserves_region_rule,
    _substring_leaks,
    assert_composition_root_present,
    assert_introduces_injection_seam,
    assert_narrow_deps_interface,
    assert_no_collaborator_interfaces_introduced,
    assert_no_deps_parameter_added,
    assert_no_production_default_deps,
    assert_skill_not_invoked,
    assert_sut_has_no_bare_globals,
    assert_sut_has_no_bare_module_refs,
)
from binom_eval import (
    AssertionFailure,
    BEGIN_AFTER_MARKER,
    BEGIN_BEFORE_MARKER,
    END_AFTER_MARKER,
    END_BEFORE_MARKER,
    EvalRun,
)


def _run(text: str, skill_invoked: bool = False) -> EvalRun:
    return EvalRun(
        eval_id="t", prompt="", skill_invoked=skill_invoked, assistant_text=text
    )


# ---------------------------------------------------------------------------
# Code-block extraction
# ---------------------------------------------------------------------------


class TestCodeBlocks:
    def test_extracts_typescript_blocks(self) -> None:
        text = (
            "```typescript\nconst x = 1;\n```\n"
            "between\n```ts\nconst y = 2;\n```"
        )
        assert _code_blocks(text) == ["const x = 1;", "const y = 2;"]

    def test_extracts_unlabelled_blocks(self) -> None:
        assert _code_blocks("```\nconst z = 3;\n```") == ["const z = 3;"]


def _after_block(body: str) -> str:
    return (
        "```ts\n"
        f"{BEGIN_AFTER_MARKER}\n{body}\n{END_AFTER_MARKER}\n"
        "```"
    )


class TestCandidateSutBlocks:
    def test_prefers_explicit_sut_markers(self) -> None:
        text = (
            "```ts\n"
            f"{BEGIN_BEFORE_MARKER}\nasync function foo() {{ await db.x(); }}\n"
            f"{END_BEFORE_MARKER}\n"
            "```\n"
            "```ts\n"
            f"{BEGIN_AFTER_MARKER}\n// SUT (under test)\n"
            "class C { run() { return this.dep.x(); } }\n"
            "// end SUT (under test)\n"
            f"{END_AFTER_MARKER}\n"
            "```\n"
        )
        blocks = _candidate_sut_blocks(text)
        assert len(blocks) == 1
        assert "this.dep.x" in blocks[0]
        assert "BEGIN BEFORE" not in blocks[0]

    def test_falls_back_to_after_snippet_when_no_sut_marker(self) -> None:
        text = _after_block("class C { run() {} }")
        assert len(_candidate_sut_blocks(text)) == 1


class TestSubstringLeaks:
    def test_finds_date_now(self) -> None:
        assert "Date.now(" in _substring_leaks("const t = Date.now();")

    def test_finds_math_random(self) -> None:
        assert "Math.random(" in _substring_leaks("Math.random()")

    def test_finds_process_env(self) -> None:
        assert "process.env" in _substring_leaks("process.env.X")

    def test_finds_console_dot(self) -> None:
        assert "console." in _substring_leaks("console.log('x')")

    def test_clean_block_no_leaks(self) -> None:
        assert _substring_leaks("this.clock(); this.log('x')") == []

    def test_comment_mentions_are_not_leaks(self) -> None:
        assert _substring_leaks("// no more Date.now( here\nthis.clock();") == []
        assert _substring_leaks("/* dropped console. calls */ this.log('x')") == []


class TestBareTokenLeaksComments:
    def test_comment_mentions_are_not_leaks(self) -> None:
        assert _bare_token_leaks("// callers used to pass db. directly\nthis.store.get(id);") == []


class TestBareTokenLeaks:
    def test_finds_bare_db(self) -> None:
        assert "db." in _bare_token_leaks("await db.x()")

    def test_no_leak_when_member_access(self) -> None:
        assert _bare_token_leaks("await this.db.x()") == []


class TestAllLeaksInBlock:
    def test_combines_both(self) -> None:
        leaks = _all_leaks_in_block(
            "const t = Date.now(); await db.x(); this.log('ok')"
        )
        assert "Date.now(" in leaks
        assert "db." in leaks


# ---------------------------------------------------------------------------
# Injection-seam heuristics
# ---------------------------------------------------------------------------


class TestHasConstructorWithDeps:
    def test_empty_constructor_does_not_count(self) -> None:
        text = "```ts\nclass C { constructor() {} }\n```"
        assert not _has_constructor_with_deps(text)

    def test_constructor_with_param_counts(self) -> None:
        text = (
            "```ts\n"
            "class C { constructor(private readonly store: Store) {} }\n"
            "```"
        )
        assert _has_constructor_with_deps(text)

    def test_no_class_does_not_count(self) -> None:
        text = "```ts\nfunction f() {}\n```"
        assert not _has_constructor_with_deps(text)


class TestHasDepsParameter:
    def test_named_deps_param(self) -> None:
        text = "```ts\nfunction f(x: string, deps: Deps) {}\n```"
        assert _has_deps_parameter(text)

    def test_no_deps_param(self) -> None:
        text = "```ts\nfunction f(x: string) {}\n```"
        assert not _has_deps_parameter(text)


class TestIntroducesInjectionSeam:
    def test_constructor_path(self) -> None:
        assert _introduces_injection_seam(
            "```ts\nclass C { constructor(store: S) {} }\n```"
        )

    def test_deps_param_path(self) -> None:
        assert _introduces_injection_seam(
            "```ts\nfunction f(id: string, deps: D): void {}\n```"
        )

    def test_neither(self) -> None:
        assert not _introduces_injection_seam(
            "```ts\nfunction f(x: number) {}\n```"
        )

    def test_param_typed_by_declared_interface(self) -> None:
        text = (
            "```ts\n"
            "interface OrderStore { getOrder(id: string): Promise<X>; }\n"
            "export async function shipOrder(\n"
            "  orderId: string,\n"
            "  store: OrderStore,\n"
            "): Promise<void> {}\n"
            "```"
        )
        assert _introduces_injection_seam(text)

    def test_param_typed_by_undeclared_type_does_not_count(self) -> None:
        text = (
            "```ts\n"
            "export function shipOrder(orderId: string, store: Db) {}\n"
            "```"
        )
        assert not _introduces_injection_seam(text)


class TestIntroducesNarrowInterface:
    def test_interface(self) -> None:
        assert _introduces_narrow_interface(
            "```ts\ninterface Store { get(id: string): Promise<X>; }\n```"
        )

    def test_type_alias(self) -> None:
        assert _introduces_narrow_interface(
            "```ts\ntype Clock = () => number;\n```"
        )

    def test_neither(self) -> None:
        assert not _introduces_narrow_interface("```ts\nfunction f() {}\n```")


class TestHasCompositionRoot:
    def test_import_plus_new(self) -> None:
        text = (
            "```ts\n"
            "import { db } from './db';\n"
            "export const prod = new Service(db, Date.now);\n"
            "```"
        )
        assert _has_composition_root(text)

    def test_import_plus_deps_literal(self) -> None:
        text = (
            "```ts\n"
            "import { sign } from 'jsonwebtoken';\n"
            "export const productionDeps: TokenDeps = { sign };\n"
            "```"
        )
        assert _has_composition_root(text)

    def test_import_alone_does_not_count(self) -> None:
        text = "```ts\nimport { db } from './db';\nfunction f() {}\n```"
        assert not _has_composition_root(text)

    def test_import_plus_partially_applied_wrapper(self) -> None:
        text = (
            "```ts\n"
            "import { db } from './db';\n"
            "export const shipOrderWithPrimaryDb = (orderId: string) =>\n"
            "  shipOrder(orderId, db);\n"
            "```"
        )
        assert _has_composition_root(text)

    def test_wrapper_with_return_type_annotation(self) -> None:
        text = (
            "```ts\n"
            "import { db } from './db';\n"
            "export const shipProd = (id: string): Promise<void> =>\n"
            "  shipOrder(id, db);\n"
            "```"
        )
        assert _has_composition_root(text)

    def test_import_plus_unannotated_deps_literal(self) -> None:
        text = (
            "```ts\n"
            "import { db } from './db';\n"
            "export const productionDeps = { store: db };\n"
            "```"
        )
        assert _has_composition_root(text)

    def test_default_param_fallback_is_not_a_root(self) -> None:
        text = (
            "```ts\n"
            "import { db } from './db';\n"
            "export async function shipOrder(\n"
            "  orderId: string,\n"
            "  store: OrderStore = db,\n"
            "): Promise<void> {}\n"
            "```"
        )
        assert not _has_composition_root(text)

    def test_forwarding_wrapper_is_not_a_root(self) -> None:
        text = (
            "```ts\n"
            "import { db } from './db';\n"
            "export const shipAlias = (id: string, store: OrderStore) =>\n"
            "  shipOrder(id, store);\n"
            "```"
        )
        assert not _has_composition_root(text)


class TestHasProductionDefaultDep:
    def test_arrow_default_date_now(self) -> None:
        text = _after_block(
            "class C { "
            "constructor(private clock: Clock = () => Date.now()) {} }"
        )
        assert _has_production_default_dep(text)

    def test_no_default(self) -> None:
        text = _after_block("class C { constructor(private clock: Clock) {} }")
        assert not _has_production_default_dep(text)


# ---------------------------------------------------------------------------
# Domain-rule preservation
# ---------------------------------------------------------------------------


class TestPreservesRegionRule:
    def test_both_present(self) -> None:
        assert _preserves_region_rule("Subject: 'Shipped (intl)' or 'Shipped'")

    def test_intl_missing(self) -> None:
        assert not _preserves_region_rule("Subject: 'Shipped'")


# ---------------------------------------------------------------------------
# Negative-case helpers
# ---------------------------------------------------------------------------


class TestAddsDepsParamToPureFn:
    def test_detects_deps_arg(self) -> None:
        text = "```ts\nfunction subtotal(lines: CartLine[], deps: Deps) {}\n```"
        assert _adds_deps_param_to_pure_fn(text)

    def test_clean_pure_fn(self) -> None:
        text = (
            "```ts\n"
            "function subtotal(lines: CartLine[]): number { return 0; }\n"
            "```"
        )
        assert not _adds_deps_param_to_pure_fn(text)


class TestIntroducesDIInterface:
    def test_detects_clock_interface(self) -> None:
        text = "```ts\ninterface Clock { now(): number; }\n```"
        assert _introduces_di_interface(text)

    def test_detects_store_type_alias(self) -> None:
        text = "```ts\ntype Store = { get(id: string): Promise<X> };\n```"
        assert _introduces_di_interface(text)

    def test_no_di_interface(self) -> None:
        text = (
            "```ts\n"
            "interface CartLine { unitPrice: number; quantity: number; }\n"
            "```"
        )
        assert not _introduces_di_interface(text)


class TestAddsTestCode:
    def test_detects_test_call(self) -> None:
        assert _adds_test_code("test('x', () => { ... })")

    def test_detects_describe_block(self) -> None:
        assert _adds_test_code("describe('y', () => {})")

    def test_detects_expect(self) -> None:
        assert _adds_test_code("expect(x).toBe(1)")

    def test_no_test_code(self) -> None:
        assert not _adds_test_code("just prose, no test code")


# ---------------------------------------------------------------------------
# Top-level assertion functions (smoke tests)
# ---------------------------------------------------------------------------


class TestAssertIntroducesInjectionSeam:
    def test_passes_with_constructor(self) -> None:
        assert_introduces_injection_seam(
            _run("```ts\nclass C { constructor(s: S) {} }\n```")
        )

    def test_fails_without_seam(self) -> None:
        with pytest.raises(AssertionError, match="injection seam"):
            assert_introduces_injection_seam(
                _run("```ts\nfunction f(id: string) {}\n```")
            )


class TestAssertSutHasNoBareGlobals:
    def test_passes_when_clean(self) -> None:
        text = _after_block("class C { run() { return this.clock(); } }")
        assert_sut_has_no_bare_globals(_run(text))

    def test_fails_on_date_now_leak(self) -> None:
        text = _after_block("class C { run() { return Date.now(); } }")
        with pytest.raises(
            AssertionFailure, match="bare global I/O tokens"
        ) as exc:
            assert_sut_has_no_bare_globals(_run(text))
        assert exc.value.sections[0][0] == "Leaking SUT block"
        assert "Date.now()" in exc.value.sections[0][1]

    def test_fails_when_no_sut_block(self) -> None:
        with pytest.raises(
            AssertionFailure, match="no refactored SUT"
        ) as exc:
            assert_sut_has_no_bare_globals(_run("just prose"))
        assert exc.value.sections == (("Assistant reply", "just prose"),)


class TestAssertSutHasNoBareModuleRefs:
    def test_passes_with_member_access(self) -> None:
        text = _after_block("class C { async run() { await this.db.x(); } }")
        assert_sut_has_no_bare_module_refs(_run(text))

    def test_fails_on_bare_db(self) -> None:
        text = _after_block("class C { async run() { await db.x(); } }")
        with pytest.raises(AssertionError, match="bare module references"):
            assert_sut_has_no_bare_module_refs(_run(text))


class TestAssertCompositionRootPresent:
    def test_passes_when_import_plus_new(self) -> None:
        text = (
            "```ts\nimport { db } from './db';\n"
            "export const prod = new S(db);\n```"
        )
        assert_composition_root_present(_run(text))

    def test_fails_when_no_root(self) -> None:
        with pytest.raises(AssertionError, match="composition root"):
            assert_composition_root_present(_run("```ts\nfunction f() {}\n```"))

    def test_passes_when_import_plus_wrapper(self) -> None:
        text = (
            "```ts\nimport { db } from './db';\n"
            "export const shipProd = (id: string) => shipOrder(id, db);\n```"
        )
        assert_composition_root_present(_run(text))


class TestAssertNarrowDepsInterface:
    def test_passes_with_interface(self) -> None:
        assert_narrow_deps_interface(
            _run("```ts\ninterface Store { get(id: string): Promise<X>; }\n```")
        )

    def test_fails_without(self) -> None:
        with pytest.raises(
            AssertionError, match="named interface or type alias"
        ):
            assert_narrow_deps_interface(_run("```ts\nclass C {}\n```"))


class TestAssertNoProductionDefaultDeps:
    def test_passes_when_no_default(self) -> None:
        text = _after_block("class C { constructor(private c: Clock) {} }")
        assert_no_production_default_deps(_run(text))

    def test_fails_when_default_is_date_now(self) -> None:
        text = _after_block(
            "class C { "
            "constructor(private c: Clock = () => Date.now()) {} }"
        )
        with pytest.raises(AssertionError, match="production-default"):
            assert_no_production_default_deps(_run(text))


class TestAssertNoDepsParameterAdded:
    def test_passes_for_pure_fn(self) -> None:
        text = (
            "```ts\n"
            "function subtotal(lines: CartLine[]): number { return 0; }\n"
            "```"
        )
        assert_no_deps_parameter_added(_run(text))

    def test_fails_when_deps_added(self) -> None:
        text = "```ts\nfunction subtotal(lines: CartLine[], deps: Deps) {}\n```"
        with pytest.raises(AssertionError, match="incorrectly applied"):
            assert_no_deps_parameter_added(_run(text))


class TestAssertNoCollaboratorInterfacesIntroduced:
    def test_passes_for_pure_fn(self) -> None:
        text = (
            "```ts\n"
            "interface CartLine { unitPrice: number; quantity: number; }\n"
            "```"
        )
        assert_no_collaborator_interfaces_introduced(_run(text))

    def test_fails_on_clock_interface(self) -> None:
        with pytest.raises(AssertionError, match="incorrectly applied"):
            assert_no_collaborator_interfaces_introduced(
                _run("```ts\ninterface Clock { now(): number; }\n```")
            )


class TestAssertSkillNotInvoked:
    def test_passes_when_not_invoked(self) -> None:
        assert_skill_not_invoked(_run("", skill_invoked=False))

    def test_fails_when_invoked(self) -> None:
        with pytest.raises(
            AssertionFailure, match="When-NOT-to-use"
        ) as exc:
            assert_skill_not_invoked(_run("", skill_invoked=True))
        assert exc.value.sections == (("Tool uses", "[]"),)
