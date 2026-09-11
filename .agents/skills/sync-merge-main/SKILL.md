---
name: sync-merge-main
description: Merge the configured local main branch into the current contributor branch with history review, semantic conflict repair, validation, and return to sync-finish.
---

# Merge Main

Use this skill when a contributor branch needs local main for validation, compatibility, closeout, or repair of a current sync conflict.

A current sync merge failure is actionable. Do not end the turn or only report it. Integrate local main, resolve every textual and semantic conflict, validate the result, and return to `sync-finish`.

Read the repository's Git, commit, and validation instructions before you start.

## Non-negotiable rules

- Merge the configured local main branch. Never merge `origin/main`.
- A branch owner repairs a current sync merge failure.
- Read both histories from their shared merge base before `git merge`.
- Do not abort a failed merge before diagnosis.
- Resolve behavior and data-model intent, not only conflict markers.
- Do not use `git checkout --ours`, `git checkout --theirs`, or a whole-file checkout to resolve a conflict.
- Do not rebase, force-push, or recreate selected main changes.
- Preserve hook-managed commit metadata. Use Git's generated merge subject.

## Prepare

1. Read `main_ref` from `coloph-sync.toml`. Use `main` when the configuration uses the default.
2. Run `git branch --show-current` and `git status --short --branch`.
3. If the checkout is detached, create a descriptive `codex/` branch at its current HEAD.
4. If the branch is the local main branch, stop. This skill is for contributor branches.
5. Commit or explicitly park a dirty tree before you merge.
6. If local main is already an ancestor of `HEAD`, do not create a no-op merge.
7. If the tip is `Sync-State: wip` or `Sync-State: failed`, create a reviewed `Sync-State: dont-merge` scaffold before the merge.

## Read both histories

Compute the merge base. Read the branch commits and the incoming main commits from that base in chronological order.

Build an intent map before you change files:

- What refactors or contract changes exist on the branch?
- What refactors or contract changes arrive from main?
- Which modules, migrations, interfaces, or tests changed on both sides?

## Merge and resolve

Run `git merge <main-ref> --no-edit`.

If the merge conflicts, list the unresolved files. For every file, inspect its commits and introducing diffs on both sides of the merge base.

Classify each conflict:

- Trivial: formatting, import order, or the same invariant.
- Refactor-coupled: one side changed a contract and the other side uses the old contract.
- Escalation: product behavior, data policy, permission behavior, or migration order needs new authority.

Resolve by meaning. Preserve required invariants from both sides. Port branch features to the main architecture. Update callers, tests, configuration, and migrations when the resolved contract requires it.

After textual resolution, do a refactor-drift sweep. Search for old symbols, deprecated tables or columns, old helpers, and old route or CLI contracts. Correct clear fallout now.

For complex conflicts, read [conflict review patterns](references/conflict-review.md) before you save the merge.

## Validate, save, and return

Run focused checks and the repository's required checks. Review `git status --short --branch`. Stage the resolved files. Complete the merge with Git's generated message.

Report the merge base, important branch and main commits, semantic risks, chosen resolution, checks, and any escalation.

Run `uv run coloph-sync status` for the new tip. If it has not checked that tip, wait through `sync-finish`. If it records another merge failure for that tip, repeat this workflow.

Return to `sync-finish` in the same turn. Do not give a final handoff from this workflow.
