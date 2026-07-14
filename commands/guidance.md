---
description: "Adds shared guidance usable by both Claude and Cursor"
---
# /guidance Command

Records new tool-agnostic guidance into the shared `~/.ai/AGENT.md` file.

## Usage

```
/guidance <guidance text>
```

If no arguments are given, ask the user what guidance they want to record and stop.

## Steps

1. Restate the user's rough guidance as clear, imperative, tool-agnostic instruction text. It must not reference mechanics specific to one tool (e.g. Claude subagents/Task tool, Cursor Composer/modes). If the guidance is inherently Claude-Code-specific and cannot be phrased tool-agnostically, say so, and propose adding it to `~/.claude/CLAUDE.md` instead — get the user's confirmation before writing there.
2. Read `~/.ai/AGENT.md` and check whether existing guidance already covers or contradicts the new guidance.
   - If it duplicates existing guidance, say so and stop.
   - If it contradicts existing guidance, surface the conflict and ask the user which should win.
3. Place the new guidance in the most fitting existing section of `AGENT.md`, or append a new `# <Topic>` section at the end if none fits. Match the file's existing formatting style (markdown `# Section` / `## Subsection` headers, bold key phrases, tables and `> [!CAUTION]` callouts where appropriate).
4. Apply the edit, then show the user a `git -C ~/.ai diff AGENT.md` of the change.
5. Remind the user that the file is version-controlled and they can run `/commit` to commit it. Do not commit automatically.

## Notes

Edits go to `~/.ai/AGENT.md` because it is the single source of truth shared by both Claude Code and Cursor: Claude Code reads it via an import in `~/.claude/CLAUDE.md` that references `~/.claude/AGENT.md` (a symlink to `~/.ai/AGENT.md`), and Cursor reads it via project-root `AGENTS.md` symlinks pointing at the same file. Guidance specific to Claude Code alone belongs in `~/.claude/CLAUDE.md` instead.