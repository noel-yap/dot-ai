---
description: "Bumps the semver git tag from conventional commits and releases"
allowed-tools:
  - "Bash(git tag:*)"
  - "Bash(git describe:*)"
  - "Bash(git log:*)"
  - "Bash(git status:*)"
  - "Bash(git rev-parse:*)"
  - "Bash(git branch:*)"
  - "Bash(git fetch:*)"
  - "Bash(git remote:*)"
  - "Bash(git push:*)"
  - "Bash(git config:*)"
  - "Bash(git add:*)"
  - "Bash(git commit:*)"
  - "Read"
  - "Edit"
  - "Grep"
  - "Glob"
---
# /release Command

Determines the next [semantic version](https://semver.org) from the Conventional Commits since the last release tag, creates an annotated tag, and pushes it.

## Usage

```
/release [major|minor|patch|<explicit-version>]
```

- With no argument, the bump is inferred from the commits since the last tag (see Steps).
- With `major`, `minor`, or `patch`, force that bump level.
- With an explicit version (e.g. `1.4.0` or `v1.4.0`), use it verbatim.

## Context
- Current branch: !`git branch --show-current`
- Status (must be clean): !`git status --porcelain`
- All tags (newest first): !`git tag --sort=-v:refname`

## Steps
1. **Gather state.** Run these as normal Bash calls (they use shell syntax that cannot be pre-evaluated in Context):
   - Latest tag: `git describe --tags --abbrev=0` (no tags yet if it errors).
   - Commits since the latest tag: `git log --no-merges --pretty=format:'%s' <latest-tag>..HEAD`. If there is no tag, use `git log --no-merges --pretty=format:'%s'` for the whole history.
   - Upstream tracking ref: `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (no upstream if it errors).
   - Tag push remote: `upstream` if `git remote get-url upstream` succeeds; otherwise `origin`.
2. **Preflight.** Abort and report if any of these hold:
   - The working tree is not clean (`git status --porcelain` is non-empty) — ask the user to commit or stash first.
   - `HEAD` is not on a branch, or the branch is behind/ahead of its upstream in a way that means unpushed/unpulled commits. Run `git fetch` first; if local and upstream have diverged, stop and explain.
   - There are no new commits since the latest tag — nothing to release.
3. **Determine the current version.**
   - Parse the latest tag matching `v?MAJOR.MINOR.PATCH`. Preserve whether the existing tags use a `v` prefix; if there are no tags, start from `0.0.0` with a `v` prefix and treat the first release as `v0.1.0`.
4. **Determine the bump** (skip if an explicit version or level was passed as an argument):
   - Inspect every commit subject (and body for footers) since the last tag.
   - `major`: any commit with a `!` after the type/scope (e.g. `feat!:`) or a `BREAKING CHANGE:` / `BREAKING-CHANGE:` footer. (While the current major version is `0`, a breaking change bumps `minor` instead, per semver's initial-development clause — confirm with the user.)
   - `minor`: any `feat` commit and no breaking change.
   - `patch`: only `fix`, `perf`, or other non-feature changes (`refactor`, `docs`, `chore`, etc.) with no `feat` and no breaking change.
   - If there are only `chore`/`docs`/`style`/`test`/`ci` commits and no `fix`/`feat`, tell the user the change set looks non-releasable and ask whether to proceed with a `patch` bump anyway.
5. **Compute the next version** by applying the bump to the current version (reset lower components: a `minor` bump zeroes `patch`; a `major` bump zeroes `minor` and `patch`). Reapply the prefix convention from step 3.
6. **Sync the project's version manifest.** Many projects hardcode the version in a manifest, and their release/publish CI fails if the Git tag and that version disagree — so the manifest must be bumped *before* the tag is created, and the tag must point at the bump commit.
   - **Detect the manifest.** Look (in the repo root, then obvious subdirs) for a static version declaration in, e.g.: `pyproject.toml` (`[project] version` or `[tool.poetry] version`), `package.json` (`"version"`), `Cargo.toml` (`[package] version`), `setup.cfg` / `setup.py`, `*.gemspec`, `build.gradle(.kts)`, `pom.xml`, a plain `VERSION` file, or a `__version__` in the package's `__init__.py`. Use Grep/Glob to find it; don't assume one ecosystem.
   - **If the version is derived from the Git tag** (dynamic / VCS versioning — e.g. `dynamic = ["version"]` with `hatch-vcs`/`setuptools-scm`, `[tool.hatch.version] source = "vcs"`, `versioningit`, `setuptools_scm`, etc.): do **not** edit anything — the tag itself is the source of truth. Note this to the user and skip to step 7.
   - **If a static version is found:** edit just that field to the computed version (strip the `v` prefix for the manifest value, even if tags use it), leaving the rest of the file untouched. If more than one manifest carries the version, update all of them. If none is found, note it and skip.
   - Do not stage or commit yet — step 9 does that as part of confirmed execution.
7. **Draft release notes.** Group the commits since the last tag by type (Features, Fixes, Performance, Other) into a short changelog.
8. **Confirm.** Show the user:
   - Current version → next version, and the reason for the chosen bump.
   - Which manifest file(s) will be bumped (or that versioning is tag-derived / no manifest was found, so no bump commit is needed).
   - The branch the tag will point at and the remote the tag will be pushed to (from step 1).
   - The drafted release notes that will become the annotated tag message.
   Then ask the user to confirm before proceeding.
9. **Commit the version bump (if any).** On confirmation, if step 6 edited a manifest, stage exactly those file(s) and commit them as `chore(release): bump version to <version-without-prefix>` (no other changes in this commit). This commit becomes the tag target so the tagged tree carries the matching version. If nothing was edited, skip.
10. **Tag.** Create an annotated tag at `HEAD` (which is now the bump commit, if one was made):
   `git tag -a <version> -m "<release notes>"`
11. **Push.** Push the branch and the tag:
   - `git push` (the branch — required if a bump commit was made or there are other unpushed commits)
   - `git push <tag-remote> <version>` (the tag — use the tag push remote from step 1: `upstream` when that remote exists, otherwise `origin`)
12. **Report** the created tag, the commit it points at, the manifest bump (if any), and the remote it was pushed to. If the remote is GitHub: tag-triggered release workflows publish on their own, so check for one (`.github/workflows`) before suggesting anything manual. If there's no release workflow and the user wants a GitHub Release, mention they can run `gh release create <version>` (only run it if they ask).

## Constraints
- Never create or move a tag that already exists — if the computed version tag exists, stop and report.
- Never use `git push --force` or `git tag -f`.
- Use annotated tags (`-a`), not lightweight tags.
- Tag only a clean working tree. The tag target must be on the remote-tracked branch — the one exception is a `chore(release)` version-bump commit created in this run, which step 11 pushes immediately after tagging.
- The version-bump commit (step 9) must contain only the manifest version change — never fold other staged work into it.
- No Claude co-authorship footer in the tag or commit messages.
