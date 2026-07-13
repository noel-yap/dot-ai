"""DI refactor-quality assertion functions and their supporting helpers."""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

# Ensure the skills/ root is on sys.path so the shared test_utils module
# is importable when this file is loaded via the evals namespace package.
_skills_root = str(Path(__file__).resolve().parents[2])
if _skills_root not in sys.path:
    sys.path.insert(0, _skills_root)

from eval_assertion_utils import after_snippet, reply_sections
from test_utils import has_bare_token as _has_bare_token, strip_code as _strip_code

from binom_eval import (
    AssertionFailure,
    EvalRun,
    code_blocks as _code_blocks,
    first_line as _first_line,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Globals that must never appear bare inside the refactored SUT.
SUT_GLOBAL_LEAK_TOKENS = (
    "Date.now(",
    "Math.random(",
    "process.env",
    "console.",
)

# Module references that are OK as `this.X` / `deps.X` member accesses but
# must NOT appear as bare identifiers in the refactored SUT.
SUT_MODULE_LEAK_TOKENS = (
    "db.",
    "emailService.",
    "fetch(",
)

CLASS_RE = re.compile(r"\bclass\s+(\w+)\b")
CONSTRUCTOR_PARAMS_RE = re.compile(r"\bconstructor\s*\(([^)]*)\)", re.DOTALL)
DEPS_PARAM_RE = re.compile(r"\bdeps\s*:\s*\w+", re.DOTALL)
INTERFACE_RE = re.compile(r"\binterface\s+(\w+)\b")
TYPE_ALIAS_RE = re.compile(r"\btype\s+(\w+)\s*=")

# A function/constructor parameter typed by a name declared elsewhere in
# the same output as an `interface` or `type` alias — i.e. the unit's
# signature names a locally-declared collaborator surface rather than a
# concrete/production type.
PARAM_TYPE_RE_TEMPLATE = r"\b\w+\s*:\s*({names})\b"

# An `import { ... } from '...'` binding list, for composition-root checks.
IMPORT_BINDINGS_RE = re.compile(r"\bimport\s*\{([^}]*)\}\s*from")

# A composition root that wires the unit via `new X(...)`.
INSTANTIATION_RE = re.compile(r"\bnew\s+\w+\s*\(")

# A composition root that wires the unit via a typed `: XDeps = {...}`
# literal.
DEPS_OBJECT_RE = re.compile(r":\s*\w*Deps\s*=\s*\{", re.IGNORECASE)

# A composition root that wires the unit via an *unannotated* `...Deps =
# {...}` literal (name hints at "deps" but carries no type annotation).
UNANNOTATED_DEPS_LITERAL_RE = re.compile(
    r"\b(?:const|let|var)\s+\w*Deps\w*\s*=\s*\{([^}]*)\}", re.IGNORECASE
)

# A partially-applied wrapper: `const f = (params) [: RetType]? =>
# call(args)`, used to detect a composition root that closes over an
# imported collaborator rather than merely forwarding its own parameter.
WRAPPER_CALL_RE = re.compile(
    r"=\s*\(([^)]*)\)\s*(?::\s*[^=\n]+)?=>\s*\n?\s*\w+\s*\(([^)]*)\)"
)

# A "test code" hint: looks like a test/expect/describe block was added.
TEST_HINT_RE = re.compile(r"\b(?:test|it|describe|expect)\s*\(", re.IGNORECASE)

# Marker for the SUT-after-refactor in the model's response, if it follows
# the SKILL convention. Optional — many models won't use the marker, in
# which case we fall back to "the largest non-BEFORE TypeScript block".
SUT_BLOCK_RE = re.compile(
    r"//\s*SUT[^\n]*\n(.*?)//\s*end\s+SUT",
    re.IGNORECASE | re.DOTALL,
)

# Patterns indicating production-defaulted deps (the anti-pattern from the
# SKILL): `clock: Clock = () => Date.now()` or `db = realDb` etc.
PROD_DEFAULT_DEP_RE = re.compile(
    r"=\s*(?:\(\s*\)\s*=>\s*)?(?:Date\.now|Math\.random|process\.env|console\.)",
    re.IGNORECASE,
)

# Suspicious tokens for the negative-case eval (pure_calculator):
# if any of these appear, Claude has incorrectly applied DI to a pure fn.
SUSPICIOUS_DI_INTERFACE_NAMES = (
    "Clock",
    "Rng",
    "Random",
    "Store",
    "Mailer",
    "Logger",
    "Http",
    "TokenDeps",
)

# Match a `deps: T` parameter on functions in the pure calculator —
# either inline destructuring or named parameter typed as a deps-like
# interface.
DEPS_PARAM_ANYWHERE_RE = re.compile(
    r"\b(?:deps|dependencies)\s*:\s*\w+", re.DOTALL
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _candidate_sut_blocks(text: str) -> list[str]:
    """Return code regions that represent the refactored unit.

    Derives the SUT from the sentinel-delimited AFTER region
    (`// <<<BEGIN AFTER>>> //` ... `// <<<END AFTER>>> //`); narrows to an
    explicit `// SUT` ... `// end SUT` sub-region if the model marked one,
    else uses the whole AFTER region. Returns `[]` when there is no AFTER
    region at all.
    """
    after = after_snippet(text)
    if not after:
        return []
    marked = SUT_BLOCK_RE.findall(after)
    return marked if marked else [after]


def _bare_token_leaks(block: str) -> list[str]:
    """All bare-module tokens that leak in `block` (comments/strings
    stripped first, so a mention inside prose doesn't count as a leak)."""
    stripped = _strip_code(block)
    return list(
        filter(lambda t: _has_bare_token(stripped, t), SUT_MODULE_LEAK_TOKENS)
    )


def _substring_leaks(block: str) -> list[str]:
    """All bare-global tokens (substring) that leak in `block` (comments/
    strings stripped first, so a mention inside prose doesn't count)."""
    stripped = _strip_code(block)
    return list(filter(stripped.__contains__, SUT_GLOBAL_LEAK_TOKENS))


def _all_leaks_in_block(block: str) -> list[str]:
    return _substring_leaks(block) + _bare_token_leaks(block)


def _leaks_with_snippets(text: str) -> list[tuple[str, str]]:
    """For every refactored block, pair each leaking token with a snippet."""
    return list(
        itertools.chain.from_iterable(
            ((tok, _first_line(block)) for tok in _all_leaks_in_block(block))
            for block in _candidate_sut_blocks(text)
        )
    )


# ---------------------------------------------------------------------------
# Injection-seam helpers
# ---------------------------------------------------------------------------


def _has_constructor_with_deps(text: str) -> bool:
    """True if the refactor introduces a class with a constructor that names
    at least one collaborator parameter (heuristic: any non-empty constructor
    parameter list)."""
    for block in _code_blocks(text):
        if not CLASS_RE.search(block):
            continue
        for params in CONSTRUCTOR_PARAMS_RE.findall(block):
            if params.strip():
                return True
    return False


def _has_deps_parameter(text: str) -> bool:
    """True if any function in the output takes a `deps: T` parameter."""
    return any(DEPS_PARAM_RE.search(block) for block in _code_blocks(text))


def _declared_interface_names(block: str) -> set[str]:
    """Names of interfaces/type aliases declared in `block`."""
    return set(INTERFACE_RE.findall(block)) | set(TYPE_ALIAS_RE.findall(block))


def _has_param_typed_by_declared_interface(text: str) -> bool:
    """True if a parameter is typed by an interface/type alias declared
    elsewhere in the same output — naming the collaborator via a narrow,
    locally-declared surface rather than a concrete/production type."""
    for block in _code_blocks(text):
        declared = _declared_interface_names(block)
        if not declared:
            continue
        param_type_re = re.compile(
            PARAM_TYPE_RE_TEMPLATE.format(
                names="|".join(re.escape(n) for n in declared)
            )
        )
        if param_type_re.search(block):
            return True
    return False


def _introduces_injection_seam(text: str) -> bool:
    """True if the refactor introduces either constructor injection, a
    `deps` parameter, or a parameter typed by a declared interface (i.e.,
    names collaborators in the unit's signature)."""
    return any(
        [
            _has_constructor_with_deps(text),
            _has_deps_parameter(text),
            _has_param_typed_by_declared_interface(text),
        ]
    )


def _introduces_narrow_interface(text: str) -> bool:
    """True if at least one TS interface or type alias is declared in the
    output — a heuristic that the unit depends on a named interface rather
    than the concrete production class."""
    return any(
        INTERFACE_RE.search(block) or TYPE_ALIAS_RE.search(block)
        for block in _code_blocks(text)
    )


def _imported_names(block: str) -> set[str]:
    """Names bound by `import { ... } from '...'` statements in `block`,
    resolving `X as Y` aliases to `Y`."""
    names: set[str] = set()
    for group in IMPORT_BINDINGS_RE.findall(block):
        for raw in group.split(","):
            name = raw.strip()
            if not name:
                continue
            names.add(name.rsplit(" as ", 1)[-1].strip())
    return names


def _wraps_imported_collaborator(block: str, imported: set[str]) -> bool:
    """True if an arrow function closes over an imported collaborator when
    calling another function — a partially-applied composition root —
    rather than merely forwarding one of its own parameters."""
    for params_str, args_str in WRAPPER_CALL_RE.findall(block):
        params = {p.split(":")[0].strip() for p in params_str.split(",") if p.strip()}
        args = {a.strip() for a in args_str.split(",") if a.strip()}
        if (args & imported) - params:
            return True
    return False


def _has_unannotated_deps_literal(block: str, imported: set[str]) -> bool:
    """True if a `...Deps = {...}` literal (no type annotation) wires in an
    imported collaborator by bare reference."""
    return any(
        any(_has_bare_token(body, name) for name in imported)
        for body in UNANNOTATED_DEPS_LITERAL_RE.findall(block)
    )


def _has_composition_root(text: str) -> bool:
    """True if the output contains a region that imports a production module
    AND constructs / wires the unit — i.e., a composition root separate from
    the unit itself.

    Heuristic: any code block that contains an `import` line AND one of:
    a `new <Identifier>(` instantiation, a `: <Identifier>Deps = {`
    literal, an unannotated `...Deps = {...}` literal referencing an
    imported binding, or a wrapper arrow function that partially applies
    an imported collaborator into another call.
    """
    for block in _code_blocks(text):
        if "import " not in block:
            continue
        if INSTANTIATION_RE.search(block) or DEPS_OBJECT_RE.search(block):
            return True
        imported = _imported_names(block)
        if not imported:
            continue
        if _wraps_imported_collaborator(block, imported):
            return True
        if _has_unannotated_deps_literal(block, imported):
            return True
    return False


def _has_production_default_dep(text: str) -> bool:
    """True if any deps default to a production global (anti-pattern).

    Looks for `= Date.now`, `= Math.random`, `= () => Date.now()`, etc.
    inside parameter lists or class fields in the refactored blocks.
    """
    return any(
        PROD_DEFAULT_DEP_RE.search(block)
        for block in _candidate_sut_blocks(text)
    )


# ---------------------------------------------------------------------------
# Domain-rule preservation helpers
# ---------------------------------------------------------------------------


def _preserves_region_rule(text: str) -> bool:
    """The refactor must preserve the international/domestic subject line."""
    return all(s in text for s in ("Shipped (intl)", "Shipped"))


# ---------------------------------------------------------------------------
# Negative-case helpers (pure_calculator should NOT get DI applied)
# ---------------------------------------------------------------------------


def _adds_deps_param_to_pure_fn(text: str) -> bool:
    """True if the output adds a deps parameter to any function — the
    canonical sign that DI was incorrectly applied to a pure calculator."""
    return any(
        DEPS_PARAM_ANYWHERE_RE.search(block) for block in _code_blocks(text)
    )


def _introduces_di_interface(text: str) -> bool:
    """True if the output declares an interface/type named like a typical
    DI collaborator (Clock, Rng, Store, Mailer, etc.)."""
    declared_names: set[str] = set()
    for block in _code_blocks(text):
        declared_names.update(INTERFACE_RE.findall(block))
        declared_names.update(TYPE_ALIAS_RE.findall(block))
    return any(name in declared_names for name in SUSPICIOUS_DI_INTERFACE_NAMES)


def _adds_test_code(text: str) -> bool:
    return bool(TEST_HINT_RE.search(text))


# ---------------------------------------------------------------------------
# Assertion functions
# ---------------------------------------------------------------------------


def assert_introduces_injection_seam(run: EvalRun) -> None:
    """Fail unless the refactor names collaborators in the unit's signature."""
    assert _introduces_injection_seam(run.assistant_text), (
        "expected refactor to introduce a constructor (or `deps:` parameter) "
        "that names collaborators; saw no injection seam"
    )


def assert_sut_has_no_bare_globals(run: EvalRun) -> None:
    """Fail if the refactored unit leaks bare global I/O tokens."""
    blocks = _candidate_sut_blocks(run.assistant_text)
    if not blocks:
        raise AssertionFailure(
            "no refactored SUT block found in claude output (no AFTER "
            "region and no `// SUT` marker)",
            sections=reply_sections(run),
        )
    for block in blocks:
        leaks = _substring_leaks(block)
        if leaks:
            raise AssertionFailure(
                "SUT block(s) leak bare global I/O tokens: "
                + ", ".join(f"{tok!r} in '{_first_line(block)}'" for tok in leaks),
                sections=(("Leaking SUT block", block),),
            )


def assert_sut_has_no_bare_module_refs(run: EvalRun) -> None:
    """Fail if the refactored unit leaks bare module references (db.,
    emailService., fetch() — must be member access on this/deps)."""
    blocks = _candidate_sut_blocks(run.assistant_text)
    if not blocks:
        raise AssertionFailure(
            "no refactored SUT block found in claude output (no AFTER "
            "region and no `// SUT` marker)",
            sections=reply_sections(run),
        )
    for block in blocks:
        leaks = _bare_token_leaks(block)
        if leaks:
            raise AssertionFailure(
                "SUT block(s) leak bare module references (use `this.X` / "
                "`deps.X` instead): "
                + ", ".join(f"{tok!r} in '{_first_line(block)}'" for tok in leaks),
                sections=(("Leaking SUT block", block),),
            )


def assert_preserves_region_rule(run: EvalRun) -> None:
    """Fail if the refactor drops the international/domestic subject line."""
    assert _preserves_region_rule(run.assistant_text), (
        "refactor lost the region rule: expected both 'Shipped (intl)' and "
        "'Shipped' to remain in the output"
    )


def assert_composition_root_present(run: EvalRun) -> None:
    """Fail if the output doesn't include a composition root wiring."""
    assert _has_composition_root(run.assistant_text), (
        "expected a composition root that imports production modules and "
        "wires them into the unit (e.g., `new OrderShipper(db, email, "
        "Date.now)` or a `productionDeps = {...}` literal)"
    )


def assert_narrow_deps_interface(run: EvalRun) -> None:
    """Fail if no narrow interface/type alias is declared for the deps."""
    assert _introduces_narrow_interface(run.assistant_text), (
        "expected at least one named interface or type alias for the "
        "injected collaborators (so the unit depends on a narrow surface, "
        "not the concrete production class)"
    )


def assert_no_production_default_deps(run: EvalRun) -> None:
    """Fail if any injected dep defaults to a production global."""
    assert not _has_production_default_dep(run.assistant_text), (
        "refactor introduces a production-default dep (e.g., `clock: Clock "
        "= () => Date.now()` or `= Math.random`); injected deps must be "
        "required so callers cannot silently re-couple to real I/O"
    )


def assert_adds_tests(run: EvalRun) -> None:
    """Fail if the output contains no test-like code for the negative case."""
    assert _adds_test_code(run.assistant_text), (
        "expected the response to add tests for computeCartTotal (test/it/"
        "describe/expect block); saw none"
    )


def assert_no_deps_parameter_added(run: EvalRun) -> None:
    """Fail if a deps parameter is added to a pure function (negative case)."""
    assert not _adds_deps_param_to_pure_fn(run.assistant_text), (
        "DI was incorrectly applied: a `deps:` parameter was added to a "
        "pure function. DI should NOT be applied here — there is nothing "
        "to inject."
    )


def assert_no_collaborator_interfaces_introduced(run: EvalRun) -> None:
    """Fail if DI-style collaborator interfaces are introduced for a pure fn."""
    assert not _introduces_di_interface(run.assistant_text), (
        "DI was incorrectly applied: a collaborator interface (Clock, Rng, "
        "Store, Mailer, etc.) was introduced for the pure calculator."
    )


def assert_skill_not_invoked(run: EvalRun) -> None:
    """Fail if the DI skill was invoked when it should have stayed silent."""
    if run.skill_invoked:
        raise AssertionFailure(
            "dependency-injection skill was invoked on the pure "
            "calculator prompt; this is the When-NOT-to-use case",
            sections=(("Tool uses", str(run.tool_uses)),),
        )


ASSERTION_HANDLERS = {
    "introduces-injection-seam": assert_introduces_injection_seam,
    "sut-has-no-bare-globals": assert_sut_has_no_bare_globals,
    "sut-has-no-bare-module-refs": assert_sut_has_no_bare_module_refs,
    "preserves-region-rule": assert_preserves_region_rule,
    "composition-root-present": assert_composition_root_present,
    "narrow-deps-interface": assert_narrow_deps_interface,
    "no-production-default-deps": assert_no_production_default_deps,
    "adds-tests": assert_adds_tests,
    "no-deps-parameter-added": assert_no_deps_parameter_added,
    "no-collaborator-interfaces-introduced": (
        assert_no_collaborator_interfaces_introduced
    ),
    "skill-not-invoked": assert_skill_not_invoked,
}
