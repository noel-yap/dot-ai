"""Structural unit tests for the extraction-for-clarity SKILL.md.

Validates that the skill follows its own contract: required frontmatter,
required sections, BEFORE/AFTER example pairing, and that each AFTER
example practices what the skill preaches — more named functions than
its BEFORE, named UPPER_SNAKE constants, no vague helper names, and
reduced nesting where the BEFORE was deep. Stdlib + pytest only.

Shared helpers (frontmatter parsing, the code-block and TS-source
regexes, required-section list, token-counting, and the
brace-depth scanner) live in `skills/test_utils.py`.
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
    AFTER_MARK_RE,
    BEFORE_MARK_RE,
    FRONTMATTER_RE,
    NAMED_FN_RE,
    REQUIRED_SECTIONS,
    TS_BLOCK_RE,
    UPPER_CONST_RE,
    VAGUE_NAME_RE,
    count_tokens_mentioned,
    extract_frontmatter,
    max_brace_depth,
)

SKILL_PATH = Path(__file__).resolve().parent.parent / "SKILL.md"

# Depth reduction is only meaningful where the BEFORE was actually deep;
# a conditional-tangle BEFORE can be brace-shallow (ternaries).
DEEP_BEFORE_THRESHOLD = 3

# The validation checklist should mention the concepts the skill grades
# refactors by.
CHECKLIST_CONCEPTS = (
    "behavior",
    "guard clause",
    "abstraction",
    "constant",
    "comment",
    "nesting",
)


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


@pytest.fixture(scope="module")
def example_pairs(body: str) -> list[tuple[str, str]]:
    """(BEFORE, AFTER) code-block pairs, in document order."""
    befores = [b for b in TS_BLOCK_RE.findall(body) if BEFORE_MARK_RE.search(b)]
    afters = [
        b
        for b in TS_BLOCK_RE.findall(body)
        if AFTER_MARK_RE.search(b) and not BEFORE_MARK_RE.search(b)
    ]
    return list(zip(befores, afters))


# ---------------------------------------------------------------------------
# Skill structural tests
# ---------------------------------------------------------------------------


def test_skill_md_exists() -> None:
    assert SKILL_PATH.is_file(), f"SKILL.md not found at {SKILL_PATH}"


def test_frontmatter_has_name(frontmatter: dict[str, str]) -> None:
    assert frontmatter.get("name") == "extraction-for-clarity", (
        f"frontmatter name should be 'extraction-for-clarity', "
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


def test_has_at_least_two_before_after_pairs(
    example_pairs: list[tuple[str, str]],
) -> None:
    assert len(example_pairs) >= 2, (
        "expected at least two BEFORE/AFTER example pairs "
        f"(found {len(example_pairs)})"
    )


def test_each_after_extracts_named_helpers(
    example_pairs: list[tuple[str, str]],
) -> None:
    for before, after in example_pairs:
        before_names = set(NAMED_FN_RE.findall(before))
        after_names = set(NAMED_FN_RE.findall(after))
        new_names = after_names - before_names
        assert len(new_names) >= 2, (
            "each AFTER example must extract at least two new named "
            f"functions; this pair added only {sorted(new_names)}"
        )


def test_after_examples_name_their_constants(
    example_pairs: list[tuple[str, str]],
) -> None:
    for _, after in example_pairs:
        consts = UPPER_CONST_RE.findall(after)
        assert len(consts) >= 3, (
            "each AFTER example should promote bare literals to at least "
            f"three UPPER_SNAKE constants; found {sorted(consts)}"
        )


def test_no_vague_helper_names_in_after_examples(
    example_pairs: list[tuple[str, str]],
) -> None:
    for _, after in example_pairs:
        vague = [n for n in NAMED_FN_RE.findall(after) if VAGUE_NAME_RE.match(n)]
        assert not vague, (
            f"AFTER example uses vague helper name(s): {vague}; the skill "
            "must practice the naming it preaches"
        )


def test_deep_before_examples_get_flattened(
    example_pairs: list[tuple[str, str]],
) -> None:
    deep_pairs = [
        (before, after)
        for before, after in example_pairs
        if max_brace_depth(before) >= DEEP_BEFORE_THRESHOLD
    ]
    assert deep_pairs, (
        "expected at least one example whose BEFORE nests "
        f">= {DEEP_BEFORE_THRESHOLD} deep"
    )
    for before, after in deep_pairs:
        assert max_brace_depth(after) < max_brace_depth(before), (
            "a deep BEFORE example must end up with strictly shallower "
            f"nesting: BEFORE depth {max_brace_depth(before)}, "
            f"AFTER depth {max_brace_depth(after)}"
        )


def test_validation_checklist_covers_key_concepts(body: str) -> None:
    section = re.search(
        r"(?ims)^#{1,6}\s+Validation checklist\s*$(.*?)(?=^#{1,6}\s+|\Z)", body
    )
    assert section, "Validation checklist section not found"
    mentioned = count_tokens_mentioned(CHECKLIST_CONCEPTS, section.group(1))
    assert mentioned >= len(CHECKLIST_CONCEPTS) // 2, (
        "Validation checklist should mention the concepts the skill "
        f"grades by; only {mentioned}/{len(CHECKLIST_CONCEPTS)} were found"
    )


def test_links_to_sibling_skills(body: str) -> None:
    """Extraction complements FCIS (do the I/O split first) and DI (which
    changes signatures; this skill doesn't) — the skill should say so."""
    assert "functional-core-imperative-shell" in body, (
        "expected a wiki-style link [[functional-core-imperative-shell]]"
    )
    assert "dependency-injection" in body, (
        "expected a wiki-style link [[dependency-injection]]"
    )
