"""DI refactor-quality assertion functions and their supporting helpers."""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable

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

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

CLASS_RE = re.compile(r"\bclass\s+(\w+)\b")
CONSTRUCTOR_PARAMS_RE = re.compile(r"\bconstructor\s*\(([^)]*)\)", re.DOTALL)
DEPS_PARAM_RE = re.compile(r"\bdeps\s*:\s*\w+", re.DOTALL)
INTERFACE_RE = re.compile(r"\binterface\s+(\w+)\b")
TYPE_ALIAS_RE = re.compile(r"\btype\s+(\w+)\s*=")

# A "test code" hint: looks like a test/expect/describe block was added.
TEST_HINT_RE = re.compile(r"\b(?:test|it|describe|expect)\s*\(", re.IGNORECASE)

# Marker for the SUT-after-refactor in the model's response, if it follows
# the SKILL convention. Optional — when absent we fall back to code blocks
# tagged `// AFTER` (see `_candidate_sut_blocks`).
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

# Function-style composition root: a module-level const arrow wrapper that
# partially applies the unit, e.g.
# `export const shipOrderWithDb = (id: string) => shipOrder(id, db);`.
# Captures the wrapper's parameter list and the wrapped call's arguments so
# `_wrapper_wires_production_value` can verify the call passes a value
# beyond the wrapper's own parameters (i.e., it actually wires something).
WRAPPER_WIRING_RE = re.compile(
    r"\bconst\s+\w+\s*(?::[^=]*)?=\s*(?:async\s*)?"
    r"\(([^)]*)\)\s*(?::[^=;{]*)?=>\s*\w+\s*\(([^()]*)\)"
)

IDENTIFIER_RE = re.compile(r"[A-Za-z_$][\w$]*")

STRING_LITERAL_RE = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`")

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


def _is_after_block(block: str) -> bool:
    """A block represents the *refactored* code if it has an AFTER marker
    or a `// SUT` marker, and does NOT identify itself as the BEFORE."""
    has_before = bool(re.search(r"//\s*BEFORE\b", block, re.IGNORECASE))
    has_after_marker = bool(
        re.search(r"//\s*(?:AFTER|SUT)\b", block, re.IGNORECASE)
    )
    return all([not has_before, has_after_marker])


def _candidate_sut_blocks(text: str) -> list[str]:
    """Return code regions that represent the refactored unit.

    Prefer explicitly-marked `// SUT` ... `// end SUT` regions if present;
    otherwise fall back to any code block tagged with `// AFTER`.
    """
    marked = SUT_BLOCK_RE.findall(text)
    if marked:
        return marked
    return list(filter(_is_after_block, _code_blocks(text)))


def _strip_comments(code: str) -> str:
    """Drop // line comments and /* */ block comments before token scans.

    Prose in comments legitimately mentions I/O collaborators ("no more
    bare Date.now here"), so only code may trip the leak tokens.
    """
    return _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", code))


def _has_bare_token(block: str, token: str) -> bool:
    """True if `token` appears not preceded by `.` or a word character —
    i.e., as a bare module reference rather than a `.X` member access."""
    return bool(re.search(r"(?<![.\w])" + re.escape(token), block))


def _bare_token_leaks(
    block: str, tokens: tuple[str, ...] = SUT_MODULE_LEAK_TOKENS
) -> list[str]:
    """All bare-module `tokens` that leak in `block`'s code."""
    code = _strip_comments(block)
    return list(filter(lambda t: _has_bare_token(code, t), tokens))


def _substring_leaks(block: str) -> list[str]:
    """All bare-global tokens (substring) that leak in `block`'s code."""
    code = _strip_comments(block)
    return list(filter(code.__contains__, SUT_GLOBAL_LEAK_TOKENS))


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


def _declared_type_names(text: str) -> set[str]:
    """All interface / type-alias names declared across the output's code."""
    declared: set[str] = set()
    for block in _code_blocks(text):
        declared.update(INTERFACE_RE.findall(block))
        declared.update(TYPE_ALIAS_RE.findall(block))
    return declared


def _has_param_typed_by_declared_interface(text: str) -> bool:
    """True if some function/constructor parameter is annotated with an
    interface or type alias declared in the output — the unit names a
    collaborator by a narrow declared type (e.g. `store: OrderStore`),
    which is parameter injection even without a `deps` bag."""
    declared = _declared_type_names(text)
    if not declared:
        return False
    param_re = re.compile(
        r"[(,]\s*(?:private\s+|public\s+|protected\s+|readonly\s+)*"
        r"\w+\s*:\s*(?:" + "|".join(map(re.escape, sorted(declared))) + r")\b"
    )
    return any(param_re.search(block) for block in _code_blocks(text))


