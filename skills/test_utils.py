"""Shared helpers for per-skill `tests/test_skill.py` suites.

Every skill under `skills/<name>/tests/test_skill.py` validates the
same baseline contract on its `SKILL.md`: a YAML-ish frontmatter block,
a fixed set of section headings, and TypeScript code blocks. The helpers
that parse those structures are identical across skills and live here.

Each skill's `test_skill.py` adds this directory to `sys.path` and
imports from `test_utils` — see e.g. `dependency-injection/tests/
test_skill.py` for the import pattern.

This module also carries pytest unit tests for the helpers themselves
(`parse_frontmatter_block`, `extract_frontmatter`, `count_tokens_mentioned`).
Those tests live with the helpers so a single source of truth covers
both behaviour and the contract callers rely on. Stdlib + pytest only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import pytest

# ---------------------------------------------------------------------------
# Shared regexes
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
TS_BLOCK_RE = re.compile(r"```(?:ts|typescript)\n(.*?)```", re.DOTALL)

# ---------------------------------------------------------------------------
# Required SKILL.md section headings
# ---------------------------------------------------------------------------

# Every skill's SKILL.md should declare these sections so readers find
# the same structure across skills. Skills MAY add more sections; they
# MUST NOT drop any of these.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "When to use",
    "When NOT to use",
    "Core idea",
    "Refactoring procedure",
    "TypeScript example 1",
    "TypeScript example 2",
    "Anti-patterns",
    "Validation checklist",
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def parse_frontmatter_block(block: str) -> dict[str, str]:
    """Parse a YAML-ish frontmatter block (the text *between* the --- lines).

    Skips blank lines and `#`-prefixed comments. Strips surrounding single or
    double quotes from values. Raises AssertionError on malformed lines
    (no colon present).
    """
    fm: dict[str, str] = {}
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition(":")
        assert sep, f"malformed frontmatter line: {raw!r}"
        fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def extract_frontmatter(text: str) -> dict[str, str]:
    """Extract a frontmatter dict from a markdown document that opens with a
    `---`-delimited YAML-ish block. Raises AssertionError if absent."""
    match = FRONTMATTER_RE.match(text)
    assert match, "document must start with a YAML frontmatter block"
    return parse_frontmatter_block(match.group(1))


def count_tokens_mentioned(tokens: Iterable[str], text: str) -> int:
    """Count how many `tokens` appear in `text` after normalising each token
    by stripping surrounding whitespace and any trailing `(`."""
    return sum(1 for tok in tokens if tok.strip().rstrip("(") in text)


# ---------------------------------------------------------------------------
# Unit tests for parse_frontmatter_block
# ---------------------------------------------------------------------------


def test_parse_frontmatter_block_empty_input_yields_empty_dict() -> None:
    assert parse_frontmatter_block("") == {}


def test_parse_frontmatter_block_skips_blank_line() -> None:
    assert parse_frontmatter_block("   \nname: foo") == {"name": "foo"}


def test_parse_frontmatter_block_skips_comment_line() -> None:
    assert parse_frontmatter_block("# heading\nname: foo") == {"name": "foo"}


def test_parse_frontmatter_block_skips_indented_comment_uses_lstrip() -> None:
    assert parse_frontmatter_block("   # indented\nname: foo") == {"name": "foo"}


def test_parse_frontmatter_block_keeps_real_line() -> None:
    assert parse_frontmatter_block("name: foo") == {"name": "foo"}


def test_parse_frontmatter_block_strips_double_quotes() -> None:
    assert parse_frontmatter_block('name: "foo"') == {"name": "foo"}


def test_parse_frontmatter_block_strips_single_quotes() -> None:
    assert parse_frontmatter_block("name: 'foo'") == {"name": "foo"}


def test_parse_frontmatter_block_keeps_inner_colons_in_value() -> None:
    assert parse_frontmatter_block("desc: a: b") == {"desc": "a: b"}


def test_parse_frontmatter_block_raises_on_malformed_line() -> None:
    with pytest.raises(AssertionError, match="malformed frontmatter line"):
        parse_frontmatter_block("no_colon_here")


def test_parse_frontmatter_block_later_keys_overwrite_earlier() -> None:
    assert parse_frontmatter_block("a: 1\nb: 2\na: 3") == {"a": "3", "b": "2"}


def test_parse_frontmatter_block_strips_key_whitespace() -> None:
    assert parse_frontmatter_block("  name  : foo") == {"name": "foo"}


def test_parse_frontmatter_block_strips_leading_whitespace_before_quoted_value() -> None:
    assert parse_frontmatter_block('name:   "foo"') == {"name": "foo"}


def test_parse_frontmatter_block_preserves_internal_single_quote() -> None:
    assert parse_frontmatter_block("name: it's a tool") == {"name": "it's a tool"}


def test_parse_frontmatter_block_empty_key_when_line_starts_with_colon() -> None:
    assert parse_frontmatter_block(": foo") == {"": "foo"}


def test_parse_frontmatter_block_empty_value_when_line_ends_with_colon() -> None:
    assert parse_frontmatter_block("name:") == {"name": ""}


def test_parse_frontmatter_block_strips_double_then_single_quote_chain() -> None:
    # `"'foo'"` — outer doubles stripped first, then inner singles.
    assert parse_frontmatter_block("name: \"'foo'\"") == {"name": "foo"}


def test_parse_frontmatter_block_single_chain_preserves_inner_double_quotes() -> None:
    # `'"foo"'` — outer singles stripped; inner doubles are not at the
    # ends after that pass and survive.
    assert parse_frontmatter_block("name: '\"foo\"'") == {"name": '"foo"'}


def test_parse_frontmatter_block_strips_only_leading_double_quote() -> None:
    # Asymmetric quoting: only the leading `"` is at the end of the value
    # before the strip chain, so `.strip('"')` removes just the leading one.
    assert parse_frontmatter_block('name: "foo') == {"name": "foo"}


# ---------------------------------------------------------------------------
# Unit tests for extract_frontmatter
# ---------------------------------------------------------------------------


def test_extract_frontmatter_parses_well_formed_document() -> None:
    doc = "---\nname: foo\ndescription: bar\n---\nbody text\n"
    assert extract_frontmatter(doc) == {"name": "foo", "description": "bar"}


def test_extract_frontmatter_raises_when_no_frontmatter_block() -> None:
    with pytest.raises(AssertionError, match="frontmatter"):
        extract_frontmatter("no frontmatter here\n")


def test_extract_frontmatter_returns_empty_dict_for_empty_block() -> None:
    assert extract_frontmatter("---\n\n---\n") == {}


def test_extract_frontmatter_raises_when_closing_marker_missing() -> None:
    with pytest.raises(AssertionError, match="frontmatter"):
        extract_frontmatter("---\nname: foo\nbody without closing marker\n")


def test_extract_frontmatter_raises_when_content_precedes_opening_marker() -> None:
    with pytest.raises(AssertionError, match="frontmatter"):
        extract_frontmatter("intro line\n---\nname: foo\n---\n")


def test_extract_frontmatter_parses_three_keys() -> None:
    doc = "---\nname: foo\ndescription: bar\nextra: baz\n---\nrest\n"
    assert extract_frontmatter(doc) == {
        "name": "foo",
        "description": "bar",
        "extra": "baz",
    }


# ---------------------------------------------------------------------------
# Unit tests for count_tokens_mentioned
# ---------------------------------------------------------------------------


def test_count_tokens_mentioned_no_tokens() -> None:
    assert count_tokens_mentioned((), "anything") == 0


def test_count_tokens_mentioned_token_present() -> None:
    assert count_tokens_mentioned(("await ",), "we await something") == 1


def test_count_tokens_mentioned_token_absent() -> None:
    assert count_tokens_mentioned(("await ",), "synchronous only") == 0


def test_count_tokens_mentioned_strips_trailing_paren_before_match() -> None:
    assert count_tokens_mentioned(("fetch(",), "use fetch sparingly") == 1


def test_count_tokens_mentioned_strips_whitespace_before_match() -> None:
    assert count_tokens_mentioned(("await ",), "no await calls allowed") == 1


def test_count_tokens_mentioned_mixed_present_and_absent() -> None:
    text = "fetch and console. but no d-b prefix here"
    assert count_tokens_mentioned(("fetch(", "db.", "console."), text) == 2


def test_count_tokens_mentioned_strips_multiple_trailing_parens() -> None:
    assert count_tokens_mentioned(("foo((",), "foo bar") == 1


def test_count_tokens_mentioned_empty_after_normalisation_matches_any_text() -> None:
    # Whitespace + trailing `(` reduce to the empty string, which is
    # always `in` any other string.
    assert count_tokens_mentioned(("(",), "any text") == 1


def test_count_tokens_mentioned_is_case_sensitive() -> None:
    assert count_tokens_mentioned(("Foo",), "foo bar") == 0


def test_count_tokens_mentioned_matches_substring_within_word() -> None:
    assert count_tokens_mentioned(("foo",), "foobar") == 1


def test_count_tokens_mentioned_combines_whitespace_and_trailing_paren_strip() -> None:
    assert count_tokens_mentioned(("  bar(  ",), "bar baz") == 1


def test_count_tokens_mentioned_counts_each_duplicate_token_separately() -> None:
    assert count_tokens_mentioned(("foo", "foo"), "foo bar") == 2


def test_count_tokens_mentioned_preserves_leading_paren() -> None:
    # rstrip only strips trailing `(`; a leading `(` is preserved and
    # must still appear in the text to count.
    assert count_tokens_mentioned(("(foo",), "(foo bar") == 1


def test_count_tokens_mentioned_does_not_strip_internal_whitespace() -> None:
    assert count_tokens_mentioned(("foo bar",), "foo bar baz") == 1
    assert count_tokens_mentioned(("foo bar",), "foobar baz") == 0