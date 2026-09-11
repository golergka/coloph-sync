---
name: sync-finish
description: Close out committed contributor work through integration, delivery, and project validation. Repair actionable branch failures in the same turn.
---

# Finish Work

Use this skill after a normal contributor commit. The goal is to integrate the current branch, complete the project's delivery command, and validate the delivered behavior.

The current user request defines the closeout scope. Do not include unrelated branches, failures, deliveries, or production changes in the handoff.

## Non-negotiable rules

- Start every closeout turn and reminder wakeup by loading this skill.
- A local commit is not completion. Do not report completion before integration, delivery, and required validation.
- A current actionable failure is a repair instruction. Do not end the turn only to report it.
- Use the named repair workflow immediately. Then return here in the same turn.
- Do not operate or diagnose the coordinator from this skill.
- Use `uv run coloph-sync status` as the routine branch-status command. Do not reconstruct its result with routine Git containment commands.
- Keep a pending branch under a bounded host reminder. Do not silently abandon integration or delivery waiting.

## Start and repair

Run `uv run coloph-sync status` for the current branch. Use `--commit` only when the intended commit is explicit.

If the status identifies a conflict, a branch that needs local main, or a merge failure for the current tip, use `sync-merge-main` now. Return here after its passed merge commit.

If the status identifies another repairable branch failure, use `sync-contributor` now. Return here after its passed repair commit.

If the status records a failure for an ancestor of the current tip, wait for the coordinator to check the new tip. Do not repair the old result again.

If the status says `action needed` because checks failed, repair the affected branch in this turn. A deployed branch still needs repair when the status reports a current check failure.

## Wait for integration and delivery

If the current tip is not integrated or delivered and no repair is required, create or reuse a bounded host reminder for this task. Check once on each wakeup. Stay quiet while the result is unchanged.

The reminder must load this skill first. It must check `uv run coloph-sync status` for this branch. It must repair a current actionable failure instead of reporting it. It must stop when delivery completes, the bounded wait expires, or work needs new user authority.

Do not give a final handoff while the reminder is active. Report only the pending state and the next automatic check.

## Validate delivery

After the branch is delivered, follow the repository's required validation procedure. Use the closest real user or operator path. A delivery record proves historical delivery. It does not prove that the service is healthy now.

Always give the user concrete manual test steps and expected results. If a real validation is unsafe or unavailable, state the reason and run the closest safe check.

Review the original request, later scope changes, and branch history. Include work held behind a deployment barrier. Delivery of a barrier parent does not complete its successors.

## Final handoff

Report all of these parts:

1. Requested scope, including material changes to that scope.
2. Delivered scope, verification, integration state, and delivery state.
3. Manual validation steps and expected results.
4. Remaining work, blockers, barrier-held successors, and the next action.

Do not claim completion while a requested outcome, required validation, or barrier-held successor remains unresolved.
