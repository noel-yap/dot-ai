---
description: "Generates unit tests for functions in the given files"
---
# /unit-test Command

Generates unit tests for functions in the specified source files.

## Usage

```
/unit-test <file> [file ...]
```

At least one file path must be provided. If none is provided, ask the user which files to target and stop.

## Steps
1. For each file argument:
   a. Read the file and identify every function, method, or callable defined in it.
   b. For each function, compute its cyclomatic complexity (count decision points: `if`, `else if`, `case`, `for`, `while`, `&&`, `||`, ternary, `catch`, etc., plus 1).
   c. Select only functions whose cyclomatic complexity is **strictly greater than 1**. Skip the rest (note them for the final report).
2. Detect the existing test framework and test file conventions for the project:
   - Look at `package.json`, `pyproject.toml`, `pom.xml`, `build.gradle`, `Cargo.toml`, `go.mod`, etc., and at existing test files near the source files.
   - Match the existing style (naming, location, imports, assertion library, mocking approach). Do not introduce a new framework.
   - If no test framework is detectable, ask the user which to use before generating tests.
3. Assess each selected function for testability and refactor if needed:
   - Flag functions that are hard to test in isolation: hidden dependencies (direct calls to `new Date()`, `Math.random()`, file I/O, network, globals, singletons), deeply nested logic, mixed concerns (I/O interleaved with pure logic), excessive parameter lists, or untestable private state.
   - For each flagged function, propose a minimal refactor (e.g. inject the dependency, split pure logic from side effects, extract a helper, parameterize a hard-coded value).
   - Present each proposal concisely and ask the user whether to apply it. Apply only those the user approves.
   - Preserve external behavior; do not change public signatures unless the user explicitly approves.
   - After approved refactors, re-read the affected files before proceeding.
4. For each selected function, design test cases that achieve **Modified Condition / Decision Coverage**:
   - Identify every atomic boolean condition in every decision.
   - For each atomic condition `c`, produce two test cases that differ only in `c`'s value and produce different decision outcomes — demonstrating that `c` independently affects the outcome.
   - Cover every branch (both sides of every decision) and every reachable path through `case`/`switch` arms.
   - Include boundary inputs for numeric/length comparisons (`<`, `<=`, `>`, `>=`, `==`).
   - Include tests for thrown exceptions and early returns where applicable.
   - Deduplicate: if one input already satisfies the independence requirement for multiple conditions, reuse it.
5. Write the tests into the appropriate test file(s):
   - Prefer adding to an existing co-located test file if one exists; otherwise create one following project conventions.
   - Each test name should describe the input scenario and expected outcome in plain language (e.g. `returns_zero_when_list_is_empty`), not reference internal coverage concepts.
   - Use the project's existing mocking / fixture style for external dependencies.
6. Run the test suite (using the project's standard command) to confirm the new tests pass. If any fail, fix the tests (not the source) unless a test failure reveals a real bug in the source — in that case, surface it to the user and stop.
7. Report back:
   - List of functions for which tests were added.
   - List of functions skipped because no branching logic was present.
   - Test command run and its result.

## Constraints
- **Do not** mention cyclomatic complexity, branch/condition/decision coverage, or MC/DC in:
  - Generated test code (names, comments, docstrings, descriptions).
  - Commit messages, PR descriptions, or any user-facing output.
  - Conversational replies to the user about this task.
  Describe tests purely in terms of the input scenarios and expected behavior.
- Do not modify the source files under test unless the user explicitly approves a testability refactor (step 3) or a fix for a real bug discovered during step 6.
- Do not generate tests for functions with cyclomatic complexity of 1 (straight-line code, single return, no branches).
- Match the project's existing test conventions exactly; do not introduce new dependencies without asking.
- Keep each test focused on one scenario; avoid combining multiple unrelated assertions into one test.
