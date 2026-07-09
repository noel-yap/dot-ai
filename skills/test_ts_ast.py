"""Unit tests for the shared ts_ast TypeScript-parsing helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ts_ast  # noqa: E402


class TestFunctions:
    def test_names_and_async_flags(self) -> None:
        code = (
            "function decide(x) { return x; }\n"
            "const pick = (x) => x;\n"
            "export async function run() { await x(); }\n"
        )
        got = {fn.name: fn.is_async for fn in ts_ast.named_functions(code)}
        assert got == {"decide": False, "pick": False, "run": True}

    def test_anonymous_callbacks_excluded_from_named(self) -> None:
        code = "const r = [1, 2].map((n) => n + 1);"
        assert ts_ast.named_functions(code) == []
        assert any(fn.name is None for fn in ts_ast.functions(code))


class TestExplainingVariables:
    def test_names_compound_initializers(self) -> None:
        code = (
            "const isOwner = doc.ownerId === user.id;\n"
            "const canTeamEdit = a && b || c;\n"
            "const isActive = !user.suspended;\n"
            "const grant = role === 'admin' ? x : y;\n"
            "const total = base * rate;\n"
            "const inTeam = ids.includes(id);\n"
        )
        got = {b.name for b in ts_ast.explaining_variables(code)}
        assert got == {
            "isOwner",
            "canTeamEdit",
            "isActive",
            "grant",
            "total",
            "inTeam",
        }

    def test_excludes_pass_throughs_and_literals(self) -> None:
        # Bare identifier, member access, and literals name nothing new.
        code = (
            "const name = user.name;\n"
            "const alias = other;\n"
            "const count = 3;\n"
            "const flag = false;\n"
            "const label = 'draft';\n"
        )
        assert ts_ast.explaining_variables(code) == []

    def test_excludes_function_expressions(self) -> None:
        # Arrow and function expressions are callables, not explaining vars.
        code = (
            "const pick = (x) => x + 1;\n"
            "const run = function () { return 1; };\n"
        )
        assert ts_ast.explaining_variables(code) == []

    def test_excludes_destructuring_pattern(self) -> None:
        code = "const { a, b } = compute();"
        assert ts_ast.explaining_variables(code) == []

    def test_comment_and_string_declarations_are_not_bindings(self) -> None:
        code = '// const ghost = a === b;\nconst s = "const x = a || b;";'
        assert ts_ast.explaining_variables(code) == []


class TestIoTokens:
    def test_detects_effects_and_nondeterminism(self) -> None:
        fn = ts_ast.functions(
            "async function s(){ await db.getOrder(id); emailService.send(a);"
            " fetch(u); Date.now(); Math.random(); const y = process.env.Y;"
            " console.log(y); }"
        )[0].node
        assert set(ts_ast.io_tokens(fn)) == {
            "await",
            "db.",
            "emailService.",
            "fetch(",
            "Date.now(",
            "Math.random(",
            "process.env",
            "console.",
        }

    def test_pure_function_has_no_io(self) -> None:
        fn = ts_ast.functions("function f(o){ return o.total > 1000; }")[0].node
        assert ts_ast.io_tokens(fn) == []

    def test_comment_and_string_mentions_are_not_io(self) -> None:
        # I/O named only inside a comment or a string literal is not a call.
        fn = ts_ast.functions(
            'function f(){ /* await db. */ return "call emailService.send"; }'
        )[0].node
        assert ts_ast.io_tokens(fn) == []


class TestObjectAndKind:
    def test_builds_object_with_keys(self) -> None:
        fn = ts_ast.functions(
            'function f(){ return { subject: "s", body: "b" }; }'
        )[0].node
        assert ts_ast.builds_object_with_keys(fn, {"subject", "body"})
        assert not ts_ast.builds_object_with_keys(fn, {"subject", "message"})

    def test_has_kind_discriminant_type(self) -> None:
        assert ts_ast.has_kind_discriminant(
            'type A = { kind: "x" } | { kind: "y" };'
        )

    def test_has_kind_discriminant_object(self) -> None:
        assert ts_ast.has_kind_discriminant('const a = { kind: "x", v: 1 };')

    def test_no_kind_discriminant(self) -> None:
        assert not ts_ast.has_kind_discriminant('const a = { subject: "x" };')
