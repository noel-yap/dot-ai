# AGENT.md

Guidance for AI agents working in this repository.

## Layout

- `skills/` — Claude Code refactoring skills, one directory per skill:
  - `dependency-injection/`
  - `extraction-for-clarity/`
  - `functional-core-imperative-shell/`

  Each skill directory holds a `SKILL.md` (the skill itself), `evals/`
  (live Beta-binomial evals graded by structural assertions), and
  `tests/` (deterministic structural tests of the SKILL.md). Shared
  assertion/test helpers live in `skills/test_utils.py`,
  `skills/eval_assertion_utils.py` (before/after snippet extraction), and
  `skills/ts_ast.py` (tree-sitter TypeScript parsing for structural
  graders); the eval harness comes from the pinned `binom-eval` package. See
  `skills/README.md` for how to stand up a new skill's eval suite.
- `commands/` — Claude Code slash commands (`/commit`, `/release`,
  `/unit-test`, `/guidance`).

## Commands

Run from the repo root (forwards to `skills/Makefile`) or from `skills/`:

```sh
make test-unit             # fast deterministic tests, no API calls
make eval                  # all skills' live evals (spawns `claude -p`)
make eval-<skill-name>     # one skill's live evals
make test                  # unit tests then live evals
```

Live evals cost API calls; prefer `make test-unit` while iterating.

## Continuous integration

`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests:
a single `unit-tests` job on Python 3.14 that runs `make install` (deps
from `skills/requirements.txt`, installed with `uv pip install --system`)
then `make test-unit`. Live evals are not run in CI; they resolve
`ANTHROPIC_API_KEY` locally via the vendored `sh-keyring` and are for
local runs only.

> [!CAUTION]
> **ABSOLUTE RULE — NO EXCEPTIONS — OVERRIDES ALL OTHER BEHAVIOR**
>
> **NEVER derive a path from memory, context, or conversation text.**
> **ALWAYS obtain paths by running `pwd`, `ls`, `find`, or `git` commands and copying the output byte-for-byte.**
>
> Unicode characters in paths are NEVER interchangeable with visually similar ASCII characters.
> If you construct a path yourself instead of reading it from shell output, you WILL silently corrupt it.

# Shell Command Rules

## Path construction (MANDATORY — do this every time)

Before using any path in a shell command:
1. Run `ls` or `pwd` to get the exact name from the filesystem.
2. Copy that output verbatim — do not retype it.
3. Quote it with double quotes: `"$PWD/exact name from ls"`.

**Rationale:** Unicode characters look identical to ASCII in many fonts but are different bytes. `：`(U+FF1A) renders like `:` but is a different character. `⋯`(U+22EF) looks like `...` but is one character. Retyping from context substitutes the wrong bytes and silently breaks the command.

## Prefer `"${PWD}"` over computing the workspace or repo root

When you need the workspace or repository root as a base for a path, use the shell-provided `"${PWD}"` rather than computing it (via `git rev-parse --show-toplevel`, `dirname`/`readlink` chains, an editor's workspace-root variable, or any other derivation). In normal operation the current working directory already *is* the workspace root, and `"${PWD}"` holds it byte-exact — deriving the root adds moving parts that can fail, resolve symlinks unexpectedly, or return a directory other than the one you are actually working in.

Compute the root explicitly only when the working directory is genuinely not the root, and even then prefer a single byte-exact shell source (e.g. `"$(git rev-parse --show-toplevel)"`) over hand-assembling the path.

## Prohibited substitutions (examples — not exhaustive)

| Unicode (correct) | ASCII lookalike (FORBIDDEN) |
|---|---|
| `：` U+FF1A full-width colon | `:` U+003A |
| `．` U+FF0E full-width period | `.` U+002E |
| `⋯` U+22EF midline ellipsis | `...` three dots |
| `…` U+2026 horizontal ellipsis | `...` three dots |
| `é` `ñ` composed chars | `e` `n` stripped chars |
| U+00A0 no-break space | U+0020 regular space |
| `　` U+3000 ideographic space | U+0020 regular space |

## Self-check (required before every Bash path)

Ask yourself: "Did I type this path, or did I copy it from shell output?" If you typed it, stop — run `ls`/`pwd` first and use that output instead.

## File tools (Write/Edit/Read): the path rule applies to tool PARAMETERS too

The shell rules above only protect you when you copy shell output *through the shell*. The `file_path` parameter of `Write`/`Edit`/`Read` has no shell in between — emitting the parameter IS retyping the path, and that is exactly where an ASCII lookalike gets substituted for the real Unicode byte. So the byte-for-byte protection does NOT transfer to tool arguments.

**Failure mode:** passing a corrupted absolute path to `Write` does not error — it silently creates a **phantom twin directory tree** next to the real one and reports success at the wrong path.

**Rules when the working dir (or any ancestor) contains non-ASCII:**
1. Do NOT pass an absolute `file_path` to `Write`/`Edit`. Create/edit files through **Bash with relative paths** from a `pwd`-verified cwd: `cat > rel/path <<'EOF' … EOF` for new files. Use `cd "$(git rev-parse --show-toplevel)"` (command substitution preserves the bytes) then operate on relative paths.
   - **When you genuinely need an absolute path, build it from `"${PWD}"`, never by retyping.** The shell holds the cwd as byte-exact (Unicode intact), so `"${PWD}/rel/path"` reconstructs the absolute path without you ever emitting the non-ASCII bytes yourself. Same for other shell-provided path variables (`"$(git rev-parse --show-toplevel)"`, `"${HOME}"`). This is shell-only — it does NOT make it safe to paste the resulting absolute string into a `Write`/`Edit` `file_path`.
2. Only use `Write`/`Edit` with an absolute path when that path is verifiably pure ASCII (e.g. a slugified dir under `~/.claude/...`).
3. **Verify-after-write:** a Write "success" is NOT proof the file landed where intended. Immediately confirm with a relative `ls rel/path` or `git status`, and check no sibling twin dir was spawned.
4. **Symptom → diagnosis:** if a file you just wrote is "not found" by a follow-up relative `Read`/`ls`, suspect path corruption — `find <parent> -name <basename>` to locate twins, confirm the phantom holds only your mis-written files, then `rm -rf` it (guard with a glob + a real-repo marker test like `<dir>/.git` so you never touch the real tree).

# Shell Script Style

When writing or editing shell scripts, follow the [Google Shell Style Guide](https://google.github.io/styleguide/shellguide.html). Key rules:

- **Which shell:** Use `bash` for executable scripts; start with `#!/usr/bin/env bash`. Reserve `sh` (POSIX) only when portability demands it. If a script grows past ~100 lines or needs non-trivial data structures, rewrite it in a more structured language instead.
- **Formatting:** 2-space indent (no tabs), max 80-column lines, blank lines between functions. Put `; then` / `; do` on the same line as `if`/`for`/`while`.
- **Quoting:** Quote everything that could contain a space or expansion: `"$var"`, `"$@"` (never `$*` for arg passing), `"$(cmd)"`. Prefer `"${var}"` braces around variables, especially inside strings.
- **Command substitution & tests:** Use `$(...)`, never backticks. Use `[[ ... ]]` over `[ ... ]` or `test`. Use `(( ... ))` / `$(( ... ))` for arithmetic.
- **Naming:** `lower_snake_case` for functions and local variables; `UPPER_SNAKE_CASE` for constants and exported/environment variables (mark constants `readonly` or `declare -r`). Name a library's functions `package::function`. Use `local` for all function-local variables, and separate declaration from command-substitution assignment so `$?` isn't masked (`local foo; foo="$(cmd)"`).
- **Error handling:** Check return values — either `if ! cmd; then …` or test `$?`. Send error messages to STDERR (a `err()` helper writing to `>&2` is idiomatic). Consider `set -euo pipefail` for non-interactive scripts.
- **Structure:** Constants and `main` at the top/bottom respectively; put all code in functions for anything beyond a trivial script, and call `main "$@"` as the last line. Prefer builtins over external processes (e.g. `${var//foo/bar}` over `sed`).
- **Misc:** Comment non-obvious logic; avoid `eval`; pipe to `while read` rather than `for` over command output; avoid SUID/SGID.

