---
name: sync-ship
description: Carry implemented contributor work through integration, delivery, and validation of the requested behavior.
---

# Ship the requested work

Keep the original requested outcome and current branch in scope.
Use only the assigned worktree. Do not create or switch worktrees or operate the coordinator from a contributor checkout.
Use `sync-contributor` to create checked repair commits and `sync-merge-main` when main must merge into this branch.
Do not rewrite history or bypass checks to make status pass.

If this is an authorized repair on coordinator main, return to `sync-operator` for delivery.
Do not wait for another operator to collect a repair already committed in its own checkout.

## Follow the evidence

Run `uv run coloph-sync status` for routine status.
Use its current branch, commit, merged, deployed, checks, phase, reason, and error fields.
Do not reconstruct routine delivery status from tags or inspect another checkout.
Use deeper diagnosis only when the status itself is inconsistent or incomplete.

- If the current branch failed a check or merge, repair it now, commit, and check status again.
- For a merge conflict, read both histories through `sync-merge-main`. Preserve both intended behaviors with a real merge.
- If an error belongs to shared integration or deployment, notify the confirmed operator with its phase and evidence.
  Keep ownership of this branch's outcome while the operator repairs the shared failure.
- If the coordinator has not observed the current tip, wait for pickup. Do not apply an ancestor's old failure to new work.
- If a branch is dirty, blocked, or unmarked, repair the specific reason. An unchanged result alone is not a new failure.
- If both merged and deployed are true, validate delivery. An unrelated later failure does not undo this result.

A repairable failure starts repair rather than a final handoff.
If a repair requires unavailable input or new authority, report the exact requirement.
Never tell the user to operate a recovery command that the assigned operator can run within existing authorization.

## Waiting

For passive waiting, use one reminder attached to this task, with its branch, requested outcome, and validation instructions.
Check every five minutes for the first thirty minutes, then every thirty minutes.
Default to four hours total unless the user specifies another duration.
Keep the original expiry when updating the reminder. Stay quiet while state is unchanged.

Each reminder must load `sync-ship`, check current status, repair actionable branch failures, and coordinate shared failures with the operator.
When delivery succeeds, validate the requested behavior and delete the reminder.
When the wait expires or required input is unavailable, delete the reminder and report the precise remaining work.
A reminder from an old scope must not continue unrelated work.

## Validate and close

After integration and delivery, exercise the changed behavior through the closest safe real user or operator path.
Use the project's validation and issue-closeout rules.
A health check alone does not prove a behavior change.
If delivered validation is unavailable, explain the limitation and use the closest safe equivalent.
Repair in-scope failures and repeat delivery. Keep unrelated failures separate.

Report the outcome, relevant validation, and any remaining work concisely.
Distinguish local checks, branch delivery, and project-defined publication.
Do not report completion while requested work or barrier-held successors remain unfinished.
