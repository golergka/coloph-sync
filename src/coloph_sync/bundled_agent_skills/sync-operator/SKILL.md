---
name: sync-operator
description: Operate and supervise the sync coordinator, diagnose failures, and carry checked repairs through recovery and delivery.
---

# Operate the coordinator

Use the assigned coordinator checkout. Read the project README and its check and delivery instructions.
An invocation authorizes normal coordinator operation unless the user requests inspection, stopping, or one cycle.
Preserve existing authorization. Ask only for missing intent, unavailable access, or work outside the assigned scope.

## Normal operation

Check the configured main branch, clean checkout, prerequisites, and existing coordinator before starting.
Keep a healthy existing instance. Otherwise, run `uv run coloph-sync run` under a known terminal or service supervisor.
Keep its exact identity. Use the project sleep-prevention mechanism when required.
A tool timeout does not prove process exit. Check the owned instance before restarting it.

Read `uv run coloph-sync status --all` and `uv run coloph-sync logs` for failures.
Use `uv run coloph-sync stop` to drain the current cycle. Wait for the owned process to exit before editing.
Never edit files, mutate Git, or run another coordinator or deployment command while that process owns the checkout.
Never operate another worktree. Contributor conflicts belong to the contributor who owns that branch.

## Recovery

A failure starts diagnosis and repair. It is not, by itself, a reason to hand the task back to the user.
Separate a branch failure from a shared integration or delivery failure through the recorded phase and reason.

- For a branch conflict or failed branch check, contact its confirmed owner with the evidence.
- For shared failures, diagnose the project command and its remote effects.
- For code repairs, use `sync-contributor` in an authorized checkout and create a checked commit.
  Explicit user authorization permits contributor repairs in the stopped coordinator checkout.
- If authorization does not cover a required repair, identify the missing authority precisely.

After a checked repair, use the normal coordinator command:

```sh
uv run coloph-sync run --once --branch REPAIR_BRANCH
```

For a repair already committed on main, use `uv run coloph-sync run --once`.
The coordinator checks the repair, resolves pending delivery, then delivers the successor.
The project reconciliation command determines whether to retry, record success, or replace a conclusively failed attempt.
If a project lacks that command, its deployment command must reconcile retries safely.
Repair the project command when it cannot distinguish remote outcomes. Never infer that a timeout means no external effect.
Never edit coordinator records, bypass checks or barriers, force-push, or run a competing deployment to escape a failure.

Retry a transient failure once. After repeated failure with the same evidence, investigate instead of repeating it unchanged.
After three unsuccessful repairs for the same cause, report the unresolved cause and the required next action.
Report authentication failures and rejected pushes with their concrete errors. Do not rewrite history to continue.

Check status after recovery. Notify confirmed branch owners of new delivery results or repair requirements.
Use the exact verdict. Do not describe `action needed` as rejection or branch delivery as package publication.
If the user requested continuous operation, resume supervision after the recovery cycle succeeds.

## Supervision

Before ending a turn with continuous operation active, create or reuse one operator reminder for this task and checkout.
Use the host automation tool. Default to every 15 minutes unless the user specifies another interval.
Check its destination, checkout, schedule, and instructions. If reminders are unavailable, keep supervising the foreground process.

Include the checkout, supervisor identity, current repair ownership, and these instructions:

> Load `sync-operator`. Supervise only this checkout and the recorded instance.
> Respect the latest stop request. Check status and logs for new failures.
> Diagnose and repair within existing authorization, then use the normal recovery cycle.
> Stay quiet while healthy or while unchanged repair work continues.
> Report meaningful changes, completion of repairs, or a precise blocker.

On a stop request, delete the reminder and wait for process exit.
Delete the reminder when recovery requires unavailable input or authority. Do not let a stale reminder restart stopped work.