# Python Rules

- Prefer `uv` over `pip install` for installing packages and managing virtual environments.

When writing or editing Python, follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html). Key rules:

- **Formatting:** 4-space indent (no tabs), max 80-column lines, two blank lines between top-level definitions and one between methods. Format with a tool (Black/`ruff format`/YAPF) rather than by hand.
- **Naming:** `module_name`, `package_name`, `ClassName`, `ExceptionName`, `function_name`, `GLOBAL_CONSTANT_NAME`, `method_name`, `local_var_name`. Prefix internal/non-public names with a single leading underscore.
- **Imports:** Import packages and modules only, not individual classes/functions (except `typing`, `collections.abc`, and a few standard exceptions). Use full package paths — no relative imports. Group as: `__future__`, stdlib, third-party, then local; sort each group lexicographically. One import per line.
- **Type annotations:** Annotate public function signatures and any non-obvious code. Use modern typing (`X | None`, built-in generics like `list[int]`).
- **Docstrings:** Triple-quoted `"""..."""` for every public module, class, and function. Use a one-line summary, then `Args:`/`Returns:`/`Raises:` sections for non-trivial functions.
- **Strings:** Prefer f-strings (or `.format()`) over `%` and over `+` concatenation in loops; pick one quote style and stay consistent. Use implicit line-joining for long literals.
- **Exceptions:** Catch specific exceptions, never a bare `except:`; minimize code inside the `try`. Don't use exceptions for ordinary control flow.
- **Comprehensions & generators:** Fine when simple and single-line-ish; fall back to loops once they need multiple `for`/`if` clauses or get hard to read.
- **General:** Prefer `is`/`is not` for `None` checks; use default arg values instead of mutable defaults (never `[]`/`{}` as a default); use `with` for resource management; avoid mutable globals; keep functions focused (roughly <40 lines as a guideline). Lint with `pylint`/`ruff`.

# Communication Style

- **Prefer assertive, first-person phrasing over passive or deferential phrasing** when describing actions you are taking. Say **"I will …"** / **"I've …"** rather than **"Let me …"**, **"I'll try to …"**, or **"Maybe we could …"**. State what you are doing directly instead of asking permission to narrate it.

  | Prefer | Avoid |
  |---|---|
  | "I will run the tests." | "Let me run the tests." |
  | "I've updated the config." | "Let me go ahead and update the config." |
  | "I'll fix the failing case next." | "Maybe I should try fixing the failing case?" |

  This applies **when you have decided to act**. Tentative phrasing is
  fine — and correct — when you are genuinely unsure and are asking a real
  question. The rule bans *false* tentativeness (dressing a decision up as a
  question), not honest questions. If you intend to try something, say so
  directly ("I'm trying to fix the failing case"); reserve "Maybe I
  should …?" / "Should I …?" for moments you actually want the user to
  decide.