def _introduces_injection_seam(text: str) -> bool:
    """True if the refactor names collaborators in the unit's signature:
    constructor injection, a `deps` parameter, or a parameter typed by an
    interface declared in the output (`store: OrderStore`)."""
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


def _wrapper_wires_production_value(block: str) -> bool:
    """True when a module-level const arrow wrapper calls the unit with at
    least one identifier beyond the wrapper's own parameters — the
    function-style composition root (partial application of production
    values). A wrapper that merely forwards its parameters wires nothing;
    neither does a defaulted parameter, which never matches the wrapper
    shape at all."""
    for params, call_args in WRAPPER_WIRING_RE.findall(block):
        param_names = {
            match.group()
            for segment in params.split(",")
            if (match := IDENTIFIER_RE.search(segment)) is not None
        }
        arg_names = set(
            IDENTIFIER_RE.findall(STRING_LITERAL_RE.sub("", call_args))
        )
        if arg_names - param_names:
            return True
    return False


def _has_composition_root(text: str) -> bool:
    """True if the output contains a region that imports a production module
    AND constructs / wires the unit — i.e., a composition root separate from
    the unit itself.

    Heuristic: any code block that contains an `import` line AND one of:

      * a `new <Identifier>(` instantiation,
      * a deps object literal (`: <X>Deps = {` or `const <x>deps = {`), or
      * a const arrow wrapper that partially applies the unit with a value
        beyond its own parameters (`const shipProd = (id) =>
        shipOrder(id, db)`) — the function-style root.

    A defaulted parameter (`store: OrderStore = db`) matches none of these:
    that is production wiring inside the unit, not a composition root.
    """
    instantiation = re.compile(r"\bnew\s+\w+\s*\(")
    deps_object = re.compile(
        r"(?::\s*\w*Deps|\bconst\s+\w*deps\w*)\s*=\s*\{", re.IGNORECASE
    )
    for block in _code_blocks(text):
        if "import " not in block:
            continue
        if (
            instantiation.search(block)
            or deps_object.search(block)
            or _wrapper_wires_production_value(block)
        ):
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


def _di_interface_blocks(text: str) -> list[str]:
    """Code blocks declaring a suspicious DI collaborator interface."""
    return [
        block
        for block in _code_blocks(text)
        if any(
            name
            in INTERFACE_RE.findall(block) + TYPE_ALIAS_RE.findall(block)
            for name in SUSPICIOUS_DI_INTERFACE_NAMES
        )
    ]


# ---------------------------------------------------------------------------
# Assertion functions
# ---------------------------------------------------------------------------


def assert_introduces_injection_seam(run: EvalRun) -> None:
    """Fail unless the refactor names collaborators in the unit's signature."""
    if not _introduces_injection_seam(run.assistant_text):
        raise AssertionFailure(
            "expected refactor to introduce a constructor (or `deps:` "
            "parameter) that names collaborators; saw no injection seam",
            sections=_reply_sections(run),
        )


def _assert_sut_free_of(
    run: EvalRun,
    leak_fn: Callable[[str], list[str]],
    message: str,
) -> None:
    """Shared locate-scan-raise for SUT leak assertions.

    Finds the refactored SUT blocks, applies ``leak_fn`` to each, and
    raises ``message`` with the offending tokens and blocks when any leak;
    raises on a missing SUT block either way.
    """
    blocks = _candidate_sut_blocks(run.assistant_text)
    if not blocks:
        raise AssertionFailure(
            "no refactored SUT block found in the model output",
            sections=_reply_sections(run),
        )
    leaks = list(
        itertools.chain.from_iterable(
            ((tok, _first_line(block)) for tok in leak_fn(block))
            for block in blocks
        )
    )
    if leaks:
        raise AssertionFailure(
            message
            + ": "
            + ", ".join(f"{tok!r} in '{snippet}'" for tok, snippet in leaks),
            sections=_block_sections(
                "Leaking SUT block",
                [b for b in blocks if leak_fn(b)],
            ),
        )


def assert_sut_has_no_bare_globals(run: EvalRun) -> None:
    """Fail if the refactored unit leaks bare global I/O tokens."""
    _assert_sut_free_of(
        run, _substring_leaks, "SUT block(s) leak bare global I/O tokens"
    )


