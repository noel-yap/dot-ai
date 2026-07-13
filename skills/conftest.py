from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make test_utils importable for all skill test modules.
sys.path.insert(0, str(Path(__file__).parent))

from test_utils import FRONTMATTER_RE, extract_frontmatter  # noqa: E402


@pytest.fixture(scope="module")
def skill_path(request: pytest.FixtureRequest) -> Path:
    """SKILL.md for the skill whose test module is currently running."""
    return request.path.parents[1] / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text(skill_path: Path) -> str:
    return skill_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(skill_text: str) -> dict[str, str]:
    return extract_frontmatter(skill_text)


@pytest.fixture(scope="module")
def body(skill_text: str) -> str:
    return FRONTMATTER_RE.sub("", skill_text, count=1)
