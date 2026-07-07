"""Shared helpers for per-skill `tests/test_skill.py` suites.

Every skill under `skills/<name>/tests/test_skill.py` validates the
same baseline contract on its `SKILL.md`: a YAML-ish frontmatter block,
a fixed set of section headings, and TypeScript code blocks. The helpers
that parse those structures are identical across skills and live here.

Each skill's `test_skill.py` adds this directory to `sys.path` and
imports from `test_utils` — see e.g. `dependency-injection/tests/
test_skill.py` for the import pattern.

The TypeScript-source helpers below (the BEFORE/AFTER markers, the
function-name / named-constant / vague-name regexes, and the
comment-and-string-stripping brace-depth scanner) are likewise
shared: extraction-for-clarity's eval graders
(`evals/_assertions.py`) and its structure tests import them from
here so the two suites cannot drift apart.

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

# `// BEFORE` / `// AFTER` markers labeling original vs refactored code
# blocks in SKILL.md examples and model responses.
BEFORE_MARK_RE = re.compile(r"//\s*BEFORE\b", re.IGNORECASE)
AFTER_MARK_RE = re.compile(r"//\s*AFTER\b", re.IGNORECASE)

# TypeScript `function name(...)` declarations. Mirrors binom-eval's
# NAMED_FN_RE; defined here too so the `tests/` suites stay stdlib-only.
NAMED_FN_RE = re.compile(r"\bfunction\s+(\w+)\s*\(")

# `const UPPER_SNAKE = ...` named-constant declarations.
UPPER_CONST_RE = re.compile(r"\bconst\s+([A-Z][A-Z0-9_]{2,})\s*(?::[^=]+)?=")

# Helper names that spend indirection without buying intent.
VAGUE_NAME_RE = re.compile(
    r"^(?:helper|helpers|util|utils|fn|func|foo|bar|baz|tmp|temp|stuff"
    r"|misc|thing|things|data|process|handle|compute|calc|do(?:It|Stuff"
    r"|Calc|Work)?)\d*$",
    re.IGNORECASE,
)

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


def strip_code(code: str) -> str:
    """Remove comments and string/template literals from TypeScript code.

    Single-pass scanner so an apostrophe inside a comment or a `//` inside
    a string cannot corrupt the result the way ordered regexes would.
    Stripping template literals also drops their `${...}` braces, which
    keeps `max_brace_depth` an honest measure of control-flow nesting.
    """
    out: list[str] = []
    i, n = 0, len(code)
    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and code[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (code[i] == "*" and code[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch in "'\"`":
            quote = ch
            i += 1
            while i < n and code[i] != quote:
                i += 2 if code[i] == "\\" else 1
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def max_brace_depth(code: str) -> int:
    """Maximum `{`-nesting depth of `code`, comments/strings excluded."""
    depth = 0
    max_depth = 0
    for ch in strip_code(code):
        if ch == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == "}":
            depth = max(0, depth - 1)
    return max_depth


# A fence line: up to three spaces of indent, then ``` and the rest of the
# line as the info string. Mirrors the fence-line parsing in binom_eval's
# `code_blocks`, so the blocks paired below line up with that function's
# output.
_FENCE_LINE_RE = re.compile(r"^ {0,3}```([^`]*)$")

# Info strings treated as TypeScript output, matching binom_eval.code_blocks.
_TS_INFOS = frozenset({"", "ts", "typescript"})

# How many trailing non-blank prose lines are eligible to carry a block's
# label when the label sits above the fence rather than inside it.
_LABEL_ZONE_LINES = 2


def code_blocks_with_labels(text: str) -> list[tuple[str, str]]:
    """TypeScript fenced code blocks paired with the text a label may live in.

    A convention like a `// BEFORE` / `// AFTER` marker is usually written
    inside the fence, but it may just as easily be written as a prose line
    directly above the fence instead. The label text returned here is the
    block body plus the last two non-blank lines of the prose immediately
    preceding the fence, so a marker regex matches either placement without
    the caller needing two code paths. Prose further up (e.g. a mention in
    an earlier paragraph) falls outside that zone and is not considered
    adjacent to the block.

    Blocks are classified as TypeScript the same way `binom_eval.code_blocks`
    does (a bare, `ts`, or `typescript` info string), so the bodies returned
    here line up one-to-one with that function's output.

    Args:
      text: Model or document output that may contain fenced code blocks.

    Returns:
      One `(body, label_text)` pair per closed fenced TypeScript block, in
      document order. `label_text` is the adjacent prose followed by
      `body`; when there is no adjacent prose, `label_text` equals `body`.
    """
    pairs: list[tuple[str, str]] = []
    lines = text.splitlines()
    info: str | None = None
    body_lines: list[str] = []
    fence_start = 0
    prose_start = 0
    for idx, line in enumerate(lines):
        fence = _FENCE_LINE_RE.match(line)
        if info is None:
            if fence:
                info = fence.group(1).strip()
                body_lines = []
                fence_start = idx
        elif fence and not fence.group(1).strip():
            if (info.split() or [""])[0].lower() in _TS_INFOS:
                body = "\n".join(body_lines)
                preceding = lines[prose_start:fence_start]
                prose = [ln for ln in preceding if ln.strip()]
                zone = prose[-_LABEL_ZONE_LINES:]
                label_text = "\n".join([*zone, body]) if zone else body
                pairs.append((body, label_text))
            info = None
            prose_start = idx + 1
        else:
            body_lines.append(line)
    return pairs


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


# ---------------------------------------------------------------------------
# Unit tests for strip_code
# ---------------------------------------------------------------------------


def test_strip_code_removes_line_comment() -> None:
    assert strip_code("a; // { nope\nb;") == "a; \nb;"


def test_strip_code_removes_block_comment() -> None:
    assert strip_code("a; /* { } */ b;") == "a;  b;"


def test_strip_code_removes_string_literal() -> None:
    assert strip_code('x = "{{{";') == "x = ;"


def test_strip_code_removes_template_literal_braces() -> None:
    assert strip_code("x = `a ${b} c`;") == "x = ;"


def test_strip_code_apostrophe_in_comment_does_not_eat_code() -> None:
    assert strip_code("// don't\nif (x) { y(); }") == "\nif (x) { y(); }"


def test_strip_code_escaped_quote_inside_string() -> None:
    assert strip_code('x = "a\\"b"; y;') == "x = ; y;"


def test_strip_code_division_is_not_a_comment() -> None:
    assert strip_code("x = a / b / c;") == "x = a / b / c;"


# ---------------------------------------------------------------------------
# Unit tests for max_brace_depth
# ---------------------------------------------------------------------------


def test_max_brace_depth_flat_code_is_depth_zero() -> None:
    assert max_brace_depth("const x = 1;") == 0


def test_max_brace_depth_single_function_body() -> None:
    assert max_brace_depth("function f() { return 1; }") == 1


def test_max_brace_depth_two_levels() -> None:
    assert max_brace_depth("f() { if (a) { g(); } }") == 2


def test_max_brace_depth_nested_ifs() -> None:
    code = "function f() { if (a) { if (b) { g(); } } }"
    assert max_brace_depth(code) == 3


def test_max_brace_depth_braces_in_strings_do_not_count() -> None:
    assert max_brace_depth('const x = "{{{";') == 0


def test_max_brace_depth_braces_in_comments_do_not_count() -> None:
    assert max_brace_depth("// {{{\nconst x = 1;") == 0


def test_max_brace_depth_unbalanced_close_does_not_go_negative() -> None:
    assert max_brace_depth("} } { ") == 1


# ---------------------------------------------------------------------------
# Unit tests for code_blocks_with_labels
# ---------------------------------------------------------------------------


def test_code_blocks_with_labels_finds_label_inside_fence() -> None:
    text = "```typescript\n// BEFORE\nfunction f() {}\n```\n"
    ((body, label_text),) = code_blocks_with_labels(text)
    assert "function f" in body
    assert BEFORE_MARK_RE.search(label_text)


def test_code_blocks_with_labels_finds_label_directly_above_fence() -> None:
    text = "// BEFORE\n```typescript\nfunction f() {}\n```\n"
    ((body, label_text),) = code_blocks_with_labels(text)
    assert not BEFORE_MARK_RE.search(body)
    assert BEFORE_MARK_RE.search(label_text)


def test_code_blocks_with_labels_finds_label_above_fence_with_blank_line() -> None:
    text = "// BEFORE\n\n```typescript\nfunction f() {}\n```\n"
    ((body, label_text),) = code_blocks_with_labels(text)
    assert not BEFORE_MARK_RE.search(body)
    assert BEFORE_MARK_RE.search(label_text)


def test_code_blocks_with_labels_ignores_mention_several_lines_above() -> None:
    text = (
        "// BEFORE\n"
        "some unrelated prose\n"
        "more unrelated prose\n"
        "```typescript\n"
        "function f() {}\n"
        "```\n"
    )
    ((body, label_text),) = code_blocks_with_labels(text)
    assert not BEFORE_MARK_RE.search(body)
    assert not BEFORE_MARK_RE.search(label_text)


def test_code_blocks_with_labels_unlabeled_block_has_no_marker() -> None:
    text = "```typescript\nfunction f() {}\n```\n"
    ((body, label_text),) = code_blocks_with_labels(text)
    assert not BEFORE_MARK_RE.search(label_text)
    assert not AFTER_MARK_RE.search(label_text)
    assert label_text == body


def test_code_blocks_with_labels_pairs_each_block_with_its_own_prose() -> None:
    text = (
        "// BEFORE\n"
        "```typescript\n"
        "function f() {}\n"
        "```\n"
        "// AFTER\n"
        "```typescript\n"
        "function g() {}\n"
        "```\n"
    )
    (before_body, before_label), (after_body, after_label) = (
        code_blocks_with_labels(text)
    )
    assert BEFORE_MARK_RE.search(before_label)
    assert not AFTER_MARK_RE.search(before_label)
    assert AFTER_MARK_RE.search(after_label)
    assert not BEFORE_MARK_RE.search(after_label)


def test_code_blocks_with_labels_skips_non_typescript_blocks() -> None:
    text = "```json\n{}\n```\n```typescript\nfunction f() {}\n```\n"
    pairs = code_blocks_with_labels(text)
    assert len(pairs) == 1
    assert "function f" in pairs[0][0]


# ---------------------------------------------------------------------------
# Unit tests for the shared TypeScript-source regexes
# ---------------------------------------------------------------------------


def test_vague_name_re_matches_helper() -> None:
    assert VAGUE_NAME_RE.match("helper2")


def test_vague_name_re_matches_do_work() -> None:
    assert VAGUE_NAME_RE.match("doWork")


def test_vague_name_re_ignores_descriptive_name() -> None:
    assert not VAGUE_NAME_RE.match("zoneSurcharge")


def test_named_fn_re_captures_declaration_name() -> None:
    assert NAMED_FN_RE.findall("function zoneRate() {}") == ["zoneRate"]


def test_upper_const_re_captures_constant_name() -> None:
    assert UPPER_CONST_RE.findall("const BASE_RATE = 4.1;") == ["BASE_RATE"]


def test_before_after_marks_are_case_insensitive() -> None:
    assert BEFORE_MARK_RE.search("// before")
    assert AFTER_MARK_RE.search("// After refactor")
