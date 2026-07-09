"""Structural unit tests for the functional-core-imperative-shell SKILL.md.

Validates that the skill follows its own contract: required frontmatter,
required sections, and BEFORE/AFTER example pairing. Stdlib + pytest only.

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


IO_TOKENS = (
    "await ",
    "db.",
    "fetch(",
    "Date.now(",
    "Math.random(",
    "process.env",
    "console.",
    "emailService.",
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


# ---------------------------------------------------------------------------
# Skill structural tests
# ---------------------------------------------------------------------------


def test_skill_md_exists() -> None:
    assert SKILL_PATH.is_file(), f"SKILL.md not found at {SKILL_PATH}"


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


def test_validation_checklist_covers_io_tokens(body: str) -> None:
    """The checklist should remind readers to grep for the same tokens we test for."""
    section = re.search(
        r"(?ims)^#{1,6}\s+Validation checklist\s*$(.*?)(?=^#{1,6}\s+|\Z)", body
    )
    assert section, "Validation checklist section not found"
    mentioned = count_tokens_mentioned(IO_TOKENS, section.group(1))
    assert mentioned >= len(IO_TOKENS) // 2, (
        "Validation checklist should mention the I/O tokens the core must avoid; "
        f"only {mentioned}/{len(IO_TOKENS)} were found"
    )