# Shared agent working agreement

Codex and Claude Code share this repository with the user, and more than one
agent may be working at the same time. `CLAUDE.md` imports this file so both
tools follow the same agreement.

## Worktrees

- The primary checkout stays on `main`. Never
  switch it to a task branch. Small, stable edits may be made directly on
  `main`; anything substantive, multi-file, or likely to overlap with someone
  else's work goes in a task branch and linked worktree.
- Worktrees live inside the repo under `.worktrees/` (gitignored), named
  `<tool>-<task>` on branch `<tool>/<task>`, created from `main`:

  ```sh
  scripts/worktree_add.sh <task> [claude|codex]   # -> .worktrees/claude-<task> on claude/<task>
  ```

  Claude Code's `EnterWorktree` goes through the same helper via the tracked
  `WorktreeCreate` hook in `.claude/settings.json`. Codex should call the helper
  rather than a bare `git worktree add`.
- A worktree contains committed `HEAD`, not the primary checkout's dirty
  changes. Read those in place; ask only when incorporating them is a real
  choice.
- The gitignored inputs and outputs are shared, not copied: the helper symlinks
  `data/`, `runs/`, `logs/` and `.env` to the primary checkout, so a trial
  launched from any worktree reads the one built dataset and lands in the one
  `runs/` archive. Never build a second `data/` inside a worktree. Each
  worktree gets its own `.venv` (`uv sync`).
- `.worktrees/inspect-eval` is the long-lived checkout of the `inspect-eval`
  branch that the Inspect report exporter publishes to; it is merged into
  `main` periodically. Do not use it for task work.
- Remove a worktree only when its branch is merged and it has no uncommitted
  or untracked work: `git worktree remove .worktrees/<name>` then
  `git branch -d <tool>/<name>`. `git worktree list` is the inventory.

## Merging to `main`

- Merge a small change without asking: a few files, behaviour preserved or
  narrowly fixed, no new dependency, prompt bytes, stored format, or grading
  change.
- Stop at a ready-to-integrate branch for anything else: new or removed
  surface area, a changed prompt or rubric, a changed run or metadata format,
  a new dependency, or results from a paid run. Say what changed, how it was
  verified (`uv run ruff check . && uv run pytest -q`), and what risk remains,
  then ask. An instruction to merge, integrate, finish, or ship in the original
  request is that approval already given.
- A dirty `main` is not a reason to stop. If the dirty paths and the incoming
  diff are disjoint, merge; if they overlap, reconcile with a path-scoped
  stash and say so. Another agent's uncommitted work is that agent's to commit;
  never discard it.
- Push `main` after merging. Collaborators commit to `main` directly; fetch
  before merging and never force-push.

## Runs and results

- `runs/` and `data/` are gitignored and exist only in the primary checkout.
- Never edit a script that a running trial is executing in place (the shell
  reads it incrementally); write a copy and `mv` it over.
- Reports and grades that feed the README numbers are tracked under
  `reports/` and `benchmark/`. Regenerate through the scripts that produced
  them and commit the outputs with the code change that changed them.
