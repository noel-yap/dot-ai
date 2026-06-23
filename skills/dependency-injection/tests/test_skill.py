"""Structural unit tests for the dependency-injection SKILL.md.

Validates that the skill follows its own contract: required frontmatter,
required sections, BEFORE/AFTER example pairing, and that any code block
labelled `// SUT (under test)` contains no bare module/global I/O tokens
(i.e., references not preceded by `.` — `this.X` and `deps.X` are fine,
bare `db.` / `Date.now(` are not). Stdlib + pytest only.

Shared helpers (frontmatter parsing, code-block regex, required-section
list, token-counting) live in `skills/test_utils.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Add `skills/` to sys.path so the shared `test_utils` module is
# importable regardless of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from test_utils import (  # noqa: E402
    FRONTMATTER_RE,
    REQUIRED_SECTIONS,
    TS_BLOCK_RE,
    count_tokens_mentioned,
    extract_frontmatter,
)

SKILL_PATH = Path(__file__).resolve().parent.parent / "SKILL.md"

SUT_BLOCK_RE = re.compile(
    r"//\s*SUT\s*\(under test\)[^\n]*\n(.*?)//\s*end\s+SUT\s*\(under test\)",
    re.IGNORECASE | re.DOTALL,
)
SHELL_MARKER_RE = re.compile(r"//\s*Composition root\b", re.IGNORECASE)

# Tokens that must never appear inside a SUT block as bare references.
# Substring-only checks for unambiguous globals; the SUT body must reach
# any I/O via `this.X` or `deps.X` instead.
SUBSTRING_LEAK_TOKENS = (
    "Date.now(",
    "Math.random(",
    "process.env",
    "console.",
)

# Tokens that are legitimate member accesses when prefixed by `.` (so
# `this.db.` / `deps.db.` are OK), but illegitimate as bare references.
# Pattern: token NOT preceded by a `.` or word character.
PREFIXED_LEAK_TOKENS = (
    "db.",
    "emailService.",
    "fetch(",
)


# ---------------------------------------------------------------------------
# DI-specific helper
# ---------------------------------------------------------------------------


def has_bare_token(block: str, token: str) -> bool:
    """Return True if `token` appears in `block` not preceded by a `.` or
    word character — i.e., as a bare identifier rather than a member access.

    Used to distinguish `this.db.` (allowed) from `db.` (a leak).
    """
    pattern = re.compile(r"(?<![.\w])" + re.escape(token))
    return bool(pattern.search(block))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(skill_text: str) -> dict[str, str]:
    return extract_frontmatter(skill_text)


@pytest.fixture(scope="module")
def body(skill_text: str) -> str:
    return FRONTMATTER_RE.sub("", skill_text, count=1)


# ---------------------------------------------------------------------------
# Skill structural tests
# ---------------------------------------------------------------------------


def test_skill_md_exists() -> None:
    assert SKILL_PATH.is_file(), f"SKILL.md not found at {SKILL_PATH}"


def test_frontmatter_has_name(frontmatter: dict[str, str]) -> None:
    assert frontmatter.get("name") == "dependency-injection", (
        f"frontmatter name should be 'dependency-injection', "
        f"got {frontmatter.get('name')!r}"
    )


def test_frontmatter_has_description(frontmatter: dict[str, str]) -> None:
    desc = frontmatter.get("description", "")
    assert len(desc) >= 80, (
        f"description should be substantive (>=80 chars) to help triggering; "
        f"got {len(desc)} chars"
    )


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_required_section_present(body: str, section: str) -> None:
    pattern = rf"(?im)^#{{1,6}}\s+.*{re.escape(section)}"
    assert re.search(pattern, body), f"missing section heading: {section!r}"


def test_has_at_least_two_typescript_blocks(body: str) -> None:
    blocks = TS_BLOCK_RE.findall(body)
    assert len(blocks) >= 2, "expected at least two TypeScript code blocks"


def test_before_and_after_examples_present(body: str) -> None:
    assert re.search(r"//\s*BEFORE\b", body), "skill must include a BEFORE example"
    assert re.search(r"//\s*AFTER\b", body), "skill must include an AFTER example"


def test_sut_blocks_are_marked(body: str) -> None:
    blocks = SUT_BLOCK_RE.findall(body)
    assert len(blocks) >= 2, (
        "expected at least two `// SUT (under test)` ... `// end SUT (under test)` "
        "regions (one per TypeScript example) so structural tests can verify "
        "the refactored unit has no bare I/O leaks"
    )


def test_composition_root_marker_present(body: str) -> None:
    assert SHELL_MARKER_RE.search(body), (
        "skill should explicitly label the composition root in at least one example"
    )


@pytest.mark.parametrize("token", SUBSTRING_LEAK_TOKENS)
def test_sut_blocks_have_no_substring_leak(body: str, token: str) -> None:
    """Globals must never appear inside a SUT block — substring match is enough."""
    for block in SUT_BLOCK_RE.findall(body):
        assert token not in block, (
            f"SUT block leaks bare global {token!r}; first 200 chars:\n"
            f"{block.strip()[:200]}"
        )


@pytest.mark.parametrize("token", PREFIXED_LEAK_TOKENS)
def test_sut_blocks_have_no_bare_module_ref(body: str, token: str) -> None:
    """Module references must be member accesses (`this.X`/`deps.X`), not bare."""
    for block in SUT_BLOCK_RE.findall(body):
        assert not has_bare_token(block, token), (
            f"SUT block leaks bare module reference {token!r}; first 200 chars:\n"
            f"{block.strip()[:200]}"
        )


def test_validation_checklist_covers_io_tokens(body: str) -> None:
    """The checklist should remind readers to grep for the same tokens we test for."""
    section = re.search(
        r"(?ims)^#{1,6}\s+Validation checklist\s*$(.*?)(?=^#{1,6}\s+|\Z)", body
    )
    assert section, "Validation checklist section not found"
    tokens = SUBSTRING_LEAK_TOKENS + PREFIXED_LEAK_TOKENS
    mentioned = count_tokens_mentioned(tokens, section.group(1))
    assert mentioned >= len(tokens) // 2, (
        "Validation checklist should mention the I/O tokens the SUT must avoid; "
        f"only {mentioned}/{len(tokens)} were found"
    )


def test_links_to_functional_core_skill(body: str) -> None:
    """DI and FCIS are complementary; the skill should link to FCIS for the
    'extract a pure core first' case."""
    assert "functional-core-imperative-shell" in body, (
        "expected a wiki-style link [[functional-core-imperative-shell]] "
        "to point readers to the complementary skill"
    )


# ---------------------------------------------------------------------------
# Unit tests for the DI-specific helper
# ---------------------------------------------------------------------------


def test_has_bare_token_matches_unprefixed() -> None:
    assert has_bare_token("db.getOrder(id)", "db.")


def test_has_bare_token_matches_at_line_start() -> None:
    assert has_bare_token("\ndb.foo()\n", "db.")


def test_has_bare_token_ignores_member_access() -> None:
    assert not has_bare_token("this.db.getOrder(id)", "db.")


def test_has_bare_token_ignores_deps_member_access() -> None:
    assert not has_bare_token("deps.db.getOrder(id)", "db.")


def test_has_bare_token_ignores_word_prefix() -> None:
    """`mydb.x` is some other identifier, not our bare `db.`."""
    assert not has_bare_token("mydb.getOrder(id)", "db.")


def test_has_bare_token_fetch_paren() -> None:
    assert has_bare_token("await fetch(url)", "fetch(")


def test_has_bare_token_this_fetch_ok() -> None:
    assert not has_bare_token("await this.fetch(url)", "fetch(")