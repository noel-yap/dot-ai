"""Structural unit tests for the functional-core-imperative-shell SKILL.md.

Validates that the skill follows its own contract: required frontmatter,
required sections, BEFORE/AFTER example pairing, and that any code block
labelled `// pure core` contains no I/O tokens. Stdlib + pytest only.

Shared helpers (frontmatter parsing, code-block regex, required-section
list, token-counting) live in `skills/test_utils.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from test_utils import (
    REQUIRED_SECTIONS,
    TS_BLOCK_RE,
    count_tokens_mentioned,
)

PURE_CORE_BLOCK_RE = re.compile(
    r"//\s*pure core\b[^\n]*\n(.*?)//\s*end pure core\b",
    re.IGNORECASE | re.DOTALL,
)
SHELL_MARKER_RE = re.compile(r"//\s*imperative shell\b", re.IGNORECASE)

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
# Skill structural tests
# ---------------------------------------------------------------------------


def test_skill_md_exists(skill_path) -> None:
    assert skill_path.is_file(), f"SKILL.md not found at {skill_path}"


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


def test_pure_core_blocks_are_marked(body: str) -> None:
    blocks = PURE_CORE_BLOCK_RE.findall(body)
    assert len(blocks) >= 2, (
        "expected at least two `// pure core` ... `// end pure core` regions "
        "to validate (one per TypeScript example)"
    )


@pytest.mark.parametrize(
    "token", IO_TOKENS, ids=[t.strip().rstrip("(") or repr(t) for t in IO_TOKENS]
)
def test_pure_core_blocks_contain_no_io(body: str, token: str) -> None:
    for block in PURE_CORE_BLOCK_RE.findall(body):
        assert token not in block, (
            f"pure-core block leaks I/O token {token!r}; first 200 chars:\n"
            f"{block.strip()[:200]}"
        )


def test_imperative_shell_marker_present(body: str) -> None:
    assert SHELL_MARKER_RE.search(body), (
        "skill should explicitly label the imperative shell side of at least one example"
    )


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


def test_trigger_concepts_covered_by_skill(skill_path: Path, body: str) -> None:
    """Deterministic proxy for the live skill-trigger eval.

    Each ``trigger_concepts`` entry in ``evals.json`` must appear in both the
    eval's prompt and the skill's ``When to use`` section.  If the metadata
    doesn't mention the same terms as the prompt, Claude won't invoke the skill
    — this catches that without calling claude.
    """
    evals_path = skill_path.parent / "evals" / "typescript" / "evals.json"
    if not evals_path.exists():
        pytest.skip("no evals.json found")

    when_match = re.search(
        r"(?ims)^#{1,6}\s+When to use\s*$(.*?)(?=^#{1,6}\s+|\Z)", body
    )
    assert when_match, "When to use section not found"
    when_text = when_match.group(1)

    evals = json.loads(evals_path.read_text(encoding="utf-8"))["evals"]
    for ev in evals:
        for concept in ev.get("trigger_concepts", []):
            assert concept in when_text, (
                f"eval {ev['id']!r}: trigger_concept {concept!r} not found "
                f"in 'When to use' section — add it or update trigger_concepts"
            )
            assert concept in ev["prompt"], (
                f"eval {ev['id']!r}: trigger_concept {concept!r} declared but "
                f"not present in the eval prompt"
            )