def assert_sut_has_no_bare_module_refs(run: EvalRun) -> None:
    """Fail if the refactored unit leaks bare module references (db.,
    emailService., fetch() — must be member access on this/deps)."""
    _assert_sut_free_of(
        run,
        _bare_token_leaks,
        "SUT block(s) leak bare module references (use `this.X` / "
        "`deps.X` instead)",
    )


def assert_sut_has_no_bare_db_refs(run: EvalRun) -> None:
    """Fail if the refactored unit still reaches the db module bare.

    Scoped variant of `assert_sut_has_no_bare_module_refs` for evals whose
    request decouples only the store: other collaborators may legitimately
    stay hardcoded, but the store must be reached via `this.X` / `deps.X`
    rather than a bare `db.` reference."""
    _assert_sut_free_of(
        run,
        lambda block: _bare_token_leaks(block, ("db.",)),
        "SUT block(s) still reach the db module bare (use `this.X` / "
        "`deps.X` member access for the injected store)",
    )


def assert_preserves_region_rule(run: EvalRun) -> None:
    """Fail if the refactor drops the international/domestic subject line."""
    if not _preserves_region_rule(run.assistant_text):
        raise AssertionFailure(
            "refactor lost the region rule: expected both 'Shipped (intl)' "
            "and 'Shipped' to remain in the output",
            sections=_reply_sections(run),
        )


def assert_composition_root_present(run: EvalRun) -> None:
    """Fail if the output doesn't include a composition root wiring."""
    if not _has_composition_root(run.assistant_text):
        raise AssertionFailure(
            "expected a composition root that imports production modules "
            "and wires them into the unit (e.g., `new OrderShipper(db, "
            "email, Date.now)`, a `productionDeps = {...}` literal, or a "
            "partially-applied wrapper like `const shipOrderWithDb = "
            "(id) => shipOrder(id, db)`)",
            sections=_reply_sections(run),
        )


def assert_narrow_deps_interface(run: EvalRun) -> None:
    """Fail if no narrow interface/type alias is declared for the deps."""
    if not _introduces_narrow_interface(run.assistant_text):
        raise AssertionFailure(
            "expected at least one named interface or type alias for the "
            "injected collaborators (so the unit depends on a narrow "
            "surface, not the concrete production class)",
            sections=_reply_sections(run),
        )


def assert_no_production_default_deps(run: EvalRun) -> None:
    """Fail if any injected dep defaults to a production global."""
    if _has_production_default_dep(run.assistant_text):
        raise AssertionFailure(
            "refactor introduces a production-default dep (e.g., `clock: "
            "Clock = () => Date.now()` or `= Math.random`); injected deps "
            "must be required so callers cannot silently re-couple to "
            "real I/O",
            sections=_block_sections(
                "Offending SUT block",
                [
                    b
                    for b in _candidate_sut_blocks(run.assistant_text)
                    if PROD_DEFAULT_DEP_RE.search(b)
                ],
            ),
        )


def assert_adds_tests(run: EvalRun) -> None:
    """Fail if the output contains no test-like code for the negative case."""
    if not _adds_test_code(run.assistant_text):
        raise AssertionFailure(
            "expected the response to add tests for computeCartTotal "
            "(test/it/describe/expect block); saw none",
            sections=_reply_sections(run),
        )


def assert_no_deps_parameter_added(run: EvalRun) -> None:
    """Fail if a deps parameter is added to a pure function (negative case)."""
    if _adds_deps_param_to_pure_fn(run.assistant_text):
        raise AssertionFailure(
            "DI was incorrectly applied: a `deps:` parameter was added to "
            "a pure function. DI should NOT be applied here — there is "
            "nothing to inject.",
            sections=_block_sections(
                "Offending code block",
                [
                    b
                    for b in _code_blocks(run.assistant_text)
                    if DEPS_PARAM_ANYWHERE_RE.search(b)
                ],
            ),
        )


def assert_no_collaborator_interfaces_introduced(run: EvalRun) -> None:
    """Fail if DI-style collaborator interfaces are introduced for a pure fn."""
    if _introduces_di_interface(run.assistant_text):
        raise AssertionFailure(
            "DI was incorrectly applied: a collaborator interface (Clock, "
            "Rng, Store, Mailer, etc.) was introduced for the pure "
            "calculator.",
            sections=_block_sections(
                "Offending code block",
                _di_interface_blocks(run.assistant_text),
            ),
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
    "sut-has-no-bare-db-refs": assert_sut_has_no_bare_db_refs,
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
