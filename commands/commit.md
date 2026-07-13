---
description: "Creates conventional commit with analysis"
allowed-tools:
  - "Bash(git add:*)"
  - "Bash(git status:*)"
  - "Bash(git commit:*)"
  - "Bash(git diff:*)"
  - "Bash(git log:*)"
---
# /commit Command

Analyzes changes and creates a Conventional Commits message.

## Usage

```
/commit [file ...]
```

If files are specified, stage only those files with `git add <files>` before proceeding. If other modified or already-staged files are detected that logically belong with the specified files, ask the user before including them. Otherwise, use whatever is already staged.

## Context
- Git status: !git status
- Diff: !git diff HEAD
- Branch: !git branch --show-current
- Jira task (branch config): !git config branch.$(git branch --show-current).task-id 2>/dev/null || true
- Recent commits: !git log --oneline -5

## Steps
1. If the current branch is `main`, warn the user that they are about to commit directly to `main` and ask for explicit confirmation before proceeding. If they decline, stop.
2. Analyze changes for type (feat, fix, docs, etc.).
3. Determine the Jira ticket ID for the scope:
   - Use the `task-id` branch config value if set.
   - Otherwise, extract the leading Jira ticket ID from the branch name (e.g. `JT-1234` from `JT-1234：some-feature`).
   - If neither is found, derive the scope from the changed code (module/component).
4. Determine if the staged changes are a single cohesive change or multiple unrelated changes.
5. Review the staged changes and suggest improvements before writing the commit message:
   - Look for bugs, unclear names, dead code, redundant code, simpler approaches, areas for refactoring, and missing edge cases.
   - Check for DRY (Don't Repeat Yourself) violations: duplicated logic, repeated literals/constants, or copy-pasted blocks that should be factored into a shared function, constant, or abstraction.
     - Exempt test code: tests favor DAMP (Descriptive And Meaningful Phrases) over DRY, so some repetition in tests is acceptable and should not be flagged as a DRY violation.
   - Check test code for cyclomatic complexity greater than one (complexity = 1 + number of decision points: `if`, `else if`, `case`, `for`, `while`, `&&`, `||`, ternary, `catch`, etc.). Tests should be straight-line. For each test with complexity > 1, recommend extracting the branching logic into a named function and running `/unit-test` on that function so the extracted logic is itself covered by tests.
   - Present each suggestion concisely and ask the user which, if any, to apply.
   - Apply approved suggestions and re-stage the affected files before continuing.
6. Generate 3 Conventional Commits candidates: `<type>(<scope>): <description>` (imperative mood, <72 chars).
   - If multiple unrelated changes: generate candidates for the primary/umbrella change.
7. Pick best one with reasoning.
8. Ask the user: "Why is this change being made?", provide suggestions, and wait for their answer.
9. Incorporate the user's rationale in the commit message body along with what has changed. If multiple unrelated changes are present, present each change as a separate bullet point.
10. If this change affects UX (new behavior, changed prompts, different output), update `README.md` to reflect it and stage it with `git stage README.md`.
   - If files were specified by the user and `README.md` is not among them, ask the user before staging it.
11. If the changes affect project organization (new directories, moved files, renamed modules, added/removed top-level components, changed entry points, or restructured dependencies), update `AGENT.md` to reflect the new structure (creating it if it does not exist) and stage it with `git add AGENT.md`.
    - If files were specified by the user and `AGENT.md` is not among them, ask the user before staging it.
12. Display:
   - Files staged for commit (will be committed)
   - Files with changes not staged (will NOT be committed)
   - Untracked files (will NOT be committed)
   - The full commit message (subject + body with rationale)
   Then ask the user to confirm before proceeding.
13. If confirmed, commit: `git commit -m "<message>"`

## Constraints
- Follow Conventional Commits: https://www.conventionalcommits.org
- No Claude co-authorship footer.
- Keep body optional/short if needed.
